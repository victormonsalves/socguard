<#
.SYNOPSIS
    Registra la tarea programada de SOCGuard en Windows Task Scheduler.
.DESCRIPTION
    Crea una tarea que ejecuta SOCGuard cada 5 minutos en segundo plano,
    asegurando que si la máquina reinicia o la tarea termina, vuelva a correr.
#>

$TaskName = "SOCGuard_Log_Inspector"
$ScriptDir = Split-Path -Parent $MyInvocation.MyCommand.Definition
$BatchFile = Join-Path $ScriptDir "run_socguard.bat"

Write-Host "==========================================================" -ForegroundColor Cyan
Write-Host "  Registrando Tarea Programada: $TaskName" -ForegroundColor Cyan
Write-Host "==========================================================" -ForegroundColor Cyan
Write-Host "Directorio: $ScriptDir"
Write-Host "Lanzador:   $BatchFile"

# 1. Definir la Acción
$Action = New-ScheduledTaskAction -Execute $BatchFile -WorkingDirectory $ScriptDir

# 2. Definir el Disparador (Trigger): Cada 5 minutos indefinidamente
$Trigger = New-ScheduledTaskTrigger -Once -At (Get-Date).Date -RepetitionInterval (New-TimeSpan -Minutes 5) -RepetitionDuration ([TimeSpan]::MaxValue)

# 3. Definir Configuración (Settings)
$Settings = New-ScheduledTaskSettingsSet -AllowStartIfOnBatteries `
                                         -DontStopIfGoingOnBatteries `
                                         -StartWhenAvailable `
                                         -MultipleInstances IgnoreNew `
                                         -ExecutionTimeLimit (New-TimeSpan -Minutes 10)

# 4. Validar si ya existe para actualizarla o crearla
$ExistingTask = Get-ScheduledTask -TaskName $TaskName -ErrorAction SilentlyContinue

if ($ExistingTask) {
    Write-Host "[*] La tarea '$TaskName' ya existe. Actualizando configuracion..." -ForegroundColor Yellow
    Unregister-ScheduledTask -TaskName $TaskName -Confirm:$false
}

Register-ScheduledTask -TaskName $TaskName `
                       -Action $Action `
                       -Trigger $Trigger `
                       -Settings $Settings `
                       -Description "Inspector continuo de logs de automatizaciones SOC y creacion de incidentes ServiceNow"

Write-Host "`n[+] Tarea programada registrada exitosamente en Windows Task Scheduler!" -ForegroundColor Green
Write-Host "    Frecuencia: Cada 5 minutos"
Write-Host "    Para probar inmediatamente, ejecuta:" -ForegroundColor Gray
Write-Host "    Start-ScheduledTask -TaskName '$TaskName'`n" -ForegroundColor White
