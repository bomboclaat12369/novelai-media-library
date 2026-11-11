using System;
using System.Collections.Generic;
using System.Diagnostics;
using System.IO;
using System.Net.Sockets;
using System.Threading.Tasks;
using System.Windows.Forms;
using NovelAI.MediaSuite;

internal static class Smoke
{
    private static async Task Until(Func<Task<bool>> check,string description)
    {
        var timer=Stopwatch.StartNew();
        while(timer.Elapsed<TimeSpan.FromSeconds(120))
        {
            if(await check()) {Console.WriteLine("Passed: "+description);return;}
            await Task.Delay(200);
        }
        throw new TimeoutException(description);
    }

    [STAThread]
    private static int Main(string[] args)
    {
        if(args.Length!=2) return 2;
        string root=Path.GetFullPath(args[0]), code=File.ReadAllText(args[1]);
        var settings=Preferences.Load<Preferences>(Path.Combine(root,"suite-qa.json"));
        if(!Directory.Exists(settings.LibraryFolder) || !File.Exists(Path.Combine(root,"Original game save.sqlite3"))) return 2;
        foreach(int port in new[]{8765,8877})
        {
            using(var tcp=new TcpClient())
                try {tcp.Connect("127.0.0.1",port);throw new Exception("Smoke test requires an unused port "+port);}
                catch(SocketException){}
        }
        var state=Path.Combine(root,"Workbench data","state");
        var processes=new List<Process>();
        var services=new Services(settings,state,start:info=>{
            if(info.Arguments.Contains("app.py")) info.Arguments+=" --state-dir "+Services.Quote(state);
            info.RedirectStandardError=true;
            var process=Process.Start(info);
            process.ErrorDataReceived+=(s,e)=>{if(e.Data!=null) Console.Error.WriteLine(e.Data);}; process.BeginErrorReadLine();
            lock(processes) processes.Add(process);
        });
        NovelAI.MediaSuite.Program.PrepareBrowserLoader();
        Application.EnableVisualStyles();Application.SetCompatibleTextRenderingDefault(false);
        int result=0;
        using(var form=new SuiteWindow(settings,Path.Combine(root,"Suite profile"),services))
        {
            async Task<string> JS(Section section,string js) => await form.View(section).CoreWebView2.ExecuteScriptAsync(js);
            async Task Page(Section section,string ready)
            {
                form.SelectPage(section);
                try { await Until(async ()=>form.Loaded(section)&&await JS(section,ready)=="true","render "+section); }
                catch (TimeoutException)
                {
                    if(form.View(section)?.CoreWebView2!=null) Console.Error.WriteLine(await JS(section,
                        "(document.getElementById('nai-media-host')?.shadowRoot?.getElementById('app')?.innerText || document.body.innerText).slice(0,400)"));
                    if(section==Section.Workbench && form.View(section)?.CoreWebView2!=null) Console.Error.WriteLine(await JS(section,
                        "({title:document.getElementById('title')?.textContent,position:document.getElementById('position')?.textContent,"+
                        "active:document.querySelector('#postList .post.active')?.innerText,cards:document.querySelectorAll('#grid .card').length})"));
                    throw;
                }
            }
            form.Shown+=async(s,e)=>{
                try
                {
                    await Page(Section.Library,"!!document.getElementById('nai-media-host')?.shadowRoot?.getElementById('characterSelect')?.options.length");
                    await JS(Section.Library,@"(function(){const select=document.getElementById('nai-media-host').shadowRoot.getElementById('characterSelect');select.value=Array.from(select.options).find(o=>o.textContent.includes('Patricia')).value;select.dispatchEvent(new Event('change',{bubbles:true}));})()");
                    await Page(Section.Workbench,
                        "!!document.getElementById('position')?.textContent && " +
                        "Array.from(document.querySelectorAll('#postList .post')).some(e=>e.textContent.includes('Post 2'))");
                    await JS(Section.Workbench,"Array.from(document.querySelectorAll('#postList .post')).find(e=>e.textContent.includes('Post 2')).click()");
                    await Until(async()=>await JS(Section.Workbench,"document.getElementById('title').textContent.includes('Post 2')")=="true","open the second post");
                    var id=File.ReadAllText(Path.Combine(root,"import-id.txt")).Trim();
                    if(await JS(Section.Workbench,"Array.from(document.querySelectorAll('#grid .card')).some(card=>card.dataset.id==='"+id+"')")!="true")
                        throw new Exception("The image to import is missing from the open post.");
                    await JS(Section.Workbench,"window.suiteImportGate=new Promise(r=>window.suiteResumeImport=r);window.suiteFinished=false;window.suiteMark='same-document';("+code+")('"+id+"').then(()=>window.suiteFinished=true).catch(e=>window.suiteFinished=e.message);");
                    await Until(async()=>await JS(Section.Workbench,"window.suiteImportStarted===true")=="true","stage import on current post");
                    await Page(Section.Battles,"!!document.getElementById('nai-media-host')?.shadowRoot?.querySelector('.naiBattleWrap')");
                    await Page(Section.AfterHours,"!!document.getElementById('nai-media-host')?.shadowRoot?.getElementById('app')?.innerText.includes('Suite QA Patricia')");
                    await JS(Section.AfterHours,"fetch('/game/api/state').then(r=>r.json()).then(x=>window.verifiedSeed=x.state.seed)");
                    await Until(async()=>await JS(Section.AfterHours,"window.verifiedSeed===123456")=="true","open original saved career");
                    await JS(Section.Workbench,"window.suiteResumeImport()");
                    await Until(async()=>{var v=await JS(Section.Workbench,"window.suiteFinished"); if(v.StartsWith("\""))throw new Exception(v);return v=="true";},"finish import while After Hours is visible");
                    await Page(Section.Workbench,"window.suiteMark==='same-document' && document.getElementById('title').textContent.includes('Post 2')");
                    var restored=Preferences.Load<Preferences>(Path.Combine(root,"Suite profile","settings.json"));
                    if(restored.LastSection!="Workbench" || processes.Count!=3) throw new Exception("Duplicate service or wrong last tab");
                    Console.WriteLine("Passed: three cold starts, persistent tabs and saved selection.");
                }
                catch(Exception err){Console.Error.WriteLine(err); result=1;}
                finally {form.Close();}
            };
            Application.Run(form);
        }
        foreach(var p in processes) {try {if(!p.HasExited) Process.Start(new ProcessStartInfo("taskkill.exe","/PID "+p.Id+" /T /F"){UseShellExecute=false,CreateNoWindow=true}).WaitForExit(8000);}catch(InvalidOperationException){}p.Dispose();}
        return result;
    }
}
