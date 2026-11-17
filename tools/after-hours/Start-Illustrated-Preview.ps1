param([switch]$NoBrowser)
$ErrorActionPreference = 'Stop'
$reviewRoot = [IO.Path]::GetFullPath((Join-Path $PSScriptRoot '..\..'))
$pythonCandidates = @()
foreach ($package in (Get-AppxPackage -Name 'OpenAI.CodexPrimaryRuntime*' | Sort-Object Version -Descending)) {
    $pythonCandidates += Join-Path $package.InstallLocation 'dependencies\python\python.exe'
}
foreach ($name in @('python.exe','python3.exe')) {
    $command = Get-Command $name -ErrorAction SilentlyContinue
    if ($command) { $pythonCandidates += $command.Source }
}
$reviewPython = $null
foreach ($candidate in ($pythonCandidates | Select-Object -Unique)) {
    if (!(Test-Path -LiteralPath $candidate)) { continue }
    try {
        & $candidate -c 'import sys; assert sys.version_info >= (3,10)' 2>$null
        if ($LASTEXITCODE -eq 0) { $reviewPython = $candidate; break }
    } catch { }
}
if (!$reviewPython) { throw 'Python 3.10 or newer is needed to open this local preview.' }
$reviewScript = Join-Path $PSScriptRoot 'preview_illustrated.py'
$reviewArguments = @('"' + $reviewScript + '"')
if (!$NoBrowser) { $reviewArguments += '--open' }
$reviewLogs = Join-Path $reviewRoot '.release-output\illustrated-preview'
New-Item -ItemType Directory -Path $reviewLogs -Force | Out-Null
Start-Process -FilePath $reviewPython -ArgumentList $reviewArguments -WorkingDirectory $reviewRoot -WindowStyle Hidden -RedirectStandardOutput (Join-Path $reviewLogs 'launcher.log') -RedirectStandardError (Join-Path $reviewLogs 'launcher-error.log')
