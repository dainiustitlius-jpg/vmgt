@echo off
rem Leidzia kitiems imones tinklo kompiuteriams jungtis prie VMGT (Windows ugniasiene).
rem Paleiskite viena karta tame kompiuteryje, kuriame veikia VMGT. Reikia administratoriaus teisiu.
rem Taisykle galioja tik domeno ir privaciame tinkle - is viesu tinklu (Wi-Fi kavineje) prisijungti negalima.
cd /d "%~dp0"
net session >nul 2>&1
if errorlevel 1 (
  echo Reikia administratoriaus teisiu - Windows paklaus leidimo...
  powershell -NoProfile -Command "Start-Process -FilePath '%~f0' -Verb RunAs"
  exit /b
)
set PORT=8080
if exist vmgt_config.json (
  for /f "tokens=2 delims=:, " %%p in ('findstr /c:"\"port\"" vmgt_config.json') do set PORT=%%p
)
netsh advfirewall firewall delete rule name="VMGT" >nul 2>&1
netsh advfirewall firewall add rule name="VMGT" dir=in action=allow protocol=TCP localport=%PORT% profile=domain,private
if errorlevel 1 (
  echo Nepavyko prideti taisykles. Galbut ugniasiene valdo IT (grupes politika) - perduokite jiems: TCP %PORT%, iejimas.
) else (
  echo Leista: TCP %PORT% is imones tinklo. Adresas kitiems kompiuteriams rodomas paleidus paleisti.bat
)
pause
