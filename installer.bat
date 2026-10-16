@echo off
rem Install / re-apply the WinWing MCDU setup for the Fenix A320 (see README.md)
cd /d "%~dp0"
python setup_mcdu.py %*
echo.
pause
