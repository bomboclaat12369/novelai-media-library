using System;
using System.IO;
using System.Diagnostics;
using System.Runtime.InteropServices;
using Microsoft.Web.WebView2.Core;
using System.Threading;
using System.Windows.Forms;
[assembly:System.Runtime.CompilerServices.InternalsVisibleTo("MediaSuite.WindowSmoke")]


namespace NovelAI.MediaSuite
{
    internal static class Program
    {
        [DllImport("user32.dll")] private static extern bool AllowSetForegroundWindow(int processId);

        [STAThread]
        private static void Main()
        {
            Application.EnableVisualStyles();
            Application.SetCompatibleTextRenderingDefault(false);
            using (var wake = new EventWaitHandle(false,EventResetMode.AutoReset,@"Local\NovelAI.MediaSuite.Show"))
            using (var single = new Mutex(false,@"Local\NovelAI.MediaSuite.Window",out bool first))
            {
                if (!first)
                {
                    using (var current=Process.GetCurrentProcess())
                    foreach (var process in Process.GetProcessesByName(current.ProcessName))
                    using (process)
                        if (process.Id!=current.Id && process.SessionId==current.SessionId) AllowSetForegroundWindow(process.Id);
                    wake.Set(); return;
                }
                try
                {
                    if (File.Exists(Path.Combine(AppDomain.CurrentDomain.BaseDirectory,"WebView2Loader.dll")))
                        CoreWebView2Environment.SetLoaderDllFolderPath(AppDomain.CurrentDomain.BaseDirectory);
                    var local = Environment.GetFolderPath(Environment.SpecialFolder.LocalApplicationData);
                    var folder = Path.Combine(local,"NovelAI Media Suite");
                    var settings = Preferences.Load<Preferences>(Path.Combine(folder,"settings.json"));
                    Installations.Discover(settings);
                    var services = new Services(settings,Path.Combine(local,"LocalDuplicateReview"));
                    using (var window = new SuiteWindow(settings,folder,services))
                    {
                        var handle = window.Handle;
                        var waiter = ThreadPool.RegisterWaitForSingleObject(wake,(s,t) => {
                            if (!window.IsDisposed && window.IsHandleCreated)
                                try { window.BeginInvoke(new Action(window.BringBack)); } catch (InvalidOperationException) { }
                        },null,-1,false);
                        try { Application.Run(window); }
                        finally { waiter.Unregister(null); }
                    }
                }
                catch (Exception e) { MessageBox.Show(e.Message,"Media Suite",MessageBoxButtons.OK,MessageBoxIcon.Error); }
            }
        }
    }
}
