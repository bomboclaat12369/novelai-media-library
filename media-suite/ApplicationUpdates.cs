using System;
using System.Collections.Generic;
using System.Diagnostics;
using System.IO;
using System.Linq;
using System.Net;
using System.Net.Http;
using System.Text;
using System.Text.Json;
using System.Text.RegularExpressions;
using System.Threading;
using System.Threading.Tasks;

namespace NovelAI.MediaSuite;

internal sealed class ApplicationUpdates
{
    private const string Suite = "Media Suite", Library = "Media Library and Battles", Bench = "Workbench", Game = "After Hours";
    private readonly Preferences settings;
    private readonly Services services;
    private readonly HttpClient local;
    private readonly GameUpdates game;
    private readonly Func<Task<string>> checkSuite;
    private readonly Func<Func<Task>,Task<bool>> whileIdle;
    private readonly CancellationToken stopping;
    private readonly object sync = new();
    private readonly Dictionary<string,string> messages = new() {
        [Suite]="Waiting to check", [Library]="Waiting to check", [Bench]="Waiting to check", [Game]="Waiting to check"
    };
    private Task checking = Task.CompletedTask;
    private readonly SemaphoreSlim applying = new(1);
    private readonly SemaphoreSlim workbenchGate = new(1);
    private bool workbenchBusy;
    private sealed record WorkbenchRelease(Uri Address, string Token, string Folder, string Version);
    private sealed record Status(string current, string version, bool available, bool ready, bool running, string error);
    private WorkbenchRelease pending;
    private WorkbenchRelease workbenchSession;
    private CompanionUpdates.Release companion;
    private string libraryInterface;

    internal ApplicationUpdates(Preferences settings, Services services, HttpClient local, GameUpdates game,
        Func<Task<string>> checkSuite, Func<Func<Task>,Task<bool>> whileIdle, CancellationToken stopping)
    {
        this.settings=settings; this.services=services; this.local=local; this.game=game;
        this.checkSuite=checkSuite; this.whileIdle=whileIdle; this.stopping=stopping;
    }

    internal object Snapshot()
    {
        lock (sync) return new {checking = !checking.IsCompleted, apps = new Dictionary<string,string>(messages)};
    }

    internal Task Check(string alreadyCheckedSuite = null)
    {
        lock (sync)
        {
            if (!checking.IsCompleted) return checking;
            foreach (string key in messages.Keys.ToArray()) messages[key] = "Checking…";
            checking = Task.WhenAll(
                Report(Suite, _ => alreadyCheckedSuite == null ? checkSuite() : Task.FromResult(alreadyCheckedSuite)),
                Report(Library, CheckLibrary), Report(Bench, CheckWorkbench),
                Report(Game, ct => Installations.Game(settings.GameFolder) ? game.Stage(settings.GameFolder, ct)
                    : Task.FromResult("Choose the game folder in Locations")));
            return checking;
        }
    }

    private async Task Report(string app, Func<CancellationToken,Task<string>> action)
    {
        using var timeout = CancellationTokenSource.CreateLinkedTokenSource(stopping);
        timeout.CancelAfter(TimeSpan.FromMinutes(8));
        try
        {
            string result = await action(timeout.Token).ConfigureAwait(false);
            if (result != null) lock (sync) messages[app] = result;
        }
        catch (Exception e)
        {
            Trace.TraceWarning("{0} update deferred: {1}", app, e.GetBaseException().Message);
            lock (sync) messages[app] = "Couldn’t verify the update. Will retry.";
        }
    }

    private async Task<string> CheckLibrary(CancellationToken ct)
    {
        var address = await services.Library(ct);
        var ui = CheckInterface(address,ct);
        var program = settings.CompanionFolder;
        if (services.CompanionUpdates == null || !Installations.Companion(program))
            return "Ready to open · " + await ui;
        var runtime = services.CompanionUpdates.Stage(program,services.ActiveLibrary,address,ct);
        string interfaceVersion;
        try { interfaceVersion = await ui; }
        catch (Exception e) { Trace.TraceWarning("Library interface check deferred: {0}",e.Message); interfaceVersion = "check deferred"; }
        CompanionUpdates.Release release;
        try { release = await runtime; }
        catch (Exception e)
        {
            Trace.TraceWarning("Companion release check deferred: {0}",e.Message);
            return "Interface " + interfaceVersion + " · companion check deferred";
        }
        bool newer = services.CompanionUpdates.NeedsRestart(release);
        lock (sync) { libraryInterface = interfaceVersion; companion = newer ? release : null; }
        return LibraryStatus(interfaceVersion,release.Version,newer);
    }

    private static string LibraryStatus(string ui,string runtime,bool pending) =>
        "Interface " + ui + " · companion " + runtime + (pending ? " ready for next session" : " ready to open");

    private async Task<string> CheckInterface(Uri address,CancellationToken ct)
    {
        using var reply = await local.PostAsync(new Uri(address,"/api/standalone/check"), null, ct);
        reply.EnsureSuccessStatusCode();
        using var data = JsonDocument.Parse(await reply.Content.ReadAsByteArrayAsync(ct));
        var v = data.RootElement.GetProperty("version").GetString();
        if (!Version.TryParse(v,out _)) throw new InvalidDataException("Missing Library version.");
        // The companion writes the verified document to its normal cache. Open
        // pages keep their current document; the next page load uses the new one.
        return v;
    }

    private async Task<HttpResponseMessage> Request(WorkbenchRelease app, string path, bool post, CancellationToken ct)
    {
        using var request = new HttpRequestMessage(post ? HttpMethod.Post : HttpMethod.Get, new Uri(app.Address,"/api/update/" + path));
        request.Headers.Add("X-Review-Token", app.Token);
        if (post) request.Content = new StringContent("{}", Encoding.UTF8, "application/json");
        return await local.SendAsync(request, ct);
    }

    private async Task<Status> Operation(WorkbenchRelease app, string path, CancellationToken ct)
    {
        while (true)
        {
            using var response = await Request(app, path, path != "status", ct);
            if (response.StatusCode == HttpStatusCode.BadRequest)
            {
                var reason = await response.Content.ReadAsStringAsync(ct);
                if (reason.Contains("bulk evaluation") || reason.Contains("Pause visual analysis")) return null;
            }
            response.EnsureSuccessStatusCode();
            var state = JsonSerializer.Deserialize<Status>(await response.Content.ReadAsByteArrayAsync(ct));
            if (state == null || !string.IsNullOrEmpty(state.error)) throw new IOException("Workbench could not verify the release.");
            if (!state.running) return state;
            await Task.Delay(400, ct);
            path = "status";
        }
    }

    private async Task<string> CheckWorkbench(CancellationToken ct)
    {
        await workbenchGate.WaitAsync(ct);
        try { return await PrepareWorkbench(ct); }
        finally { workbenchGate.Release(); }
    }

    private async Task<string> PrepareWorkbench(CancellationToken ct)
    {
        string folder = settings.WorkbenchFolder;
        var address = await services.Workbench(ct);
        var app = await Session(address,folder,ct);
        lock (sync) workbenchSession = app;
        var state = await Operation(app, "check", ct);
        if (state is {available:true, ready:false}) state = await Operation(app, "install", ct);
        lock (sync) workbenchBusy = state == null;
        if (state == null) return "Will check when Workbench is idle";
        if (state.available && !state.ready) throw new IOException("Workbench update is still pending.");
        lock (sync) pending = state.available ? app with { Version = state.version } : null;
        return state.available ? "Ready for next session · " + state.version : "Up to date · " + state.current;
    }

    private async Task<WorkbenchRelease> Session(Uri address,string folder,CancellationToken ct)
    {
        using var page = await local.GetAsync(address, HttpCompletionOption.ResponseHeadersRead, ct);
        page.EnsureSuccessStatusCode();
        var policy = string.Join(" ", page.Headers.GetValues("Content-Security-Policy"));
        var nonce = Regex.Match(policy, @"(?:^|;)\s*script-src\s+'nonce-([A-Za-z0-9_-]{16,128})'");
        if (!nonce.Success) throw new InvalidDataException("Unrecognized Workbench session.");
        return new WorkbenchRelease(address, nonce.Groups[1].Value, folder, null);
    }

    private async Task<string> ApplyWorkbench(WorkbenchRelease app, CancellationToken ct)
    {
        if (!await workbenchGate.WaitAsync(0,ct)) return null;
        try { return await RestartWorkbench(app,ct); }
        finally { workbenchGate.Release(); }
    }

    private async Task<string> RestartWorkbench(WorkbenchRelease app, CancellationToken ct)
    {
        if (services.RecordedWorkbench() != app.Address || !StringComparer.OrdinalIgnoreCase.Equals(app.Folder, settings.WorkbenchFolder))
        { lock (sync) if (pending == app) pending = null; return null; }
        using var response = await Request(app, "apply", true, ct);
        // Workbench holds its operation lock while checking its scanner,
        // organizer and bulk jobs. A rejected activation stays queued.
        if (response.StatusCode == HttpStatusCode.BadRequest) return "Ready when Workbench is idle · " + app.Version;
        response.EnsureSuccessStatusCode();
        lock (sync) if (pending == app) pending = null;
        // Workbench re-execs itself and records its new port. Give it time to
        // finish before the next tab can start another copy or use the old port.
        for (int i = 0; i < 24 && services.RecordedWorkbench() == app.Address; i++) await Task.Delay(150,ct);
        var address = await services.Workbench(ct);
        var resumed = await Session(address,app.Folder,ct);
        var state = await Operation(resumed,"status",ct);
        if (state==null || !Version.TryParse(state.current,out var current) || current < Version.Parse(app.Version))
            throw new IOException("Workbench has not reopened the selected release.");
        lock (sync) workbenchSession = resumed;
        return "Installed · " + app.Version;
    }

    private async Task<bool> WorkbenchIsIdle(CancellationToken ct)
    {
        var address = await services.RunningWorkbench(ct);
        if (address == null) return true;
        WorkbenchRelease session;
        lock (sync) session = workbenchSession;
        if (address != session?.Address) session = await Session(address,settings.WorkbenchFolder,ct);
        foreach (var (path,field) in new[] {("/api/state","status"),("/api/organizer/state","progress"),("/api/bulk/state","")})
        {
            using var req = new HttpRequestMessage(HttpMethod.Get,new Uri(address,path));
            req.Headers.Add("X-Review-Token",session.Token);
            using var res = await local.SendAsync(req,ct);
            if (!res.IsSuccessStatusCode) return false;
            using var data = JsonDocument.Parse(await res.Content.ReadAsByteArrayAsync(ct));
            var job = field=="" ? data.RootElement : data.RootElement.GetProperty(field);
            if (job.GetProperty("running").GetBoolean()) return false;
        }
        return true;
    }

    private async Task<string> ApplyLibrary(CompanionUpdates.Release r,CancellationToken ct)
    {
        if (!StringComparer.OrdinalIgnoreCase.Equals(r.Program,settings.CompanionFolder)
            || !StringComparer.OrdinalIgnoreCase.Equals(r.Library,services.ActiveLibrary))
        { lock (sync) if (companion==r) companion=null; return null; }
        if (!await WorkbenchIsIdle(ct) || !await services.CompanionUpdates.Apply(r,ct))
            return "Ready when Library and Workbench are idle · " + r.Version;
        lock (sync)
        {
            if (companion != r) return null;
            companion=null;
            return LibraryStatus(libraryInterface,r.Version,false);
        }
    }

    internal async Task ApplyWhenIdle()
    {
        if (!await applying.WaitAsync(0,stopping)) return;
        try
        {
            WorkbenchRelease app;
            CompanionUpdates.Release library;
            lock (sync)
            {
                app = pending;
                library = companion;
                if (workbenchBusy && checking.IsCompleted)
                {
                    workbenchBusy = false;
                    checking = Report(Bench,CheckWorkbench);
                }
            }
            string folder = settings.GameFolder;
            bool gameReady = game.Pending(folder);
            if (app == null && library == null && !gameReady) return;
            await whileIdle(async () => {
                if (library != null) await Report(Library,ct => ApplyLibrary(library,ct));
                var benchTask = app == null ? Task.CompletedTask : Report(Bench, ct => ApplyWorkbench(app,ct));
                var gameTask = !gameReady ? Task.CompletedTask : Report(Game, async ct => {
                    using var bounded = CancellationTokenSource.CreateLinkedTokenSource(ct);
                    bounded.CancelAfter(TimeSpan.FromSeconds(20));
                    return await game.Apply(folder,bounded.Token);
                });
                await Task.WhenAll(benchTask,gameTask);
            });
        }
        finally { applying.Release(); }
    }
}
