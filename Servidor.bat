@echo off
setlocal
chcp 65001 >nul
cd /d "%~dp0"
if not exist "tools" mkdir "tools"

rem Quando roda sozinho (tarefa do Windows), grava tudo em tools\servidor.log.
if /i "%~1"=="/auto" if /i not "%~2"=="/log" (
  call "%~f0" /auto /log >> "tools\servidor.log" 2>&1
  exit /b
)
set "AUTO="
if /i "%~1"=="/auto" set "AUTO=1"
title FolhaWeb - servidor na internet

echo.
echo  ===========================================
echo    FolhaWeb - servidor publicado na internet
echo  ===========================================
echo   %date% %time%
echo.

rem ---- 0. Ja esta rodando? ----------------------------------------------------
powershell -NoProfile -Command "if (Get-NetTCPConnection -LocalPort 8000 -State Listen -ErrorAction SilentlyContinue) { exit 0 } else { exit 1 }"
if errorlevel 1 goto livre
echo  O FolhaWeb ja esta rodando neste computador ^(porta 8000 ocupada^).
if exist "ENDERECO.txt" (
  echo  Endereco na internet:
  type "ENDERECO.txt"
)
echo  Se quiser reiniciar, feche a outra janela do FolhaWeb e abra este arquivo de novo.
if not defined AUTO pause
exit /b 0
:livre

rem ---- 1. Atualizacoes ------------------------------------------------------
where git >nul 2>nul
if errorlevel 1 (
  echo  [1/7] Git nao encontrado: seguindo sem baixar atualizacoes.
) else (
  echo  [1/7] Baixando atualizacoes...
  git -c safe.directory=* pull --ff-only
  if errorlevel 1 echo  [AVISO] Nao foi possivel atualizar agora. Seguindo com a versao atual.
)

rem ---- 2. Ambiente do Python ---------------------------------------------------
set "PY=.venv\Scripts\python.exe"
if exist "%PY%" goto temvenv
set "PYBASE="
python --version >nul 2>nul && set "PYBASE=python"
if not defined PYBASE py -3 --version >nul 2>nul && set "PYBASE=py -3"
if not defined PYBASE (
  echo  [ERRO] Python nao encontrado. Instale em https://www.python.org/downloads/
  echo         marcando "Add python.exe to PATH", e abra este arquivo de novo.
  if not defined AUTO pause
  exit /b 1
)
echo  [2/7] Preparando o ambiente pela primeira vez - pode levar 1 minuto...
%PYBASE% -m venv .venv
if errorlevel 1 (
  echo  [ERRO] Nao foi possivel criar o ambiente do Python.
  if not defined AUTO pause
  exit /b 1
)
:temvenv
echo  [2/7] Conferindo bibliotecas...
"%PY%" -m pip install --quiet --disable-pip-version-check -r requirements.txt
if errorlevel 1 (
  echo  [ERRO] Falha ao instalar as bibliotecas. Verifique a internet e tente de novo.
  if not defined AUTO pause
  exit /b 1
)

rem ---- 3. Configuracao de producao (.env com chave secreta) --------------------
echo  [3/7] Conferindo a configuracao do servidor...
"%PY%" manage.py preparar_servidor
if errorlevel 1 (
  echo  [ERRO] Nao foi possivel criar o arquivo .env.
  if not defined AUTO pause
  exit /b 1
)
set "TOKEN="
for /f "usebackq eol=# tokens=1,* delims==" %%a in (".env") do if /i "%%a"=="FOLHA_CLOUDFLARE_TOKEN" set "TOKEN=%%b"

rem ---- 4. Banco de dados, arquivos visuais e primeiro usuario -------------------
echo  [4/7] Atualizando o banco de dados...
"%PY%" manage.py migrate --noinput
if errorlevel 1 (
  echo  [ERRO] Falha ao atualizar o banco de dados.
  if not defined AUTO pause
  exit /b 1
)
"%PY%" manage.py collectstatic --noinput --verbosity 0
if errorlevel 1 (
  echo  [ERRO] Falha ao preparar os arquivos visuais.
  if not defined AUTO pause
  exit /b 1
)
"%PY%" manage.py shell --verbosity 0 -c "from django.contrib.auth.models import User; import sys; sys.exit(0 if User.objects.exists() else 3)"
if not errorlevel 3 goto temusuario
if defined AUTO (
  echo  [ERRO] Nenhum usuario cadastrado. Abra o Servidor.bat com dois cliques uma vez para criar.
  exit /b 1
)
echo.
echo  Nenhum usuario cadastrado. Vamos criar o seu acesso agora.
echo  Como o sistema vai ficar na internet, use uma senha forte ^(12 ou mais caracteres^).
echo.
"%PY%" manage.py createsuperuser
:temusuario

rem ---- 5. Copia de seguranca ----------------------------------------------------
echo  [5/7] Fazendo copia de seguranca na pasta backups...
"%PY%" manage.py backup
if errorlevel 1 echo  [AVISO] O backup falhou. O sistema vai abrir assim mesmo.

rem ---- 6. Fila automatica do eSocial (a cada 5 minutos) -------------------------
echo  [6/7] Ligando a fila automatica do eSocial ^(registro em tools\fila.log^)...
start "" /b cmd /c ""%PY%" manage.py processar_esocial --intervalo 300 >> "tools\fila.log" 2>&1"

rem ---- 7. Tunel da Cloudflare (publica na internet sem abrir portas) -----------
if exist "tools\cloudflared.exe" goto temtunel
echo  [7/7] Baixando o Cloudflare Tunnel ^(so na primeira vez^)...
curl.exe -L --fail --silent --show-error -o "tools\cloudflared.exe" https://github.com/cloudflare/cloudflared/releases/latest/download/cloudflared-windows-amd64.exe
if errorlevel 1 (
  del "tools\cloudflared.exe" >nul 2>nul
  echo  [ERRO] Nao foi possivel baixar o cloudflared. Verifique a internet.
  if not defined AUTO pause
  exit /b 1
)
:temtunel
if defined TOKEN goto tunelfixo
if exist "tools\cloudflared.yml" goto tuneldominio

echo  [7/7] Abrindo o endereco provisorio na internet...
del "tools\tunel.log" "tools\tunel-saida.log" >nul 2>nul
del "ENDERECO.txt" >nul 2>nul
start "" /b cmd /c "tools\cloudflared.exe tunnel --no-autoupdate --url http://127.0.0.1:8000 --logfile tools\tunel.log > "tools\tunel-saida.log" 2>&1"
powershell -NoProfile -Command "for ($i=0; $i -lt 60; $i++) { Start-Sleep 1; $m = Select-String -Path 'tools\tunel.log','tools\tunel-saida.log' -Pattern 'https://[a-z0-9-]+\.trycloudflare\.com' -ErrorAction SilentlyContinue | Select-Object -First 1; if ($m) { Set-Content -Path 'ENDERECO.txt' -Value $m.Matches[0].Value -Encoding ASCII; exit 0 } }; exit 1"
if errorlevel 1 (
  echo  [AVISO] O endereco ainda nao apareceu. Veja o arquivo tools\tunel.log.
  goto servir
)
set /p ENDERECO=<"ENDERECO.txt"
if not defined AUTO clip < "ENDERECO.txt"
echo.
echo  ==============================================================
echo    Endereco do FolhaWeb na internet ^(ja copiado^):
echo.
echo      %ENDERECO%
echo.
echo    Ele tambem fica salvo no arquivo ENDERECO.txt.
echo    ATENCAO: este endereco provisorio muda sempre que o servidor
echo    reinicia. Para um endereco fixo, veja o README ^(dominio proprio^).
echo  ==============================================================
goto servir

:tuneldominio
echo  [7/7] Ligando o tunel do seu dominio proprio...
start "" /b cmd /c "tools\cloudflared.exe tunnel --no-autoupdate --logfile tools\tunel.log --config tools\cloudflared.yml run >nul 2>&1"
set /p ENDERECO=<"ENDERECO.txt"
echo.
echo  Pronto: o FolhaWeb esta em %ENDERECO%
goto servir

:tunelfixo
echo  [7/7] Ligando o tunel do seu dominio proprio...
start "" /b cmd /c "tools\cloudflared.exe tunnel --no-autoupdate --logfile tools\tunel.log run --token %TOKEN% >nul 2>&1"
echo.
echo  Pronto: o FolhaWeb esta no endereco que voce configurou na Cloudflare.

:servir
echo.
echo  Deixe esta janela aberta: fechar a janela tira o sistema do ar.
echo.
"%PY%" manage.py servir --porta 8000
if defined AUTO (
  echo  O servidor parou. Religando em 10 segundos...
  ping -n 11 127.0.0.1 >nul
  goto servir
)
pause
