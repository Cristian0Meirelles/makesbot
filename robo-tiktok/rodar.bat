@echo off
chcp 65001 >nul
title Voltou! - Robo do TikTok Shop e lojas
cd /d "%~dp0.."

if not exist "robo-tiktok\.env" (
  echo.
  echo  Falta o arquivo robo-tiktok\.env  - rode o instalar.bat primeiro.
  echo.
  pause
  exit /b 1
)

rem carrega as configuracoes do .env
for /f "usebackq eol=# tokens=1,* delims==" %%a in ("robo-tiktok\.env") do set "%%a=%%b"
set PYTHONIOENCODING=utf-8

set "PY=python"
where python >nul 2>&1 || set "PY=py -3"

echo.
echo  ==========================================================
echo   Robo do TikTok Shop - %date% %time:~0,5%
echo   Vai abrir uma janela do Chrome. Pode usar o PC normalmente,
echo   so nao feche essa janela. Se aparecer o quebra-cabeca do
echo   TikTok, resolva que o robo continua sozinho.
echo  ==========================================================
echo.

echo  [1/2] TikTok Shop (todas as lojas de maquiagem)
%PY% -m bot.main tiktok_catalogo --chrome --sem-abrir-site

echo.
echo  [2/2] Lojas pelo navegador (MAC Cosmetics e outras do config)
%PY% -m bot.main navegador --chrome

if not defined SITE_URL set "SITE_URL=https://voltou-lilac.vercel.app"
start "" "%SITE_URL%/#catalogo"

echo.
echo  Terminou. Esta janela fecha em 30 segundos.
timeout /t 30 >nul
