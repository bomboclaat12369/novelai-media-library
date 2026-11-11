"""Assemble a Windows installation ZIP and its externally verifiable manifest."""
import argparse
import hashlib
import json
from pathlib import Path
from zipfile import ZipFile, ZipInfo, ZIP_DEFLATED
from xml.etree.ElementTree import parse

ROOT = Path(__file__).resolve().parent

def sha(data):
    return hashlib.sha256(data).hexdigest()

def package(build, output):
    version = parse(ROOT / "MediaSuite.csproj").findtext(".//Version")
    names = ["MediaSuite.exe", "Microsoft.Web.WebView2.Core.dll", "Microsoft.Web.WebView2.WinForms.dll",
             "WebView2-LICENSE.txt", "WebView2-NOTICE.txt"]
    files = {name: (build / name).read_bytes() for name in names}
    loader = next((path for path in (build / "runtimes/win-x64/native/WebView2Loader.dll",
                                     build / "x64/WebView2Loader.dll", build / "WebView2Loader.dll") if path.is_file()), None)
    if loader is None:
        raise FileNotFoundError("x64 WebView2Loader.dll is missing")
    files["WebView2Loader.dll"] = loader.read_bytes()
    files["Open-MainCodex.ps1"] = (ROOT / "Open-MainCodex.ps1").read_bytes()
    config = build / "MediaSuite.exe.config"
    if config.exists():
        files[config.name] = config.read_bytes()
    output.mkdir(parents=True, exist_ok=True)
    package_path = output / f"Media-Suite-{version}.zip"
    manifest = {"version": version, "files": [{"name": n, "sha256": sha(b)} for n, b in files.items()]}
    with ZipFile(package_path, "w", ZIP_DEFLATED) as archive:
        def entry(name, data):
            info = ZipInfo(name, (2026, 1, 1, 0, 0, 0))
            info.create_system = 3
            info.external_attr = 0o100644 << 16
            archive.writestr(info, data, compress_type=ZIP_DEFLATED)
        for name, data in files.items():
            entry("app/" + name, data)
        entry("files.json", json.dumps(manifest, indent=2))
        for name in ("Install.ps1","Install Media Suite.cmd"):
            entry(name, (ROOT / name).read_text(encoding="utf-8").replace("\n", "\r\n").encode("utf-8"))
    data = package_path.read_bytes()
    digest = sha(data)
    report = {"version": version, "file": package_path.name, "bytes": len(data), "sha256": digest}
    release_tag = "media-suite-v" + version
    download = "https://github.com/bomboclaat12369/novelai-media-library/releases/download/" + release_tag + "/" + package_path.name
    # All interpolated values originate in the build. User paths stay PowerShell values.
    script = (ROOT / "download.cmd.in").read_text().replace("@DOWNLOAD@",download).replace("@SHA256@",digest)
    (output / "Install-Media-Suite.cmd").write_bytes(script.replace("\n","\r\n").encode("ascii"))
    report["installer_sha256"] = sha((output / "Install-Media-Suite.cmd").read_bytes())
    (output / "media-suite-manifest.json").write_text(json.dumps(report,indent=2)+"\n",encoding="utf-8")
    print(json.dumps(report))

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--build", type=Path, default=ROOT / "bin/Release/net48")
    parser.add_argument("--out", type=Path, default=ROOT / "artifacts")
    args = parser.parse_args()
    package(args.build, args.out)
