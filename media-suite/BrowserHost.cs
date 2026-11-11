using Microsoft.AspNetCore.Builder;
using Microsoft.AspNetCore.Hosting;
using Microsoft.AspNetCore.Http;
using Microsoft.Extensions.Logging;
using Microsoft.Extensions.DependencyInjection;
using System;
using System.Collections.Generic;
using System.IO;
using System.Linq;
using System.Net;
using System.Security.Cryptography;
using System.Text.Json;
using System.Threading;
using System.Threading.Tasks;
using System.Windows.Forms;

namespace NovelAI.MediaSuite;

internal sealed class BrowserHost : IDisposable
{
    private readonly Preferences settings;
    private readonly string folder;
    private readonly Services services;
    private readonly string token = Convert.ToHexString(RandomNumberGenerator.GetBytes(24));
    private readonly object preferencesLock = new();
    private int locationRevision;
    private readonly CancellationTokenSource closing = new();
    private readonly List<WebApplication> servers = new();
    private readonly Dictionary<Section, ApplicationProxy> applications = new();
    private readonly object requestLock = new();
    private int activeRequests;
    private bool handingOff;
    internal bool InUse { get { lock (requestLock) return activeRequests != 0; } }
    internal bool TryHandOff()
    {
        lock (requestLock)
        {
            if (activeRequests != 0) return false;
            handingOff = true;
            return true;
        }
    }
    internal Uri Address { get; private set; }
    private volatile bool ready;

    internal BrowserHost(Preferences settings, string folder, Services services)
    { this.settings = settings; this.folder = folder; this.services = services; }

    internal async Task StartAsync()
    {
        Directory.CreateDirectory(folder);
        string file = Path.Combine(folder, "chrome-ports.json");
        int[] ports = File.Exists(file) ? JsonSerializer.Deserialize<int[]>(File.ReadAllText(file)) : null;
        if (ports?.Length != 4 || ports.Any(p => p is < 1024 or > 65535) || ports.Distinct().Count() != 4)
            ports = new[] {8764, 8861, 8862, 8863};
        Address = await Listen(ports[0], Shell);
        foreach (var section in new[] {Section.Library, Section.Workbench, Section.AfterHours})
        {
            var proxy = new ApplicationProxy(section, Address);
            applications[section] = proxy;
            int index = section == Section.Library ? 1 : (int)section;
            proxy.Address = await Listen(ports[index], proxy.Handle);
            ports[index] = proxy.Address.Port;
        }
        applications[Section.Battles] = applications[Section.Library];
        ports[0] = Address.Port;
        File.WriteAllText(file + ".new", JsonSerializer.Serialize(ports));
        File.Move(file + ".new", file, true);
        ready = true;
    }

    private async Task<Uri> Listen(int preferred, RequestDelegate handle)
    {
        foreach (int port in new[] {preferred, 0})
        {
            var builder = WebApplication.CreateEmptyBuilder(new WebApplicationOptions { ApplicationName = typeof(BrowserHost).Assembly.GetName().Name });
            builder.Logging.ClearProviders();
            builder.Services.AddRoutingCore();
            builder.WebHost.UseKestrel(options => {
                options.AddServerHeader = false;
                options.Limits.MaxRequestBodySize = null; // The original apps enforce their upload limits.
                options.Listen(IPAddress.Loopback, port);
            });
            var app = builder.Build();
            app.Run(async context => {
                if (context.Request.Host.Value != "127.0.0.1:" + context.Connection.LocalPort)
                { context.Response.StatusCode = 403; return; }
                lock (requestLock)
                {
                    if (handingOff) { context.Response.StatusCode = 503; return; }
                    activeRequests++;
                }
                try { await handle(context); }
                finally { lock (requestLock) activeRequests--; }
            });
            try { await app.StartAsync(); }
            catch (IOException) when (port != 0) { await app.DisposeAsync(); continue; }
            servers.Add(app);
            return new Uri(app.Urls.Single());
        }
        throw new IOException("Could not open a local Media Suite address.");
    }

    internal static async Task Asset(HttpContext context, string file, string mime)
    {
        using var content = typeof(BrowserHost).Assembly.GetManifestResourceStream("browser/" + file)
            ?? throw new FileNotFoundException(file);
        context.Response.ContentType = mime;
        context.Response.ContentLength = content.Length;
        await content.CopyToAsync(context.Response.Body, context.RequestAborted);
    }

    private async Task Shell(HttpContext context)
    {
        var req = context.Request;
        var res = context.Response;
        var path = req.Path.Value;
        if (!ready) { res.StatusCode = 503; return; }
        res.Headers.CacheControl = "no-store";
        res.Headers.XContentTypeOptions = "nosniff";
        res.Headers["Referrer-Policy"] = "origin";
        res.Headers["Content-Security-Policy"] = "default-src 'none'; script-src 'self'; style-src 'self'; img-src 'self'; connect-src 'self'; " +
            "frame-src " + string.Join(" ", applications.Values.Distinct().Select(p => p.Address?.GetLeftPart(UriPartial.Authority))) +
            "; frame-ancestors 'none'; base-uri 'none'; form-action 'none'";
        if (req.Method == "GET")
        {
            switch (path)
            {
                case "/": await Asset(context, "index.html", "text/html; charset=utf-8"); return;
                case "/suite.js": await Asset(context, "suite.js", "text/javascript; charset=utf-8"); return;
                case "/suite.css": await Asset(context, "suite.css", "text/css; charset=utf-8"); return;
                case "/favicon.ico": await Asset(context, "favicon.ico", "image/x-icon"); return;
                case "/api/presence":
                    if (req.Headers["Sec-Fetch-Site"] != "same-origin" || req.Headers.Accept != "text/event-stream")
                    { res.StatusCode = 403; return; }
                    res.ContentType = "text/event-stream";
                    await res.WriteAsync(": connected\n\n", context.RequestAborted);
                    await res.Body.FlushAsync(context.RequestAborted);
                    using (var lifetime = CancellationTokenSource.CreateLinkedTokenSource(closing.Token, context.RequestAborted))
                        try { await Task.Delay(Timeout.Infinite, lifetime.Token); } catch (OperationCanceledException) { }
                    return;
                case "/api/session":
                    if (req.Headers["X-Suite-Request"] != "session") { res.StatusCode = 403; return; }
                    object snapshot;
                    lock (preferencesLock)
                        snapshot = new {token, version = typeof(BrowserHost).Assembly.GetName().Version.ToString(3), lastSection = settings.LastSection, locations = new {
                            settings.LibraryFolder, settings.CompanionFolder, settings.WorkbenchFolder, settings.GameFolder }};
                    await res.WriteAsJsonAsync(snapshot); return;
                default: res.StatusCode = 404; return;
            }
        }
        if (req.Method != "POST") { res.StatusCode = 405; return; }
        if (req.Headers.Origin != Address.GetLeftPart(UriPartial.Authority) || req.Headers["X-Suite-Request"] != token)
        { res.StatusCode = 403; return; }
        if (req.ContentLength.GetValueOrDefault() > 32768 || req.Headers.ContainsKey("Transfer-Encoding"))
        { res.StatusCode = 413; return; }
        try
        {
            string[] parts = path.Trim('/').Split('/');
            if (parts.Length == 3 && parts[0] == "api" && Enum.TryParse(parts[2], out Section section) && section.ToString() == parts[2] && Enum.IsDefined(section))
            {
                if (parts[1] == "select")
                {
                    lock (preferencesLock) { settings.LastSection = section.ToString(); settings.Save(folder); }
                    res.StatusCode = 204; return;
                }
                if (parts[1] == "open")
                {
                    int revision;
                    lock (preferencesLock) revision = locationRevision;
                    if (section == Section.AfterHours && string.IsNullOrEmpty(services.ActiveLibrary)) _ = WarmLibrary();
                    var upstream = await services.Open(section, closing.Token);
                    var proxy = applications[section];
                    lock (preferencesLock)
                    {
                        if (revision != locationRevision) throw new InvalidOperationException("Locations changed while the program was opening. Retry to connect.");
                        RememberLibrary();
                        proxy.Upstream = upstream;
                    }
                    await res.WriteAsJsonAsync(new {url = new Uri(proxy.Address, upstream.AbsolutePath).AbsoluteUri});
                    return;
                }
            }
            if (path == "/api/workbench-changed")
            {
                var recorded = services.RecordedWorkbench();
                await res.WriteAsJsonAsync(new {changed = recorded != null && recorded != applications[Section.Workbench].Upstream});
                return;
            }
            if (path == "/api/locations")
            {
                var input = await req.ReadFromJsonAsync<Dictionary<string,string>>();
                string Resolve(string key, Func<string,bool> test, params string[] relatives)
                {
                    if (input == null || !input.TryGetValue(key, out var raw)) throw new ArgumentException("A location is missing from the form.");
                    var value = Environment.ExpandEnvironmentVariables((raw ?? "").Trim().Trim('"'));
                    if (value.Length == 0) return null;
                    if (key == "libraryFolder") value = Installations.LibraryDirectory(value);
                    return Installations.InFolder(value, test, relatives) ?? throw new IOException("Could not find the selected installation or library in " + value);
                }
                var library = Resolve("libraryFolder", Installations.Library, "");
                var companion = Resolve("companionFolder", Installations.Companion, "");
                var workbench = Resolve("workbenchFolder", Installations.Workbench, "", "duplicate-review");
                var game = Resolve("gameFolder", Installations.Game, "", "game", Path.Combine("project","game"));
                var changed = new List<Section>();
                lock (preferencesLock)
                {
                    var paths = StringComparer.OrdinalIgnoreCase;
                    if (!paths.Equals(settings.LibraryFolder, library) || !paths.Equals(settings.CompanionFolder, companion))
                        changed.AddRange(new[] {Section.Library, Section.Battles, Section.Workbench});
                    else if (!paths.Equals(settings.WorkbenchFolder, workbench)) changed.Add(Section.Workbench);
                    if (!paths.Equals(settings.GameFolder, game) || !paths.Equals(settings.LibraryFolder, library)) changed.Add(Section.AfterHours);
                    var next = new Preferences { LibraryFolder = library, CompanionFolder = companion, WorkbenchFolder = workbench,
                        GameFolder = game, LastSection = settings.LastSection, Maximized = settings.Maximized };
                    next.Save(folder);
                    settings.LibraryFolder = library; settings.CompanionFolder = companion; settings.WorkbenchFolder = workbench; settings.GameFolder = game;
                    if (changed.Count != 0) locationRevision++;
                    foreach (var item in changed) applications[item].Upstream = null;
                }
                await res.WriteAsJsonAsync(new {changed = changed.Select(item => item.ToString()).ToArray()}); return;
            }
            if (path == "/api/browse")
            {
                var initial = await req.ReadFromJsonAsync<string>();
                await res.WriteAsJsonAsync(new {path = await ChooseFolder(initial)}); return;
            }
            res.StatusCode = 404;
        }
        catch (Exception e) when (e is not OperationCanceledException)
        {
            res.StatusCode = 400;
            await res.WriteAsJsonAsync(new {error = e.GetBaseException().Message});
        }
    }

    private void RememberLibrary()
    {
        lock (preferencesLock)
            if (string.IsNullOrEmpty(settings.LibraryFolder) && !string.IsNullOrEmpty(services.ActiveLibrary))
            { settings.LibraryFolder = services.ActiveLibrary; settings.Save(folder); }
    }

    private async Task WarmLibrary()
    {
        try { await services.Library(closing.Token); RememberLibrary(); }
        catch (Exception) { /* Opening Library reports any failure and offers Retry. */ }
    }

    private static Task<string> ChooseFolder(string initial)
    {
        var result = new TaskCompletionSource<string>(TaskCreationOptions.RunContinuationsAsynchronously);
        var thread = new Thread(() => {
            try
            {
                using var picker = new FolderBrowserDialog {ShowNewFolderButton = false, Description = "Choose a suite location"};
                if (Directory.Exists(initial)) picker.InitialDirectory = initial;
                using var owner = new Form {TopMost = true, ShowInTaskbar = false, Opacity = 0};
                owner.Show();
                result.SetResult(picker.ShowDialog(owner) == DialogResult.OK ? picker.SelectedPath : null);
            }
            catch (Exception e) { result.SetException(e); }
        }) {IsBackground = true};
        thread.SetApartmentState(ApartmentState.STA); thread.Start();
        return result.Task;
    }

    public void Dispose()
    {
        closing.Cancel();
        foreach (var app in servers) { app.StopAsync().GetAwaiter().GetResult(); app.DisposeAsync().AsTask().GetAwaiter().GetResult(); }
        foreach (var proxy in applications.Values.Distinct()) proxy.Dispose();
        closing.Dispose();
    }
}
