@echo off
chcp 65001 >nul
title GAMEB Studio - Nucleo IA V2
cd /d "%~dp0"
echo ============================================
echo      GAMEB STUDIO - NUCLEO IA V2
echo ============================================
echo.
set "PYEXE="
where py >nul 2>nul
if not errorlevel 1 (
  py -3 --version >nul 2>nul
  if not errorlevel 1 set "PYEXE=py -3"
)
if not defined PYEXE (
  where python >nul 2>nul
  if not errorlevel 1 set "PYEXE=python"
)
if not defined PYEXE (
  echo ERROR: No se encontro Python. Ejecuta la instalacion de Python 3.10 o superior.
  pause
  exit /b 1
)
echo Usando el mismo interprete que selecciona el instalador: %PYEXE%
%PYEXE% --version
%PYEXE% -c "import rembg, onnxruntime" >nul 2>nul
if errorlevel 1 (
  echo AVISO: rembg/onnxruntime no estan disponibles en este Python.
  echo Ejecuta INSTALAR_DEPENDENCIAS.bat y verifica que termine correctamente.
  echo.
)
start "" http://127.0.0.1:8766
%PYEXE% server.py
if errorlevel 1 (
  echo.
  echo GAMEB Studio se cerro con un error. Revisa el mensaje anterior.
)
pause
