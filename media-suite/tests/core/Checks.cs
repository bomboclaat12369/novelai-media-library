using System;
using System.Collections.Generic;
using System.IO;
using System.Net;
using System.Net.Http;
using System.Text;
using System.Text.Json;
using System.Threading;
using System.Threading.Tasks;
using NovelAI.MediaSuite;

internal static class Checks
{
    private static int count;
    private static void Check(bool value,string reason) { if (!value) throw new Exception(reason); count++; }
    private sealed class Mock : HttpMessageHandler
    {
        internal string Root;
        internal bool Library, Workbench, Game, Forged;
        protected override Task<HttpResponseMessage> SendAsync(HttpRequestMessage req,CancellationToken ct)
        {
            var uri=req.RequestUri;
            string text=null;
            if (uri.AbsolutePath=="/api/health" && Library)
                text=Forged?"<html>Unknown service</html>":JsonSerializer.Serialize(new {standalone_library=true,library_root=Root});
            if(uri.AbsolutePath=="/organizer" && Workbench) text="<html data-local-duplicate-review=\"1\">";
            if(uri.AbsolutePath=="/game/" && Game) text="<title>After Hours · Club</title>";
            return Task.FromResult(new HttpResponseMessage(text==null?HttpStatusCode.NotFound:HttpStatusCode.OK)
                {Content=new StringContent(text??"",Encoding.UTF8)});
        }
    }

    private static async Task Main()
    {
        var root=Path.Combine(Path.GetTempPath(),"Suite checks "+Guid.NewGuid().ToString("N"));
        Directory.CreateDirectory(root);
        try
        {
            var settings=new Preferences{CompanionFolder=Path.Combine(root,"Library program"),WorkbenchFolder=Path.Combine(root,"Workbench"),
                LibraryFolder=Path.Combine(root,"Real media"),GameFolder=Path.Combine(root,"Game checkout","game"),LastSection="AfterHours"};
            foreach(var dir in new[]{settings.CompanionFolder,settings.WorkbenchFolder,settings.LibraryFolder,settings.GameFolder}) Directory.CreateDirectory(dir);
            foreach(var item in new[]{(settings.CompanionFolder,"companion.pyw"),(settings.CompanionFolder,".venv/Scripts/python.exe"),
                (settings.WorkbenchFolder,"app.py"),(settings.WorkbenchFolder,"organizer.py"),(settings.WorkbenchFolder,".venv/Scripts/python.exe"),
                (settings.LibraryFolder,"library.json"),(settings.GameFolder,"Launch.ps1"),(settings.GameFolder,"server.py"),
                (settings.GameFolder,"../runtime-src/companion-runtime.pyw")})
            { var file=Path.Combine(item.Item1,item.Item2); Directory.CreateDirectory(Path.GetDirectoryName(file)); File.WriteAllText(file,""); }
            settings.Save(root);settings.Save(root);
            Check(Preferences.Load<Preferences>(Path.Combine(root,"settings.json")).LastSection=="AfterHours","Restore last tab");
            var other=Path.Combine(root,"Other library"); Directory.CreateDirectory(other);File.WriteAllText(Path.Combine(other,"library.json"),"{}");
            Check(Installations.ChooseUnique(new[]{settings.LibraryFolder,other},Installations.Library)==null,"Never guess between libraries");
            Check(Installations.ChooseUnique(new[]{settings.LibraryFolder,settings.LibraryFolder},Installations.Library)==settings.LibraryFolder,"Deduplicate paths");
            foreach(var url in new[]{"https://example.com/organizer","http://127.0.0.1.evil.com/organizer","file:///organizer","http://user@127.0.0.1/organizer","http://127.0.0.1:4321/organizer?token=bad","http://127.0.0.1:4321/game/"})
                Check(Services.WorkbenchAddress(url)==null,"Untrusted or stale address: "+url);
            Check(Services.Quote("a b")=="\"a b\"","Quoted path with spaces");
            Check(Services.Quote("x\\")=="\"x\\\\\"","Trailing slash quoting");
            var mock=new Mock{Root=settings.LibraryFolder};
            var launches=new List<System.Diagnostics.ProcessStartInfo>();
            var api=new Services(settings,root,mock,info=>{
                lock(launches) launches.Add(info);
                if(info.Arguments.Contains("companion.pyw")) mock.Library=true;
                else if(info.Arguments.Contains("app.py"))
                {mock.Workbench=true;File.WriteAllText(Path.Combine(root,"running-url.txt"),"http://127.0.0.1:49491/organizer");}
                else if(info.Arguments.Contains("Launch.ps1")) mock.Game=true;
            },TimeSpan.FromSeconds(2));
            var ct=CancellationToken.None;
            var results=await Task.WhenAll(api.Open(Section.Workbench,ct),api.Open(Section.Library,ct),api.Open(Section.Battles,ct));
            Check(launches.Count==2 && launches[0].Arguments.Contains("--headless") && launches[1].Arguments.Contains("--no-browser"),"Concurrent cold starts must use one companion");
            Check(results[0].Port==49491 && results[1]==results[2],"Attach to actual Workbench address");
            File.WriteAllText(Path.Combine(root,"running-url.txt"),"http://127.0.0.1:49492/organizer");
            Check((await api.Open(Section.Workbench,ct)).Port==49492 && launches.Count==2,"Reattach after a Workbench update");
            File.WriteAllText(Path.Combine(settings.GameFolder,"local.json"),JsonSerializer.Serialize(new {library=Path.Combine(other,"library.json"),save="existing.sqlite3"}));
            await api.Open(Section.AfterHours,ct);await api.Open(Section.AfterHours,ct);
            Check(launches.Count==3 && launches[2].Arguments.Contains("-NoBrowser") && launches[2].Arguments.Contains(other) && !launches[2].Arguments.Contains("-Save"),"Game owns its configured existing save");
            Check(api.ActiveLibrary==settings.LibraryFolder,"Remember a verified companion");
            mock.Root=other; bool refused=false;
            try{await api.Library(ct);}catch(InvalidOperationException){refused=true;}
            Check(refused && launches.Count==3,"Do not start a second companion or attach to wrong inventory");
            mock.Forged=true;settings.LibraryFolder=Path.Combine(root,"absent");
            refused=false;try{await api.Library(ct);}catch(InvalidOperationException){refused=true;}
            Check(refused && !Directory.Exists(settings.LibraryFolder),"Foreign service cannot create/reset a library");
            Console.WriteLine(count+" service and settings checks passed.");
        }
        finally { Directory.Delete(root,true); }
    }
}
