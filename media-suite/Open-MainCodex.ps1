[CmdletBinding()]
param([string]$WorkspaceParent, [switch]$PrepareOnly)
$ErrorActionPreference = 'Stop'
$stateDir = Join-Path $env:LOCALAPPDATA 'NovelAI Media Suite'
$record = Join-Path $stateDir 'main-workspace.txt'
$remote = 'https://github.com/bomboclaat12369/novelai-media-library.git'
$prompt = 'This is my main Media Suite Codex thread for the Windows suite, Media Library, Battles, and Workbench. Read AGENTS.md, media-suite/MAIN-CODEX.md, and docs/PROJECT-MAP.md. Identify my existing installed programs, fill in any missing suite locations, and verify the connections on my PC. Continue using my separate After Hours thread for game development.'

function Test-MainWorkspace($Folder) {
    if (!(Test-Path -LiteralPath (Join-Path $Folder '.git'))) { return $false }
    $url = [string](& git -C $Folder config --get remote.origin.url 2>$null)
    if ($LASTEXITCODE -ne 0 -or $url.Trim() -notmatch '^(https://github\.com/|git@github\.com:)bomboclaat12369/novelai-media-library(?:\.git)?/?$') { return $false }
    $branch = [string](& git -C $Folder branch --show-current)
    return ($LASTEXITCODE -eq 0 -and $branch -and $branch -notlike 'game-*' -and !(Test-Path -LiteralPath (Join-Path $Folder 'game/Launch.ps1')))
}

if (!(Get-Command git -ErrorAction SilentlyContinue)) { throw 'Git for Windows is required to prepare the main Codex project. Install Git, then use Media Suite - Main Codex in Start.' }
if (!$WorkspaceParent -and (Test-Path -LiteralPath $record)) {
    $saved = (Get-Content -LiteralPath $record -Raw).Trim()
    if ($saved -and (Test-MainWorkspace $saved)) { $workspace = $saved }
}
if (!$workspace) {
    if (!$WorkspaceParent) {
        $WorkspaceParent = if (Test-Path -LiteralPath 'C:\Codex') { 'C:\Codex' } else { Join-Path $env:USERPROFILE 'Codex' }
    }
    $null = New-Item -ItemType Directory -Path $WorkspaceParent -Force
    foreach ($name in @('Media-Suite','Media-Suite-Main')) {
        $candidate = Join-Path $WorkspaceParent $name
        if (!(Test-Path -LiteralPath $candidate)) {
            & git clone --filter=blob:none --single-branch --branch main --no-tags $remote $candidate
            if ($LASTEXITCODE -ne 0) { throw 'The main project download failed. Reopen Media Suite - Main Codex from Start to retry.' }
        }
        if (Test-MainWorkspace $candidate) { $workspace = $candidate; break }
    }
}
if (!$workspace) { throw 'Both proposed main project folders are already in use. Run Open-MainCodex.ps1 -WorkspaceParent with an available parent folder.' }
$workspace = (Resolve-Path -LiteralPath $workspace).Path
$null = New-Item -ItemType Directory -Path $stateDir -Force
[IO.File]::WriteAllText($record,$workspace)
if ($PrepareOnly) { Write-Output $workspace; return }
$link = 'codex://threads/new?path=' + [uri]::EscapeDataString($workspace) + '&prompt=' + [uri]::EscapeDataString($prompt)
try { Start-Process $link -ErrorAction Stop }
catch {
    Set-Clipboard -Value $prompt
    throw "Open a new local Codex chat in $workspace and paste the starter message from your clipboard."
}
