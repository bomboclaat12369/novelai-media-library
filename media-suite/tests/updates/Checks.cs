using System;
using System.IO;
using System.Net;
using System.Net.Http;
using System.Security.Cryptography;
using System.Text;
using System.Text.Json;
using System.Threading;
using System.Threading.Tasks;
using NovelAI.MediaSuite;

// Drive the production updater with the exact release ZIP and an isolated feed.
var archive = Path.GetFullPath(args[0]);
var root = Path.GetFullPath(args[1]);
if (Directory.Exists(root)) throw new Exception("A fresh update fixture is required.");
var directory = Path.GetDirectoryName(archive);
var manifest = File.ReadAllText(Path.Combine(directory, "media-suite-manifest.json"));
using var json = JsonDocument.Parse(manifest);
var version = json.RootElement.GetProperty("version").GetString();
var fake = new Feed(archive, manifest);
using var http = new HttpClient(fake);
var updater = new SuiteUpdates(root, new Version(1, 0, 0), http);

fake.Offline = true;
await updater.CheckAsync();
if (updater.NewerProgram() != null || fake.Downloads != 0) throw new Exception("Offline fallback failed.");
fake.Offline = false;
fake.Damage = true;
await updater.CheckAsync();
if (updater.NewerProgram() != null || File.Exists(Path.Combine(root, "updates/active.json"))) throw new Exception("A damaged download became active.");
fake.Damage = false;
fake.Manifest = manifest.Replace(json.RootElement.GetProperty("sha256").GetString(), new string('0', 64));
await updater.CheckAsync();
if (updater.NewerProgram() != null) throw new Exception("A checksum mismatch became active.");
fake.Manifest = manifest;
int before = fake.Downloads;
await Task.WhenAll(updater.CheckAsync(), updater.CheckAsync());
var active = updater.NewerProgram();
if (active != Path.Combine(root, "updates", "versions", version, "MediaSuite.exe") || fake.Downloads != before + 1)
    throw new Exception("Concurrent updates did not activate exactly one verified release.");
var installed = File.ReadAllText(Path.Combine(Path.GetDirectoryName(active), "suite-install.json"));
foreach (var item in JsonDocument.Parse(installed).RootElement.GetProperty("files").EnumerateArray())
{
    using var file = File.OpenRead(Path.Combine(Path.GetDirectoryName(active), item.GetProperty("name").GetString()));
    if (!Convert.ToHexString(SHA256.HashData(file)).Equals(item.GetProperty("sha256").GetString(), StringComparison.OrdinalIgnoreCase))
        throw new Exception("A staged file differs from its tested package.");
}
before = fake.Downloads;
await updater.CheckAsync();
await new SuiteUpdates(root, new Version(version), http).CheckAsync();
if (fake.Downloads != before) throw new Exception("An installed update was downloaded again.");
fake.Manifest = JsonSerializer.Serialize(new {version = "99.0.0", file = "Media-Suite-99.0.0.zip", bytes = 12, sha256 = new string('0', 64)});
await updater.CheckAsync();
if (updater.NewerProgram() != active) throw new Exception("A bad subsequent release displaced the working suite.");
Console.WriteLine("Verified automatic staging, concurrent checks, offline fallback, corrupt-package rollback and no repeat download.");

sealed class Feed(string file, string manifest) : HttpMessageHandler
{
    internal string Manifest = manifest;
    internal int Downloads;
    internal bool Offline, Damage;
    protected override Task<HttpResponseMessage> SendAsync(HttpRequestMessage request, CancellationToken token)
    {
        if (Offline) throw new HttpRequestException("Fixture offline.");
        var result = new HttpResponseMessage(HttpStatusCode.OK);
        if (request.RequestUri.AbsoluteUri == SuiteUpdates.Feed) result.Content = new StringContent(Manifest, Encoding.UTF8, "application/json");
        else
        {
            var uri = request.RequestUri;
            if (uri.Scheme != "https" || uri.Host != "github.com" || !uri.AbsolutePath.StartsWith("/bomboclaat12369/novelai-media-library/releases/download/media-suite-v"))
                throw new InvalidOperationException("Unexpected update origin.");
            Interlocked.Increment(ref Downloads);
            result.Content = Damage ? new ByteArrayContent(new byte[] {1,2,3}) : new StreamContent(File.OpenRead(file));
        }
        return Task.FromResult(result);
    }
}
