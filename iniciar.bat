@echo off
title Proyectos IA - lanzador
rem Arranca las tres aplicaciones, cada una en su ventana. Al cerrar esas
rem ventanas se apaga todo.

cd /d "%~dp0"
set PY=python
where python >nul 2>nul || set PY=py

echo.
echo  Instalando lo que falte (la primera vez tarda varios minutos)...
%PY% -m pip install -r requirements.txt --quiet --disable-pip-version-check

echo.
echo  Arrancando las tres aplicaciones...
start "Video - NO CERRAR"      /d "%~dp0" cmd /k %PY% run.py --no-browser
start "Documentos - NO CERRAR" /d "%~dp0" cmd /k %PY% run_documentos.py --no-browser
start "Contactos - NO CERRAR"  /d "%~dp0" cmd /k %PY% run_contactos.py --no-browser

echo  Esperando a que respondan...
timeout /t 12 /nobreak >nul

start "" http://127.0.0.1:8100

echo.
echo  Listo. Si el navegador no se abrio, entra a:
echo     Video       http://127.0.0.1:8000
echo     Documentos  http://127.0.0.1:8100
echo     Contactos   http://127.0.0.1:8200
echo.
echo  Para apagar todo, cierra las tres ventanas negras.
echo.
pause
