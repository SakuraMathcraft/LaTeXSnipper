#define MyAppName "LaTeXSnipper Office Runtime"
#define MyAppVersion "2.3.2"
#define MyAppPublisher "SakuraMathcraft"
#define MyAppURL "https://github.com/SakuraMathcraft/LaTeXSnipper"
#if GetEnv("LATEXSNIPPER_OFFICE_STAGE") != ""
#define MySourceRoot GetEnv("LATEXSNIPPER_OFFICE_STAGE")
#else
#define MySourceRoot "E:\LaTexSnipper\build\office_addin\windows"
#endif
#if GetEnv("LATEXSNIPPER_OFFICE_OUTPUT") != ""
#define MyOutputDir GetEnv("LATEXSNIPPER_OFFICE_OUTPUT")
#else
#define MyOutputDir "E:\LaTexSnipper\dist\office-addin"
#endif

[Setup]
AppId={{EBE04571-A40B-49EA-A897-FDCD2551AB09}
AppName={#MyAppName}
AppVersion={#MyAppVersion}
AppPublisher={#MyAppPublisher}
AppPublisherURL={#MyAppURL}
AppSupportURL={#MyAppURL}/issues
DefaultDirName={localappdata}\LaTeXSnipper\OfficeAddin
ArchitecturesAllowed=x64compatible
ArchitecturesInstallIn64BitMode=x64compatible
PrivilegesRequired=lowest
DisableProgramGroupPage=yes
UninstallDisplayIcon={app}\icon.ico
UninstallDisplayName={#MyAppName}
OutputDir={#MyOutputDir}
OutputBaseFilename=OfficeAddinSetup-{#MyAppVersion}
SetupIconFile={#MySourceRoot}\icon.ico
SolidCompression=yes
WizardStyle=modern

[Languages]
Name: "english"; MessagesFile: "compiler:Default.isl"
Name: "chinesesimplified"; MessagesFile: "{#MySourceRoot}\ChineseSimplified.isl"

[Files]
Source: "{#MySourceRoot}\site\*"; DestDir: "{app}\site"; Flags: ignoreversion recursesubdirs createallsubdirs
Source: "{#MySourceRoot}\manifests\*"; DestDir: "{app}\manifests"; Flags: ignoreversion
Source: "{#MySourceRoot}\install.ps1"; DestDir: "{app}"; Flags: ignoreversion
Source: "{#MySourceRoot}\icon.ico"; DestDir: "{app}"; Flags: ignoreversion
Source: "{#MySourceRoot}\uninstall.ps1"; DestDir: "{app}"; Flags: ignoreversion

[Run]
Filename: "{sys}\WindowsPowerShell\v1.0\powershell.exe"; Parameters: "-NoProfile -ExecutionPolicy Bypass -File ""{app}\install.ps1"" -InstallRoot ""{app}"""; Flags: runhidden waituntilterminated

[UninstallRun]
Filename: "{sys}\WindowsPowerShell\v1.0\powershell.exe"; Parameters: "-NoProfile -ExecutionPolicy Bypass -File ""{app}\uninstall.ps1"" -InstallRoot ""{app}"""; Flags: runhidden waituntilterminated; RunOnceId: "UnregisterOfficeAddin"
