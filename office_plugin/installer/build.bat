@echo off
setlocal

:: LaTeXSnipper Office Plugin Installer Builder
:: Usage: build.bat [version] [config]
::   version: e.g. 1.2.3 (defaults to 0.0.0)
::   config:  Debug or Release (defaults to Release)

set VERSION=%1
if "%VERSION%"=="" set VERSION=0.0.0

set CONFIG=%2
if "%CONFIG%"=="" set CONFIG=Release

set SCRIPT_DIR=%~dp0
set PLUGIN_ROOT=%SCRIPT_DIR%..
set DIST_DIR=%PLUGIN_ROOT%\dist

echo ============================================
echo  LaTeXSnipper Office Plugin Installer Build
echo  Version: %VERSION%
echo  Configuration: %CONFIG%
echo ============================================

:: Step 1: Build Word VSTO
echo [1/4] Building Word VSTO Add-in...
call powershell -ExecutionPolicy Bypass -File "%PLUGIN_ROOT%\tools\Register-WordVstoAddIn.ps1" ^
  -Configuration %CONFIG% ^
  -SkipCertificateTrust ^
  -SkipVstoInstaller
if %ERRORLEVEL% neq 0 (
  echo ERROR: Word VSTO build failed.
  exit /b 1
)

:: Step 2: Build PowerPoint VSTO
echo [2/4] Building PowerPoint VSTO Add-in...
call powershell -ExecutionPolicy Bypass -File "%PLUGIN_ROOT%\tools\Register-PowerPointVstoAddIn.ps1" ^
  -Configuration %CONFIG% ^
  -SkipCertificateTrust ^
  -SkipVstoInstaller
if %ERRORLEVEL% neq 0 (
  echo ERROR: PowerPoint VSTO build failed.
  exit /b 1
)

:: Step 3: Build EditorAssets (dotnet build to copy to output)
echo [3/4] Copying EditorAssets...
dotnet build "%PLUGIN_ROOT%\LaTeXSnipper.OfficePlugin.slnx" -c %CONFIG% > nul 2>&1

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
