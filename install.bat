@echo off
REM Instala Jayth desde esta carpeta (sin permisos de administrador).
powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0install.ps1" %*
pause
