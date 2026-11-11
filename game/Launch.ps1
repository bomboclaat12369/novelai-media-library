param([switch]$Demo, [switch]$Check, [switch]$NoBrowser, [int]$Port=8877, [string]$Save='', [string]$Library='', [string]$InstallFolder=$PSScriptRoot)
$ErrorActionPreference = 'Stop'
Set-Location -LiteralPath $InstallFolder
$install = (Get-Item -LiteralPath '.').FullName
$config = @{}
$configPath = Join-Path $install 'local.json'
if (Test-Path -LiteralPath $configPath) { $config = Get-Content -LiteralPath $configPath -Raw | ConvertFrom-Json }
$candidates = @()
if ($config.python) { $candidates += $config.python }
foreach ($name in @('python.exe','python3.exe')) {
    $command = Get-Command $name -ErrorAction SilentlyContinue
    if ($command) { $candidates += $command.Source }
}
if (!$config.python -or !(Test-Path -LiteralPath $config.python)) {
    try {
        $packages = Get-AppxPackage -Name 'OpenAI.CodexPrimaryRuntime*' -ErrorAction Stop
        foreach ($package in $packages) { $candidates += Join-Path $package.InstallLocation 'dependencies\python\python.exe' }
    } catch { Write-Verbose 'App runtime discovery unavailable; checking configured and PATH runtimes.' }
}
$pythonExe = $null
foreach ($candidate in ($candidates | Select-Object -Unique)) {
    if (!(Test-Path -LiteralPath $candidate)) { continue }
    $candidate = (Get-Item -LiteralPath $candidate).FullName
    try { & $candidate -c 'import sys; assert sys.version_info >= (3,10)' 2>$null; if ($LASTEXITCODE -eq 0) { $pythonExe=$candidate;break } } catch {}
}
if (!$pythonExe) { throw 'Python 3.10+ is required. Install Python or set python in game/local.json. The Windows Store alias is not a Python installation.' }
if ($Check) {
    & $pythonExe --version
    & $pythonExe -c 'import sqlite3, json, pathlib'
    if ($LASTEXITCODE -ne 0) { throw 'Python dependency check failed.' }
    Write-Output 'SQLite and standard-library dependencies ready.'
    Write-Output 'After Hours launcher check passed. No save or library was changed.'
    exit $LASTEXITCODE
}
if (!$Library -and $config.library) { $Library=$config.library }
if (!$Demo -and !$Library) { $Library=Read-Host 'Full path to the Media Library folder or library.json' }
if ($Library -and [IO.Path]::GetFileName($Library) -eq 'library.json') { $Library=Split-Path -Parent $Library }
if (!$Demo -and !(Test-Path -LiteralPath (Join-Path $Library 'library.json'))) { throw 'The selected folder does not contain library.json.' }
if (!$Save -and $config.save) { $Save=$config.save }
if ($install -ne $PSScriptRoot -and !$env:AFTER_HOURS_DATA) {
    $env:AFTER_HOURS_DATA = Join-Path $install 'data'
}
if ($Demo) {
    $launchArgs=@((Join-Path $PSScriptRoot 'server.py'),'--port',"$Port",'--restartable')
    if ($Save) { $launchArgs+=@('--save',$Save) }
    if (!$NoBrowser) { $launchArgs+='--open' }
} else {
    $runtime = Join-Path (Split-Path -Parent $PSScriptRoot) 'runtime-src\companion-runtime.pyw'
    $launchArgs=@($runtime,'--game-only','--game-port',"$Port",'--root',$Library,'--game-restartable')
    if ($Save) { $launchArgs+=@('--game-save',$Save) }
    if (!$NoBrowser) { $launchArgs+='--open-game' }
}
Write-Output 'Keep this window open while playing. Use Restart game in the page to load local updates.'
Write-Output 'Press Ctrl+C to stop playing.'
do {
    & $pythonExe @launchArgs
    $gameExitCode=$LASTEXITCODE
    if ($gameExitCode -eq 75) {
        Write-Output 'Restarting After Hours. Your game is saved.'
        $launchArgs=@($launchArgs | Where-Object { $_ -notin @('--open','--open-game') })
    }
} while ($gameExitCode -eq 75)
exit $gameExitCode
