@echo off
title Contactos - Directorio vivo
cd /d "%~dp0"
set PY=python
where python >nul 2>nul || set PY=py
echo.
echo  Directorio vivo  ->  http://127.0.0.1:8200
echo  (la primera vez carga los datos; deja esta ventana abierta)
echo.
if not exist "data\contactos\contactos.db" %PY% run_contactos.py --importar
%PY% run_contactos.py
pause
