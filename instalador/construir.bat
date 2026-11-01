@echo off
rem ============================================================================
rem  Construye ContFactu.exe y el instalador en un PC con Windows 10/11.
rem  Requisitos (una sola vez):
rem    1) Python 3.12 o 3.13 de 64 bits (python.org), marcando "Add python.exe to PATH".
rem    2) Inno Setup 6 (jrsoftware.org) - solo para el paso del instalador.
rem    3) Conexion a Internet la primera vez (descarga 7-Zip 25.01 de www.7-zip.org).
rem  Uso: doble clic en este archivo, o desde la carpeta del proyecto:  instalador\construir.bat
rem ============================================================================
setlocal
cd /d "%~dp0.."

if not exist venv-win\Scripts\python.exe (
  echo Creando entorno de Python...
  python -m venv venv-win || goto :error
)
call venv-win\Scripts\activate.bat
python -m pip install --upgrade pip || goto :error
python -m pip install -r requirements.txt pyinstaller || goto :error

echo Comprobando que los tests pasan...
python -m pytest -q tests || goto :error

echo Comprobando 7-Zip (para abrir copias .rar)...
rem 7-Zip no se guarda en el repositorio (LGPL + restriccion unRAR): se descarga de 7-zip.org y se comprueba su SHA-256.
if not exist instalador\7zip\7z.exe (
  if not exist instalador\7zip mkdir instalador\7zip
  powershell -NoProfile -ExecutionPolicy Bypass -File instalador\obtener_7zip.ps1 || goto :error
)

echo Empaquetando con PyInstaller...
if exist build rmdir /s /q build
if exist dist rmdir /s /q dist
for /f "usebackq delims=" %%v in (`python -c "import app; print(app.__version__)"`) do set VERSION=%%v
echo Version: %VERSION%
pyinstaller --noconfirm instalador\ContFactu.spec || goto :error

rem Seguridad: el paquete NO debe contener datos
dir /s /b dist\ContFactu | findstr /i /e ".db .dbf .pdf" && (echo ERROR: hay datos dentro de dist & goto :error)

set ISCC="%ProgramFiles(x86)%\Inno Setup 6\ISCC.exe"
if not exist %ISCC% set ISCC="%LOCALAPPDATA%\Programs\Inno Setup 6\ISCC.exe"
if not exist %ISCC% set ISCC="%ProgramFiles%\Inno Setup 6\ISCC.exe"
if exist %ISCC% (
  %ISCC% /DMyAppVersion=%VERSION% instalador\ContFactu.iss || goto :error
  echo.
  echo LISTO: instalador\Output\ContFactu-Setup-%VERSION%.exe
) else (
  echo.
  echo Inno Setup no esta instalado: se ha creado solo dist\ContFactu\ContFactu.exe
  echo Instale Inno Setup 6 y vuelva a ejecutar este archivo para obtener el instalador.
)
if not defined CONTFACTU_NOPAUSE pause
exit /b 0

:error
echo.
echo *** Ha fallado la construccion. Revise los mensajes de arriba. ***
if not defined CONTFACTU_NOPAUSE pause
exit /b 1
