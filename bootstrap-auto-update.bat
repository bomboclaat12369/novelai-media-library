@echo off
setlocal
set "REPO_RAW=https://raw.githubusercontent.com/bomboclaat12369/novelai-media-library/main"

echo NovelAI Media Library - one-time automatic-update bootstrap
echo.
echo This installs the self-updating launcher into your EXISTING NovelAI Media Library program folder
echo and opens the self-updating Tampermonkey userscript for installation/update.
echo.

powershell -NoProfile -ExecutionPolicy Bypass -Command ^
  "Add-Type -AssemblyName System.Windows.Forms;" ^
  "$d=New-Object System.Windows.Forms.FolderBrowserDialog;" ^
  "$d.Description='Select your existing NovelAI Media Library program folder (the folder containing companion.pyw and run.bat)';" ^
  "$d.ShowNewFolderButton=$false;" ^
  "if($d.ShowDialog() -ne [System.Windows.Forms.DialogResult]::OK){exit 2};" ^
  "$dir=$d.SelectedPath;" ^
  "if(!(Test-Path (Join-Path $dir 'companion.pyw'))){[System.Windows.Forms.MessageBox]::Show('That folder does not contain companion.pyw. Nothing was changed.','NovelAI Media Library'); exit 3};" ^
  "Get-CimInstance Win32_Process -ErrorAction SilentlyContinue | Where-Object {$_.CommandLine -and $_.CommandLine -match 'companion\.pyw'} | ForEach-Object {Stop-Process -Id $_.ProcessId -Force -ErrorAction SilentlyContinue};" ^
  "Start-Sleep -Milliseconds 700;" ^
  "Invoke-WebRequest -UseBasicParsing '%REPO_RAW%/companion.pyw' -OutFile (Join-Path $dir 'companion.pyw');" ^
  "Start-Process '%REPO_RAW%/novelai-media.user.js';" ^
  "if(Test-Path (Join-Path $dir 'run.bat')){Start-Process (Join-Path $dir 'run.bat')};" ^
  "[System.Windows.Forms.MessageBox]::Show('Automatic updating is installed. Tampermonkey should now be showing the userscript install/update page. Approve that one update once; after that, future userscript, launcher, and companion runtime changes update automatically.','NovelAI Media Library')"

if errorlevel 1 (
  echo.
  echo Bootstrap did not complete. Your media files and library.json were not modified.
  pause
  exit /b 1
)

exit /b 0
