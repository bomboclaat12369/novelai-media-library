param([Parameter(Mandatory=$true)][string]$Archive)
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
    Add-Content -LiteralPath (Join-Path $source 'app/MediaSuite.exe') -Value 'tampered fixture'
    $caught = $false
    try { & $install -InstallRoot $dest -NoLaunch -NoCodex -NoShortcuts } catch { $caught = $true }
    if (!$caught -or (Get-FileHash -LiteralPath $exe).Hash -ne $before) { throw 'A bad upgrade affected the working install.' }
    $manifest = Get-Content -LiteralPath (Join-Path $source 'files.json') -Raw | ConvertFrom-Json
    foreach ($item in $manifest.files) {
        if ((Get-FileHash -LiteralPath (Join-Path $dest $item.name)).Hash -ne $item.sha256) { throw "Invalid installed file $($item.name)" }
    }
    if ($env:GITHUB_ACTIONS -eq 'true') {
        & powershell.exe -NoProfile -ExecutionPolicy Bypass -File (Join-Path $PSScriptRoot 'check-first-run.ps1') -Program $dest -TestRoot $root
        if ($LASTEXITCODE) { throw 'Packaged Chrome shortcut or Codex handoff check failed.' }
    }
    Write-Host 'Verified clean installation, repeated installation and failed-upgrade rollback.'
} finally { if (Test-Path $root) { Remove-Item -LiteralPath $root -Recurse -Force } }
