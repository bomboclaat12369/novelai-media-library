using System;
using System.Diagnostics;
using System.IO;
using System.Net.Http;
using System.Runtime.InteropServices;
using System.Threading;
using System.Threading.Tasks;
using System.Windows.Forms;

namespace NovelAI.MediaSuite;

internal static class Program
{
    private const string ShowEvent = @"Local\NovelAI.MediaSuite.Chrome.Show";
    private const string StopEvent = @"Local\NovelAI.MediaSuite.Chrome.Stop";
    [DllImport("user32.dll")] private static extern bool AllowSetForegroundWindow(int processId);

    [STAThread]
    private static int Main(string[] args)
    {
        Application.SetHighDpiMode(HighDpiMode.PerMonitorV2);
        if (args.Length == 1 && args[0] == "--stop")
        {
            if (EventWaitHandle.TryOpenExisting(StopEvent, out var signal))
                using (signal) signal.Set();
            return 0;
        }
        try
        {
            bool resumeTabs = args.Length == 1 && args[0] == "--resume-tabs";
            string next = RunHost(ref resumeTabs);
            if (next != null)
            {
                var start = new ProcessStartInfo(next) {UseShellExecute = false, WorkingDirectory = Path.GetDirectoryName(next)};
                if (resumeTabs) start.ArgumentList.Add("--resume-tabs");
                using var child = Process.Start(start);
                if (!resumeTabs) AllowSetForegroundWindow(child.Id);
            }
            return 0;
        }
        catch (Exception error)
        {
            MessageBox.Show(error.GetBaseException().Message, "Media Suite", MessageBoxButtons.OK, MessageBoxIcon.Error);
            return 1;
        }
    }

    private static string RunHost(ref bool resumeTabs)
    {
        using var show = new EventWaitHandle(false, EventResetMode.AutoReset, ShowEvent);
        using var stop = new EventWaitHandle(false, EventResetMode.AutoReset, StopEvent);
        // Keep the established IPC names so the existing installer can stop either generation.
        using var single = new Mutex(false, @"Local\NovelAI.MediaSuite.Chrome.Host", out bool first);
        if (!first)
        {
            if (resumeTabs) return null;
            using var current = Process.GetCurrentProcess();
            foreach (var process in Process.GetProcessesByName(current.ProcessName))
                using (process)
                    if (process.Id != current.Id && process.SessionId == current.SessionId)
                        AllowSetForegroundWindow(process.Id);
            show.Set();
            return null;
        }
        var local = Environment.GetFolderPath(Environment.SpecialFolder.LocalApplicationData);
        var folder = Path.Combine(local, "NovelAI Media Suite");
        var updates = new SuiteUpdates(folder, typeof(Program).Assembly.GetName().Version);
        string next = updates.NewerProgram();
        if (next != null) return next;
        Task<bool> check = resumeTabs ? Task.FromResult(false) : Task.Run(updates.CheckAsync);
        bool checkedSuite = check.GetAwaiter().GetResult();
        if (!resumeTabs && (next = updates.NewerProgram()) != null) return next;

        var settings = Preferences.Load<Preferences>(Path.Combine(folder, "settings.json"));
        Installations.Discover(settings);
        var services = new Services(settings, Path.Combine(local, "LocalDuplicateReview"));
        var edge = new EdgeLauncher();
        using var host = new BrowserHost(settings, folder, services);
        using var stopping = new CancellationTokenSource();
        using var localApps = new HttpClient(new SocketsHttpHandler {UseProxy=false, AllowAutoRedirect=false}) {Timeout=TimeSpan.FromSeconds(55)};
        using var releases = new HttpClient {Timeout=TimeSpan.FromSeconds(15)};
        var game = new GameUpdates(folder,releases);
        services.GameUpdates = game;
        services.CompanionUpdates = new CompanionUpdates(folder,localApps);
        var checkLock = new object();
        string SuiteStatus(bool online) => updates.NewerProgram() != null ? "Update ready"
            : online ? "Up to date · " + typeof(Program).Assembly.GetName().Version.ToString(3) : "Couldn’t check. Will retry.";
        async Task<string> CheckSuite()
        {
            Task<bool> run;
            lock (checkLock) { if (check.IsCompleted) check = Task.Run(updates.CheckAsync); run = check; }
            return SuiteStatus(await run);
        }
        var apps = new ApplicationUpdates(settings,services,localApps,game,CheckSuite,host.WhileIdle,stopping.Token);
        using var replace = new AutoResetEvent(false);
        string requestedLauncher = null;
        host.FindLauncher = updates.NewerProgram;
        host.ReplaceLauncher = path => { requestedLauncher = path; replace.Set(); };
        host.Updates = apps;
        host.StartAsync(resumeTabs).GetAwaiter().GetResult();
        _ = apps.Check(resumeTabs ? null : SuiteStatus(checkedSuite));
        var signals = new WaitHandle[] {stop, show, replace};
        bool showBrowser = !resumeTabs;
        var lastCheck = DateTime.UtcNow;
        try
        {
            while (true)
            {
                if (showBrowser) edge.Show(host.Address);
                showBrowser = true;
                int signal;
                do
                {
                    signal = WaitHandle.WaitAny(signals, TimeSpan.FromSeconds(30));
                    if (signal == 0) return null;
                    if (signal == 2) { resumeTabs = true; return requestedLauncher; }
                    bool idleLaunch = signal == 1 && !host.InUse;
                    if (idleLaunch)
                    {
                        var status = CheckSuite().GetAwaiter().GetResult();
                        next = updates.NewerProgram();
                        if (next != null && host.TryHandOff()) return next;
                        apps.ApplyWhenIdle().GetAwaiter().GetResult();
                        _ = apps.Check(status);
                        lastCheck = DateTime.UtcNow;
                    }
                    else
                    {
                        if (!host.Updating && DateTime.UtcNow - lastCheck > TimeSpan.FromHours(1))
                        { _ = apps.Check(); lastCheck = DateTime.UtcNow; }
                        if (!host.InUse) _ = apps.ApplyWhenIdle();
                    }
                } while (signal != 1);
            }
        }
        finally { stopping.Cancel(); }
    }
}
