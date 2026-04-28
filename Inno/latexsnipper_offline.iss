#define MyAppName "LaTeXSnipperOffline"
#define MyAppVersion "2.3.2"
#define MyAppPublisher "MathCraft"
#define MyAppURL "https://github.com/SakuraMathcraft/LaTeXSnipper"
#define MyAppExeName "LaTeXSnipperOffline.exe"
#if GetEnv("LATEXSNIPPER_REPO_ROOT") != ""
#define MyRepoRoot GetEnv("LATEXSNIPPER_REPO_ROOT")
#else
#define MyRepoRoot "E:\LaTexSnipper"
#endif
#define MyBuildDir MyRepoRoot + "\dist\LaTeXSnipperOffline"
#define MyOutputDir MyRepoRoot + "\dist\installer"
#define MyLicenseFile MyRepoRoot + "\LICENSE"

[Setup]
AppId={{B4F7AE05-D837-4F3B-A971-28BD8CCE631A}
AppName={#MyAppName}
AppVersion={#MyAppVersion}
AppPublisher={#MyAppPublisher}
AppPublisherURL={#MyAppURL}
AppSupportURL={#MyAppURL}/issues
AppUpdatesURL={#MyAppURL}/releases
DefaultDirName=D:\{#MyAppName}
UninstallDisplayIcon={app}\{#MyAppExeName}
ArchitecturesAllowed=x64compatible
ArchitecturesInstallIn64BitMode=x64compatible
ChangesAssociations=no
DisableProgramGroupPage=yes
LicenseFile={#MyLicenseFile}
OutputDir={#MyOutputDir}
OutputBaseFilename=LaTeXSnipperOfflineSetup-{#MyAppVersion}
SetupIconFile={#MyRepoRoot}\src\assets\icon.ico
SolidCompression=yes
WizardStyle=modern

[Languages]
Name: "english"; MessagesFile: "compiler:Default.isl"

[Tasks]
Name: "desktopicon"; Description: "{cm:CreateDesktopIcon}"; GroupDescription: "{cm:AdditionalIcons}"; Flags: unchecked

[Files]
Source: "{#MyBuildDir}\*"; DestDir: "{app}"; Flags: ignoreversion recursesubdirs createallsubdirs

[Icons]
Name: "{autoprograms}\{#MyAppName}"; Filename: "{app}\{#MyAppExeName}"
Name: "{autodesktop}\{#MyAppName}"; Filename: "{app}\{#MyAppExeName}"; Tasks: desktopicon

[Run]
Filename: "{app}\{#MyAppExeName}"; Description: "{cm:LaunchProgram,{#StringChange(MyAppName, '&', '&&')}}"; Flags: nowait postinstall skipifsilent
