[CmdletBinding()]
param([string]$InstallRoot = (Join-Path $env:LOCALAPPDATA 'Programs\Media Suite'),
      [switch]$NoLaunch, [switch]$NoCodex, [switch]$NoShortcuts)
$ErrorActionPreference = 'Stop'
$payload = Join-Path $PSScriptRoot 'app'
$manifest = Get-Content -LiteralPath (Join-Path $PSScriptRoot 'files.json') -Raw | ConvertFrom-Json
$parent = Split-Path -Parent $InstallRoot
$null = New-Item -ItemType Directory -Path $parent -Force
$stage = Join-Path $parent ('MediaSuite-stage-' + [guid]::NewGuid().ToString('N'))
$previous = Join-Path $parent ('MediaSuite-previous-' + [guid]::NewGuid().ToString('N'))
$installed = Test-Path -LiteralPath $InstallRoot
try {
    $null = New-Item -ItemType Directory -Path $stage
    foreach ($item in $manifest.files) {
        if ($item.name -notmatch '^[a-zA-Z0-9._-]+$' -or $item.name -in @('.','..')) { throw 'Invalid installer entry.' }
        $source = Join-Path $payload $item.name
        Copy-Item -LiteralPath $source -Destination $stage
        $actual = (Get-FileHash -LiteralPath (Join-Path $stage $item.name) -Algorithm SHA256).Hash
        if ($actual -ne $item.sha256) { throw "Download verification failed for $($item.name)." }
    }
    foreach ($required in @('MediaSuite.exe','Open-MainCodex.ps1')) {
        if (!(Test-Path -LiteralPath (Join-Path $stage $required))) { throw "The package is missing $required." }
    }
    Copy-Item -LiteralPath (Join-Path $PSScriptRoot 'files.json') -Destination (Join-Path $stage 'suite-install.json')
    if ($installed) {
        $oldIndex = Join-Path $InstallRoot 'suite-install.json'
        if (!(Test-Path -LiteralPath $oldIndex)) { throw "The chosen installation folder already exists and belongs to a different installation: $InstallRoot" }
        $oldFiles = @((Get-Content -LiteralPath $oldIndex -Raw | ConvertFrom-Json).files.name) + 'suite-install.json'
        $keepPrevious = @(Get-ChildItem -LiteralPath $InstallRoot -Force | Where-Object { $_.Name -notin $oldFiles }).Count -gt 0
        $currentExe = Join-Path $InstallRoot 'MediaSuite.exe'
        $running = @(Get-Process -Name MediaSuite -ErrorAction SilentlyContinue | Where-Object { $_.Path -eq $currentExe })
        if ($running.Count) {
            $oldVersion = (Get-Content -LiteralPath $oldIndex -Raw | ConvertFrom-Json).version
            if ([version]$oldVersion -ge [version]'1.1.0') {
                $null = Start-Process -FilePath $currentExe -ArgumentList '--stop' -Wait -PassThru -WindowStyle Hidden
            } else {
                foreach ($process in $running) { $null = $process.CloseMainWindow() }
            }
            foreach ($process in $running) {
                if (!$process.WaitForExit(12000)) { throw 'Close Media Suite and run the installer again.' }
            }
        }
        if (!(Test-Path -LiteralPath (Join-Path $InstallRoot 'MediaSuite.exe'))) { throw "The install location is in use by a different folder: $InstallRoot" }
        try { [IO.Directory]::Move($InstallRoot,$previous) } catch { throw 'Close the Media Suite window and run the installer again.' }
    }
    try { [IO.Directory]::Move($stage,$InstallRoot) }
    catch { if ($installed) { [IO.Directory]::Move($previous,$InstallRoot) }; throw }
} finally { if (Test-Path -LiteralPath $stage) { Remove-Item -LiteralPath $stage -Recurse -Force } }
if (Test-Path -LiteralPath $previous) {
    if ($keepPrevious) { Write-Host "Kept the previous folder with your additional files at $previous" }
    else { Remove-Item -LiteralPath $previous -Recurse -Force }
}
$exe = Join-Path $InstallRoot 'MediaSuite.exe'
if (!$NoShortcuts) {
    $shell = New-Object -ComObject WScript.Shell
    $menu = [Environment]::GetFolderPath('Programs')
    $desktop = [Environment]::GetFolderPath('DesktopDirectory')
    foreach ($folder in @($menu,$desktop)) {
        $shortcut = $shell.CreateShortcut((Join-Path $folder 'Media Suite.lnk'))
        $shortcut.TargetPath = $exe; $shortcut.WorkingDirectory = $InstallRoot; $shortcut.IconLocation = "$exe,0"; $shortcut.Save()
    }
    $shortcut = $shell.CreateShortcut((Join-Path $menu 'Media Suite - Main Codex.lnk'))
    $shortcut.TargetPath = Join-Path $PSHOME 'powershell.exe'
    $shortcut.Arguments = '-NoProfile -ExecutionPolicy Bypass -File "' + (Join-Path $InstallRoot 'Open-MainCodex.ps1') + '"'
    $shortcut.WorkingDirectory = $InstallRoot; $shortcut.IconLocation = "$exe,0"; $shortcut.Save()
}
if (!$NoLaunch) { Start-Process -FilePath $exe -WorkingDirectory $InstallRoot }
if (!$NoCodex -and !$installed -and !(Test-Path -LiteralPath (Join-Path $env:LOCALAPPDATA 'NovelAI Media Suite\main-chat-opened'))) {
    try {
        & (Join-Path $InstallRoot 'Open-MainCodex.ps1')
        $null = New-Item -ItemType File -Path (Join-Path $env:LOCALAPPDATA 'NovelAI Media Suite\main-chat-opened') -Force
    } catch { Write-Warning "Media Suite is installed. $($_.Exception.Message)"; if (!$NoLaunch) { Read-Host 'Press Enter to finish' } }
}
