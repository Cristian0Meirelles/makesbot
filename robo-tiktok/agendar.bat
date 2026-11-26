@echo off
chcp 65001 >nul
rem Agenda o robo para rodar sozinho todo dia as 09:00 e 21:00 (com o PC ligado e voce logado).

schtasks /Create /TN "Voltou - Robo TikTok 09h" /TR "\"%~dp0rodar.bat\"" /SC DAILY /ST 09:00 /F >nul
schtasks /Create /TN "Voltou - Robo TikTok 21h" /TR "\"%~dp0rodar.bat\"" /SC DAILY /ST 21:00 /F >nul

if errorlevel 1 (
  echo  Nao consegui criar o agendamento. Clique com o botao direito no agendar.bat e "Executar como administrador".
) else (
  echo  Pronto: o robo vai rodar todo dia as 09:00 e as 21:00.
  echo  Para mudar ou apagar: abra o "Agendador de Tarefas" do Windows e procure "Voltou - Robo TikTok".
)
echo.
pause
