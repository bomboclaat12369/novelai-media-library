using System;
using System.Diagnostics;
using System.IO;
using System.Linq;
using System.Net;
using System.Net.Http;
using System.Security.Cryptography;
using System.Text;
using System.Text.Json;
using System.Threading;
using System.Threading.Tasks;

namespace NovelAI.MediaSuite;

// After Hours owns its package, save migration and safe activation. The suite only
// runs an adapter from a verified release, scoped to the connected game installation.
internal sealed class GameUpdates
{
    internal const string Feed = "https://raw.githubusercontent.com/bomboclaat12369/novelai-media-library/game-build-20261109/release-after-hours.json";
    private const string Releases = "https://github.com/bomboclaat12369/novelai-media-library/releases/download/after-hours-v";
    private const string Script = "Update-AfterHours.ps1";
    private const int Limit = 1024 * 1024;
    private sealed record Release(int schema, string version, int updater_bytes, string updater_sha256);
    private readonly string root;
    private readonly HttpClient http;
    private readonly Func<ProcessStartInfo,CancellationToken,Task<int>> run;
    private readonly SemaphoreSlim gate = new(1);

    internal GameUpdates(string suiteFolder, HttpClient http, Func<ProcessStartInfo,CancellationToken,Task<int>> run = null)
    { root = Path.Combine(suiteFolder, "after-hours"); this.http = http; this.run = run ?? Run; }

    private string State(string folder)
    {
        var path = Path.TrimEndingDirectorySeparator(Path.GetFullPath(folder)).ToUpperInvariant();
        return Path.Combine(root, Convert.ToHexString(SHA256.HashData(Encoding.UTF8.GetBytes(path))));
    }

    private static bool Valid(Release r) => r?.schema == 1 && Version.TryParse(r.version, out var v)
        && v.Build >= 0 && v.Revision < 0 && v.ToString() == r.version && r.updater_bytes is > 0 and <= Limit
        && r.updater_sha256?.Length == 64 && r.updater_sha256.All(Uri.IsHexDigit);

    private static string FileFor(string state, Release r) => Path.Combine(state, r.version, Script);
    private static bool Verified(string path, Release r)
    {
        if (!File.Exists(path) || new FileInfo(path).Length != r.updater_bytes) return false;
        using var file = File.OpenRead(path);
        return Convert.ToHexString(SHA256.HashData(file)).Equals(r.updater_sha256, StringComparison.OrdinalIgnoreCase);
    }

    private static Release Read(string state, string name)
    {
        try
        {
            var r = JsonSerializer.Deserialize<Release>(File.ReadAllBytes(Path.Combine(state, name + ".json")));
            return Valid(r) && Verified(FileFor(state, r), r) ? r : null;
        }
        catch (Exception e) when (e is IOException or JsonException or UnauthorizedAccessException) { return null; }
    }

    private static void Save(string dest, byte[] bytes)
    {
        Directory.CreateDirectory(Path.GetDirectoryName(dest));
        var temp = dest + "." + Guid.NewGuid().ToString("N") + ".tmp";
        try { File.WriteAllBytes(temp, bytes); File.Move(temp, dest, true); }
        finally { File.Delete(temp); }
    }

    private static ProcessStartInfo Command(string state, string folder, Release r, string phase, string library = null)
    {
        var shell = Path.Combine(Environment.GetFolderPath(Environment.SpecialFolder.System), "WindowsPowerShell", "v1.0", "powershell.exe");
        var info = new ProcessStartInfo(shell) {WorkingDirectory=folder, UseShellExecute=false, CreateNoWindow=true};
        foreach (var arg in new[] {"-NoProfile","-NonInteractive","-ExecutionPolicy","Bypass","-File",FileFor(state,r),
                                    "-Phase",phase,"-GameFolder",folder,"-StateFolder",state}) info.ArgumentList.Add(arg);
        if (library != null) { info.ArgumentList.Add("-Library"); info.ArgumentList.Add(library); }
        return info;
    }

    private static async Task<int> Run(ProcessStartInfo info, CancellationToken token)
    {
        using var child = Process.Start(info);
        try { await child.WaitForExitAsync(token); }
        catch (OperationCanceledException)
        {
            try { if (!child.HasExited) child.Kill(entireProcessTree:true); } catch (InvalidOperationException) { }
            throw;
        }
        return child.ExitCode;
    }

    private static async Task<byte[]> Bytes(HttpResponseMessage response, int limit, CancellationToken token)
    {
        response.EnsureSuccessStatusCode();
        if (response.Content.Headers.ContentLength > limit) throw new InvalidDataException("Game update exceeds its declared size.");
        await response.Content.LoadIntoBufferAsync(limit).WaitAsync(token);
        return await response.Content.ReadAsByteArrayAsync(token);
    }

    internal async Task<string> Stage(string folder, CancellationToken token)
    {
        await gate.WaitAsync(token);
        try
        {
            var state = State(folder);
            using var response = await http.GetAsync(Feed, HttpCompletionOption.ResponseHeadersRead, token);
            if (response.StatusCode == HttpStatusCode.NotFound) return "Waiting for a published game release";
            var r = JsonSerializer.Deserialize<Release>(await Bytes(response, 32768, token));
            if (!Valid(r)) throw new InvalidDataException("Invalid game release.");
            var active = Read(state, "active");
            var staged = Read(state, "staged");
            foreach (var known in new[] {active, staged}.Where(x => x != null))
            {
                if (known.version == r.version && known != r) throw new InvalidDataException("The game release changed at the same version.");
                if (Version.Parse(known.version) > Version.Parse(r.version)) return "Keeping the newer installed download";
            }
            if (active == r) return "Up to date · " + r.version;
            if (staged != r)
            {
                var path = FileFor(state, r);
                if (!Verified(path, r))
                {
                    using var asset = await http.GetAsync(Releases + r.version + "/" + Script, HttpCompletionOption.ResponseHeadersRead, token);
                    var bytes = await Bytes(asset, r.updater_bytes, token);
                    if (bytes.Length != r.updater_bytes || !Convert.ToHexString(SHA256.HashData(bytes)).Equals(r.updater_sha256, StringComparison.OrdinalIgnoreCase))
                        throw new InvalidDataException("Game adapter verification failed.");
                    Save(path, bytes);
                }
                int exit = await run(Command(state, folder, r, "Stage"), token);
                if (exit == 75) return "Game download deferred";
                if (exit != 0) throw new IOException("Game package could not be staged.");
                Save(Path.Combine(state, "staged.json"), JsonSerializer.SerializeToUtf8Bytes(r));
            }
            return "Ready for next session · " + r.version;
        }
        finally { gate.Release(); }
    }

    internal bool Pending(string folder)
    {
        if (string.IsNullOrWhiteSpace(folder)) return false;
        var state = State(folder);
        var r = Read(state, "staged");
        return r != null && r != Read(state, "active");
    }

    internal async Task<string> Apply(string folder, CancellationToken token)
    {
        if (!await gate.WaitAsync(0,token)) return null;
        try
        {
            var state = State(folder);
            var r = Read(state, "staged");
            if (r == null || r == Read(state, "active")) return null;
            int exit = await run(Command(state, folder, r, "Apply"), token);
            if (exit == 75) return "Waiting for the game to finish";
            if (exit != 0) throw new IOException("Game activation deferred.");
            Save(Path.Combine(state, "active.json"), JsonSerializer.SerializeToUtf8Bytes(r));
            return "Installed · " + r.version;
        }
        finally { gate.Release(); }
    }

    internal ProcessStartInfo LaunchCommand(string folder, string library)
    {
        var state = State(folder);
        var r = Read(state, "active");
        return r == null ? null : Command(state,folder,r,"Launch",library);
    }
}
