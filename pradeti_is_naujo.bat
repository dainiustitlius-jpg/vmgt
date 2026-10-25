@echo off
rem Istrina testine baze ir ikeltus failus (aplankas data). Kita karta paleidus
rem bus sukurti nauji pavyzdiniai duomenys. Tikriems duomenims NENAUDOTI.
cd /d "%~dp0"
if not exist data (
  echo Aplanko data nera - nieko trinti nereikia.
  pause
  exit /b 0
)
echo Bus istrinta testine baze: %CD%\data
set /p ATS=Ar tikrai istrinti? Iveskite TAIP: 
if /i not "%ATS%"=="TAIP" (
  echo Atsaukta.
  pause
  exit /b 0
)
rmdir /s /q data
echo Istrinta. Dabar paleiskite paleisti.bat
pause
