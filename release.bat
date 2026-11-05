@echo off
chcp 65001 >nul
python "%~dp0scripts\release.py" %*
if %ERRORLEVEL% NEQ 0 (
    pause
)

