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

echo ============================================
echo  LaTeXSnipper Office Plugin Installer Build
echo  Version: %VERSION%
echo  Configuration: %CONFIG%
echo ============================================

:: Step 1: Build Word and PowerPoint VSTO add-ins without registering them
echo [1/4] Building VSTO add-ins...
call powershell -ExecutionPolicy Bypass -File "%PLUGIN_ROOT%\tools\Build-VstoAddIns.ps1" ^
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
set MSBUILD_EXE=
if exist "%ProgramFiles(x86)%\Microsoft Visual Studio\Installer\vswhere.exe" (
  for /f "usebackq delims=" %%i in (`"%ProgramFiles(x86)%\Microsoft Visual Studio\Installer\vswhere.exe" -latest -products * -requires Microsoft.VisualStudio.Component.VC.ATL -find MSBuild\Current\Bin\amd64\MSBuild.exe`) do (
    if not defined MSBUILD_EXE set "MSBUILD_EXE=%%i"
  )
)
if not defined MSBUILD_EXE if exist "D:\Microsoft Visual Studio\2026\MSBuild\Current\Bin\MSBuild.exe" (
  set "MSBUILD_EXE=D:\Microsoft Visual Studio\2026\MSBuild\Current\Bin\MSBuild.exe"
)
if not defined MSBUILD_EXE if exist "D:\Microsoft Visual Studio\2022\Community\MSBuild\Current\Bin\amd64\MSBuild.exe" (
  set "MSBUILD_EXE=D:\Microsoft Visual Studio\2022\Community\MSBuild\Current\Bin\amd64\MSBuild.exe"
)
if not defined MSBUILD_EXE (
  for /f "delims=" %%i in ('where msbuild 2^>nul') do set MSBUILD_EXE=%%i
)
if not defined MSBUILD_EXE (
  echo ERROR: MSBuild with Visual C++ support was not found.
  exit /b 1
)

"%MSBUILD_EXE%" "%PLUGIN_ROOT%\hosts\OleFormulaObjectNative\LaTeXSnipper.OfficePlugin.OleFormulaObjectHandler.vcxproj" /p:Configuration=%CONFIG% /p:Platform=x64 /m
if %ERRORLEVEL% neq 0 (
  echo ERROR: Native OLE handler x64 build failed.
  exit /b 1
)

"%MSBUILD_EXE%" "%PLUGIN_ROOT%\hosts\OleFormulaObjectNative\LaTeXSnipper.OfficePlugin.OleFormulaObjectHandler.vcxproj" /p:Configuration=%CONFIG% /p:Platform=Win32 /m
if %ERRORLEVEL% neq 0 (
  echo ERROR: Native OLE handler x86 build failed.
  exit /b 1
)

:: Export signing certificate
echo [3.5/4] Exporting certificate...
powershell -ExecutionPolicy Bypass -Command "$subject = 'CN=LaTeXSnipper Office Plugin VSTO'; $cert = Get-ChildItem Cert:\CurrentUser\My | Where-Object { $_.Subject -eq $subject } | Sort-Object NotAfter -Descending | Select-Object -First 1; if ($cert) { Export-Certificate -Cert $cert -FilePath '%SCRIPT_DIR%vsto-signing.cer' -Type CERT -Force } else { Write-Host 'WARNING: VSTO signing cert not found, installer may fail' }"

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
