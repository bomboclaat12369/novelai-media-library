using System;
using System.Diagnostics;
using System.IO;
using System.Runtime.InteropServices;
using System.Threading;
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
            using var show = new EventWaitHandle(false, EventResetMode.AutoReset, ShowEvent);
            using var stop = new EventWaitHandle(false, EventResetMode.AutoReset, StopEvent);
            using var single = new Mutex(false, @"Local\NovelAI.MediaSuite.Chrome.Host", out bool first);
            if (!first)
            {
                using var current = Process.GetCurrentProcess();
                foreach (var process in Process.GetProcessesByName(current.ProcessName))
                    using (process)
                        if (process.Id != current.Id && process.SessionId == current.SessionId)
                            AllowSetForegroundWindow(process.Id);
                show.Set();
                return 0;
            }
            var local = Environment.GetFolderPath(Environment.SpecialFolder.LocalApplicationData);
            var folder = Path.Combine(local, "NovelAI Media Suite");
            var settings = Preferences.Load<Preferences>(Path.Combine(folder, "settings.json"));
            Installations.Discover(settings);
            var services = new Services(settings, Path.Combine(local, "LocalDuplicateReview"));
            var chrome = new ChromeLauncher();
            using var host = new BrowserHost(settings, folder, services);
            host.StartAsync().GetAwaiter().GetResult();
            do { chrome.Show(host.Address); }
            while (WaitHandle.WaitAny(new WaitHandle[] {stop, show}) == 1);
            return 0;
        }
        catch (Exception error)
        {
            MessageBox.Show(error.GetBaseException().Message, "Media Suite", MessageBoxButtons.OK, MessageBoxIcon.Error);
            return 1;
        }
    }
}
