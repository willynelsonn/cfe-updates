@echo off
setlocal
chcp 65001 >nul
title FolhaWeb
cd /d "%~dp0"

echo.
echo  ===========================================
echo    FolhaWeb - atualizando e iniciando
echo  ===========================================
echo.

rem ---- 1. Programas necessarios ---------------------------------------------
set "PYBASE="
python --version >nul 2>nul && set "PYBASE=python"
if not defined PYBASE py -3 --version >nul 2>nul && set "PYBASE=py -3"
if not defined PYBASE (
  echo  [ERRO] Python nao encontrado. Instale em https://www.python.org/downloads/
  echo         e marque a opcao "Add python.exe to PATH" durante a instalacao.
  pause
  exit /b 1
)
where git >nul 2>nul
if errorlevel 1 (
  echo  [AVISO] Git nao encontrado: o sistema vai abrir, mas sem baixar atualizacoes.
  echo          Para atualizar sozinho, instale em https://git-scm.com/download/win
  echo.
) else (
  echo  [1/5] Baixando atualizacoes...
  git pull --ff-only
  if errorlevel 1 echo  [AVISO] Nao foi possivel atualizar agora. Seguindo com a versao atual.
)

rem ---- 2. Ambiente isolado do Python (criado so na primeira vez) -------------
if not exist ".venv\Scripts\python.exe" (
  echo  [2/5] Preparando o ambiente pela primeira vez - pode levar 1 minuto...
  %PYBASE% -m venv .venv
  if errorlevel 1 (
    echo  [ERRO] Nao foi possivel criar o ambiente do Python.
    pause
    exit /b 1
  )
) else (
  echo  [2/5] Ambiente pronto.
)
set "PY=.venv\Scripts\python.exe"

rem ---- 3. Bibliotecas ---------------------------------------------------------
echo  [3/5] Conferindo bibliotecas...
"%PY%" -m pip install --quiet --disable-pip-version-check -r requirements.txt
if errorlevel 1 (
  echo  [ERRO] Falha ao instalar as bibliotecas. Verifique a internet e tente de novo.
  pause
  exit /b 1
)

rem ---- 4. Banco de dados e primeiro usuario -----------------------------------
echo  [4/5] Atualizando o banco de dados...
"%PY%" manage.py migrate --noinput
if errorlevel 1 (
  echo  [ERRO] Falha ao atualizar o banco de dados.
  pause
  exit /b 1
)
"%PY%" manage.py shell --verbosity 0 -c "from django.contrib.auth.models import User; import sys; sys.exit(0 if User.objects.exists() else 3)"
if errorlevel 3 (
  echo.
  echo  Nenhum usuario cadastrado. Vamos criar o seu acesso agora.
  echo  ^(o e-mail pode ficar em branco; a senha nao aparece enquanto voce digita^)
  echo.
  "%PY%" manage.py createsuperuser
)

rem ---- 5. Atalho na Area de Trabalho (so na primeira vez) --------------------
powershell -NoProfile -ExecutionPolicy Bypass -Command "$d=[Environment]::GetFolderPath('Desktop'); $l=Join-Path $d 'FolhaWeb.lnk'; if (-not (Test-Path $l)) { $s=(New-Object -ComObject WScript.Shell).CreateShortcut($l); $s.TargetPath='%~f0'; $s.WorkingDirectory='%~dp0'; $s.IconLocation='%SystemRoot%\System32\shell32.dll,165'; $s.Save(); Write-Host '  Atalho FolhaWeb criado na Area de Trabalho.' }"

rem ---- Inicia (ou reaproveita) o servidor e abre o navegador ------------------
powershell -NoProfile -Command "if (Get-NetTCPConnection -LocalPort 8000 -State Listen -ErrorAction SilentlyContinue) { exit 0 } else { exit 1 }"
if not errorlevel 1 (
  echo  [5/5] O FolhaWeb ja estava aberto: so abrindo o navegador.
  start "" "http://127.0.0.1:8000"
  timeout /t 3 >nul
  exit /b 0
)
echo  [5/5] Iniciando o FolhaWeb em http://127.0.0.1:8000
echo.
echo  Deixe esta janela aberta enquanto usa o sistema.
echo  Para encerrar, feche esta janela.
echo.
start "" /min cmd /c "timeout /t 4 >nul & start http://127.0.0.1:8000"
"%PY%" manage.py runserver 127.0.0.1:8000
pause
