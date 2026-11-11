using System;
using System.Collections.Generic;
using System.Diagnostics;
using System.IO;
using System.IO.Compression;
using System.Linq;
using System.Net.Http;
using System.Security.Cryptography;
using System.Text.Json;
using System.Threading;
using System.Threading.Tasks;

namespace NovelAI.MediaSuite;

// The installed shortcut stays valid. Complete releases live beside each other
// so an update never replaces the executable serving an open suite session.
internal sealed class SuiteUpdates
{
    internal const string Feed = "https://raw.githubusercontent.com/bomboclaat12369/novelai-media-library/main/release-media-suite.json";
    private const string Releases = "https://github.com/bomboclaat12369/novelai-media-library/releases/download/media-suite-v";
    private const long Limit = 256L * 1024 * 1024;
    private static readonly HttpClient Network = new() {Timeout = Timeout.InfiniteTimeSpan};
    private readonly string root;
    private readonly Version current;
    private readonly HttpClient http;
    private string Versions => Path.Combine(root, "versions");
    private string Pointer => Path.Combine(root, "active.json");

    private sealed record Release(string version, string file, long bytes, string sha256);
    private sealed record Entry(string name, string sha256);
    private sealed record Package(string version, Entry[] files);
    private sealed record Active(string version);

    internal SuiteUpdates(string suiteFolder, Version current, HttpClient http = null)
    {
        root = Path.Combine(suiteFolder, "updates");
        this.current = new Version(current.ToString(3));
        this.http = http ?? Network;
    }

    private static Version Parse(string value) =>
        Version.TryParse(value, out var v) && v.Build >= 0 && v.Revision < 0 && v.ToString() == value ? v : null;

    internal string NewerProgram()
    {
        try
        {
            var v = Parse(JsonSerializer.Deserialize<Active>(File.ReadAllText(Pointer))?.version);
            if (v == null || v <= current) return null;
            var folder = Path.Combine(Versions, v.ToString());
            var exe = Path.Combine(folder, "MediaSuite.exe");
            return File.Exists(exe) && File.Exists(Path.Combine(folder, "suite-install.json")) &&
                Parse(FileVersionInfo.GetVersionInfo(exe).ProductVersion) == v ? exe : null;
        }
        catch (Exception e) when (e is IOException or UnauthorizedAccessException or JsonException) { return null; }
    }

    private static async Task<long> CopyLimited(Stream input, Stream output, long limit, CancellationToken token)
    {
        byte[] buffer = new byte[81920];
        long total = 0;
        int count;
        while ((count = await input.ReadAsync(buffer, token)) != 0)
        {
            total += count;
            if (total > limit) throw new InvalidDataException("The update exceeds its declared size.");
            await output.WriteAsync(buffer.AsMemory(0, count), token);
        }
        return total;
    }

    private async Task<long> Download(string url, Stream output, long limit, CancellationToken token)
    {
        using var response = await http.GetAsync(url, HttpCompletionOption.ResponseHeadersRead, token);
        response.EnsureSuccessStatusCode();
        if (response.Content.Headers.ContentLength > limit) throw new InvalidDataException("Unexpected update size.");
        using var input = await response.Content.ReadAsStreamAsync(token);
        return await CopyLimited(input, output, limit, token);
    }

    private static void Verify(string path, string digest)
    {
        using var file = File.OpenRead(path);
        if (!string.Equals(Convert.ToHexString(SHA256.HashData(file)), digest, StringComparison.OrdinalIgnoreCase))
            throw new InvalidDataException("Checksum mismatch for " + Path.GetFileName(path));
    }

    private static async Task Unpack(string zip, string folder, string version, CancellationToken token)
    {
        using var archive = ZipFile.OpenRead(zip);
        var index = archive.GetEntry("files.json") ?? throw new InvalidDataException("Missing package index.");
        if (index.Length > 65536) throw new InvalidDataException("Invalid package index.");
        using var source = index.Open();
        using var json = new MemoryStream();
        await CopyLimited(source, json, 65536, token);
        var bytes = json.ToArray();
        var package = JsonSerializer.Deserialize<Package>(bytes);
        if (package?.version != version || package.files == null) throw new InvalidDataException("Wrong package version.");
        Directory.CreateDirectory(folder);
        var names = new HashSet<string>(StringComparer.OrdinalIgnoreCase);
        long remaining = Limit;
        foreach (var file in package.files)
        {
            string name = file?.name;
            if (string.IsNullOrEmpty(name) || name is "." or ".." || name.EndsWith('.') ||
                !name.All(c => char.IsAsciiLetterOrDigit(c) || c is '.' or '-' or '_') || !names.Add(name))
                throw new InvalidDataException("Invalid package entry.");
            var entry = archive.GetEntry("app/" + name) ?? throw new InvalidDataException("Missing " + name);
            var target = Path.Combine(folder, name);
            using (var read = entry.Open())
            using (var write = new FileStream(target, FileMode.CreateNew, FileAccess.Write, FileShare.None))
                remaining -= await CopyLimited(read, write, remaining, token);
            Verify(target, file.sha256);
        }
        if (!names.Contains("MediaSuite.exe") || !names.Contains("Open-MainCodex.ps1")) throw new InvalidDataException("Incomplete suite package.");
        if (FileVersionInfo.GetVersionInfo(Path.Combine(folder, "MediaSuite.exe")).ProductVersion != version)
            throw new InvalidDataException("The launcher and release versions disagree.");
        await File.WriteAllBytesAsync(Path.Combine(folder, "suite-install.json"), bytes, token);
    }

    internal async Task CheckAsync()
    {
        try
        {
            Directory.CreateDirectory(root);
            // File sharing, unlike a thread-owned mutex, also serializes async continuations and processes.
            using var gate = new FileStream(Path.Combine(root, "update.lock"), FileMode.OpenOrCreate, FileAccess.Write, FileShare.None);
            using var info = new MemoryStream();
            using (var timeout = new CancellationTokenSource(TimeSpan.FromSeconds(4)))
                await Download(Feed, info, 32768, timeout.Token);
            var release = JsonSerializer.Deserialize<Release>(info.ToArray());
            var wanted = Parse(release?.version) ?? throw new InvalidDataException("Invalid update version.");
            if (wanted <= current) return;
            var active = NewerProgram();
            if (active != null && Parse(Path.GetFileName(Path.GetDirectoryName(active))) >= wanted) return;
            if (release.file != $"Media-Suite-{wanted}.zip" || release.bytes <= 0 || release.bytes > Limit ||
                release.sha256?.Length != 64 || !release.sha256.All(Uri.IsHexDigit))
                throw new InvalidDataException("Invalid suite release manifest.");
            await Stage(release);
        }
        catch (Exception e) when (e is IOException or InvalidDataException or UnauthorizedAccessException or HttpRequestException or OperationCanceledException or JsonException)
        {
            Trace.TraceWarning("Suite update deferred: {0}", e.Message);
        }
    }

    private async Task Stage(Release release)
    {
        Directory.CreateDirectory(Versions);
        foreach (string abandoned in Directory.GetDirectories(root, "stage-*"))
            if (Guid.TryParseExact(Path.GetFileName(abandoned)[6..], "N", out _)) RemoveOwned(abandoned);
        var stage = Directory.CreateDirectory(Path.Combine(root, "stage-" + Guid.NewGuid().ToString("N"))).FullName;
        try
        {
            using var timeout = new CancellationTokenSource(TimeSpan.FromMinutes(3));
            var zip = Path.Combine(stage, release.file);
            var url = Releases + release.version + "/" + release.file;
            using (var output = File.Create(zip))
                if (await Download(url, output, release.bytes, timeout.Token) != release.bytes)
                    throw new InvalidDataException("Incomplete suite download.");
            Verify(zip, release.sha256);
            var program = Path.Combine(stage, "app");
            await Unpack(zip, program, release.version, timeout.Token);
            var destination = Path.Combine(Versions, release.version);
            if (!Directory.Exists(destination)) Directory.Move(program, destination);
            else
            {
                // A prior process may have committed the directory before the pointer.
                foreach (var path in Directory.GetFiles(program))
                {
                    using var expected = File.OpenRead(path);
                    Verify(Path.Combine(destination, Path.GetFileName(path)), Convert.ToHexString(SHA256.HashData(expected)));
                }
            }
            var pending = Path.Combine(stage, "active.json");
            File.WriteAllText(pending, JsonSerializer.Serialize(new Active(release.version)));
            File.Move(pending, Pointer, true);
            var old = Directory.GetDirectories(Versions).Select(dir => (dir, v: Parse(Path.GetFileName(dir))))
                .Where(x => x.v != null && x.v < Parse(release.version) && File.Exists(Path.Combine(x.dir, "suite-install.json")))
                .OrderByDescending(x => x.v).Skip(1);
            foreach (var item in old) if (item.v != current) RemoveOwned(item.dir);
        }
        finally { RemoveOwned(stage); }
    }

    private static void RemoveOwned(string path)
    {
        try { Directory.Delete(path, true); }
        catch (IOException) { }
        catch (UnauthorizedAccessException) { }
    }
}
