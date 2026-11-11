using System;
using System.Diagnostics;
using System.IO;
using System.Net.Http;
using System.Runtime.Serialization;
using System.Text;
using System.Threading;
using System.Threading.Tasks;

namespace NovelAI.MediaSuite
{
    internal enum Section { Library, Battles, Workbench, AfterHours }

    [DataContract]
    internal sealed class Health
    {
        [DataMember(Name="standalone_library")] public bool Standalone { get; set; }
        [DataMember(Name="library_root")] public string Root { get; set; }
    }

    internal sealed class Services
    {
        internal static readonly Uri LibraryPage = new Uri("http://127.0.0.1:8765/library/");
        internal static readonly Uri GamePage = new Uri("http://127.0.0.1:8877/game/");
        private readonly Preferences settings;
        private readonly string workbenchState;
        private readonly HttpClient http;
        private readonly Action<ProcessStartInfo> start;
        private readonly SemaphoreSlim companionGate = new SemaphoreSlim(1);
        private readonly SemaphoreSlim workbenchGate = new SemaphoreSlim(1);
        private readonly SemaphoreSlim gameGate = new SemaphoreSlim(1);
        private readonly TimeSpan wait;
        internal string ActiveLibrary { get; private set; }

        internal Services(Preferences settings, string workbenchState, HttpMessageHandler handler = null,
            Action<ProcessStartInfo> start = null, TimeSpan? wait = null)
        {
            this.settings = settings;
            this.workbenchState = workbenchState;
            this.start = start ?? (info => { using (Process.Start(info)) { } });
            this.wait = wait ?? TimeSpan.FromSeconds(90);
            http = new HttpClient(handler ?? new HttpClientHandler { UseProxy = false, AllowAutoRedirect = false });
            http.Timeout = TimeSpan.FromSeconds(2);
        }

        private async Task<byte[]> Probe(Uri uri, CancellationToken token, int max = 12288)
        {
            try
            {
                using (var response = await http.GetAsync(uri,HttpCompletionOption.ResponseHeadersRead,token).ConfigureAwait(false))
                {
                    if (!response.IsSuccessStatusCode) return null;
                    using (var stream = await response.Content.ReadAsStreamAsync().ConfigureAwait(false))
                    using (var output = new MemoryStream())
                    using (var timeout = CancellationTokenSource.CreateLinkedTokenSource(token))
                    {
                        timeout.CancelAfter(TimeSpan.FromSeconds(2));
                        var buffer = new byte[4096];
                        while (output.Length < max)
                        {
                            var n = await stream.ReadAsync(buffer,0,Math.Min(buffer.Length,max-(int)output.Length),timeout.Token).ConfigureAwait(false);
                            if (n == 0) break;
                            output.Write(buffer,0,n);
                        }
                        return output.ToArray();
                    }
                }
            }
            catch (HttpRequestException) { return null; }
            catch (IOException) { return null; }
            catch (OperationCanceledException) when (!token.IsCancellationRequested) { return null; }
        }

        internal static Uri WorkbenchAddress(string text)
        {
            Uri uri;
            if (!Uri.TryCreate((text ?? "").Trim(), UriKind.Absolute, out uri) || uri.Scheme != "http" ||
                uri.Host != "127.0.0.1" || uri.Port < 1 || uri.UserInfo != "" || uri.AbsolutePath != "/organizer" ||
                uri.Fragment != "" || uri.Query != "") return null;
            return uri;
        }

        internal Uri RecordedWorkbench()
        {
            try { return WorkbenchAddress(File.ReadAllText(Path.Combine(workbenchState,"running-url.txt"))); }
            catch (IOException) { return null; }
        }

        private async Task<Uri> RunningLibrary(CancellationToken token)
        {
            var bytes = await Probe(new Uri(LibraryPage,"/api/health"),token).ConfigureAwait(false);
            if (bytes == null) return null;
            Health health;
            try { using (var data = new MemoryStream(bytes)) health = Preferences.Read<Health>(data); }
            catch (SerializationException) { return null; }
            if (health == null || !health.Standalone || string.IsNullOrWhiteSpace(health.Root)) return null;
            if (!string.IsNullOrWhiteSpace(settings.LibraryFolder) &&
                !string.Equals(Path.GetFullPath(settings.LibraryFolder).TrimEnd(Path.DirectorySeparatorChar),
                               Path.GetFullPath(health.Root).TrimEnd(Path.DirectorySeparatorChar),StringComparison.OrdinalIgnoreCase))
                throw new InvalidOperationException("The running companion uses " + health.Root +
                    ". Choose that library in Locations, or close that companion and retry with your chosen library.");
            ActiveLibrary = health.Root;
            return LibraryPage;
        }

        private async Task<Uri> RunningWorkbench(CancellationToken token)
        {
            var address = RecordedWorkbench();
            if (address == null) return null;
            var bytes = await Probe(address,token,4096).ConfigureAwait(false);
            return bytes != null && Encoding.UTF8.GetString(bytes).Contains("data-local-duplicate-review=") ? address : null;
        }

        private async Task<Uri> RunningGame(CancellationToken token)
        {
            var bytes = await Probe(GamePage,token,2048).ConfigureAwait(false);
            return bytes != null && Encoding.UTF8.GetString(bytes).IndexOf("<title>After Hours",StringComparison.OrdinalIgnoreCase)>=0 ? GamePage : null;
        }

        // ProcessStartInfo on .NET Framework takes a single Windows command line.
        internal static string Quote(string value)
        {
            var text = new StringBuilder("\"");
            int slashes = 0;
            foreach (var ch in value)
            {
                if (ch == '\\') { slashes++; continue; }
                if (ch == '"') { text.Append('\\',slashes*2+1).Append(ch); }
                else { text.Append('\\',slashes).Append(ch); }
                slashes = 0;
            }
            return text.Append('\\',slashes*2).Append('"').ToString();
        }

        private void Start(string executable,string directory,params string[] args)
        {
            start(new ProcessStartInfo(executable,string.Join(" ",Array.ConvertAll(args,Quote))) {
                WorkingDirectory=directory, UseShellExecute=false, CreateNoWindow=true
            });
        }

        private void LaunchLibrary()
        {
            if (!Installations.Library(settings.LibraryFolder))
                throw new InvalidOperationException("In Locations, choose your existing media folder containing library.json.");
            if (!Installations.Companion(settings.CompanionFolder))
                throw new InvalidOperationException("In Locations, choose the installed Media Library program folder containing companion.pyw and its .venv.");
            Start(Installations.Python(settings.CompanionFolder),settings.CompanionFolder,"companion.pyw","--headless","--root",settings.LibraryFolder);
        }

        private void LaunchWorkbench()
        {
            if (!Installations.Workbench(settings.WorkbenchFolder))
                throw new InvalidOperationException("In Locations, choose the installed Workbench folder containing app.py and its .venv.");
            Start(Installations.Python(settings.WorkbenchFolder),settings.WorkbenchFolder,"app.py","--no-browser");
        }

        private void LaunchGame()
        {
            var folder = settings.GameFolder;
            if (!Installations.Game(folder))
                throw new InvalidOperationException("In Locations, choose your After Hours installation containing game/Launch.ps1.");
            var local = Preferences.Load<GameConfig>(Path.Combine(folder,"local.json"));
            var library = Installations.LibraryDirectory(local.Library);
            if (string.IsNullOrWhiteSpace(library)) library = ActiveLibrary ?? settings.LibraryFolder;
            if (!Installations.Library(library))
                throw new InvalidOperationException("After Hours needs an existing library.json. Check the library in game/local.json or in Locations.");
            var shell = Path.Combine(Environment.GetFolderPath(Environment.SpecialFolder.System),"WindowsPowerShell","v1.0","powershell.exe");
            Start(shell,folder,"-NoProfile","-NonInteractive","-ExecutionPolicy","Bypass","-File",
                Path.Combine(folder,"Launch.ps1"),"-NoBrowser","-Library",library);
        }

        private async Task<Uri> Connect(SemaphoreSlim gate, Func<CancellationToken,Task<Uri>> probe,
            Action launch, string name, CancellationToken token)
        {
            await gate.WaitAsync(token).ConfigureAwait(false);
            try
            {
                var found = await probe(token).ConfigureAwait(false);
                if (found!=null) return found;
                token.ThrowIfCancellationRequested();
                launch();
                var clock = Stopwatch.StartNew();
                do
                {
                    await Task.Delay(300,token).ConfigureAwait(false);
                    found = await probe(token).ConfigureAwait(false);
                    if (found!=null) return found;
                } while (clock.Elapsed < wait);
                throw new InvalidOperationException(name + " did not become available. Check Locations or open its usual launcher for diagnostics, then retry.");
            }
            finally { gate.Release(); }
        }

        internal Task<Uri> Library(CancellationToken token) => Connect(companionGate,RunningLibrary,LaunchLibrary,"Media Library",token);
        internal async Task<Uri> Open(Section section,CancellationToken token)
        {
            switch (section)
            {
                case Section.Workbench:
                    await Library(token).ConfigureAwait(false);
                    return await Connect(workbenchGate,RunningWorkbench,LaunchWorkbench,"Workbench",token).ConfigureAwait(false);
                case Section.AfterHours:
                    return await Connect(gameGate,RunningGame,LaunchGame,"After Hours",token).ConfigureAwait(false);
                default: return await Library(token).ConfigureAwait(false);
            }
        }
    }
}
