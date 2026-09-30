param([int]$Port=8765)
$ErrorActionPreference='Stop'
$demoRoot=$PSScriptRoot
$projectRoot=Split-Path -Parent $demoRoot
$demoPython=if($env:CERT_DEMO_PYTHON){$env:CERT_DEMO_PYTHON}else{'D:\Apps\miniconda3\envs\fapiao\python.exe'}
if(-not $env:CERT_OCR_MODEL_ROOT){$env:CERT_OCR_MODEL_ROOT=Join-Path $projectRoot 'models\official_models'}
if(-not $env:CERT_OCR_DEVICE){$env:CERT_OCR_DEVICE='cpu'}
if(-not $env:CERT_OCR_CPU_THREADS){$env:CERT_OCR_CPU_THREADS='8'}
if(-not(Test-Path -LiteralPath $demoPython)){throw '找不到本地 Paddle Python，请设置 CERT_DEMO_PYTHON'}
$demoHealth=$null
try{$demoHealth=Invoke-RestMethod -Uri "http://127.0.0.1:$Port/api/state" -TimeoutSec 2}catch{}
if($null -ne $demoHealth -and $null -ne $demoHealth.settings){Write-Output "Demo 已在运行：http://127.0.0.1:$Port";exit 0}
$demoLogs=Join-Path $demoRoot 'data'
[void](New-Item -ItemType Directory -Path $demoLogs -Force)
$demoScript=Join-Path $demoRoot 'app.py'
$demoArgs=@('-X','utf8','-B',('"'+$demoScript+'"'),'--port',"$Port")
$demoProcess=Start-Process -FilePath $demoPython -ArgumentList $demoArgs -WorkingDirectory $demoRoot -WindowStyle Hidden -RedirectStandardOutput (Join-Path $demoLogs 'server.log') -RedirectStandardError (Join-Path $demoLogs 'server-error.log') -PassThru
$demoProcess.Id | Set-Content -LiteralPath (Join-Path $demoLogs 'server.pid')
for($attempt=0;$attempt -lt 20;$attempt++){
    try{
        $demoHealth=Invoke-RestMethod -Uri "http://127.0.0.1:$Port/api/state" -TimeoutSec 2
        if($null -ne $demoHealth.settings){Write-Output "本地 Demo 已就绪，进程 $($demoProcess.Id)：http://127.0.0.1:$Port";exit 0}
    }catch{}
    if($demoProcess.HasExited){throw 'Demo 启动失败，请查看 data/server-error.log'}
    Start-Sleep -Milliseconds 500
}
throw 'Demo 启动超时，请查看 data/server-error.log'
