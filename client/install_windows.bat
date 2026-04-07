@echo off
:: Installa Jarvis Client come task avvio automatico su Windows

echo === Jarvis Client - Installazione Windows ===

:: Controlla Python
python --version >nul 2>&1
if errorlevel 1 (
    echo ERRORE: Python non trovato. Installa Python 3.10+ da python.org
    pause
    exit /b 1
)

:: Installa dipendenze
echo Installo dipendenze Python...
pip install -r requirements.txt
if errorlevel 1 (
    echo ERRORE nell'installazione delle dipendenze
    pause
    exit /b 1
)

:: Crea script di avvio in background (nessuna finestra)
set SCRIPT_DIR=%~dp0
set STARTUP_SCRIPT=%APPDATA%\Microsoft\Windows\Start Menu\Programs\Startup\jarvis_client.vbs

echo Set WshShell = CreateObject("WScript.Shell") > "%STARTUP_SCRIPT%"
echo WshShell.Run "python ""%SCRIPT_DIR%jarvis_client.py""", 0, False >> "%STARTUP_SCRIPT%"

echo.
echo ✅ Jarvis Client installato!
echo    - Si avvia automaticamente al login
echo    - Avvio script: %STARTUP_SCRIPT%
echo    - Per avviarlo ora: python jarvis_client.py
echo    - Per disinstallare: elimina %STARTUP_SCRIPT%
echo.

:: Chiedi se avviare subito
set /p START=Vuoi avviare Jarvis adesso? (s/n):
if /i "%START%"=="s" (
    start "" python "%SCRIPT_DIR%jarvis_client.py"
    echo Jarvis avviato in background.
)

pause
