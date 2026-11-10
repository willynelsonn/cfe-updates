# Cria (ou remove) as tarefas do Windows que mantem o FolhaWeb no ar.
# Chamado pelo InstalarNoServidor.bat. Precisa de administrador.
param([switch]$Remover)
$ErrorActionPreference = 'Stop'
$raiz = Split-Path -Parent $PSScriptRoot

function Parar-FolhaWeb {
    Get-CimInstance Win32_Process | Where-Object {
        ($_.ExecutablePath -and $_.ExecutablePath.StartsWith($raiz, 'OrdinalIgnoreCase')) -or
        ($_.CommandLine -match 'manage\.py"?\s+(servir|processar_esocial)')
    } | ForEach-Object { Stop-Process -Id $_.ProcessId -Force -ErrorAction SilentlyContinue }
}

foreach ($nome in 'FolhaWeb Servidor', 'FolhaWeb Backup') {
    if (Get-ScheduledTask -TaskName $nome -ErrorAction SilentlyContinue) {
        Stop-ScheduledTask -TaskName $nome -ErrorAction SilentlyContinue
        Unregister-ScheduledTask -TaskName $nome -Confirm:$false
    }
}
Parar-FolhaWeb

if ($Remover) {
    Write-Host '  Tarefas removidas. O FolhaWeb nao liga mais sozinho.'
    exit 0
}

$sistema = New-ScheduledTaskPrincipal -UserId 'SYSTEM' -LogonType ServiceAccount -RunLevel Highest

# 1) Servidor: liga junto com o Windows (1 minuto depois, para a rede subir), sem limite de tempo,
#    e tenta de novo a cada minuto se cair.
$acao = New-ScheduledTaskAction -Execute 'cmd.exe' -Argument ('/c ""' + (Join-Path $raiz 'Servidor.bat') + '" /auto"') -WorkingDirectory $raiz
$gatilho = New-ScheduledTaskTrigger -AtStartup
$gatilho.Delay = 'PT1M'
$config = New-ScheduledTaskSettingsSet -ExecutionTimeLimit ([TimeSpan]::Zero) -AllowStartIfOnBatteries -DontStopIfGoingOnBatteries `
    -RestartCount 999 -RestartInterval (New-TimeSpan -Minutes 1) -StartWhenAvailable -MultipleInstances IgnoreNew
Register-ScheduledTask -TaskName 'FolhaWeb Servidor' -Action $acao -Trigger $gatilho -Principal $sistema -Settings $config `
    -Description 'Mantem o FolhaWeb no ar (Waitress + Cloudflare Tunnel + fila do eSocial).' | Out-Null

# 2) Backup diario as 2h da manha.
$py = Join-Path $raiz '.venv\Scripts\python.exe'
$acaoB = New-ScheduledTaskAction -Execute $py -Argument ('"' + (Join-Path $raiz 'manage.py') + '" backup') -WorkingDirectory $raiz
$gatilhoB = New-ScheduledTaskTrigger -Daily -At '02:00'
$configB = New-ScheduledTaskSettingsSet -AllowStartIfOnBatteries -DontStopIfGoingOnBatteries -StartWhenAvailable
Register-ScheduledTask -TaskName 'FolhaWeb Backup' -Action $acaoB -Trigger $gatilhoB -Principal $sistema -Settings $configB `
    -Description 'Copia de seguranca diaria do FolhaWeb (pasta backups).' | Out-Null

Start-ScheduledTask -TaskName 'FolhaWeb Servidor'
Write-Host '  Tarefas criadas: o FolhaWeb liga sozinho com o Windows e faz backup todo dia as 2h.'
