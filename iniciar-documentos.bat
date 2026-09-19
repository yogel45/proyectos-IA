@echo off
title Documentos - DocuFlow AI
cd /d "%~dp0"
set PY=python
where python >nul 2>nul || set PY=py
echo.
echo  DocuFlow AI  ->  http://127.0.0.1:8100
echo  (deja esta ventana abierta; cierrala para apagar)
echo.
%PY% run_documentos.py
pause
