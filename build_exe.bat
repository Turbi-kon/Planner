@echo off
chcp 65001 >nul
cd /d "%~dp0"
if not exist ".venv\Scripts\python.exe" (
    where py >nul 2>&1
    if errorlevel 1 (
        python -m venv .venv
    ) else (
        py -3 -m venv .venv
    )
    if errorlevel 1 goto error
)
".venv\Scripts\python.exe" -m pip install --disable-pip-version-check -r requirements-build.txt
if errorlevel 1 goto error
".venv\Scripts\python.exe" build_exe.py
if errorlevel 1 goto error
echo.
echo Готово! Файл: dist\ListPlanner.exe
echo Его можно скопировать на другой компьютер с Windows 10/11 x64.
pause
exit /b 0
:error
echo Не удалось собрать EXE. Нужен Python 3.10-3.13 x64 под Windows и интернет для установки зависимостей.
pause
exit /b 1
