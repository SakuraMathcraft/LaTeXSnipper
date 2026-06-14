@echo off
setlocal

:: LaTeXSnipper Office Plugin Installer Builder
:: Usage: build.bat [version] [config]
::   config:  Debug or Release (defaults to Release)

set VERSION=%1
if "%VERSION%"=="" set VERSION=2.3.2

set CONFIG=%2
if "%CONFIG%"=="" set CONFIG=Release

set SCRIPT_DIR=%~dp0
set PLUGIN_ROOT=%SCRIPT_DIR%..
set DIST_DIR=%PLUGIN_ROOT%\dist
set WINDOWS_POWERSHELL=%SystemRoot%\System32\WindowsPowerShell\v1.0\powershell.exe

if not exist "%WINDOWS_POWERSHELL%" (
  echo ERROR: Windows PowerShell is required for VSTO certificate signing.
  exit /b 1
)

echo ============================================
echo  LaTeXSnipper Office Plugin Installer Build
echo  Version: %VERSION%
echo  Configuration: %CONFIG%
echo ============================================

:: Step 1: Build Word and PowerPoint VSTO add-ins without registering them
echo [1/4] Building VSTO add-ins...
"%WINDOWS_POWERSHELL%" -NoProfile -ExecutionPolicy Bypass -File "%PLUGIN_ROOT%\tools\Build-VstoAddIns.ps1" ^
  -Configuration %CONFIG%
if %ERRORLEVEL% neq 0 (
  echo ERROR: VSTO build failed.
  exit /b 1
)

:: Step 2: Build EditorAssets (dotnet build to copy to output)
echo [2/4] Building shared libraries and EditorAssets...
dotnet build "%PLUGIN_ROOT%\LaTeXSnipper.OfficePlugin.slnx" -c %CONFIG%
if %ERRORLEVEL% neq 0 (
  echo ERROR: Shared build failed.
  exit /b 1
)

:: Step 3: Build native OLE formula object handler for 64-bit and 32-bit Office
echo [3/4] Building native OLE formula object handler...
"%WINDOWS_POWERSHELL%" -NoProfile -ExecutionPolicy Bypass -File "%PLUGIN_ROOT%\tools\Build-NativeOleHandler.ps1" ^
  -Configuration %CONFIG%
if %ERRORLEVEL% neq 0 (
  echo ERROR: Native OLE handler build failed.
  exit /b 1
)

:: Step 4: Run Inno Setup
echo [4/4] Building installer...
if not exist "%DIST_DIR%" mkdir "%DIST_DIR%"

:: Find Inno Setup ISCC.exe from PATH or common install locations
for %%d in ("%ProgramFiles(x86)%\Inno Setup 6" "%ProgramFiles%\Inno Setup 6") do (
  if exist "%%~d\ISCC.exe" set ISCC=%%~d\ISCC.exe
)
if not defined ISCC (
  for /f "delims=" %%i in ('where iscc 2^>nul') do set ISCC=%%i
)
if not defined ISCC (
  echo ERROR: Inno Setup 6 not found. Install from https://jrsoftware.org/isinfo.php
  exit /b 1
)

"%ISCC%" /DVersion=%VERSION% /DConfig=%CONFIG% "%SCRIPT_DIR%setup.iss"
if %ERRORLEVEL% neq 0 (
  echo ERROR: Installer build failed.
  exit /b 1
)

echo ============================================
echo  Installer built successfully!
echo  Output: %DIST_DIR%\OfficePluginSetup-%VERSION%.exe
echo ============================================
