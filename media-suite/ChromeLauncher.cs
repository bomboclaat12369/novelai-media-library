using Microsoft.Win32;
using System;
using System.Diagnostics;
using System.IO;
using System.Linq;
using System.Runtime.InteropServices;
using System.Windows.Automation;

namespace NovelAI.MediaSuite;

internal sealed class ChromeLauncher
{
    [DllImport("user32.dll")] private static extern bool SetForegroundWindow(IntPtr window);
    [DllImport("user32.dll")] private static extern bool IsIconic(IntPtr window);
    [DllImport("user32.dll")] private static extern bool ShowWindowAsync(IntPtr window, int command);
    private readonly string executable;
    private DateTime lastLaunch;

    internal ChromeLauncher()
    {
        const string key = @"Software\Microsoft\Windows\CurrentVersion\App Paths\chrome.exe";
        var candidates = new[] {
            Registry.CurrentUser.OpenSubKey(key)?.GetValue(null) as string,
            Registry.LocalMachine.OpenSubKey(key)?.GetValue(null) as string,
            Environment.GetFolderPath(Environment.SpecialFolder.ProgramFiles),
            Environment.GetFolderPath(Environment.SpecialFolder.ProgramFilesX86),
            Environment.GetFolderPath(Environment.SpecialFolder.LocalApplicationData)
        };
        executable = candidates.Where(s => !string.IsNullOrWhiteSpace(s))
            .Select(s => s.EndsWith(".exe", StringComparison.OrdinalIgnoreCase) ? s : Path.Combine(s, @"Google\Chrome\Application\chrome.exe"))
            .FirstOrDefault(File.Exists) ?? throw new FileNotFoundException("Google Chrome is required to open Media Suite. Install Chrome and open the shortcut again.");
    }

    internal void Show(Uri address)
    {
        // Allow Chrome to finish creating its tab if the shortcut was double-launched.
        if (DateTime.UtcNow - lastLaunch < TimeSpan.FromSeconds(2)) return;
        if (ActivateExisting(address)) return;
        var info = new ProcessStartInfo(executable) {UseShellExecute = false};
        info.ArgumentList.Add("--no-first-run");
        info.ArgumentList.Add("--no-default-browser-check");
        info.ArgumentList.Add(address.AbsoluteUri);
        using var process = Process.Start(info);
        lastLaunch = DateTime.UtcNow;
    }

    private static bool ActivateExisting(Uri address)
    {
        var windows = AutomationElement.RootElement.FindAll(TreeScope.Children,
            new PropertyCondition(AutomationElement.ClassNameProperty, "Chrome_WidgetWin_1"));
        foreach (AutomationElement window in windows)
        {
            try
            {
                using var owner = Process.GetProcessById(window.Current.ProcessId);
                if (!owner.ProcessName.Equals("chrome", StringComparison.OrdinalIgnoreCase)) continue;
                var match = new PropertyCondition(AutomationElement.ControlTypeProperty, ControlType.TabItem);
                foreach (AutomationElement tab in window.FindAll(TreeScope.Descendants, match))
                {
                    string name = tab.Current.Name;
                    if (name != "Media Suite" && !name.StartsWith("Media Suite - ") && !name.StartsWith("Media Suite – ")) continue;
                    if (!tab.TryGetCurrentPattern(SelectionItemPattern.Pattern, out object pattern)) continue;
                    var selection = (SelectionItemPattern)pattern;
                    var group = selection.Current.SelectionContainer;
                    var previous = group?.TryGetCurrentPattern(SelectionPattern.Pattern, out object groupPattern) == true
                        ? ((SelectionPattern)groupPattern).Current.GetSelection().FirstOrDefault() : null;
                    selection.Select();
                    // Chrome omits the scheme and trailing slash in its address field.
                    var edits = window.FindAll(TreeScope.Descendants, new PropertyCondition(AutomationElement.ControlTypeProperty, ControlType.Edit));
                    if (edits.Cast<AutomationElement>().Any(edit => edit.Current.ClassName == "OmniboxViewViews" &&
                        edit.TryGetCurrentPattern(ValuePattern.Pattern, out object value) &&
                        IsAddress(((ValuePattern)value).Current.Value, address)))
                    {
                        var handle = new IntPtr(window.Current.NativeWindowHandle);
                        if (IsIconic(handle)) ShowWindowAsync(handle, 9);
                        SetForegroundWindow(handle);
                        return true;
                    }
                    if (previous?.TryGetCurrentPattern(SelectionItemPattern.Pattern, out object old) == true)
                        ((SelectionItemPattern)old).Select();
                }
            }
            catch (Exception e) when (e is ElementNotAvailableException or InvalidOperationException or ArgumentException or COMException)
            { /* A browser window or tab can disappear during enumeration. */ }
        }
        return false;
    }

    private static bool IsAddress(string text, Uri target)
    {
        text = text.Trim();
        if (!text.Contains("://")) text = "http://" + text;
        return Uri.TryCreate(text, UriKind.Absolute, out var uri) && uri.GetLeftPart(UriPartial.Path) == target.AbsoluteUri;
    }
}
