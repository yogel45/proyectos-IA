@echo off
title Reto 7 - Pruebas de carga sobre ContactHub
cd /d "%~dp0"

set PY=python
%PY% --version >/dev/null 2>&1 || set PY=py

echo.
echo  ============================================================
echo   Reto 7 - Pruebas de trafico y carga sobre ContactHub
echo  ============================================================
echo.
echo  Antes de seguir, ContactHub tiene que estar arrancado.
echo  Si no lo esta, abre su iniciar.bat y espera a que diga
echo  que esta en http://localhost:8765
echo.
echo  Si ContactHub esta en otra carpeta, arrastra aqui su carpeta
echo  o escribe la ruta. Si ya esta arrancado, pulsa Enter.
echo.
set RUTA=
set /p RUTA=  Carpeta de ContactHub (Enter para omitir): 

echo.
echo  Comprobando el entorno...
echo.
if defined RUTA (
  %PY% run_pruebas.py --check --ruta %RUTA%
) else (
  %PY% run_pruebas.py --check
)
if errorlevel 1 goto error

echo.
echo  Todo listo. La sesion completa tarda unos 20 minutos.
echo  Deja esta ventana abierta; al final dice donde quedaron
echo  los resultados y las graficas.
echo.
pause

if defined RUTA (
  %PY% run_pruebas.py --ruta %RUTA%
) else (
  %PY% run_pruebas.py
)
goto fin

:error
echo.
echo  Falta algo. Si son dependencias:  pip install -r requirements.txt
echo  Si es ContactHub, arrancalo con su iniciar.bat y vuelve a intentarlo.

:fin
echo.
pause
