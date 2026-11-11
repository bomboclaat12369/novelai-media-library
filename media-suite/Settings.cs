using System;
using System.Collections.Generic;
using System.IO;
using System.Linq;
using System.Runtime.Serialization;
using System.Runtime.Serialization.Json;

namespace NovelAI.MediaSuite
{
    [DataContract]
    internal sealed class Preferences
    {
        [DataMember] public string LibraryFolder;
        [DataMember] public string CompanionFolder;
        [DataMember] public string WorkbenchFolder;
        [DataMember] public string GameFolder;
        [DataMember] public string LastSection;
        [DataMember] public bool Maximized;

        internal static T Read<T>(Stream stream)
        {
            return (T)new DataContractJsonSerializer(typeof(T)).ReadObject(stream);
        }

        internal static T Load<T>(string path) where T : new()
        {
            try { using (var file = File.OpenRead(path)) return Read<T>(file); }
            catch (FileNotFoundException) { return new T(); }
            catch (DirectoryNotFoundException) { return new T(); }
        }

        internal void Save(string folder)
        {
            Directory.CreateDirectory(folder);
            var path = Path.Combine(folder, "settings.json");
            var temp = path + ".new";
            using (var file = new FileStream(temp, FileMode.Create, FileAccess.Write, FileShare.None))
            {
                new DataContractJsonSerializer(typeof(Preferences)).WriteObject(file, this);
                file.Flush(true);
            }
            if (File.Exists(path)) File.Replace(temp, path, null);
            else File.Move(temp, path);
        }
    }

    [DataContract]
    internal sealed class GameConfig
    {
        [DataMember(Name="library")] public string Library { get; set; }
    }

    internal static class Installations
    {
        internal static string Python(string root) => Path.Combine(root, ".venv", "Scripts", "python.exe");
        internal static bool Library(string root) => Has(root, "library.json");
        internal static bool Companion(string root) => Has(root, "companion.pyw") && File.Exists(Python(root));
        internal static bool Workbench(string root) => Has(root, "app.py") && Has(root, "organizer.py") && File.Exists(Python(root));
        internal static bool Game(string root) => Has(root, "Launch.ps1") && Has(root, "server.py") &&
            File.Exists(Path.Combine(root, "..", "runtime-src", "companion-runtime.pyw"));

        private static bool Has(string root, string name) =>
            !string.IsNullOrWhiteSpace(root) && File.Exists(Path.Combine(root, name));

        internal static string LibraryDirectory(string value)
        {
            if (string.IsNullOrWhiteSpace(value)) return null;
            return string.Equals(Path.GetFileName(value), "library.json", StringComparison.OrdinalIgnoreCase)
                ? (string.IsNullOrEmpty(Path.GetDirectoryName(value)) ? "." : Path.GetDirectoryName(value)) : value;
        }

        internal static string GameLibrary(string folder,string value)
        {
            var directory=LibraryDirectory(value);
            if(string.IsNullOrWhiteSpace(directory)) return null;
            return Path.GetFullPath(Path.Combine(folder,directory));
        }

        internal static string InFolder(string root, Func<string, bool> valid, params string[] relatives)
        {
            if (string.IsNullOrEmpty(root)) return null;
            return relatives.Select(sub => Path.GetFullPath(Path.Combine(root, sub))).FirstOrDefault(valid);
        }

        internal static string ChooseUnique(IEnumerable<string> candidates, Func<string,bool> valid)
        {
            var found = candidates.Where(valid).Select(Path.GetFullPath)
                .Distinct(StringComparer.OrdinalIgnoreCase).Take(2).ToArray();
            return found.Length == 1 ? found[0] : null;
        }

        // Check likely program folders only. Large photo collections never need indexing for launch.
        private static IEnumerable<string> ProgramFolders(IEnumerable<string> parents)
        {
            foreach (var parent in parents.Where(Directory.Exists).Distinct(StringComparer.OrdinalIgnoreCase))
            {
                yield return parent;
                string[] dirs;
                try { dirs = Directory.GetDirectories(parent); }
                catch (UnauthorizedAccessException) { continue; }
                catch (IOException) { continue; }
                foreach (var dir in dirs)
                {
                    var name = Path.GetFileName(dir).ToLowerInvariant();
                    if (new[] { "media", "novelai", "duplicate", "workbench", "after-hours", "companion" }.Any(name.Contains))
                        yield return dir;
                }
            }
        }

        internal static void Discover(Preferences settings)
        {
            var user = Environment.GetFolderPath(Environment.SpecialFolder.UserProfile);
            var docs = Environment.GetFolderPath(Environment.SpecialFolder.MyDocuments);
            var known = new[] { AppDomain.CurrentDomain.BaseDirectory,
                Environment.GetFolderPath(Environment.SpecialFolder.DesktopDirectory), docs,
                Path.Combine(user,"Downloads"), Path.Combine(user,"Codex"), @"C:\Codex" };
            var roots = ProgramFolders(known).ToArray();
            if (string.IsNullOrEmpty(settings.GameFolder))
                settings.GameFolder = ChooseUnique(roots.Select(p=>InFolder(p,Game,"","game",Path.Combine("project","game"))),Game);
            if (string.IsNullOrEmpty(settings.CompanionFolder))
                settings.CompanionFolder = ChooseUnique(roots.Select(p=>InFolder(p,Companion,"","novelai-media-library-main")),Companion);
            if (string.IsNullOrEmpty(settings.WorkbenchFolder))
                settings.WorkbenchFolder = ChooseUnique(roots.Select(p=>InFolder(p,Workbench,"","duplicate-review",
                    Path.Combine("novelai-media-library-main","duplicate-review"))),Workbench);
            if (string.IsNullOrEmpty(settings.LibraryFolder))
            {
                var sources = new List<string> { Path.Combine(docs,"NovelAI Media Library"), Path.Combine(user,"NovelAI Media Library") };
                if (Game(settings.GameFolder))
                {
                    try { sources.Add(GameLibrary(settings.GameFolder,Preferences.Load<GameConfig>(Path.Combine(settings.GameFolder,"local.json")).Library)); }
                    catch (IOException) { } catch (SerializationException) { }
                }
                settings.LibraryFolder = ChooseUnique(sources,Library);
            }
        }
    }
}
