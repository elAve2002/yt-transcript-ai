@echo off
setlocal
if not exist "%~dp0.venv\Scripts\python.exe" (
    echo Error: no se encontro .venv\Scripts\python.exe. Ejecuta "uv sync" primero. 1>&2
    exit /b 1
)
"%~dp0.venv\Scripts\python.exe" -m app.cli actualizar %*
exit /b %ERRORLEVEL%
