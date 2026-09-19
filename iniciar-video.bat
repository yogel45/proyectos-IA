@echo off
title Video - OfficeVision AI
cd /d "%~dp0"
set PY=python
where python >nul 2>nul || set PY=py
echo.
echo  OfficeVision AI  ->  http://127.0.0.1:8000
echo  (deja esta ventana abierta; cierrala para apagar)
echo.
%PY% run.py
pause
