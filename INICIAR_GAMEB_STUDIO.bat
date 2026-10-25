@echo off
chcp 65001 >nul
title GAMEB Studio - version nueva
cd /d "%~dp0"
echo ============================================
echo      GAMEB STUDIO - VERSION NUEVA
echo ============================================
echo.
echo Esta ventana cierra el programa viejo y abre el nuevo.
echo La direccion del navegador sigue siendo la misma.
echo Lo que cambia es el texto de la pagina.
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
echo Usando: %PYEXE%
%PYEXE% --version
%PYEXE% -c "import rembg, onnxruntime" >nul 2>nul
if errorlevel 1 (
  echo AVISO: rembg/onnxruntime no estan disponibles en este Python.
  echo Ejecuta INSTALAR_DEPENDENCIAS.bat y verifica que termine correctamente.
  echo.
)
echo Cerrando el programa viejo...
for /f "tokens=5" %%a in ('netstat -ano ^| findstr ":8766" ^| findstr /I "LISTENING ESCUCHANDO"') do taskkill /F /PID %%a >nul 2>nul
echo Programa viejo cerrado.
timeout /t 1 /nobreak >nul
echo Abriendo el servidor nuevo. Deja abierta la otra ventana negra.
start "GAMEB Studio - version nueva" /D "%~dp0" %PYEXE% server.py
powershell -NoProfile -Command "$ok=$false; for($i=0; $i -lt 40; $i++){ try { $r=Invoke-WebRequest -UseBasicParsing 'http://127.0.0.1:8766/health' -TimeoutSec 2; if($r.Content -match 'nueva'){ $ok=$true; break } } catch { Start-Sleep -Milliseconds 500 } }; if(-not $ok){ exit 1 }"
if errorlevel 1 (
  echo.
  echo Sigue abierto el programa viejo. Cierra la ventana negra que dice Nucleo IA V2.
  echo Despues vuelve a hacer doble clic en este archivo.
  pause
  exit /b 1
)
start "" "http://127.0.0.1:8766/desarmador.html?nueva=1"
echo.
echo Listo. En la pagina, debajo del titulo, debe decir: Mandas el boceto. El estudio hace una imagen, luego la siguiente.
echo Si no lo dice, cierra Edge por completo y vuelve a hacer doble clic en este archivo.
echo.
pause
