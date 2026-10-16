#define MyAppName "LaTeXSnipper"
#define VersionFileHandle FileOpen(AddBackslash(SourcePath) + "..\VERSION")
#define MyAppVersion Trim(FileRead(VersionFileHandle))
#expr FileClose(VersionFileHandle)
#define MyRepoRoot AddBackslash(SourcePath) + ".."
#ifndef MyBuildDir
  #error Build using scripts/build_desktop_release.py on GitHub Actions
#endif

[Setup]
AppId={{B4F7AE05-D837-4F3B-A971-28BD8CCE631A}
AppName={#MyAppName}
AppVersion={#MyAppVersion}
AppPublisher=MathCraft
AppPublisherURL=https://github.com/SakuraMathcraft/LaTeXSnipper
DefaultDirName={localappdata}\LaTeXSnipper
UninstallDisplayIcon={app}\LaTeXSnipper.exe
ArchitecturesAllowed=x64os
ArchitecturesInstallIn64BitMode=x64compatible
PrivilegesRequired=lowest
DisableProgramGroupPage=yes
LicenseFile={#MyRepoRoot}\LICENSE
OutputDir={#MyOutputDir}
OutputBaseFilename=LaTeXSnipper_{#MyAppVersion}_windows_x86_64_{#MyEdition}
SetupIconFile={#MyRepoRoot}\src\assets\icon.ico
Compression=lzma2
SolidCompression=yes
WizardStyle=modern
CloseApplications=yes
CloseApplicationsFilter=LaTeXSnipper.exe
RestartApplications=no

[Languages]
Name: "english"; MessagesFile: "compiler:Default.isl"
Name: "chinesesimplified"; MessagesFile: "{#MyRepoRoot}\Inno\ChineseSimplified.isl"

[Tasks]
Name: "desktopicon"; Description: "{cm:CreateDesktopIcon}"; Flags: unchecked

[CustomMessages]
english.InstallFailure=Resource installation failed. See the runtime log for the deployment and recovery result.
english.CleanupAppData=Remove LaTeXSnipper settings, history, logs and temporary files?
english.CleanupModels=Remove the shared MathCraft model cache? This also affects other MathCraft clients.
chinesesimplified.InstallFailure=安装资源部署失败，请查看运行日志中的部署与恢复结果。
chinesesimplified.CleanupAppData=是否删除 LaTeXSnipper 设置、历史记录、日志和临时文件？
chinesesimplified.CleanupModels=是否删除共享 MathCraft 模型缓存？这也会影响其他 MathCraft 客户端。

[Files]
Source: "{#MyBuildDir}\LaTeXSnipper.exe"; DestDir: "{app}"; Flags: onlyifdoesntexist uninsneveruninstall
Source: "{#MyBuildDir}\application\updater.exe"; DestDir: "{tmp}"; DestName: "installer-updater.exe"; Flags: deleteafterinstall
Source: "{#MyBuildDir}\application\*"; DestDir: "{tmp}\latexsnipper-payload\application"; Flags: recursesubdirs createallsubdirs deleteafterinstall
Source: "{#MyBuildDir}\inference\*"; DestDir: "{tmp}\latexsnipper-payload\inference"; Flags: recursesubdirs createallsubdirs deleteafterinstall
Source: "{#MyBuildDir}\models\*"; DestDir: "{tmp}\latexsnipper-payload\models"; Flags: recursesubdirs createallsubdirs deleteafterinstall
Source: "{#MyBuildDir}\distribution.json"; DestDir: "{tmp}\latexsnipper-payload"; Flags: deleteafterinstall

[Icons]
Name: "{autoprograms}\LaTeXSnipper"; Filename: "{app}\LaTeXSnipper.exe"
Name: "{autodesktop}\LaTeXSnipper"; Filename: "{app}\LaTeXSnipper.exe"; Tasks: desktopicon

[Run]
Filename: "{app}\LaTeXSnipper.exe"; Description: "{cm:LaunchProgram,LaTeXSnipper}"; Flags: nowait postinstall skipifsilent

[UninstallDelete]
Type: filesandordirs; Name: "{app}\application"
Type: filesandordirs; Name: "{app}\inference"
Type: filesandordirs; Name: "{app}\models"
Type: filesandordirs; Name: "{app}\.deployment"
Type: files; Name: "{app}\.deployment.lock"
Type: files; Name: "{app}\distribution.json"
Type: files; Name: "{app}\LaTeXSnipper.exe"

[Code]
procedure RegisterExtraCloseApplicationsResources;
begin
  RegisterExtraCloseApplicationsResource(ExpandConstant('{app}\application\LaTeXSnipper.exe'));
  RegisterExtraCloseApplicationsResource(ExpandConstant('{app}\inference\python.exe'));
end;

procedure CurStepChanged(CurStep: TSetupStep);
var ResultCode: Integer;
begin
  if CurStep = ssPostInstall then
    if not Exec(ExpandConstant('{tmp}\installer-updater.exe'),
      '--install-from "' + ExpandConstant('{tmp}\latexsnipper-payload') + '" --root "' + ExpandConstant('{app}') + '"',
      '', SW_HIDE, ewWaitUntilTerminated, ResultCode) or (ResultCode <> 0) then
      RaiseException(ExpandConstant('{cm:InstallFailure}'));
end;

procedure CurUninstallStepChanged(CurUninstallStep: TUninstallStep);
begin
  if UninstallSilent then Exit;
  if CurUninstallStep = usPostUninstall then begin
    if MsgBox(ExpandConstant('{cm:CleanupAppData}'), mbConfirmation, MB_YESNO or MB_DEFBUTTON2) = IDYES then begin
      DelTree(ExpandConstant('{userprofile}\.latexsnipper'), True, True, True);
      DelTree(ExpandConstant('{tmp}\LaTeXSnipper'), True, True, True);
    end;
    if MsgBox(ExpandConstant('{cm:CleanupModels}'), mbConfirmation, MB_YESNO or MB_DEFBUTTON2) = IDYES then
      DelTree(ExpandConstant('{userappdata}\MathCraft\models'), True, True, True);
  end;
end;
