@echo off
REM Instala Agente Local desde esta carpeta (sin permisos de administrador).
powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0install.ps1" %*
pause
