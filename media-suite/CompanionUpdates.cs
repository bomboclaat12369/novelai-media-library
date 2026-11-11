using System;
using System.Diagnostics;
using System.IO;
using System.Net;
using System.Net.Http;
using System.Security.Cryptography;
using System.Text;
using System.Text.Json;
using System.Threading;
using System.Threading.Tasks;

namespace NovelAI.MediaSuite;

internal sealed class CompanionUpdates
{
    private readonly string root;
    private readonly HttpClient local;
    private sealed record Session(string version, string token, int port);
    internal sealed record Release(string Program, string Library, Uri Address, string Version);
    internal CompanionUpdates(string suiteFolder, HttpClient local)
    { root=Path.Combine(suiteFolder,"companions"); this.local=local; }

    private string State(string program,string library)
    {
        string key = string.Join("\n",Path.TrimEndingDirectorySeparator(Path.GetFullPath(program)),
            Path.TrimEndingDirectorySeparator(Path.GetFullPath(library))).ToUpperInvariant();
        return Path.Combine(root,Convert.ToHexString(SHA256.HashData(Encoding.UTF8.GetBytes(key))));
    }

    internal ProcessStartInfo Command(string action,string program,string library)
    {
        string script=Path.Combine(AppContext.BaseDirectory,"companion-session.py");
        return new ProcessStartInfo(Installations.Python(program),
            string.Join(" ", Array.ConvertAll(new[] {script,action,program,State(program,library),library},Services.Quote)))
            {WorkingDirectory=program,UseShellExecute=false,CreateNoWindow=true};
    }

    internal async Task<Release> Stage(string program,string library,Uri address,CancellationToken ct)
    {
        var info=Command("stage",program,library);
        info.RedirectStandardOutput=true;
        using var child=Process.Start(info);
        var output=child.StandardOutput.ReadToEndAsync(ct);
        try { await child.WaitForExitAsync(ct); }
        catch (OperationCanceledException)
        {
            try { if (!child.HasExited) child.Kill(entireProcessTree:true); } catch (InvalidOperationException) { }
            throw;
        }
        var version=(await output).Trim();
        if (child.ExitCode!=0 || !Version.TryParse(version,out _)) throw new IOException("Companion release check failed.");
        return new Release(program,library,address,version);
    }

    private Session Running(Release r)
    {
        try
        {
            var session=JsonSerializer.Deserialize<Session>(File.ReadAllBytes(Path.Combine(State(r.Program,r.Library),"session.json")));
            return session?.port==r.Address.Port && !string.IsNullOrEmpty(session.token) ? session : null;
        }
        catch(Exception e) when(e is IOException or JsonException or UnauthorizedAccessException) { return null; }
    }

    internal bool NeedsRestart(Release r) => Running(r) is { } s && Version.TryParse(s.version,out var current) && current < Version.Parse(r.Version);

    internal async Task<bool> Apply(Release r,CancellationToken ct)
    {
        var session=Running(r);
        if (session==null || !NeedsRestart(r)) return true;
        using var req=new HttpRequestMessage(HttpMethod.Post,new Uri(r.Address,"/_media-suite/apply-runtime"));
        req.Headers.Add("X-Suite-Companion",session.token);
        using var reply=await local.SendAsync(req,ct);
        if (reply.StatusCode==HttpStatusCode.Conflict) return false;
        // A standalone companion may have taken the port. Its own launcher
        // manages that process; the verified release is ready for a suite start.
        if (reply.StatusCode is HttpStatusCode.NotFound or HttpStatusCode.Forbidden) return true;
        reply.EnsureSuccessStatusCode();
        for (int i=0; i<80 && NeedsRestart(r); i++) await Task.Delay(150,ct);
        return !NeedsRestart(r);
    }
}
