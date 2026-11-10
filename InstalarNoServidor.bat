@echo off
setlocal
chcp 65001 >nul
title FolhaWeb - ligar sozinho com o Windows
cd /d "%~dp0"

rem Precisa de administrador para criar tarefas do Windows: pede a permissao.
net session >nul 2>nul
if errorlevel 1 (
  if "%~1"=="" (
    powershell -NoProfile -Command "Start-Process -FilePath '%~f0' -Verb RunAs"
  ) else (
    powershell -NoProfile -Command "Start-Process -FilePath '%~f0' -ArgumentList '%~1' -Verb RunAs"
  )
  exit /b
)

echo.
echo  ===========================================
echo    FolhaWeb - ligar sozinho com o Windows
echo  ===========================================
echo.

if /i "%~1"=="/remover" (
  powershell -NoProfile -ExecutionPolicy Bypass -File "scripts\tarefas-windows.ps1" -Remover
  pause
  exit /b
)

if not exist ".venv\Scripts\python.exe" (
  echo  [ERRO] Abra primeiro o Servidor.bat com dois cliques, uma vez,
  echo         para preparar o sistema e criar o seu usuario.
  pause
  exit /b 1
)

echo  Isto vai:
echo   - ligar o FolhaWeb sozinho sempre que o Windows iniciar ^(mesmo sem ninguem logado^);
echo   - religar em 1 minuto se ele cair;
echo   - fazer copia de seguranca todo dia as 2h ^(pasta backups^).
echo.
echo  Feche antes a janela do Servidor.bat, se estiver aberta.
echo.
pause
powershell -NoProfile -ExecutionPolicy Bypass -File "scripts\tarefas-windows.ps1"
if errorlevel 1 (
  echo  [ERRO] Nao foi possivel criar as tarefas.
  pause
  exit /b 1
)
echo.
echo  Em cerca de 1 minuto o sistema estara no ar.
echo  O endereco fica no arquivo ENDERECO.txt ^(ou no seu dominio, se configurou o token^).
echo  O registro do que aconteceu fica em tools\servidor.log.
echo  Para desfazer: InstalarNoServidor.bat /remover
echo.
pause
