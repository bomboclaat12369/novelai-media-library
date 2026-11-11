using System;
using System.Collections.Generic;
using System.Diagnostics;
using System.Drawing;
using System.IO;
using System.Threading;
using System.Threading.Tasks;
using System.Windows.Forms;
using Microsoft.Web.WebView2.Core;
using Microsoft.Web.WebView2.WinForms;

namespace NovelAI.MediaSuite
{
    internal sealed class SuiteWindow : Form
    {
        private sealed class Page
        {
            internal Panel Host;
            internal Label Status;
            internal Button Retry;
            internal WebView2 Browser;
            internal Uri Address;
            internal bool Busy, Ready, Navigating;
        }

        private readonly Preferences settings;
        private readonly string folder;
        private readonly Services services;
        private readonly Dictionary<Section,Page> pages=new Dictionary<Section,Page>();
        private readonly Dictionary<Section,ToolStripButton> buttons=new Dictionary<Section,ToolStripButton>();
        private readonly CancellationTokenSource closing=new CancellationTokenSource();
        private readonly ToolStrip strip=new ToolStrip();
        private readonly Panel body=new Panel {Dock=DockStyle.Fill};
        private readonly System.Windows.Forms.Timer checkWorkbench=new System.Windows.Forms.Timer {Interval=2500};
        private Task<CoreWebView2Environment> environment;
        private Section selected;
        private FormWindowState beforeFullScreen;
        private bool fullScreen;
        internal static readonly string[] Labels={"Media Library","Battles","Workbench","After Hours"};

        internal SuiteWindow(Preferences settings,string folder,Services services)
        {
            this.settings=settings;this.folder=folder;this.services=services;
            Text="Media Suite";Size=new Size(1280,850);MinimumSize=new Size(600,400);
            AutoScaleMode=AutoScaleMode.Dpi;StartPosition=FormStartPosition.CenterScreen;
            Icon=Icon.ExtractAssociatedIcon(Application.ExecutablePath);
            if (settings.Maximized) WindowState=FormWindowState.Maximized;
            strip.GripStyle=ToolStripGripStyle.Hidden;strip.RenderMode=ToolStripRenderMode.System;
            strip.Padding=new Padding(8,4,8,4);strip.Dock=DockStyle.Top;
            strip.BackColor=Color.FromArgb(224,233,239);strip.Font=new Font("Segoe UI",10);
            Controls.Add(body);Controls.Add(strip);
            foreach (Section section in Enum.GetValues(typeof(Section)))
            {
                var button=new ToolStripButton(Labels[(int)section]) {Padding=new Padding(6,3,6,3),DisplayStyle=ToolStripItemDisplayStyle.Text};
                button.Click+=(s,e)=>SelectPage(section);
                buttons.Add(section,button);strip.Items.Add(button);
                var page=new Page {Host=new Panel {Dock=DockStyle.Fill,Visible=false,Padding=Padding.Empty}};
                var feedback=new FlowLayoutPanel {Dock=DockStyle.Fill,Padding=new Padding(20),FlowDirection=FlowDirection.TopDown};
                page.Status=new Label {AutoSize=true,MaximumSize=new Size(650,0),Font=SystemFonts.MessageBoxFont};
                page.Retry=new Button {AutoSize=true,Text="Retry",Visible=false};
                page.Retry.Click+=(s,e)=>ConnectPage(section);
                feedback.Controls.Add(page.Status);feedback.Controls.Add(page.Retry);page.Host.Controls.Add(feedback);
                pages.Add(section,page);body.Controls.Add(page.Host);
            }
            var locations=new ToolStripButton("Locations…") {Alignment=ToolStripItemAlignment.Right};
            locations.Click+=(s,e)=> {
                if (string.IsNullOrEmpty(settings.LibraryFolder)) settings.LibraryFolder=services.ActiveLibrary;
                using (var dialog=new Locations(settings)) if(dialog.ShowDialog(this)==DialogResult.OK)
                { WriteSettings(); if (!pages[selected].Ready) ConnectPage(selected); }
            };
            strip.Items.Add(locations);
            if (!Enum.TryParse(settings.LastSection,out selected) || !Enum.IsDefined(typeof(Section),selected)) selected=Section.Library;
            Shown+=(s,e)=> {
                SelectPage(selected);
                if (selected==Section.AfterHours) WarmCompanion();
                checkWorkbench.Start();
            };
            checkWorkbench.Tick+=(s,e)=>RefreshWorkbench();
            FormClosing+=(s,e)=> {closing.Cancel();checkWorkbench.Stop();settings.Maximized=fullScreen?beforeFullScreen==FormWindowState.Maximized:WindowState==FormWindowState.Maximized;WriteSettings();};
            FormClosed+=(s,e)=>checkWorkbench.Dispose();
        }

        private async void WarmCompanion()
        {
            try { await services.Library(closing.Token); RememberLibrary(); }
            catch (Exception) { /* The Library tab offers its own connection and retry. */ }
        }

        private void RememberLibrary()
        {
            if(!closing.IsCancellationRequested && string.IsNullOrEmpty(settings.LibraryFolder) && !string.IsNullOrEmpty(services.ActiveLibrary))
            { settings.LibraryFolder=services.ActiveLibrary; WriteSettings(); }
        }

        internal void BringBack()
        {
            if (WindowState==FormWindowState.Minimized) WindowState=settings.Maximized?FormWindowState.Maximized:FormWindowState.Normal;
            Show();Activate();BringToFront();
        }

        private void WriteSettings()
        {
            try { settings.Save(folder); }
            catch (Exception err) { MessageBox.Show(this,err.Message,"Could not save suite settings"); }
        }

        internal void SelectPage(Section section)
        {
            selected=section;
            foreach(var item in pages) {item.Value.Host.Visible=item.Key==section;buttons[item.Key].Checked=item.Key==section;}
            pages[section].Host.BringToFront();settings.LastSection=section.ToString();WriteSettings();
            var page=pages[section];
            if (!page.Ready) ConnectPage(section);
            else {page.Browser.Focus();if (section==Section.Battles) OpenBattles(); if(section==Section.Workbench) RefreshWorkbench();}
        }

        private void RefreshWorkbench()
        {
            var page=pages[Section.Workbench];
            if(selected!=Section.Workbench || !page.Ready || page.Busy) return;
            var recorded=services.RecordedWorkbench();
            if(recorded!=null && recorded!=page.Address) ConnectPage(Section.Workbench);
        }

        private async void ConnectPage(Section section)
        {
            var page=pages[section];
            if (page.Busy || page.Navigating) return;
            page.Busy=true;page.Ready=false;page.Retry.Visible=false;
            page.Status.Text="Opening "+Labels[(int)section]+"…";
            if(page.Browser!=null) page.Browser.Visible=false;
            try
            {
                var address=await services.Open(section,closing.Token);
                RememberLibrary();
                closing.Token.ThrowIfCancellationRequested();
                if(environment==null || environment.IsFaulted)
                    environment=CoreWebView2Environment.CreateAsync(null,Path.Combine(folder,"Browser"));
                var env=await environment;
                closing.Token.ThrowIfCancellationRequested();
                if (page.Browser==null || page.Browser.CoreWebView2==null)
                {
                    if(page.Browser!=null) page.Browser.Dispose();
                    var web=new WebView2 {Dock=DockStyle.Fill};
                    page.Host.Controls.Add(web);web.SendToBack();page.Browser=web;
                    var handle=web.Handle;
                    await web.EnsureCoreWebView2Async(env);
                    closing.Token.ThrowIfCancellationRequested();
                    var core=web.CoreWebView2;
                    core.Settings.AreHostObjectsAllowed=false;core.Settings.IsWebMessageEnabled=false;
                    core.NavigationStarting+=(s,e)=> {
                        Uri uri;
                        if (Uri.TryCreate(e.Uri,UriKind.Absolute,out uri) && uri.GetLeftPart(UriPartial.Authority)==page.Address?.GetLeftPart(UriPartial.Authority)) return;
                        e.Cancel=true;
                        if(e.IsUserInitiated && uri!=null && (uri.Scheme=="http"||uri.Scheme=="https"))
                            Process.Start(new ProcessStartInfo(uri.AbsoluteUri){UseShellExecute=true});
                    };
                    core.NavigationCompleted+=(s,e)=> {
                        if(closing.IsCancellationRequested) return;
                        page.Navigating=false;
                        if(!e.IsSuccess)
                        {
                            if(e.WebErrorStatus==CoreWebView2WebErrorStatus.OperationCanceled) return;
                            Fail(page,Labels[(int)section]+" could not load ("+e.WebErrorStatus+").");
                        }
                        else
                        {
                            page.Ready=true;page.Browser.Visible=true;page.Browser.BringToFront();
                            if(section==Section.Battles) OpenBattles();
                        }
                    };
                    core.ProcessFailed+=(s,e)=> {
                        if(!closing.IsCancellationRequested && (e.ProcessFailedKind==CoreWebView2ProcessFailedKind.BrowserProcessExited ||
                            e.ProcessFailedKind==CoreWebView2ProcessFailedKind.RenderProcessExited))
                        { Fail(page,"The browser view stopped. Retry to reconnect."); page.Browser.Dispose();page.Browser=null; }
                    };
                    core.ContainsFullScreenElementChanged+=(s,e)=> {if(selected==section) SetFullScreen(core.ContainsFullScreenElement);};
                }
                page.Address=address;page.Navigating=true;
                page.Browser.CoreWebView2.Navigate(address.AbsoluteUri);
            }
            catch(OperationCanceledException) when(closing.IsCancellationRequested) { }
            catch(Exception err) { if(!closing.IsCancellationRequested) Fail(page,err is WebView2RuntimeNotFoundException ?
                "Install Microsoft Edge WebView2 Runtime, then retry." : err.Message); }
            finally {page.Busy=false;}
        }

        private static void Fail(Page page,string message)
        {
            page.Ready=false;page.Navigating=false;
            if(page.Browser!=null) page.Browser.Visible=false;
            page.Status.Text=message;page.Retry.Visible=true;
        }

        private async void OpenBattles()
        {
            var page=pages[Section.Battles];
            if(!page.Ready || page.Browser?.CoreWebView2==null) return;
            try
            {
                string owner="null";
                var library=pages[Section.Library];
                if(library.Ready) owner=await library.Browser.CoreWebView2.ExecuteScriptAsync(
                    "document.getElementById('nai-media-host')?.shadowRoot?.getElementById('characterSelect')?.value || null");
                if(closing.IsCancellationRequested || !page.Ready) return;
                await page.Browser.CoreWebView2.ExecuteScriptAsync(@"(function(owner) {
                    if(window.suiteBattleOpen) return;
                    let attempts=0;
                    const timer=setInterval(function() {
                        const root=document.getElementById('nai-media-host')?.shadowRoot;
                        const select=root?.getElementById('characterSelect');
                        if(!root?.naiOpenBattles || !select || !select.options.length) {
                            if(++attempts<160) return;
                        }
                        clearInterval(timer); window.suiteBattleOpen=false;
                        if(!select || !root?.naiOpenBattles || root.querySelector('.naiBattleWrap')) return;
                        if(owner && Array.from(select.options).some(o=>o.value===owner) && select.value!==owner) {
                            select.value=owner;select.dispatchEvent(new Event('change',{bubbles:true}));
                        }
                        if(select.value) root.naiOpenBattles();
                        else if(!select.dataset.suiteBattleChoice) {
                            select.dataset.suiteBattleChoice='1'; select.focus();
                            select.addEventListener('change',function onChoose(){
                                if(!select.value) return;
                                select.removeEventListener('change',onChoose);delete select.dataset.suiteBattleChoice;
                                root.naiOpenBattles();
                            });
                        }
                    },125);
                    window.suiteBattleOpen=true;
                })("+owner+")");
            }
            catch(InvalidOperationException) { /* WebView is being closed or restarted. */ }
        }

        private void SetFullScreen(bool value)
        {
            if(value==fullScreen) return;
            fullScreen=value;
            if(value) { beforeFullScreen=WindowState;FormBorderStyle=FormBorderStyle.None;WindowState=FormWindowState.Maximized; }
            else {FormBorderStyle=FormBorderStyle.Sizable;WindowState=beforeFullScreen;}
            strip.Visible=!value;
        }

        internal WebView2 View(Section section) => pages[section].Browser;
        internal bool Loaded(Section section) => pages[section].Ready;
    }
}
