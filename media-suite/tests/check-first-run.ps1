param([string]$Program,[string]$TestRoot,[string]$OlderLauncher,[string]$StagedUpdate)
$ErrorActionPreference = 'Stop'
if ($env:GITHUB_ACTIONS -ne 'true') { throw 'Run this isolated desktop startup check on the disposable Windows runner.' }
$profile = Join-Path ([Environment]::GetFolderPath('LocalApplicationData')) 'NovelAI Media Suite'
if ((Test-Path -LiteralPath $profile) -or (Get-Process MediaSuite -ErrorAction SilentlyContinue)) { throw 'A clean runner profile is required.' }
$null = New-Item -ItemType Directory -Path $profile
try {
    $missing = Join-Path $TestRoot 'unconfigured'
    @{LibraryFolder=$missing; CompanionFolder=$missing; WorkbenchFolder=$missing; GameFolder=$missing} | ConvertTo-Json |
        Set-Content -LiteralPath (Join-Path $profile 'settings.json') -Encoding ascii
    Add-Type -AssemblyName UIAutomationClient,UIAutomationTypes
    Add-Type -TypeDefinition 'using System; using System.Runtime.InteropServices; public static class SuiteTestWindow { [DllImport("user32.dll")] public static extern bool ShowWindow(IntPtr h, int c); [DllImport("user32.dll")] public static extern bool IsIconic(IntPtr h); [DllImport("user32.dll")] public static extern IntPtr GetForegroundWindow(); }'
    function Get-SuiteTabs($window) {
        $element = [Windows.Automation.AutomationElement]::FromHandle($window)
        $condition = New-Object Windows.Automation.PropertyCondition(
            [Windows.Automation.AutomationElement]::ControlTypeProperty, [Windows.Automation.ControlType]::TabItem)
        $element.FindAll([Windows.Automation.TreeScope]::Descendants,$condition) | Where-Object { $_.Current.Name -like 'Media Suite*' }
    }
    $exe = Join-Path $Program 'MediaSuite.exe'
    $first = Start-Process -FilePath $exe -PassThru
    for ($n=0; $n -lt 200; $n++) {
        Start-Sleep -Milliseconds 250
        if ($first.HasExited) { throw 'Packaged launcher exited before opening Edge.' }
        $edge = Get-Process msedge -ErrorAction SilentlyContinue | Where-Object MainWindowTitle -like 'Media Suite*' | Select-Object -First 1
        if ($edge -and @(Get-SuiteTabs $edge.MainWindowHandle).Count -eq 1) { break }
    }
    if (!$edge -or @(Get-SuiteTabs $edge.MainWindowHandle).Count -ne 1) { throw 'Packaged launcher did not show one Media Suite tab in Edge.' }
    $window = $edge.MainWindowHandle
    Start-Process -FilePath $edge.Path -ArgumentList 'about:blank'
    for ($n=0; $n -lt 40 -and $edge.MainWindowTitle -like 'Media Suite*'; $n++) { Start-Sleep -Milliseconds 150; $edge.Refresh() }
    $null = [SuiteTestWindow]::ShowWindow($window,6)
    $second = Start-Process -FilePath $exe -PassThru
    if (!$second.WaitForExit(10000)) { throw 'Second launch opened another instance.' }
    for ($n=0; $n -lt 100; $n++) {
        Start-Sleep -Milliseconds 200; $edge.Refresh()
        if (![SuiteTestWindow]::IsIconic($window) -and $edge.MainWindowTitle -like 'Media Suite*') { break }
    }
    if ([SuiteTestWindow]::IsIconic($window) -or $edge.MainWindowTitle -notlike 'Media Suite*' -or @(Get-SuiteTabs $window).Count -ne 1) {
        throw 'Second launch did not restore the original Edge tab.'
    }
    $marker = Join-Path $TestRoot 'edge-window.html'
    Set-Content -LiteralPath $marker -Value '<title>Suite second profile</title>' -Encoding ascii
    $otherProfile = Join-Path $env:RUNNER_TEMP 'Media Suite second Edge profile'
    Start-Process -FilePath $edge.Path -ArgumentList ('--no-first-run --no-default-browser-check --user-data-dir="' + $otherProfile + '" "' + ([uri]$marker).AbsoluteUri + '"')
    for ($n=0; $n -lt 150; $n++) {
        Start-Sleep -Milliseconds 200
        $other = Get-Process msedge -ErrorAction SilentlyContinue | Where-Object MainWindowTitle -like 'Suite second profile*' | Select-Object -First 1
        if ($other -and [SuiteTestWindow]::GetForegroundWindow() -eq $other.MainWindowHandle) { break }
    }
    if (!$other -or [SuiteTestWindow]::GetForegroundWindow() -ne $other.MainWindowHandle) { throw 'The second Edge profile did not become active.' }
    $otherWindow = $other.MainWindowHandle
    for ($attempt=0; $attempt -lt 2; $attempt++) {
        Start-Process -FilePath $exe -Wait
        for ($n=0; $n -lt 80; $n++) {
            Start-Sleep -Milliseconds 150; $other.Refresh()
            if ($other.MainWindowTitle -like 'Media Suite*' -and @(Get-SuiteTabs $otherWindow).Count -eq 1) { break }
        }
        if ($other.MainWindowTitle -notlike 'Media Suite*' -or [SuiteTestWindow]::GetForegroundWindow() -ne $otherWindow -or
            @(Get-SuiteTabs $otherWindow).Count -ne 1 -or @(Get-SuiteTabs $window).Count -ne 1) { throw 'The shortcut did not use the previously active Edge window and profile.' }
    }
    Write-Host 'Verified opening and reusing one tab in the active Edge profile while another profile holds its own suite tab.'
    Start-Process -FilePath $exe -ArgumentList '--stop' -Wait
    if (!$first.WaitForExit(12000)) { throw 'Test host did not stop.' }
    $updateDir = Join-Path $profile 'updates'
    Copy-Item -LiteralPath (Join-Path $StagedUpdate 'updates/versions') -Destination $updateDir -Recurse
    Copy-Item -LiteralPath (Join-Path $StagedUpdate 'updates/active.json') -Destination $updateDir
    $v = (Get-Content -Raw -LiteralPath (Join-Path $updateDir 'active.json') | ConvertFrom-Json).version
    $expected = [IO.Path]::GetFullPath((Join-Path $updateDir "versions/$v/MediaSuite.exe"))
    $bootstrap = Start-Process -FilePath $OlderLauncher -PassThru
    if (!$bootstrap.WaitForExit(20000) -or $bootstrap.ExitCode -ne 0) { throw 'Older shortcut did not hand off to its verified update.' }
    for ($n=0; $n -lt 80; $n++) {
        $first = Get-Process MediaSuite -ErrorAction SilentlyContinue | Where-Object Path -eq $expected | Select-Object -First 1
        if ($first) { break }; Start-Sleep -Milliseconds 200
    }
    if (!$first) { throw 'The original shortcut did not run the updated executable.' }
    $port = (Get-Content -Raw -LiteralPath (Join-Path $profile 'chrome-ports.json') | ConvertFrom-Json)[0]
    for ($n=0; $n -lt 80; $n++) {
        try { $session = Invoke-RestMethod -UseBasicParsing -Uri "http://127.0.0.1:$port/api/session" -Headers @{'X-Suite-Request'='session'} -TimeoutSec 2; if ($session.version -eq $v) { break } } catch {}
        Start-Sleep -Milliseconds 150
    }
    if ($session.version -ne $v) { throw 'The verified replacement did not serve its own version.' }
    Write-Host 'Verified the original launcher starts the staged release without another installer.'
} catch {
    foreach ($proc in (Get-Process msedge,MediaSuite -ErrorAction SilentlyContinue | Where-Object MainWindowHandle -ne 0)) {
        Write-Host "Fixture window: $($proc.ProcessName) $($proc.MainWindowTitle)"
        $ui = [Windows.Automation.AutomationElement]::FromHandle($proc.MainWindowHandle)
        $type = if ($proc.ProcessName -eq 'MediaSuite') { [Windows.Automation.ControlType]::Text } else { [Windows.Automation.ControlType]::Edit }
        $filter = New-Object Windows.Automation.PropertyCondition([Windows.Automation.AutomationElement]::ControlTypeProperty,$type)
        $ui.FindAll([Windows.Automation.TreeScope]::Descendants,$filter) | Select-Object -First 6 | ForEach-Object { Write-Host "  $($_.Current.Name) $($_.Current.ClassName) $($_.Current.AutomationId)" }
    }
    throw
} finally {
    if ($first -and !$first.HasExited) { Start-Process $exe -ArgumentList '--stop' -Wait; if (!$first.WaitForExit(10000)) { $first.Kill() } }
    if ($other -and !$other.HasExited) { $null = $other.CloseMainWindow() }
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
