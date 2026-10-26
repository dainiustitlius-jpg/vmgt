@echo off
rem VMGT paleidimas: dukart spustelekite si faila.
rem Pereina i savo aplanka, parsisiuncia naujausia versija, idiegia bibliotekas ir paleidzia servisa.
cd /d "%~dp0"
echo Tikrinama naujausia versija...
git pull
echo Tikrinamos bibliotekos...
py -m pip install -q -r requirements.txt
if errorlevel 1 (
  echo Nepavyko idiegti biblioteku. Patikrinkite, ar idiegtas Python: py --version
  pause
  exit /b 1
)
echo.
echo Narsykleje atidarykite http://localhost:8080 - kitu kompiuteriu adresas parodytas zemiau (sustabdyti - uzdarykite si langa)
py -m vmgt
pause
