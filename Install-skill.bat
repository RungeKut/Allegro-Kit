@echo off
rem Installs Allegro-Kit by double click.
rem
rem Wrapper around tools\setup.ps1: execution policy is lifted for this run
rem only, the script path is taken next to this file, and the window stays
rem open until the messages are read. No administrator rights needed.
rem
rem All messages are printed by setup.ps1 itself: PowerShell writes unicode
rem to the console regardless of the code page. Here echo is Latin only -
rem cmd reads this file in the current code page and Russian text would be
rem garbled on some machines.

setlocal
powershell.exe -NoProfile -ExecutionPolicy Bypass -File "%~dp0tools\setup.ps1"
set RC=%ERRORLEVEL%

if not %RC% equ 0 (
    echo.
    echo SETUP FAILED, exit code %RC% -- see the message above.
)
echo.
pause
endlocal & exit /b %RC%
