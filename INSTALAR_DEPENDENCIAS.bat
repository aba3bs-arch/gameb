@echo off
chcp 65001 >nul
title GAMEB Studio - Instalador de dependencias
cd /d "%~dp0"
echo ============================================
echo  GAMEB STUDIO - INSTALADOR DE DEPENDENCIAS
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
  echo ERROR: No se encontro Python 3.10 o superior.
  echo Instala Python desde python.org y marca Add Python to PATH.
  pause
  exit /b 1
)
echo Python seleccionado: %PYEXE%
%PYEXE% --version
if errorlevel 1 goto error

echo.
echo [1/4] Actualizando pip...
%PYEXE% -m pip install --upgrade pip
if errorlevel 1 goto error

echo.
echo [2/4] Instalando dependencias del proyecto...
%PYEXE% -m pip install -r requirements.txt
if errorlevel 1 goto error

echo.
echo [3/4] Verificando motor de siluetas (rembg)...
%PYEXE% -c "from rembg import new_session, remove; import onnxruntime; print('rembg y onnxruntime importados correctamente'); print('Proveedores ONNX:', onnxruntime.get_available_providers())"
if errorlevel 1 (
  echo.
  echo No se pudo importar el motor. Intentando instalar los paquetes directamente...
  %PYEXE% -m pip install --upgrade "rembg[cpu]>=2.0.60,<3.0.0" onnxruntime
  if errorlevel 1 goto error
  %PYEXE% -c "from rembg import new_session, remove; import onnxruntime; print('Motor rembg listo')"
  if errorlevel 1 goto error
)
echo.
echo [4/4] Preparando el modelo de recorte (la primera vez puede tardar)...
%PYEXE% -c "from rembg import new_session; new_session('isnet-general-use'); print('Modelo isnet-general-use listo')"
if errorlevel 1 (
  echo AVISO: no se pudo preparar isnet-general-use. El desarmador intentara u2net al recortar.
)
echo.
echo Instalacion y verificacion completadas.
echo IMPORTANTE: inicia GAMEB Studio con INICIAR_GAMEB_STUDIO.bat para usar el mismo Python.
echo La primera segmentacion puede tardar si el modelo todavia no se descargo.
pause
exit /b 0
:error
echo.
echo ERROR: La instalacion o verificacion fallo.
echo Copia el mensaje anterior para diagnosticarlo. Comprueba internet y que Python sea compatible.
pause
exit /b 1
