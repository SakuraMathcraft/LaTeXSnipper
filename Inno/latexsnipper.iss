#define MyAppName "LaTeXSnipper"
#define MyAppVersion "2.4.0"
#define MyAppPublisher "MathCraft"
#define MyAppURL "https://github.com/SakuraMathcraft/LaTeXSnipper"
#define MyAppExeName "LaTeXSnipper.exe"
#if GetEnv("LATEXSNIPPER_REPO_ROOT") != ""
#define MyRepoRoot GetEnv("LATEXSNIPPER_REPO_ROOT")
#else
#define MyRepoRoot "E:\LaTexSnipper"
#endif
#define MyBuildDir MyRepoRoot + "\dist\LaTeXSnipper"
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
DefaultDirName={localappdata}\{#MyAppName}
UninstallDisplayIcon={app}\{#MyAppExeName}
ArchitecturesAllowed=x64compatible
ArchitecturesInstallIn64BitMode=x64compatible
PrivilegesRequired=lowest
ChangesAssociations=no
DisableProgramGroupPage=yes
LicenseFile={#MyLicenseFile}
OutputDir={#MyOutputDir}
OutputBaseFilename=LaTeXSnipperSetup-{#MyAppVersion}
SetupIconFile={#MyRepoRoot}\src\assets\icon.ico
SolidCompression=yes
WizardStyle=modern

[Languages]
Name: "english"; MessagesFile: "compiler:Default.isl"
Name: "chinesesimplified"; MessagesFile: "{#MyRepoRoot}\Inno\ChineseSimplified.isl"

[CustomMessages]
english.UninstallCleanupTitle=Optional cleanup
english.UninstallCleanupDetail=LaTeXSnipper preserves user data by default so upgrades and reinstalls keep settings, history, dependencies, and downloaded MathCraft models.
english.UninstallCleanupAppData=Remove LaTeXSnipper settings, history, logs, dependency state, and temporary files
english.UninstallCleanupModels=Remove MathCraft model weights from %APPDATA%\MathCraft\models
chinesesimplified.UninstallCleanupTitle=可选清理
chinesesimplified.UninstallCleanupDetail=LaTeXSnipper 默认保留用户数据，方便升级或重装后继续使用原配置、历史记录、依赖环境和已下载的 MathCraft 模型。
chinesesimplified.UninstallCleanupAppData=删除 LaTeXSnipper 设置、历史记录、日志、依赖状态和临时文件
chinesesimplified.UninstallCleanupModels=删除 %APPDATA%\MathCraft\models 中的 MathCraft 模型权重

[Tasks]
Name: "desktopicon"; Description: "{cm:CreateDesktopIcon}"; GroupDescription: "{cm:AdditionalIcons}"; Flags: unchecked

[Files]
Source: "{#MyBuildDir}\*"; DestDir: "{app}"; Flags: ignoreversion recursesubdirs createallsubdirs

[Icons]
Name: "{autoprograms}\{#MyAppName}"; Filename: "{app}\{#MyAppExeName}"
Name: "{autodesktop}\{#MyAppName}"; Filename: "{app}\{#MyAppExeName}"; Tasks: desktopicon

[Run]
Filename: "{app}\{#MyAppExeName}"; Description: "{cm:LaunchProgram,{#StringChange(MyAppName, '&', '&&')}}"; Flags: nowait postinstall skipifsilent

[Code]
var
  DeleteAppDataOnUninstall: Boolean;
  DeleteMathCraftModelsOnUninstall: Boolean;
  UninstallAppDataCheckBox: TNewCheckBox;
  UninstallModelsCheckBox: TNewCheckBox;

function CleanupPath(Path: String): Boolean;
begin
  Result := False;
  if Path = '' then
    Exit;
  if DirExists(Path) then
    Result := DelTree(Path, True, True, True);
end;

function InitializeUninstall(): Boolean;
begin
  DeleteAppDataOnUninstall := False;
  DeleteMathCraftModelsOnUninstall := False;
  Result := True;
end;

procedure InitializeUninstallProgressForm();
var
  Delta: Integer;
  BaseTop: Integer;
  TitleLabel: TNewStaticText;
  DetailLabel: TNewStaticText;
begin
  if UninstallSilent then
    Exit;

  Delta := ScaleY(128);
  BaseTop := UninstallProgressForm.CancelButton.Top;
  UninstallProgressForm.ClientHeight := UninstallProgressForm.ClientHeight + Delta;
  UninstallProgressForm.CancelButton.Top := UninstallProgressForm.CancelButton.Top + Delta;

  TitleLabel := TNewStaticText.Create(UninstallProgressForm);
  TitleLabel.Parent := UninstallProgressForm;
  TitleLabel.Left := ScaleX(16);
  TitleLabel.Top := BaseTop + ScaleY(6);
  TitleLabel.Width := UninstallProgressForm.ClientWidth - ScaleX(32);
  TitleLabel.Height := ScaleY(18);
  TitleLabel.Font.Style := [fsBold];
  TitleLabel.Caption := CustomMessage('UninstallCleanupTitle');

  DetailLabel := TNewStaticText.Create(UninstallProgressForm);
  DetailLabel.Parent := UninstallProgressForm;
  DetailLabel.Left := ScaleX(16);
  DetailLabel.Top := TitleLabel.Top + ScaleY(22);
  DetailLabel.Width := UninstallProgressForm.ClientWidth - ScaleX(32);
  DetailLabel.Height := ScaleY(34);
  DetailLabel.WordWrap := True;
  DetailLabel.Caption := CustomMessage('UninstallCleanupDetail');

  UninstallAppDataCheckBox := TNewCheckBox.Create(UninstallProgressForm);
  UninstallAppDataCheckBox.Parent := UninstallProgressForm;
  UninstallAppDataCheckBox.Left := ScaleX(16);
  UninstallAppDataCheckBox.Top := DetailLabel.Top + ScaleY(42);
  UninstallAppDataCheckBox.Width := UninstallProgressForm.ClientWidth - ScaleX(32);
  UninstallAppDataCheckBox.Height := ScaleY(20);
  UninstallAppDataCheckBox.Caption := CustomMessage('UninstallCleanupAppData');
  UninstallAppDataCheckBox.Checked := False;

  UninstallModelsCheckBox := TNewCheckBox.Create(UninstallProgressForm);
  UninstallModelsCheckBox.Parent := UninstallProgressForm;
  UninstallModelsCheckBox.Left := ScaleX(16);
  UninstallModelsCheckBox.Top := UninstallAppDataCheckBox.Top + ScaleY(24);
  UninstallModelsCheckBox.Width := UninstallProgressForm.ClientWidth - ScaleX(32);
  UninstallModelsCheckBox.Height := ScaleY(20);
  UninstallModelsCheckBox.Caption := CustomMessage('UninstallCleanupModels');
  UninstallModelsCheckBox.Checked := False;
end;

procedure CurUninstallStepChanged(CurUninstallStep: TUninstallStep);
begin
  if CurUninstallStep <> usPostUninstall then
    Exit;

  if not UninstallSilent then
  begin
    DeleteAppDataOnUninstall := UninstallAppDataCheckBox.Checked;
    DeleteMathCraftModelsOnUninstall := UninstallModelsCheckBox.Checked;
  end;

  if DeleteAppDataOnUninstall then
  begin
    CleanupPath(ExpandConstant('{userprofile}\.latexsnipper'));
    CleanupPath(ExpandConstant('{localappdata}\LaTeXSnipper\logs'));
    CleanupPath(ExpandConstant('{tmp}\LaTeXSnipper'));
  end;

  if DeleteMathCraftModelsOnUninstall then
    CleanupPath(ExpandConstant('{userappdata}\MathCraft\models'));
end;
