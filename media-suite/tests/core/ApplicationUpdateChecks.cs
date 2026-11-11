using System;
using System.Collections.Generic;
using System.IO;
using System.Linq;
using System.Net;
using System.Net.Http;
using System.Security.Cryptography;
using System.Text;
using System.Text.Json;
using System.Threading;
using System.Threading.Tasks;
using NovelAI.MediaSuite;

internal sealed class ApplicationUpdateChecks : HttpMessageHandler
{
    private const string Nonce = "fixture_per_launch_token";
    private readonly byte[] adapter = Encoding.UTF8.GetBytes("# Test release adapter");
    private readonly string state;
    private bool corrupt, absent, downloaded, installed, busy = true;
    private int installs, checks, applied;
    private ApplicationUpdateChecks(string state) { this.state=state; }
    private string Address(bool next=false) => "http://127.0.0.1:" + (next ? 49002 : 49001) + "/organizer";

    protected override Task<HttpResponseMessage> SendAsync(HttpRequestMessage req, CancellationToken token)
    {
        var uri=req.RequestUri;
        var result=new HttpResponseMessage(HttpStatusCode.OK);
        object json=null;
        if (uri.AbsoluteUri == GameUpdates.Feed)
        {
            if (absent) result.StatusCode=HttpStatusCode.NotFound;
            json=new {schema=1,version="1.1.0",updater_bytes=adapter.Length,updater_sha256=Convert.ToHexString(SHA256.HashData(adapter))};
        }
        else if (uri.Host=="github.com" && uri.AbsolutePath.EndsWith("/after-hours-v1.1.0/Update-AfterHours.ps1"))
            result.Content=new ByteArrayContent(corrupt ? new byte[adapter.Length] : adapter);
        else if (uri.AbsolutePath=="/api/health") json=new {standalone_library=true,library_root=state};
        else if (uri.AbsolutePath=="/api/standalone/check" && req.Method==HttpMethod.Post)
        { checks++; json=new {version="3.1.0"}; }
        else if (uri.AbsolutePath=="/organizer")
        {
            result.Headers.Add("Content-Security-Policy","default-src 'self'; script-src 'nonce-" + Nonce + "'; style-src 'unsafe-inline'");
            result.Content=new StringContent("<html data-local-duplicate-review=\"1\">");
        }
        else if (req.Headers.TryGetValues("X-Review-Token",out var tokens) && tokens.Single()==Nonce)
        {
            if (uri.AbsolutePath=="/api/update/install" && req.Method==HttpMethod.Post) { downloaded=true; installs++; }
            if (uri.AbsolutePath=="/api/update/apply" && req.Method==HttpMethod.Post)
            {
                applied++;
                if (busy) result.StatusCode=HttpStatusCode.BadRequest;
                else { installed=true; File.WriteAllText(Path.Combine(state,"running-url.txt"),Address(true)); }
            }
            json=new {version="2.0.2",current=installed ? "2.0.2" : "2.0.1",available=!installed,ready=downloaded&&!installed,running=false};
        }
        else throw new Exception("Unexpected test request: " + uri);
        if (json!=null) result.Content=new StringContent(JsonSerializer.Serialize(json));
        return Task.FromResult(result);
    }

    internal static async Task Verify(string root, Preferences settings)
    {
        var mock=new ApplicationUpdateChecks(root);
        File.WriteAllText(Path.Combine(root,"running-url.txt"),mock.Address());
        settings.LibraryFolder=root;
        using var http=new HttpClient(mock);
        var calls=new List<string>();
        bool inUse=true, gameBusy=true;
        var game=new GameUpdates(root,http,(info,_)=>{
            string phase=info.ArgumentList[info.ArgumentList.IndexOf("-Phase")+1];
            calls.Add(phase);
            if (!info.ArgumentList.Contains(settings.GameFolder) || !info.CreateNoWindow) throw new Exception("Lost game installation context.");
            return Task.FromResult(phase=="Apply" && gameBusy ? 75 : 0);
        });
        var services=new Services(settings,root,mock, info=>throw new Exception("Running services should be reused."));
        var apps=new ApplicationUpdates(settings,services,http,game,()=>Task.FromResult("Host is current"),async action=>{
            if (inUse) return false;
            await action(); return true;
        },CancellationToken.None);
        string Report()=>JsonSerializer.Serialize(apps.Snapshot());
        mock.absent=true;
        await apps.Check();
        if (mock.installs!=1 || mock.checks!=1 || !Report().Contains("Waiting for a published game release"))
            throw new Exception("One missing release prevented updates to other programs.");
        await apps.ApplyWhenIdle();
        if (mock.applied!=0) throw new Exception("Applied while a suite tab was open.");
        mock.absent=false; mock.corrupt=true;
        await apps.Check();
        if (calls.Count!=0 || game.Pending(settings.GameFolder)) throw new Exception("Ran a corrupt game adapter.");
        mock.corrupt=false;
        await apps.Check();
        if (!calls.SequenceEqual(new[]{"Stage"}) || game.LaunchCommand(settings.GameFolder,root)!=null)
            throw new Exception("Staging changed the active game.");
        inUse=false;
        await apps.ApplyWhenIdle();
        if (mock.installed || !game.Pending(settings.GameFolder) || !Report().Contains("Workbench is idle"))
            throw new Exception("Busy releases were not deferred.");
        mock.busy=false; gameBusy=false;
        await apps.ApplyWhenIdle();
        var launch=new GameUpdates(root,http).LaunchCommand(settings.GameFolder,root);
        if (!mock.installed || mock.installs!=1 || launch==null || !launch.ArgumentList.Contains("Launch")
            || !launch.ArgumentList.Contains(root) || game.Pending(settings.GameFolder))
            throw new Exception("Verified selections did not survive the session.");
        await apps.Check();
        if (mock.installs!=1 || calls.Count(c=>c=="Stage")!=1 || !Report().Contains("Up to date"))
            throw new Exception("An unchanged release was downloaded again.");
        Console.WriteLine("Unified update checks passed for independent releases, open tabs, busy jobs, corrupt downloads and offline game launch.");
    }
}
