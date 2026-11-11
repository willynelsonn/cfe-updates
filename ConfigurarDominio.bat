@echo off
setlocal
chcp 65001 >nul
title FolhaWeb - endereco fixo na internet (dominio proprio)
cd /d "%~dp0"
if not exist "tools" mkdir "tools"

echo.
echo  ======================================================
echo    FolhaWeb - endereco fixo na internet com a Cloudflare
echo  ======================================================
echo.
echo  Antes de continuar voce precisa:
echo   1. Ter uma conta gratis na Cloudflare: https://dash.cloudflare.com/sign-up
echo   2. Ter adicionado o seu dominio na Cloudflare ^(Add a domain, plano Free^)
echo      e trocado os servidores DNS no Registro.br pelos que a Cloudflare mostrar.
echo      O dominio precisa aparecer como "Active" na Cloudflare.
echo.

set "PY=.venv\Scripts\python.exe"
if not exist "%PY%" (
  echo  [ERRO] Abra primeiro o Servidor.bat uma vez, para preparar o sistema.
  pause
  exit /b 1
)

set "DOMINIO="
set /p DOMINIO=  Digite o endereco desejado ^(ex.: folha.seudominio.com.br^): 
if not defined DOMINIO (
  echo  Nenhum endereco digitado.
  pause
  exit /b 1
)

rem ---- 1. Programa do tunel ---------------------------------------------------
if not exist "tools\cloudflared.exe" (
  echo  [1/4] Baixando o Cloudflare Tunnel...
  curl.exe -L --fail --silent --show-error -o "tools\cloudflared.exe" https://github.com/cloudflare/cloudflared/releases/latest/download/cloudflared-windows-amd64.exe
  if errorlevel 1 (
    del "tools\cloudflared.exe" >nul 2>nul
    echo  [ERRO] Nao foi possivel baixar o cloudflared. Verifique a internet.
    pause
    exit /b 1
  )
)

rem ---- 2. Autorizar a Cloudflare --------------------------------------------
if exist "%USERPROFILE%\.cloudflared\cert.pem" goto autorizado
echo.
echo  [2/4] O navegador vai abrir na Cloudflare.
echo        Entre na sua conta, clique no seu dominio e depois em "Authorize".
echo.
pause
"tools\cloudflared.exe" tunnel login
if errorlevel 1 (
  echo  [ERRO] A autorizacao nao foi concluida. Tente de novo.
  pause
  exit /b 1
)
:autorizado
echo  [2/4] Cloudflare autorizada.

rem ---- 3. Criar o tunel e apontar o endereco ---------------------------------
set "TUNEL=folhaweb-%COMPUTERNAME%"
echo  [3/4] Criando o tunel %TUNEL%...
if not exist "tools\tunel-credenciais.json" (
  "tools\cloudflared.exe" tunnel create --credentials-file "tools\tunel-credenciais.json" %TUNEL% >nul 2>nul
  if errorlevel 1 "tools\cloudflared.exe" tunnel token --cred-file "tools\tunel-credenciais.json" %TUNEL% >nul
  if errorlevel 1 (
    echo  [ERRO] Nao foi possivel criar o tunel na Cloudflare.
    pause
    exit /b 1
  )
)
"tools\cloudflared.exe" tunnel route dns --overwrite-dns %TUNEL% %DOMINIO%
if errorlevel 1 (
  echo  [ERRO] Nao foi possivel apontar %DOMINIO% para o tunel.
  echo         Confira se o dominio esta "Active" na Cloudflare e se foi digitado certo.
  pause
  exit /b 1
)

rem ---- 4. Configurar o FolhaWeb ------------------------------------------------
echo  [4/4] Configurando o FolhaWeb...
"%PY%" manage.py configurar_dominio "%DOMINIO%" --credenciais "tools\tunel-credenciais.json"
if errorlevel 1 (
  pause
  exit /b 1
)

echo.
echo  ==============================================================
echo    Tudo pronto! Endereco fixo do FolhaWeb:
echo.
type "ENDERECO.txt"
echo.
echo    Agora feche a janela do Servidor.bat ^(se estiver aberta^)
echo    e abra o Servidor.bat de novo. Se instalou para ligar sozinho,
echo    basta reiniciar o computador.
echo  ==============================================================
echo.
pause
