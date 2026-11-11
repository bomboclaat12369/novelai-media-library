using Microsoft.Win32;
using System;
using System.Collections.Generic;
using System.Diagnostics;
using System.IO;
using System.Linq;
using System.Runtime.InteropServices;
using System.Text;
using System.Threading;
using System.Windows.Automation;
using System.Windows.Forms;

namespace NovelAI.MediaSuite;

internal sealed class EdgeLauncher
{
    private delegate bool WindowCallback(IntPtr handle, IntPtr data);
    [DllImport("user32.dll")] private static extern bool EnumWindows(WindowCallback callback, IntPtr data);
    [DllImport("user32.dll")] private static extern bool IsWindowVisible(IntPtr window);
    [DllImport("user32.dll")] private static extern bool IsIconic(IntPtr window);
    [DllImport("user32.dll")] private static extern bool ShowWindowAsync(IntPtr window, int command);
    [DllImport("user32.dll")] private static extern bool SetForegroundWindow(IntPtr window);
    [DllImport("user32.dll")] private static extern IntPtr GetForegroundWindow();
    [DllImport("user32.dll")] private static extern uint GetWindowThreadProcessId(IntPtr window, out int processId);
    [DllImport("user32.dll", CharSet = CharSet.Unicode)] private static extern int GetClassName(IntPtr window, StringBuilder name, int length);
    [DllImport("dwmapi.dll")] private static extern int DwmGetWindowAttribute(IntPtr window, int attribute, out int value, int size);
    private static readonly PropertyCondition Tab = new(AutomationElement.ControlTypeProperty, ControlType.TabItem);
    private static readonly PropertyCondition Edit = new(AutomationElement.ControlTypeProperty, ControlType.Edit);
    private DateTime launchedWithoutWindow;

    private static string Executable()
    {
        const string key = @"Software\Microsoft\Windows\CurrentVersion\App Paths\msedge.exe";
        using var perUser = Registry.CurrentUser.OpenSubKey(key);
        using var machine = Registry.LocalMachine.OpenSubKey(key);
        string[] candidates = {
            perUser?.GetValue(null) as string, machine?.GetValue(null) as string,
            Path.Combine(Environment.GetFolderPath(Environment.SpecialFolder.ProgramFilesX86), @"Microsoft\Edge\Application\msedge.exe"),
            Path.Combine(Environment.GetFolderPath(Environment.SpecialFolder.ProgramFiles), @"Microsoft\Edge\Application\msedge.exe"),
            Path.Combine(Environment.GetFolderPath(Environment.SpecialFolder.LocalApplicationData), @"Microsoft\Edge\Application\msedge.exe")
        };
        return candidates.FirstOrDefault(File.Exists) ?? throw new FileNotFoundException("Microsoft Edge is required to open Media Suite.");
    }

    private static List<IntPtr> EdgeWindows()
    {
        var windows = new List<IntPtr>();
        var foreground = GetForegroundWindow();
        EnumWindows((handle, _) => {
            if (!IsWindowVisible(handle)) return true;
            var name = new StringBuilder(80);
            GetClassName(handle, name, name.Capacity);
            if (name.ToString() != "Chrome_WidgetWin_1") return true;
            if (DwmGetWindowAttribute(handle, 14, out int cloaked, sizeof(int)) == 0 && cloaked != 0) return true;
            GetWindowThreadProcessId(handle, out int pid);
            try
            {
                using var process = Process.GetProcessById(pid);
                if (process.ProcessName.Equals("msedge", StringComparison.OrdinalIgnoreCase)) windows.Add(handle);
            }
            catch (ArgumentException) { /* Window closed during enumeration. */ }
            return true;
        }, IntPtr.Zero);
        // EnumWindows visits top-level windows in stacking order. Prefer a visible
        // browser over a minimized one when Explorer owns the foreground.
        return windows.OrderBy(h => h == foreground ? 0 : IsIconic(h) ? 2 : 1).ToList();
    }

    // A web document can also have edits and tabs. Only use Edge's own controls.
    private static bool BrowserControl(AutomationElement element, AutomationElement window)
    {
        for (var current = element; current != null; current = TreeWalker.ControlViewWalker.GetParent(current))
        {
            if (Automation.Compare(current, window)) return true;
            if (current.Current.ControlType == ControlType.Document || current.Current.ClassName == "Chrome_RenderWidgetHostHWND") return false;
        }
        return false;
    }

    private static AutomationElement AddressBar(AutomationElement window)
    {
        return window.FindAll(TreeScope.Descendants, Edit).Cast<AutomationElement>().FirstOrDefault(e =>
            (e.Current.ClassName.Contains("Omnibox", StringComparison.OrdinalIgnoreCase) ||
             e.Current.AutomationId == "addressEditBox" || e.Current.Name.Equals("Address and search bar", StringComparison.OrdinalIgnoreCase)) &&
            BrowserControl(e, window));
    }

    private static bool Matches(string text, Uri target)
    {
        text = text.Trim();
        if (!text.Contains("://")) text = "http://" + text;
        return Uri.TryCreate(text, UriKind.Absolute, out var uri) && uri.GetLeftPart(UriPartial.Path) == target.AbsoluteUri;
    }

    private static bool SelectSuiteTab(AutomationElement window, Uri address)
    {
        var tabs = window.FindAll(TreeScope.Descendants, Tab).Cast<AutomationElement>();
        foreach (var tab in tabs.Where(t => t.Current.Name.StartsWith("Media Suite", StringComparison.Ordinal) && BrowserControl(t, window)))
        {
            if (!tab.TryGetCurrentPattern(SelectionItemPattern.Pattern, out var item)) continue;
            var selection = (SelectionItemPattern)item;
            var group = selection.Current.SelectionContainer;
            var previous = group?.TryGetCurrentPattern(SelectionPattern.Pattern, out var groupPattern) == true
                ? ((SelectionPattern)groupPattern).Current.GetSelection().FirstOrDefault() : null;
            selection.Select();
            var bar = AddressBar(window);
            if (bar?.TryGetCurrentPattern(ValuePattern.Pattern, out var value) == true &&
                Matches(((ValuePattern)value).Current.Value, address)) return true;
            if (previous?.TryGetCurrentPattern(SelectionItemPattern.Pattern, out var old) == true)
                ((SelectionItemPattern)old).Select();
        }
        return false;
    }

    private static bool WaitFor(Func<bool> condition)
    {
        var watch = Stopwatch.StartNew();
        do { if (condition()) return true; Thread.Sleep(50); } while (watch.ElapsedMilliseconds < 2500);
        return condition();
    }

    private static void OpenInWindow(IntPtr handle, AutomationElement window, Uri address)
    {
        if (IsIconic(handle)) ShowWindowAsync(handle, 9);
        SetForegroundWindow(handle);
        if (SelectSuiteTab(window, address)) return;
        if (!WaitFor(() => GetForegroundWindow() == handle && !IsIconic(handle)))
            throw new InvalidOperationException("Bring the Edge window you want to the front and open Media Suite again.");

        // Create a tab in this HWND. Sending the URL to msedge.exe here would
        // allow Edge's external-link profile preference to choose a different window.
        int TabCount() => window.FindAll(TreeScope.Descendants, Tab).Cast<AutomationElement>().Count(t => BrowserControl(t, window));
        int before = TabCount();
        SendKeys.SendWait("^t");
        if (!WaitFor(() => TabCount() > before) || GetForegroundWindow() != handle)
            throw new InvalidOperationException("Edge could not create a tab in the selected window.");
        SendKeys.SendWait("^l");
        AutomationElement bar = null;
        bool focused = WaitFor(() => {
            if (GetForegroundWindow() != handle) return false;
            bar = AddressBar(window);
            return bar != null && bar.Current.HasKeyboardFocus;
        });
        if (!focused || !bar.TryGetCurrentPattern(ValuePattern.Pattern, out var pattern))
            throw new InvalidOperationException("Edge could not focus the address bar for the new Media Suite tab.");
        var value = (ValuePattern)pattern;
        value.SetValue(address.AbsoluteUri);
        if (GetForegroundWindow() == handle && bar.Current.HasKeyboardFocus && Matches(value.Current.Value, address))
            SendKeys.SendWait("{ENTER}");
    }

    internal void Show(Uri address)
    {
        foreach (var handle in EdgeWindows())
        {
            try
            {
                var window = AutomationElement.FromHandle(handle);
                if (AddressBar(window) == null) continue; // Edge apps and popups have no regular address bar.
                OpenInWindow(handle, window, address);
                return;
            }
            catch (ElementNotAvailableException) { /* Try the next open window if this one closed. */ }
        }
        if (DateTime.UtcNow - launchedWithoutWindow < TimeSpan.FromSeconds(2)) return;
        var start = new ProcessStartInfo(Executable()) {UseShellExecute = false};
        start.ArgumentList.Add("--no-first-run");
        start.ArgumentList.Add("--no-default-browser-check");
        start.ArgumentList.Add(address.AbsoluteUri);
        using var process = Process.Start(start);
        launchedWithoutWindow = DateTime.UtcNow;
    }
}
