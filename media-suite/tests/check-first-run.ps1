param([string]$Program,[string]$TestRoot)
$ErrorActionPreference = 'Stop'
if ($env:GITHUB_ACTIONS -ne 'true') { throw 'Run this isolated desktop startup check on the disposable Windows runner.' }
$profile = Join-Path ([Environment]::GetFolderPath('LocalApplicationData')) 'NovelAI Media Suite'
if ((Test-Path -LiteralPath $profile) -or (Get-Process MediaSuite -ErrorAction SilentlyContinue)) { throw 'A clean runner profile is required.' }
$null = New-Item -ItemType Directory -Path $profile
try {
    $missing = Join-Path $TestRoot 'unconfigured'
    @{LibraryFolder=$missing; CompanionFolder=$missing; WorkbenchFolder=$missing; GameFolder=$missing} | ConvertTo-Json |
        Set-Content -LiteralPath (Join-Path $profile 'settings.json') -Encoding ascii
    Add-Type -TypeDefinition 'using System; using System.Runtime.InteropServices; public static class SuiteTestWindow { [DllImport("user32.dll")] public static extern bool ShowWindow(IntPtr h, int c); [DllImport("user32.dll")] public static extern bool IsIconic(IntPtr h); }'
    $exe = Join-Path $Program 'MediaSuite.exe'
    $first = Start-Process -FilePath $exe -PassThru
    for ($n=0; $n -lt 80; $n++) {
        Start-Sleep -Milliseconds 150; $first.Refresh()
        if ($first.HasExited) { throw 'Packaged application exited before showing its window.' }
        if ($first.MainWindowTitle -eq 'Media Suite') { break }
    }
    if ($first.MainWindowTitle -ne 'Media Suite') { throw 'Packaged window did not appear.' }
    $null = [SuiteTestWindow]::ShowWindow($first.MainWindowHandle,6)
    $second = Start-Process -FilePath $exe -PassThru
    if (!$second.WaitForExit(10000)) { throw 'Second launch opened another instance.' }
    for ($n=0; $n -lt 40 -and [SuiteTestWindow]::IsIconic($first.MainWindowHandle); $n++) { Start-Sleep -Milliseconds 150 }
    if ([SuiteTestWindow]::IsIconic($first.MainWindowHandle)) { throw 'Second launch did not restore the first window.' }
} finally {
    if ($first -and !$first.HasExited) { $null = $first.CloseMainWindow(); if (!$first.WaitForExit(6000)) { $first.Kill() } }
    Remove-Item -LiteralPath $profile -Recurse -Force
}

# Redirect only this test's Git transport to a local fixture with a dirty game branch.
$game = Join-Path $TestRoot 'existing game checkout'
& git init -q -b main $game
& git -C $game -c user.name=QA -c user.email=qa@example.test commit -q --allow-empty -m fixture
& git -C $game switch -q -c game-build-qa
Set-Content -LiteralPath (Join-Path $game 'game-work-in-progress.txt') -Value 'keep'
$before = [string](& git -C $game status --porcelain --branch)
$oldLocal = $env:LOCALAPPDATA
try {
    $env:LOCALAPPDATA = Join-Path $TestRoot 'Codex test profile'
    $env:GIT_CONFIG_COUNT = '1'
    $env:GIT_CONFIG_KEY_0 = 'url.' + ([uri]$game).AbsoluteUri + '.insteadOf'
    $env:GIT_CONFIG_VALUE_0 = 'https://github.com/bomboclaat12369/novelai-media-library.git'
    $parent = Join-Path $TestRoot 'Codex projects'
    $workspace = & (Join-Path $Program 'Open-MainCodex.ps1') -WorkspaceParent $parent -PrepareOnly
    if ([string](& git -C $workspace branch --show-current) -ne 'main') { throw 'Main chat did not get its own main checkout.' }
    $captureFile = Join-Path $TestRoot 'opened-link.txt'
    & {
        function Start-Process([string]$FilePath) { [IO.File]::WriteAllText($captureFile,$FilePath) }
        & (Join-Path $Program 'Open-MainCodex.ps1')
    }
    Add-Type -AssemblyName System.Web
    $opened = [uri][IO.File]::ReadAllText($captureFile)
    $query = [Web.HttpUtility]::ParseQueryString($opened.Query)
    if ($opened.Scheme -ne 'codex' -or $opened.Host -ne 'threads' -or $opened.AbsolutePath -ne '/new' -or $query['path'] -ne $workspace -or $query['prompt'] -notlike '*MAIN-CODEX.md*') { throw 'Wrong main Codex thread link.' }
    $after = [string](& git -C $game status --porcelain --branch)
    if ($before -ne $after) { throw 'Game checkout was modified.' }
} finally {
    $env:LOCALAPPDATA=$oldLocal
    Remove-Item Env:GIT_CONFIG_COUNT,Env:GIT_CONFIG_KEY_0,Env:GIT_CONFIG_VALUE_0 -ErrorAction SilentlyContinue
}
Write-Host 'Verified packaged single-instance restore and a correctly scoped fresh Codex chat with the game checkout intact.'
