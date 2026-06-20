@echo off
if not "%1"=="silent" (
    start "" /min "%~f0" silent
    exit
)
cd /d "%~dp0"
pythonw "%~dp0deepseek_monitor.pyw"
