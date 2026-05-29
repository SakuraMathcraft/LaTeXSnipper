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

[Run]
; Trust the signing certificate (development self-signed cert)
Filename: "{sys}\certutil.exe"; Parameters: "-addstore -f ""TrustedPublisher"" ""{app}\Word\{#WordAddInName}.dll"""; \
  StatusMsg: "{cm:InstallingCertificate}"; Flags: runhidden
Filename: "{sys}\certutil.exe"; Parameters: "-addstore -f ""TrustedPublisher"" ""{app}\PowerPoint\{#PowerPointAddInName}.dll"""; \
  StatusMsg: "{cm:InstallingCertificate}"; Flags: runhidden

; Run VSTOInstaller silently for Word
Filename: "{code:GetVstoInstallerPath}"; Parameters: "/Install ""{app}\Word\{#WordAddInName}.vsto"" /Silent"; \
  StatusMsg: "{cm:RegisteringWord}"; Flags: runhidden

; Run VSTOInstaller silently for PowerPoint
Filename: "{code:GetVstoInstallerPath}"; Parameters: "/Install ""{app}\PowerPoint\{#PowerPointAddInName}.vsto"" /Silent"; \
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
function GetManifestUri(Param: string): string;
var
  AppDir: string;
begin
  AppDir := ExpandConstant('{app}');
  StringChange(AppDir, '\', '/');
  Result := 'file:///' + AppDir + '/' + Param + '|vstolocal';
end;

function GetVstoInstallerPath(Param: string): string;
var
  Path: string;
begin
  Path := ExpandConstant('{commonpf}\Common Files\Microsoft Shared\VSTO\10.0\VSTOInstaller.exe');
  if FileExists(Path) then
    Result := Path
  else
  begin
    Path := ExpandConstant('{commonpf32}\Common Files\Microsoft Shared\VSTO\10.0\VSTOInstaller.exe');
    if FileExists(Path) then
      Result := Path
    else
      Result := '';
  end;
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
  begin
    for i := 0 to GetArrayLength(SubkeyNames) - 1 do
    begin
      KeyPath := UninstallRoot + '\' + SubkeyNames[i];
      if RegQueryStringValue(HKEY_CURRENT_USER, KeyPath, 'DisplayName', DisplayName) then
      begin
        if Pos('LaTeXSnipper.OfficePlugin', DisplayName) > 0 then
        begin
          RegWriteDWordValue(HKEY_CURRENT_USER, KeyPath, 'SystemComponent', 1);
          Log('Hid VSTO uninstall entry: ' + DisplayName);
        end;
      end;
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

procedure CleanResiliencyForApp(App: string);
var
  ResRoots: array [0..1] of string;
  Subkeys: array [0..1] of string;
  KeyPath: string;
  ValueNames: TArrayOfString;
  i, j, k: Integer;
begin
  ResRoots[0] := 'Software\Microsoft\Office\' + App + '\Resiliency';
  ResRoots[1] := 'Software\Microsoft\Office\16.0\' + App + '\Resiliency';
  Subkeys[0] := 'DisabledItems';
  Subkeys[1] := 'CrashingAddinList';

  for i := 0 to 1 do
    for j := 0 to 1 do
    begin
      KeyPath := ResRoots[i] + '\' + Subkeys[j];
      if RegGetValueNames(HKEY_CURRENT_USER, KeyPath, ValueNames) then
        for k := 0 to GetArrayLength(ValueNames) - 1 do
          if Pos('LaTeXSnipper', ValueNames[k]) > 0 then
          begin
            RegDeleteValue(HKEY_CURRENT_USER, KeyPath, ValueNames[k]);
            Log('Cleaned resiliency: ' + KeyPath + '\' + ValueNames[k]);
          end;
    end;
end;

procedure CleanHkcuUninstallEntries;
var
  UninstallRoot: string;
  SubkeyNames: TArrayOfString;
  DisplayName, KeyPath: string;
  i: Integer;
begin
  UninstallRoot := 'Software\Microsoft\Windows\CurrentVersion\Uninstall';
  if RegGetSubkeyNames(HKEY_CURRENT_USER, UninstallRoot, SubkeyNames) then
  begin
    for i := 0 to GetArrayLength(SubkeyNames) - 1 do
    begin
      KeyPath := UninstallRoot + '\' + SubkeyNames[i];
      if RegQueryStringValue(HKEY_CURRENT_USER, KeyPath, 'DisplayName', DisplayName) then
      begin
        if Pos('LaTeXSnipper.OfficePlugin', DisplayName) > 0 then
        begin
          RegDeleteKeyIncludingSubkeys(HKEY_CURRENT_USER, KeyPath);
          Log('Removed HKCU uninstall: ' + DisplayName);
        end;
      end;
    end;
  end;
end;

procedure CleanVstoSolutionMetadata;
var
  MetaRoot: string;
  SubkeyNames: TArrayOfString;
  KeyPath, ValueStr: string;
  ValueNames: TArrayOfString;
  i, j: Integer;
  found: Boolean;
begin
  MetaRoot := 'Software\Microsoft\VSTO\SolutionMetadata';
  if RegGetSubkeyNames(HKEY_CURRENT_USER, MetaRoot, SubkeyNames) then
  begin
    for i := 0 to GetArrayLength(SubkeyNames) - 1 do
    begin
      KeyPath := MetaRoot + '\' + SubkeyNames[i];
      found := False;
      if RegGetValueNames(HKEY_CURRENT_USER, KeyPath, ValueNames) then
      begin
        for j := 0 to GetArrayLength(ValueNames) - 1 do
        begin
          if RegQueryStringValue(HKEY_CURRENT_USER, KeyPath, ValueNames[j], ValueStr) then
          begin
            if Pos('LaTeXSnipper', ValueStr) > 0 then
            begin
              found := True;
              break;
            end;
          end;
        end;
      end;
      if found then
      begin
        RegDeleteKeyIncludingSubkeys(HKEY_CURRENT_USER, KeyPath);
        Log('Removed VSTO metadata: ' + SubkeyNames[i]);
      end;
    end;
  end;
end;

procedure CurUninstallStepChanged(CurUninstallStep: TUninstallStep);
begin
  if CurUninstallStep = usPostUninstall then
  begin
    CleanResiliencyForApp('Word');
    CleanResiliencyForApp('PowerPoint');
    CleanHkcuUninstallEntries;
    CleanVstoSolutionMetadata;
    Log('Registry cleanup complete.');
  end;
end;
