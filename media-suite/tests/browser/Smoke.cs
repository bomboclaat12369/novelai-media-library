using System;
using System.Collections.Generic;
using System.Diagnostics;
using System.IO;
using System.Net;
using System.Net.Http;
using System.Net.Sockets;
using System.Text.Json;
using System.Threading;
using System.Threading.Tasks;
using NovelAI.MediaSuite;

var root = Path.GetFullPath(args[0]);
if (!File.Exists(Path.Combine(root, "Original game save.sqlite3"))) throw new Exception("A disposable suite fixture is required.");
Trace.Listeners.Add(new TextWriterTraceListener(Console.Error));
Trace.AutoFlush = true;
var ports = JsonSerializer.Deserialize<int[]>(File.ReadAllText(Path.Combine(root, "test-ports.json")));
foreach (var port in ports)
{
    using var tcp = new TcpClient();
    try { tcp.Connect("127.0.0.1", port); throw new Exception("Fixture requires a free service port " + port); }
    catch (SocketException) {}
}
var profile = Path.Combine(root, "Suite profile");
var settings = Preferences.Load<Preferences>(Path.Combine(root, "suite-qa.json"));
if (!Path.GetFullPath(settings.LibraryFolder).Equals(Path.Combine(root, "Media data"), StringComparison.OrdinalIgnoreCase))
    throw new Exception("Refusing a non-fixture media library.");
var state = Path.Combine(root, "Workbench data", "state");
var started = new List<Process>();
var services = new Services(settings, state, start: info => {
    if (info.Arguments.Contains("app.py")) info.Arguments += " --state-dir " + Services.Quote(state);
    if (info.Arguments.Contains("Launch.ps1")) info.Arguments += " -Port " + ports[1];
    info.RedirectStandardError = true;
    info.RedirectStandardOutput = true;
    info.RedirectStandardInput = true;
    var process = Process.Start(info);
    process.StandardInput.Close();
    process.OutputDataReceived += (_, e) => { if (e.Data != null) Console.Error.WriteLine(e.Data); };
    process.ErrorDataReceived += (_, e) => { if (e.Data != null) Console.Error.WriteLine(e.Data); };
    process.BeginOutputReadLine(); process.BeginErrorReadLine();
    lock (started) started.Add(process);
}, libraryPage: new Uri($"http://127.0.0.1:{ports[0]}/library/"), gamePage: new Uri($"http://127.0.0.1:{ports[1]}/game/"));
try
{
    using var host = new BrowserHost(settings, profile, services);
    using var localApps = new HttpClient(new HttpClientHandler {UseProxy=false,AllowAutoRedirect=false});
    services.CompanionUpdates = new CompanionUpdates(profile,localApps);
    using var gameFeed = new HttpClient(new NoGameRelease());
    var apps = new ApplicationUpdates(settings, services, localApps, new GameUpdates(profile,gameFeed),
        () => Task.FromResult("Up to date"), host.WhileIdle, CancellationToken.None);
    host.Updates = apps;
    await host.StartAsync();
    _ = apps.Check();
    Console.WriteLine(host.Address.AbsoluteUri);
    string command;
    while ((command = Console.ReadLine()) is "handoff" or "apply")
    {
        if (command == "handoff") Console.WriteLine(host.TryHandOff() ? "idle" : "busy");
        else
        {
            await apps.ApplyWhenIdle();
            var status = JsonSerializer.SerializeToElement(apps.Snapshot()).GetProperty("apps").GetProperty("Workbench").GetString();
            Console.WriteLine(status == "Installed · 2.0.1" && File.Exists(Path.Combine(state,"updates","active.json")) ? "applied"
                : status == "Ready for next session · 2.0.1" ? "waiting" : status);
        }
    }
    if (started.Count != 3 && !(started.Count==4 && started[3].StartInfo.Arguments.Contains("2.0.1")))
        throw new Exception("Unexpected service starts: " + started.Count);
}

finally
{
    foreach (var process in started)
    {
        try { if (!process.HasExited) { process.Kill(entireProcessTree: true); process.WaitForExit(8000); } }
        catch (InvalidOperationException) {}
        process.Dispose();
    }
}

internal sealed class NoGameRelease : HttpMessageHandler
{
    protected override Task<HttpResponseMessage> SendAsync(HttpRequestMessage request, CancellationToken token)
        => Task.FromResult(new HttpResponseMessage(HttpStatusCode.NotFound));
}
