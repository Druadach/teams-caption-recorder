$ErrorActionPreference = 'Stop'
$root = Split-Path -Parent $MyInvocation.MyCommand.Path

Write-Host '== Teams Caption Recorder installer ==' -ForegroundColor Cyan

# 1) dependencies
python -m pip install --quiet -r (Join-Path $root 'requirements.txt')
if ($LASTEXITCODE -ne 0) { throw 'pip install failed' }

# 2) locate a windowless python if available
$pyw = (Get-Command pythonw.exe -ErrorAction SilentlyContinue).Source
if (-not $pyw) {
    $py  = (Get-Command python.exe -ErrorAction Stop).Source
    $dir = Split-Path -Parent $py
    $cand = Join-Path $dir 'pythonw.exe'
    if (Test-Path $cand) { $pyw = $cand } else { $pyw = $py }   # console fallback
}

# 3) register autostart for the current user
$watchdog = Join-Path $root 'caption_watchdog.py'
$value    = "`"$pyw`" `"$watchdog`""
reg add "HKCU\Software\Microsoft\Windows\CurrentVersion\Run" /v TeamsCaptionWatchdog /t REG_SZ /d $value /f | Out-Null

# 4) start it now
Start-Process -FilePath $pyw -ArgumentList "`"$watchdog`"" -WindowStyle Hidden

Write-Host ''
Write-Host 'Installed and running.' -ForegroundColor Green
Write-Host "  watchdog : $watchdog"
Write-Host "  autostart: HKCU...\Run -> TeamsCaptionWatchdog"
Write-Host "  output   : $env:USERPROFILE\Documents\TeamsCaptions\"
