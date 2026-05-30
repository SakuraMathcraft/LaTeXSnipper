; LaTeXSnipper Office Plugin - Inno Setup Installer
; Build: iscc /DVersion=%VERSION% /DConfig=Release installer.iss
;   or for Debug: iscc /DVersion=0.0.0 /DConfig=Debug installer.iss

#define AppName "LaTeXSnipper Office Plugin"
#define AppPublisher "SakuraMathcraft"
#define AppUrl "https://github.com/SakuraMathcraft/LaTeXSnipper"
#define WordAddInName "LaTeXSnipper.OfficePlugin.WordVstoAddIn"
#define PowerPointAddInName "LaTeXSnipper.OfficePlugin.PowerPointVstoAddIn"

#ifndef Version
  #define Version "0.0.0"
#endif
#ifndef Config
  #define Config "Release"
#endif

[Setup]
AppId={{B8F4A3D2-7E6C-4F91-A2B5-9D3C8E1F6A07}}
AppName={#AppName}
AppVersion={#Version}
AppPublisher={#AppPublisher}
AppPublisherURL={#AppUrl}
DefaultDirName={commonpf}\LaTeXSnipper\OfficePlugin
DefaultGroupName=LaTeXSnipper
DisableProgramGroupPage=yes
OutputDir=..\dist
OutputBaseFilename=OfficePluginSetup-{#Version}
Compression=lzma2
SolidCompression=yes
PrivilegesRequired=admin
ArchitecturesInstallIn64BitMode=x64compatible
WizardStyle=modern
SetupIconFile=icon.ico
UninstallDisplayIcon={app}\Word\icon.ico
LicenseFile=LICENSE.txt

[Languages]
Name: "english"; MessagesFile: "compiler:Default.isl"
Name: "chinesesimplified"; MessagesFile: "ChineseSimplified.isl"

[Files]
; ===== Word VSTO Add-in =====
Source: "..\hosts\WordVstoAddIn\bin\{#Config}\LaTeXSnipper.OfficePlugin.WordVstoAddIn.vsto"; \
  DestDir: "{app}\Word"; Flags: ignoreversion
Source: "..\hosts\WordVstoAddIn\bin\{#Config}\LaTeXSnipper.OfficePlugin.WordVstoAddIn.dll"; \
  DestDir: "{app}\Word"; Flags: ignoreversion
Source: "..\hosts\WordVstoAddIn\bin\{#Config}\LaTeXSnipper.OfficePlugin.WordVstoAddIn.dll.manifest"; \
  DestDir: "{app}\Word"; Flags: ignoreversion
Source: "..\hosts\WordVstoAddIn\bin\{#Config}\LaTeXSnipper.OfficePlugin.WordAddIn.dll"; \
  DestDir: "{app}\Word"; Flags: ignoreversion
Source: "..\hosts\WordVstoAddIn\bin\{#Config}\LaTeXSnipper.OfficePlugin.Abstractions.dll"; \
  DestDir: "{app}\Word"; Flags: ignoreversion
Source: "..\hosts\WordVstoAddIn\bin\{#Config}\LaTeXSnipper.OfficePlugin.Bridge.dll"; \
  DestDir: "{app}\Word"; Flags: ignoreversion
Source: "..\hosts\WordVstoAddIn\bin\{#Config}\LaTeXSnipper.OfficePlugin.Editor.dll"; \
  DestDir: "{app}\Word"; Flags: ignoreversion
Source: "..\hosts\WordVstoAddIn\bin\{#Config}\Microsoft.Office.Tools.Common.v4.0.Utilities.dll"; \
  DestDir: "{app}\Word"; Flags: ignoreversion
Source: "..\hosts\WordVstoAddIn\bin\{#Config}\Microsoft.Web.WebView2.Core.dll"; \
  DestDir: "{app}\Word"; Flags: ignoreversion
Source: "..\hosts\WordVstoAddIn\bin\{#Config}\Microsoft.Web.WebView2.WinForms.dll"; \
  DestDir: "{app}\Word"; Flags: ignoreversion

; ===== PowerPoint VSTO Add-in =====
Source: "..\hosts\PowerPointVstoAddIn\bin\{#Config}\LaTeXSnipper.OfficePlugin.PowerPointVstoAddIn.vsto"; \
  DestDir: "{app}\PowerPoint"; Flags: ignoreversion
Source: "..\hosts\PowerPointVstoAddIn\bin\{#Config}\LaTeXSnipper.OfficePlugin.PowerPointVstoAddIn.dll"; \
  DestDir: "{app}\PowerPoint"; Flags: ignoreversion
Source: "..\hosts\PowerPointVstoAddIn\bin\{#Config}\LaTeXSnipper.OfficePlugin.PowerPointVstoAddIn.dll.manifest"; \
  DestDir: "{app}\PowerPoint"; Flags: ignoreversion
Source: "..\hosts\PowerPointVstoAddIn\bin\{#Config}\LaTeXSnipper.OfficePlugin.PowerPointAddIn.dll"; \
  DestDir: "{app}\PowerPoint"; Flags: ignoreversion
Source: "..\hosts\PowerPointVstoAddIn\bin\{#Config}\LaTeXSnipper.OfficePlugin.Abstractions.dll"; \
  DestDir: "{app}\PowerPoint"; Flags: ignoreversion
Source: "..\hosts\PowerPointVstoAddIn\bin\{#Config}\LaTeXSnipper.OfficePlugin.Bridge.dll"; \
  DestDir: "{app}\PowerPoint"; Flags: ignoreversion
Source: "..\hosts\PowerPointVstoAddIn\bin\{#Config}\LaTeXSnipper.OfficePlugin.Editor.dll"; \
  DestDir: "{app}\PowerPoint"; Flags: ignoreversion
Source: "..\hosts\PowerPointVstoAddIn\bin\{#Config}\Microsoft.Office.Tools.Common.v4.0.Utilities.dll"; \
  DestDir: "{app}\PowerPoint"; Flags: ignoreversion
Source: "..\hosts\PowerPointVstoAddIn\bin\{#Config}\Microsoft.Web.WebView2.Core.dll"; \
  DestDir: "{app}\PowerPoint"; Flags: ignoreversion
Source: "..\hosts\PowerPointVstoAddIn\bin\{#Config}\Microsoft.Web.WebView2.WinForms.dll"; \
  DestDir: "{app}\PowerPoint"; Flags: ignoreversion

; ===== Certificate =====
Source: "devcert.cer"; DestDir: "{app}"; Flags: ignoreversion

; ===== VSTO inclusion helper script =====
Source: "WriteVstoInclusions.ps1"; DestDir: "{app}"; Flags: ignoreversion

; ===== Force cleanup script =====
; Pre-install copy extracted to {tmp} via ExtractTemporaryFile, runs BEFORE registry/VSTO
Source: "..\tools\ForceClean.ps1"; DestDir: "{tmp}"; Flags: dontcopy
; Runtime copy installed to {app} for use during uninstall
Source: "..\tools\ForceClean.ps1"; DestDir: "{app}"; Flags: ignoreversion

; ===== Icon =====
Source: "icon.ico"; DestDir: "{app}\Word"; Flags: ignoreversion
Source: "icon.ico"; DestDir: "{app}\PowerPoint"; Flags: ignoreversion

; ===== EditorAssets (shared, installed alongside both hosts) =====
Source: "..\hosts\WordAddIn\bin\{#Config}\net48\EditorAssets\*"; \
  DestDir: "{app}\Word\EditorAssets"; Flags: ignoreversion recursesubdirs
Source: "..\hosts\PowerPointAddIn\bin\{#Config}\net48\EditorAssets\*"; \
  DestDir: "{app}\PowerPoint\EditorAssets"; Flags: ignoreversion recursesubdirs

[Registry]
; ===== Word Add-in (versionless path) =====
Root: HKLM; Subkey: "Software\Microsoft\Office\Word\Addins\{#WordAddInName}"; \
  ValueType: string; ValueName: "Description"; ValueData: "LaTeXSnipper native Word plugin"; Flags: uninsdeletekey
Root: HKLM; Subkey: "Software\Microsoft\Office\Word\Addins\{#WordAddInName}"; \
  ValueType: string; ValueName: "FriendlyName"; ValueData: "LaTeXSnipper"; Flags: uninsdeletekey
Root: HKLM; Subkey: "Software\Microsoft\Office\Word\Addins\{#WordAddInName}"; \
  ValueType: dword; ValueName: "LoadBehavior"; ValueData: "3"; Flags: uninsdeletekey
Root: HKLM; Subkey: "Software\Microsoft\Office\Word\Addins\{#WordAddInName}"; \
  ValueType: string; ValueName: "Manifest"; ValueData: "{code:GetManifestUri|Word\{#WordAddInName}.vsto}"; Flags: uninsdeletekey
Root: HKLM; Subkey: "Software\Microsoft\Office\Word\Addins\{#WordAddInName}"; \
  ValueType: dword; ValueName: "CommandLineSafe"; ValueData: "1"; Flags: uninsdeletekey

; ===== Word Add-in (Office 16.0 path) =====
Root: HKLM; Subkey: "Software\Microsoft\Office\16.0\Word\Addins\{#WordAddInName}"; \
  ValueType: string; ValueName: "Description"; ValueData: "LaTeXSnipper native Word plugin"; Flags: uninsdeletekey
Root: HKLM; Subkey: "Software\Microsoft\Office\16.0\Word\Addins\{#WordAddInName}"; \
  ValueType: string; ValueName: "FriendlyName"; ValueData: "LaTeXSnipper"; Flags: uninsdeletekey
Root: HKLM; Subkey: "Software\Microsoft\Office\16.0\Word\Addins\{#WordAddInName}"; \
  ValueType: dword; ValueName: "LoadBehavior"; ValueData: "3"; Flags: uninsdeletekey
Root: HKLM; Subkey: "Software\Microsoft\Office\16.0\Word\Addins\{#WordAddInName}"; \
  ValueType: string; ValueName: "Manifest"; ValueData: "{code:GetManifestUri|Word\{#WordAddInName}.vsto}"; Flags: uninsdeletekey
Root: HKLM; Subkey: "Software\Microsoft\Office\16.0\Word\Addins\{#WordAddInName}"; \
  ValueType: dword; ValueName: "CommandLineSafe"; ValueData: "1"; Flags: uninsdeletekey

; ===== Word Add-in (WOW6432Node for 32-bit Office on 64-bit Windows) =====
Root: HKLM; Subkey: "Software\WOW6432Node\Microsoft\Office\Word\Addins\{#WordAddInName}"; \
  ValueType: string; ValueName: "Description"; ValueData: "LaTeXSnipper native Word plugin"; Flags: uninsdeletekey; Check: IsWin64
Root: HKLM; Subkey: "Software\WOW6432Node\Microsoft\Office\Word\Addins\{#WordAddInName}"; \
  ValueType: string; ValueName: "FriendlyName"; ValueData: "LaTeXSnipper"; Flags: uninsdeletekey; Check: IsWin64
Root: HKLM; Subkey: "Software\WOW6432Node\Microsoft\Office\Word\Addins\{#WordAddInName}"; \
  ValueType: dword; ValueName: "LoadBehavior"; ValueData: "3"; Flags: uninsdeletekey; Check: IsWin64
Root: HKLM; Subkey: "Software\WOW6432Node\Microsoft\Office\Word\Addins\{#WordAddInName}"; \
  ValueType: string; ValueName: "Manifest"; ValueData: "{code:GetManifestUri|Word\{#WordAddInName}.vsto}"; Flags: uninsdeletekey; Check: IsWin64
Root: HKLM; Subkey: "Software\WOW6432Node\Microsoft\Office\Word\Addins\{#WordAddInName}"; \
  ValueType: dword; ValueName: "CommandLineSafe"; ValueData: "1"; Flags: uninsdeletekey; Check: IsWin64
Root: HKLM; Subkey: "Software\WOW6432Node\Microsoft\Office\16.0\Word\Addins\{#WordAddInName}"; \
  ValueType: string; ValueName: "Description"; ValueData: "LaTeXSnipper native Word plugin"; Flags: uninsdeletekey; Check: IsWin64
Root: HKLM; Subkey: "Software\WOW6432Node\Microsoft\Office\16.0\Word\Addins\{#WordAddInName}"; \
  ValueType: string; ValueName: "FriendlyName"; ValueData: "LaTeXSnipper"; Flags: uninsdeletekey; Check: IsWin64
Root: HKLM; Subkey: "Software\WOW6432Node\Microsoft\Office\16.0\Word\Addins\{#WordAddInName}"; \
  ValueType: dword; ValueName: "LoadBehavior"; ValueData: "3"; Flags: uninsdeletekey; Check: IsWin64
Root: HKLM; Subkey: "Software\WOW6432Node\Microsoft\Office\16.0\Word\Addins\{#WordAddInName}"; \
  ValueType: string; ValueName: "Manifest"; ValueData: "{code:GetManifestUri|Word\{#WordAddInName}.vsto}"; Flags: uninsdeletekey; Check: IsWin64
Root: HKLM; Subkey: "Software\WOW6432Node\Microsoft\Office\16.0\Word\Addins\{#WordAddInName}"; \
  ValueType: dword; ValueName: "CommandLineSafe"; ValueData: "1"; Flags: uninsdeletekey; Check: IsWin64

; ===== Word Add-in (ClickToRun virtualized registry — required for Office 365 / C2R) =====
Root: HKLM; Subkey: "Software\Microsoft\Office\ClickToRun\REGISTRY\MACHINE\Software\Microsoft\Office\Word\Addins\{#WordAddInName}"; \
  ValueType: string; ValueName: "Description"; ValueData: "LaTeXSnipper native Word plugin"; Flags: uninsdeletekey
Root: HKLM; Subkey: "Software\Microsoft\Office\ClickToRun\REGISTRY\MACHINE\Software\Microsoft\Office\Word\Addins\{#WordAddInName}"; \
  ValueType: string; ValueName: "FriendlyName"; ValueData: "LaTeXSnipper"; Flags: uninsdeletekey
Root: HKLM; Subkey: "Software\Microsoft\Office\ClickToRun\REGISTRY\MACHINE\Software\Microsoft\Office\Word\Addins\{#WordAddInName}"; \
  ValueType: dword; ValueName: "LoadBehavior"; ValueData: "3"; Flags: uninsdeletekey
Root: HKLM; Subkey: "Software\Microsoft\Office\ClickToRun\REGISTRY\MACHINE\Software\Microsoft\Office\Word\Addins\{#WordAddInName}"; \
  ValueType: string; ValueName: "Manifest"; ValueData: "{code:GetManifestUri|Word\{#WordAddInName}.vsto}"; Flags: uninsdeletekey
Root: HKLM; Subkey: "Software\Microsoft\Office\ClickToRun\REGISTRY\MACHINE\Software\Microsoft\Office\Word\Addins\{#WordAddInName}"; \
  ValueType: dword; ValueName: "CommandLineSafe"; ValueData: "1"; Flags: uninsdeletekey

Root: HKLM; Subkey: "Software\Microsoft\Office\ClickToRun\REGISTRY\MACHINE\Software\Microsoft\Office\16.0\Word\Addins\{#WordAddInName}"; \
  ValueType: string; ValueName: "Description"; ValueData: "LaTeXSnipper native Word plugin"; Flags: uninsdeletekey
Root: HKLM; Subkey: "Software\Microsoft\Office\ClickToRun\REGISTRY\MACHINE\Software\Microsoft\Office\16.0\Word\Addins\{#WordAddInName}"; \
  ValueType: string; ValueName: "FriendlyName"; ValueData: "LaTeXSnipper"; Flags: uninsdeletekey
Root: HKLM; Subkey: "Software\Microsoft\Office\ClickToRun\REGISTRY\MACHINE\Software\Microsoft\Office\16.0\Word\Addins\{#WordAddInName}"; \
  ValueType: dword; ValueName: "LoadBehavior"; ValueData: "3"; Flags: uninsdeletekey
Root: HKLM; Subkey: "Software\Microsoft\Office\ClickToRun\REGISTRY\MACHINE\Software\Microsoft\Office\16.0\Word\Addins\{#WordAddInName}"; \
  ValueType: string; ValueName: "Manifest"; ValueData: "{code:GetManifestUri|Word\{#WordAddInName}.vsto}"; Flags: uninsdeletekey
Root: HKLM; Subkey: "Software\Microsoft\Office\ClickToRun\REGISTRY\MACHINE\Software\Microsoft\Office\16.0\Word\Addins\{#WordAddInName}"; \
  ValueType: dword; ValueName: "CommandLineSafe"; ValueData: "1"; Flags: uninsdeletekey

Root: HKLM; Subkey: "Software\WOW6432Node\Microsoft\Office\ClickToRun\REGISTRY\MACHINE\Software\Microsoft\Office\Word\Addins\{#WordAddInName}"; \
  ValueType: string; ValueName: "Description"; ValueData: "LaTeXSnipper native Word plugin"; Flags: uninsdeletekey; Check: IsWin64
Root: HKLM; Subkey: "Software\WOW6432Node\Microsoft\Office\ClickToRun\REGISTRY\MACHINE\Software\Microsoft\Office\Word\Addins\{#WordAddInName}"; \
  ValueType: string; ValueName: "FriendlyName"; ValueData: "LaTeXSnipper"; Flags: uninsdeletekey; Check: IsWin64
Root: HKLM; Subkey: "Software\WOW6432Node\Microsoft\Office\ClickToRun\REGISTRY\MACHINE\Software\Microsoft\Office\Word\Addins\{#WordAddInName}"; \
  ValueType: dword; ValueName: "LoadBehavior"; ValueData: "3"; Flags: uninsdeletekey; Check: IsWin64
Root: HKLM; Subkey: "Software\WOW6432Node\Microsoft\Office\ClickToRun\REGISTRY\MACHINE\Software\Microsoft\Office\Word\Addins\{#WordAddInName}"; \
  ValueType: string; ValueName: "Manifest"; ValueData: "{code:GetManifestUri|Word\{#WordAddInName}.vsto}"; Flags: uninsdeletekey; Check: IsWin64
Root: HKLM; Subkey: "Software\WOW6432Node\Microsoft\Office\ClickToRun\REGISTRY\MACHINE\Software\Microsoft\Office\Word\Addins\{#WordAddInName}"; \
  ValueType: dword; ValueName: "CommandLineSafe"; ValueData: "1"; Flags: uninsdeletekey; Check: IsWin64

Root: HKLM; Subkey: "Software\WOW6432Node\Microsoft\Office\ClickToRun\REGISTRY\MACHINE\Software\Microsoft\Office\16.0\Word\Addins\{#WordAddInName}"; \
  ValueType: string; ValueName: "Description"; ValueData: "LaTeXSnipper native Word plugin"; Flags: uninsdeletekey; Check: IsWin64
Root: HKLM; Subkey: "Software\WOW6432Node\Microsoft\Office\ClickToRun\REGISTRY\MACHINE\Software\Microsoft\Office\16.0\Word\Addins\{#WordAddInName}"; \
  ValueType: string; ValueName: "FriendlyName"; ValueData: "LaTeXSnipper"; Flags: uninsdeletekey; Check: IsWin64
Root: HKLM; Subkey: "Software\WOW6432Node\Microsoft\Office\ClickToRun\REGISTRY\MACHINE\Software\Microsoft\Office\16.0\Word\Addins\{#WordAddInName}"; \
  ValueType: dword; ValueName: "LoadBehavior"; ValueData: "3"; Flags: uninsdeletekey; Check: IsWin64
Root: HKLM; Subkey: "Software\WOW6432Node\Microsoft\Office\ClickToRun\REGISTRY\MACHINE\Software\Microsoft\Office\16.0\Word\Addins\{#WordAddInName}"; \
  ValueType: string; ValueName: "Manifest"; ValueData: "{code:GetManifestUri|Word\{#WordAddInName}.vsto}"; Flags: uninsdeletekey; Check: IsWin64
Root: HKLM; Subkey: "Software\WOW6432Node\Microsoft\Office\ClickToRun\REGISTRY\MACHINE\Software\Microsoft\Office\16.0\Word\Addins\{#WordAddInName}"; \
  ValueType: dword; ValueName: "CommandLineSafe"; ValueData: "1"; Flags: uninsdeletekey; Check: IsWin64

; ===== PowerPoint Add-in (versionless path) =====
Root: HKLM; Subkey: "Software\Microsoft\Office\PowerPoint\Addins\{#PowerPointAddInName}"; \
  ValueType: string; ValueName: "Description"; ValueData: "LaTeXSnipper native PowerPoint plugin"; Flags: uninsdeletekey
Root: HKLM; Subkey: "Software\Microsoft\Office\PowerPoint\Addins\{#PowerPointAddInName}"; \
  ValueType: string; ValueName: "FriendlyName"; ValueData: "LaTeXSnipper"; Flags: uninsdeletekey
Root: HKLM; Subkey: "Software\Microsoft\Office\PowerPoint\Addins\{#PowerPointAddInName}"; \
  ValueType: dword; ValueName: "LoadBehavior"; ValueData: "3"; Flags: uninsdeletekey
Root: HKLM; Subkey: "Software\Microsoft\Office\PowerPoint\Addins\{#PowerPointAddInName}"; \
  ValueType: string; ValueName: "Manifest"; ValueData: "{code:GetManifestUri|PowerPoint\{#PowerPointAddInName}.vsto}"; Flags: uninsdeletekey
Root: HKLM; Subkey: "Software\Microsoft\Office\PowerPoint\Addins\{#PowerPointAddInName}"; \
  ValueType: dword; ValueName: "CommandLineSafe"; ValueData: "1"; Flags: uninsdeletekey

; ===== PowerPoint Add-in (Office 16.0 path) =====
Root: HKLM; Subkey: "Software\Microsoft\Office\16.0\PowerPoint\Addins\{#PowerPointAddInName}"; \
  ValueType: string; ValueName: "Description"; ValueData: "LaTeXSnipper native PowerPoint plugin"; Flags: uninsdeletekey
Root: HKLM; Subkey: "Software\Microsoft\Office\16.0\PowerPoint\Addins\{#PowerPointAddInName}"; \
  ValueType: string; ValueName: "FriendlyName"; ValueData: "LaTeXSnipper"; Flags: uninsdeletekey
Root: HKLM; Subkey: "Software\Microsoft\Office\16.0\PowerPoint\Addins\{#PowerPointAddInName}"; \
  ValueType: dword; ValueName: "LoadBehavior"; ValueData: "3"; Flags: uninsdeletekey
Root: HKLM; Subkey: "Software\Microsoft\Office\16.0\PowerPoint\Addins\{#PowerPointAddInName}"; \
  ValueType: string; ValueName: "Manifest"; ValueData: "{code:GetManifestUri|PowerPoint\{#PowerPointAddInName}.vsto}"; Flags: uninsdeletekey
Root: HKLM; Subkey: "Software\Microsoft\Office\16.0\PowerPoint\Addins\{#PowerPointAddInName}"; \
  ValueType: dword; ValueName: "CommandLineSafe"; ValueData: "1"; Flags: uninsdeletekey

; ===== PowerPoint Add-in (WOW6432Node) =====
Root: HKLM; Subkey: "Software\WOW6432Node\Microsoft\Office\PowerPoint\Addins\{#PowerPointAddInName}"; \
  ValueType: string; ValueName: "Description"; ValueData: "LaTeXSnipper native PowerPoint plugin"; Flags: uninsdeletekey; Check: IsWin64
Root: HKLM; Subkey: "Software\WOW6432Node\Microsoft\Office\PowerPoint\Addins\{#PowerPointAddInName}"; \
  ValueType: string; ValueName: "FriendlyName"; ValueData: "LaTeXSnipper"; Flags: uninsdeletekey; Check: IsWin64
Root: HKLM; Subkey: "Software\WOW6432Node\Microsoft\Office\PowerPoint\Addins\{#PowerPointAddInName}"; \
  ValueType: dword; ValueName: "LoadBehavior"; ValueData: "3"; Flags: uninsdeletekey; Check: IsWin64
Root: HKLM; Subkey: "Software\WOW6432Node\Microsoft\Office\PowerPoint\Addins\{#PowerPointAddInName}"; \
  ValueType: string; ValueName: "Manifest"; ValueData: "{code:GetManifestUri|PowerPoint\{#PowerPointAddInName}.vsto}"; Flags: uninsdeletekey; Check: IsWin64
Root: HKLM; Subkey: "Software\WOW6432Node\Microsoft\Office\PowerPoint\Addins\{#PowerPointAddInName}"; \
  ValueType: dword; ValueName: "CommandLineSafe"; ValueData: "1"; Flags: uninsdeletekey; Check: IsWin64
Root: HKLM; Subkey: "Software\WOW6432Node\Microsoft\Office\16.0\PowerPoint\Addins\{#PowerPointAddInName}"; \
  ValueType: string; ValueName: "Description"; ValueData: "LaTeXSnipper native PowerPoint plugin"; Flags: uninsdeletekey; Check: IsWin64
Root: HKLM; Subkey: "Software\WOW6432Node\Microsoft\Office\16.0\PowerPoint\Addins\{#PowerPointAddInName}"; \
  ValueType: string; ValueName: "FriendlyName"; ValueData: "LaTeXSnipper"; Flags: uninsdeletekey; Check: IsWin64
Root: HKLM; Subkey: "Software\WOW6432Node\Microsoft\Office\16.0\PowerPoint\Addins\{#PowerPointAddInName}"; \
  ValueType: dword; ValueName: "LoadBehavior"; ValueData: "3"; Flags: uninsdeletekey; Check: IsWin64
Root: HKLM; Subkey: "Software\WOW6432Node\Microsoft\Office\16.0\PowerPoint\Addins\{#PowerPointAddInName}"; \
  ValueType: string; ValueName: "Manifest"; ValueData: "{code:GetManifestUri|PowerPoint\{#PowerPointAddInName}.vsto}"; Flags: uninsdeletekey; Check: IsWin64
Root: HKLM; Subkey: "Software\WOW6432Node\Microsoft\Office\16.0\PowerPoint\Addins\{#PowerPointAddInName}"; \
  ValueType: dword; ValueName: "CommandLineSafe"; ValueData: "1"; Flags: uninsdeletekey; Check: IsWin64

; ===== PowerPoint Add-in (ClickToRun virtualized registry — required for Office 365 / C2R) =====
Root: HKLM; Subkey: "Software\Microsoft\Office\ClickToRun\REGISTRY\MACHINE\Software\Microsoft\Office\PowerPoint\Addins\{#PowerPointAddInName}"; \
  ValueType: string; ValueName: "Description"; ValueData: "LaTeXSnipper native PowerPoint plugin"; Flags: uninsdeletekey
Root: HKLM; Subkey: "Software\Microsoft\Office\ClickToRun\REGISTRY\MACHINE\Software\Microsoft\Office\PowerPoint\Addins\{#PowerPointAddInName}"; \
  ValueType: string; ValueName: "FriendlyName"; ValueData: "LaTeXSnipper"; Flags: uninsdeletekey
Root: HKLM; Subkey: "Software\Microsoft\Office\ClickToRun\REGISTRY\MACHINE\Software\Microsoft\Office\PowerPoint\Addins\{#PowerPointAddInName}"; \
  ValueType: dword; ValueName: "LoadBehavior"; ValueData: "3"; Flags: uninsdeletekey
Root: HKLM; Subkey: "Software\Microsoft\Office\ClickToRun\REGISTRY\MACHINE\Software\Microsoft\Office\PowerPoint\Addins\{#PowerPointAddInName}"; \
  ValueType: string; ValueName: "Manifest"; ValueData: "{code:GetManifestUri|PowerPoint\{#PowerPointAddInName}.vsto}"; Flags: uninsdeletekey
Root: HKLM; Subkey: "Software\Microsoft\Office\ClickToRun\REGISTRY\MACHINE\Software\Microsoft\Office\PowerPoint\Addins\{#PowerPointAddInName}"; \
  ValueType: dword; ValueName: "CommandLineSafe"; ValueData: "1"; Flags: uninsdeletekey

Root: HKLM; Subkey: "Software\Microsoft\Office\ClickToRun\REGISTRY\MACHINE\Software\Microsoft\Office\16.0\PowerPoint\Addins\{#PowerPointAddInName}"; \
  ValueType: string; ValueName: "Description"; ValueData: "LaTeXSnipper native PowerPoint plugin"; Flags: uninsdeletekey
Root: HKLM; Subkey: "Software\Microsoft\Office\ClickToRun\REGISTRY\MACHINE\Software\Microsoft\Office\16.0\PowerPoint\Addins\{#PowerPointAddInName}"; \
  ValueType: string; ValueName: "FriendlyName"; ValueData: "LaTeXSnipper"; Flags: uninsdeletekey
Root: HKLM; Subkey: "Software\Microsoft\Office\ClickToRun\REGISTRY\MACHINE\Software\Microsoft\Office\16.0\PowerPoint\Addins\{#PowerPointAddInName}"; \
  ValueType: dword; ValueName: "LoadBehavior"; ValueData: "3"; Flags: uninsdeletekey
Root: HKLM; Subkey: "Software\Microsoft\Office\ClickToRun\REGISTRY\MACHINE\Software\Microsoft\Office\16.0\PowerPoint\Addins\{#PowerPointAddInName}"; \
  ValueType: string; ValueName: "Manifest"; ValueData: "{code:GetManifestUri|PowerPoint\{#PowerPointAddInName}.vsto}"; Flags: uninsdeletekey
Root: HKLM; Subkey: "Software\Microsoft\Office\ClickToRun\REGISTRY\MACHINE\Software\Microsoft\Office\16.0\PowerPoint\Addins\{#PowerPointAddInName}"; \
  ValueType: dword; ValueName: "CommandLineSafe"; ValueData: "1"; Flags: uninsdeletekey

Root: HKLM; Subkey: "Software\WOW6432Node\Microsoft\Office\ClickToRun\REGISTRY\MACHINE\Software\Microsoft\Office\PowerPoint\Addins\{#PowerPointAddInName}"; \
  ValueType: string; ValueName: "Description"; ValueData: "LaTeXSnipper native PowerPoint plugin"; Flags: uninsdeletekey; Check: IsWin64
Root: HKLM; Subkey: "Software\WOW6432Node\Microsoft\Office\ClickToRun\REGISTRY\MACHINE\Software\Microsoft\Office\PowerPoint\Addins\{#PowerPointAddInName}"; \
  ValueType: string; ValueName: "FriendlyName"; ValueData: "LaTeXSnipper"; Flags: uninsdeletekey; Check: IsWin64
Root: HKLM; Subkey: "Software\WOW6432Node\Microsoft\Office\ClickToRun\REGISTRY\MACHINE\Software\Microsoft\Office\PowerPoint\Addins\{#PowerPointAddInName}"; \
  ValueType: dword; ValueName: "LoadBehavior"; ValueData: "3"; Flags: uninsdeletekey; Check: IsWin64
Root: HKLM; Subkey: "Software\WOW6432Node\Microsoft\Office\ClickToRun\REGISTRY\MACHINE\Software\Microsoft\Office\PowerPoint\Addins\{#PowerPointAddInName}"; \
  ValueType: string; ValueName: "Manifest"; ValueData: "{code:GetManifestUri|PowerPoint\{#PowerPointAddInName}.vsto}"; Flags: uninsdeletekey; Check: IsWin64
Root: HKLM; Subkey: "Software\WOW6432Node\Microsoft\Office\ClickToRun\REGISTRY\MACHINE\Software\Microsoft\Office\PowerPoint\Addins\{#PowerPointAddInName}"; \
  ValueType: dword; ValueName: "CommandLineSafe"; ValueData: "1"; Flags: uninsdeletekey; Check: IsWin64

Root: HKLM; Subkey: "Software\WOW6432Node\Microsoft\Office\ClickToRun\REGISTRY\MACHINE\Software\Microsoft\Office\16.0\PowerPoint\Addins\{#PowerPointAddInName}"; \
  ValueType: string; ValueName: "Description"; ValueData: "LaTeXSnipper native PowerPoint plugin"; Flags: uninsdeletekey; Check: IsWin64
Root: HKLM; Subkey: "Software\WOW6432Node\Microsoft\Office\ClickToRun\REGISTRY\MACHINE\Software\Microsoft\Office\16.0\PowerPoint\Addins\{#PowerPointAddInName}"; \
  ValueType: string; ValueName: "FriendlyName"; ValueData: "LaTeXSnipper"; Flags: uninsdeletekey; Check: IsWin64
Root: HKLM; Subkey: "Software\WOW6432Node\Microsoft\Office\ClickToRun\REGISTRY\MACHINE\Software\Microsoft\Office\16.0\PowerPoint\Addins\{#PowerPointAddInName}"; \
  ValueType: dword; ValueName: "LoadBehavior"; ValueData: "3"; Flags: uninsdeletekey; Check: IsWin64
Root: HKLM; Subkey: "Software\WOW6432Node\Microsoft\Office\ClickToRun\REGISTRY\MACHINE\Software\Microsoft\Office\16.0\PowerPoint\Addins\{#PowerPointAddInName}"; \
  ValueType: string; ValueName: "Manifest"; ValueData: "{code:GetManifestUri|PowerPoint\{#PowerPointAddInName}.vsto}"; Flags: uninsdeletekey; Check: IsWin64
Root: HKLM; Subkey: "Software\WOW6432Node\Microsoft\Office\ClickToRun\REGISTRY\MACHINE\Software\Microsoft\Office\16.0\PowerPoint\Addins\{#PowerPointAddInName}"; \
  ValueType: dword; ValueName: "CommandLineSafe"; ValueData: "1"; Flags: uninsdeletekey; Check: IsWin64

; ===== EnableLocalMachineVSTO — REQUIRED for VSTO to even look at HKLM add-ins =====
Root: HKLM; Subkey: "SYSTEM\CurrentControlSet\Control\Session Manager\Environment"; \
  ValueType: string; ValueName: "EnableLocalMachineVSTO"; ValueData: "1"; Flags: uninsdeletevalue

[Run]
; Trust the signing certificate (both Root and TrustedPublisher needed for self-signed)
Filename: "{sys}\certutil.exe"; Parameters: "-addstore -f ""Root"" ""{app}\devcert.cer"""; \
  Flags: runhidden
Filename: "{sys}\certutil.exe"; Parameters: "-addstore -f ""TrustedPublisher"" ""{app}\devcert.cer"""; \
  StatusMsg: "{cm:InstallingCertificate}"; Flags: runhidden

; Run VSTOInstaller silently for Word
Filename: "{code:GetVstoInstallerPath}"; Parameters: "/Install ""{app}\Word\{#WordAddInName}.vsto"" /Silent"; \
  StatusMsg: "{cm:RegisteringWord}"; Flags: runhidden

; Run VSTOInstaller silently for PowerPoint
Filename: "{code:GetVstoInstallerPath}"; Parameters: "/Install ""{app}\PowerPoint\{#PowerPointAddInName}.vsto"" /Silent"; \
  StatusMsg: "{cm:RegisteringPowerPoint}"; Flags: runhidden

; Write VSTO security inclusion entries to HKLM (admin context, machine-wide)
; Word also needs HKCU inclusion which is created by a per-user post-install step
Filename: "{sys}\WindowsPowerShell\v1.0\powershell.exe"; \
  Parameters: "-ExecutionPolicy Bypass -File ""{app}\WriteVstoInclusions.ps1"" -ManifestPath ""{app}\Word\{#WordAddInName}.vsto"""; \
  StatusMsg: "{cm:RegisteringWord}"; Flags: runhidden

Filename: "{sys}\WindowsPowerShell\v1.0\powershell.exe"; \
  Parameters: "-ExecutionPolicy Bypass -File ""{app}\WriteVstoInclusions.ps1"" -ManifestPath ""{app}\PowerPoint\{#PowerPointAddInName}.vsto"""; \
  StatusMsg: "{cm:RegisteringPowerPoint}"; Flags: runhidden

[UninstallRun]
; Uninstall VSTO for Word
Filename: "{code:GetVstoInstallerPath}"; Parameters: "/Uninstall ""{app}\Word\{#WordAddInName}.vsto"" /Silent"; \
  Flags: runhidden; RunOnceId: "UninstallWordVsto"

; Uninstall VSTO for PowerPoint
Filename: "{code:GetVstoInstallerPath}"; Parameters: "/Uninstall ""{app}\PowerPoint\{#PowerPointAddInName}.vsto"" /Silent"; \
  Flags: runhidden; RunOnceId: "UninstallPowerPointVsto"

[CustomMessages]
InstallingCertificate=Installing add-in certificate to Trusted Publisher store...
RegisteringWord=Registering Word add-in...
RegisteringPowerPoint=Registering PowerPoint add-in...
chinesesimplified.InstallingCertificate=正在将加载项证书安装到受信任的发布者存储...
chinesesimplified.RegisteringWord=正在注册 Word 加载项...
chinesesimplified.RegisteringPowerPoint=正在注册 PowerPoint 加载项...

[Code]
function VstoInstallerExists: Boolean;
var
  Path: string;
begin
  Path := ExpandConstant('{commonpf32}\Common Files\Microsoft Shared\VSTO\10.0\VSTOInstaller.exe');
  if FileExists(Path) then
  begin
    Result := True;
    Exit;
  end;
  Path := ExpandConstant('{commonpf}\Common Files\Microsoft Shared\VSTO\10.0\VSTOInstaller.exe');
  Result := FileExists(Path);
end;

function InitializeSetup: Boolean;
begin
  if not VstoInstallerExists then
  begin
    SuppressibleMsgBox(
      'Microsoft Visual Studio Tools for Office Runtime is required but was not found.'#13#13 +
      'Please install the VSTO Runtime before installing this add-in.'#13#13 +
      'Download: https://go.microsoft.com/fwlink/?LinkId=140384',
      mbCriticalError, MB_OK, 0);
    Result := False;
  end
  else
    Result := True;
end;

function GetManifestUri(Param: string): string;
var
  AppDir: string;
begin
  AppDir := ExpandConstant('{app}');
  StringChange(AppDir, '\', '/');
  StringChange(Param, '\', '/');
  Result := 'file:///' + AppDir + '/' + Param + '|vstolocal';
end;

function GetVstoInstallerPath(Param: string): string;
var
  Path: string;
begin
  Path := ExpandConstant('{commonpf32}\Common Files\Microsoft Shared\VSTO\10.0\VSTOInstaller.exe');
  if FileExists(Path) then
    Result := Path
  else
  begin
    Path := ExpandConstant('{commonpf}\Common Files\Microsoft Shared\VSTO\10.0\VSTOInstaller.exe');
    if FileExists(Path) then
      Result := Path
    else
      RaiseException('Microsoft VSTO Runtime 10.0 is required but was not found. Please install Visual Studio Tools for Office.');
  end;
end;

procedure CurUninstallStepChanged(CurUninstallStep: TUninstallStep);
var
  ResultCode: Integer;
begin
  if CurUninstallStep = usUninstall then
  begin
    Exec(ExpandConstant('{sys}\WindowsPowerShell\v1.0\powershell.exe'),
         '-ExecutionPolicy Bypass -File "' + ExpandConstant('{app}') + '\ForceClean.ps1"',
         '', SW_HIDE, ewWaitUntilTerminated, ResultCode);
    Log('ForceClean exited with code ' + IntToStr(ResultCode));
  end;
end;

function CleanClickOnceStore(const RootKey: Integer; const SubPath: string): Boolean;
var
  SubKeys, ValueNames: TArrayOfString;
  KeyPath, ValueStr: string;
  i, j: Integer;
begin
  Result := False;
  if not RegGetSubkeyNames(RootKey, SubPath, SubKeys) then Exit;
  for i := 0 to GetArrayLength(SubKeys) - 1 do
  begin
    KeyPath := SubPath + '\' + SubKeys[i];
    if RegGetValueNames(RootKey, KeyPath, ValueNames) then
      for j := 0 to GetArrayLength(ValueNames) - 1 do
        if RegQueryStringValue(RootKey, KeyPath, ValueNames[j], ValueStr) then
          if Pos('LaTeXSnipper', ValueStr) > 0 then
          begin
            RegDeleteKeyIncludingSubkeys(RootKey, KeyPath);
            Log('Cleaned ClickOnce: ' + KeyPath);
            Result := True;
            break;
          end;
  end;
end;

function PrepareToInstall(var NeedsRestart: Boolean): String;
var
  ResultCode: Integer;
begin
  Result := '';

  // PowerShell cleanup: certs, file cache, HKLM+WOW registry paths
  ExtractTemporaryFile('ForceClean.ps1');
  Exec(ExpandConstant('{sys}\WindowsPowerShell\v1.0\powershell.exe'),
       '-ExecutionPolicy Bypass -File "' + ExpandConstant('{tmp}') + '\ForceClean.ps1"',
       '', SW_HIDE, ewWaitUntilTerminated, ResultCode);
  Log('ForceClean exited ' + IntToStr(ResultCode));

  // Native Pascal: directly clean ClickOnce stores (SubscriptionStore,
  // SolutionMetadata, ActivationData) — the root cause of AddInAlreadyInstalledException
  CleanClickOnceStore(HKEY_CURRENT_USER, 'Software\Microsoft\Windows\CurrentVersion\Deployment\SubscriptionStore');
  CleanClickOnceStore(HKEY_CURRENT_USER, 'Software\Microsoft\VSTO\SolutionMetadata');
  CleanClickOnceStore(HKEY_CURRENT_USER, 'Software\Microsoft\Windows\CurrentVersion\Deployment\ActivationData');
end;

procedure HideVstoUninstallEntries;
var
  UninstallRoot: string;
  SubkeyNames: TArrayOfString;
  DisplayName, KeyPath: string;
  i: Integer;
begin
  UninstallRoot := 'Software\Microsoft\Windows\CurrentVersion\Uninstall';
  if RegGetSubkeyNames(HKEY_CURRENT_USER, UninstallRoot, SubkeyNames) then
    for i := 0 to GetArrayLength(SubkeyNames) - 1 do
    begin
      KeyPath := UninstallRoot + '\' + SubkeyNames[i];
      if RegQueryStringValue(HKEY_CURRENT_USER, KeyPath, 'DisplayName', DisplayName) then
        if Pos('LaTeXSnipper.OfficePlugin', DisplayName) > 0 then
        begin
          RegWriteDWordValue(HKEY_CURRENT_USER, KeyPath, 'SystemComponent', 1);
          Log('Hid VSTO uninstall entry: ' + DisplayName);
        end;
    end;
end;

procedure CurStepChanged(CurStep: TSetupStep);
begin
  if CurStep = ssPostInstall then
  begin
    HideVstoUninstallEntries;
    Log('LaTeXSnipper Office Plugin v{#Version} installed to ' + ExpandConstant('{app}'));
  end;
end;
