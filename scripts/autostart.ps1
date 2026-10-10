# JARVIS — démarrage automatique à l'ouverture de session (tâche planifiée, sans console)
# Installer :   powershell -ExecutionPolicy Bypass -File scripts\autostart.ps1
# Retirer :     powershell -ExecutionPolicy Bypass -File scripts\autostart.ps1 -Remove
param([switch]$Remove)
$ErrorActionPreference = "Stop"
$root = Split-Path $PSScriptRoot -Parent
$name = "Jarvis"

if ($Remove) {
    Unregister-ScheduledTask -TaskName $name -Confirm:$false -ErrorAction SilentlyContinue
    Write-Host "Démarrage automatique retiré."
    return
}

$pyw = Join-Path $root ".venv\Scripts\pythonw.exe"
if (-not (Test-Path $pyw)) { throw "Lancez d'abord scripts\install.ps1" }

$action   = New-ScheduledTaskAction -Execute $pyw -Argument "-m jarvis run" -WorkingDirectory $root
$trigger  = New-ScheduledTaskTrigger -AtLogOn -User $env:USERNAME
$trigger.Delay = "PT20S"   # laisse le temps au micro et au réseau
$settings = New-ScheduledTaskSettingsSet -AllowStartIfOnBatteries -DontStopIfGoingOnBatteries `
            -ExecutionTimeLimit ([TimeSpan]::Zero) -RestartCount 3 -RestartInterval (New-TimeSpan -Minutes 1)
$principal = New-ScheduledTaskPrincipal -UserId $env:USERNAME -LogonType Interactive -RunLevel Limited

Register-ScheduledTask -TaskName $name -Action $action -Trigger $trigger -Settings $settings -Principal $principal -Force | Out-Null
Write-Host "Jarvis démarrera à chaque ouverture de session (journal : %LOCALAPPDATA%\Jarvis\jarvis.log)."
