@echo off
chcp 65001 >nul
cd /d "%~dp0"
if not exist ".venv\Scripts\python.exe" (
    py -3 -m venv .venv
    if errorlevel 1 goto error
)
".venv\Scripts\python.exe" -c "import PySide6" >nul 2>&1
if errorlevel 1 (
    ".venv\Scripts\python.exe" -m pip install -r requirements.txt
    if errorlevel 1 goto error
)
".venv\Scripts\python.exe" main.py
if errorlevel 1 goto error
exit /b 0
:error
echo Не удалось запустить приложение. Проверьте Python 3.10+ и подключение к интернету при первой установке.
pause
exit /b 1
