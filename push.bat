@echo off
setlocal

cd /d "%~dp0"

echo.
set /p COMMITMSG=Commit-Message eingeben: 

if "%COMMITMSG%"=="" (
    echo Commit-Message darf nicht leer sein.
    pause
    exit /b 1
)

echo.
echo === Git Add ===
git add .

echo.
echo === Git Commit ===
git commit -m "%COMMITMSG%"

if errorlevel 1 (
    echo Commit fehlgeschlagen.
    pause
    exit /b 1
)

echo.
echo === Git Push ===
git push -u origin main

echo.
echo Fertig.
pause
