using System;
using System.Collections.Generic;
using System.Diagnostics;
using System.IO;
using System.Net.Sockets;
using System.Text.Json;
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
    await host.StartAsync();
    Console.WriteLine(host.Address.AbsoluteUri);
    Console.ReadLine();
    if (started.Count != 3) throw new Exception("Expected three cold starts, got " + started.Count);
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
