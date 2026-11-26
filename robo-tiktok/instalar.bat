@echo off
chcp 65001 >nul
title Voltou! - Instalar robo do TikTok Shop
cd /d "%~dp0.."

set "PY=python"
where python >nul 2>&1 || set "PY=py -3"
%PY% --version >nul 2>&1
if errorlevel 1 (
  echo.
  echo  Python nao encontrado. Instale em https://www.python.org/downloads/
  echo  e marque a opcao "Add python.exe to PATH" na instalacao. Depois rode este arquivo de novo.
  echo.
  pause
  exit /b 1
)

echo.
echo  [1/3] Instalando o que o robo precisa...
%PY% -m pip install --upgrade -r requirements.txt "playwright>=1.47"
if errorlevel 1 ( echo  Falhou a instalacao. & pause & exit /b 1 )

echo.
echo  [2/3] Configuracao (Supabase)...
if not exist "robo-tiktok\.env" (
  copy "robo-tiktok\.env.exemplo" "robo-tiktok\.env" >nul
  echo  Vou abrir o arquivo .env no Bloco de Notas. Preencha, salve e feche.
  notepad "robo-tiktok\.env"
) else (
  echo  robo-tiktok\.env ja existe, mantendo.
)

echo.
echo  [3/3] Agendando 2x por dia (09:00 e 21:00)...
call "robo-tiktok\agendar.bat"

echo.
echo  Tudo pronto. Para rodar agora, de dois cliques em robo-tiktok\rodar.bat
pause
