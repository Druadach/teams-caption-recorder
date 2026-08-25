$ErrorActionPreference = 'SilentlyContinue'

Write-Host '== Teams Caption Recorder uninstaller ==' -ForegroundColor Cyan

# 1) remove autostart entry
Remove-ItemProperty -Path 'HKCU:\Software\Microsoft\Windows\CurrentVersion\Run' `
    -Name 'TeamsCaptionWatchdog'
Write-Host 'autostart entry removed'

# 2) kill any running watchdog / recorder
Get-CimInstance Win32_Process -Filter "Name like 'python%'" |
    Where-Object { $_.CommandLine -match 'caption_(recorder|watchdog)\.py' } |
    ForEach-Object {
        Stop-Process -Id $_.ProcessId -Force
        Write-Host "stopped pid $($_.ProcessId)"
    }

Write-Host ''
Write-Host 'Uninstalled. Transcripts kept in Documents\TeamsCaptions\.' -ForegroundColor Green
