param([Parameter(Mandatory=$true)][string]$Archive,[string]$OlderLauncher,[string]$StagedUpdate)
$ErrorActionPreference='Stop'
$root = Join-Path ([IO.Path]::GetTempPath()) ('Suite install test ' + [guid]::NewGuid().ToString('N'))
$source = Join-Path $root 'package'
$dest = Join-Path $root 'program'
try {
    Expand-Archive -LiteralPath $Archive -DestinationPath $source
    $install = Join-Path $source 'Install.ps1'
    & $install -InstallRoot $dest -NoLaunch -NoCodex -NoShortcuts
    & $install -InstallRoot $dest -NoLaunch -NoCodex -NoShortcuts
    $exe = Join-Path $dest 'MediaSuite.exe'
    $before = (Get-FileHash -LiteralPath $exe).Hash
    if ($env:GITHUB_ACTIONS -eq 'true') {
        $indexFile = Join-Path $dest 'suite-install.json'
        $legacy = Get-Content -Raw -LiteralPath $indexFile | ConvertFrom-Json
        $legacy.version = '1.1.1'
        $legacy | ConvertTo-Json -Depth 5 | Set-Content -LiteralPath $indexFile
        & $install -InstallRoot $dest -OnNextLaunch -NoLaunch -NoCodex
        $dir = @(Get-ChildItem -LiteralPath (Join-Path $root 'MediaSuite-queued') -Directory)
        if ($dir.Count -ne 1) { throw 'Expected one queued installation.' }
        $pending = Join-Path $dir[0].FullName 'Install.ps1'
        $shortcut = Join-Path ([Environment]::GetFolderPath('DesktopDirectory')) 'Media Suite.lnk'
        $shell = New-Object -ComObject WScript.Shell
        if (!$shell.CreateShortcut($shortcut).Arguments.Contains($pending) -or (Get-Content -Raw -LiteralPath $indexFile | ConvertFrom-Json).version -ne '1.1.1') { throw 'Queuing changed the live install or missed the shortcut.' }
        & $pending -InstallRoot $dest -Queued -NoLaunch -NoCodex
        $link = $shell.CreateShortcut($shortcut)
        if ($link.TargetPath -ne $exe -or $link.Arguments -or (Get-Content -Raw -LiteralPath $indexFile | ConvertFrom-Json).version -eq '1.1.1') { throw 'Queued upgrade did not restore the ordinary shortcut.' }
        Write-Host 'Verified a legacy install can queue a one-time upgrade without opening or stopping the suite.'
    }
    Add-Content -LiteralPath (Join-Path $source 'app/MediaSuite.exe') -Value 'tampered fixture'
    $caught = $false
    try { & $install -InstallRoot $dest -NoLaunch -NoCodex -NoShortcuts } catch { $caught = $true }
    if (!$caught -or (Get-FileHash -LiteralPath $exe).Hash -ne $before) { throw 'A bad upgrade affected the working install.' }
    $manifest = Get-Content -LiteralPath (Join-Path $source 'files.json') -Raw | ConvertFrom-Json
    foreach ($item in $manifest.files) {
        if ((Get-FileHash -LiteralPath (Join-Path $dest $item.name)).Hash -ne $item.sha256) { throw "Invalid installed file $($item.name)" }
    }
    if ($env:GITHUB_ACTIONS -eq 'true') {
        & powershell.exe -NoProfile -ExecutionPolicy Bypass -File (Join-Path $PSScriptRoot 'check-first-run.ps1') -Program $dest -TestRoot $root -OlderLauncher $OlderLauncher -StagedUpdate $StagedUpdate
        if ($LASTEXITCODE) { throw 'Packaged Edge shortcut or update handoff check failed.' }
    }
    Write-Host 'Verified clean installation, repeated installation and failed-upgrade rollback.'
} finally { if (Test-Path $root) { Remove-Item -LiteralPath $root -Recurse -Force } }
