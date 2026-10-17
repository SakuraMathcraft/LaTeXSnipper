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
ArchitecturesAllowed=x64compatible
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
english.CleanupAppData=Remove LaTeXSnipper settings, history, logs and temporary files
english.CleanupModels=Remove the shared MathCraft model cache (also used by other MathCraft clients)
chinesesimplified.InstallFailure=安装资源部署失败，请查看运行日志中的部署与恢复结果。
chinesesimplified.CleanupAppData=删除 LaTeXSnipper 设置、历史记录、日志和临时文件
chinesesimplified.CleanupModels=删除共享 MathCraft 模型缓存（其他 MathCraft 客户端也会使用）

english.UninstallCleanupTitle=Optional cleanup

english.UninstallCleanupDetail=Settings, history, logs and the shared model cache are kept unless you select them below.

english.UninstallCleanupAction=Uninstall

chinesesimplified.UninstallCleanupTitle=可选清理

chinesesimplified.UninstallCleanupDetail=默认保留设置、历史记录、日志和共享模型缓存，可在下方选择清理。

chinesesimplified.UninstallCleanupAction=卸载

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
var
  DeleteAppDataOnUninstall: Boolean;
  DeleteMathCraftModelsOnUninstall: Boolean;

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

function ConfirmUninstallCleanup(): Boolean;
var
  CleanupForm: TSetupForm;
  TitleLabel: TNewStaticText;
  DetailLabel: TNewStaticText;
  AppDataCheckBox: TNewCheckBox;
  ModelsCheckBox: TNewCheckBox;
  UninstallButton: TNewButton;
  CancelButton: TNewButton;
begin
  Result := True;
  if UninstallSilent then
    Exit;

  CleanupForm := CreateCustomForm(ScaleX(430), ScaleY(190), False, True);
  try
    CleanupForm.Caption := CustomMessage('UninstallCleanupTitle');

    TitleLabel := TNewStaticText.Create(CleanupForm);
    TitleLabel.Parent := CleanupForm;
    TitleLabel.Left := ScaleX(14);
    TitleLabel.Top := ScaleY(12);
    TitleLabel.Width := CleanupForm.ClientWidth - ScaleX(28);
    TitleLabel.Height := ScaleY(18);
    TitleLabel.Font.Style := [fsBold];
    TitleLabel.Caption := CustomMessage('UninstallCleanupTitle');

    DetailLabel := TNewStaticText.Create(CleanupForm);
    DetailLabel.Parent := CleanupForm;
    DetailLabel.Left := ScaleX(14);
    DetailLabel.Top := TitleLabel.Top + ScaleY(24);
    DetailLabel.Width := CleanupForm.ClientWidth - ScaleX(28);
    DetailLabel.Height := ScaleY(42);
    DetailLabel.WordWrap := True;
    DetailLabel.Caption := CustomMessage('UninstallCleanupDetail');

    AppDataCheckBox := TNewCheckBox.Create(CleanupForm);
    AppDataCheckBox.Parent := CleanupForm;
    AppDataCheckBox.Left := ScaleX(14);
    AppDataCheckBox.Top := DetailLabel.Top + ScaleY(50);
    AppDataCheckBox.Width := CleanupForm.ClientWidth - ScaleX(28);
    AppDataCheckBox.Height := ScaleY(20);
    AppDataCheckBox.Caption := CustomMessage('CleanupAppData');

    ModelsCheckBox := TNewCheckBox.Create(CleanupForm);
    ModelsCheckBox.Parent := CleanupForm;
    ModelsCheckBox.Left := ScaleX(14);
    ModelsCheckBox.Top := AppDataCheckBox.Top + ScaleY(26);
    ModelsCheckBox.Width := CleanupForm.ClientWidth - ScaleX(28);
    ModelsCheckBox.Height := ScaleY(20);
    ModelsCheckBox.Caption := CustomMessage('CleanupModels');

    UninstallButton := TNewButton.Create(CleanupForm);
    UninstallButton.Parent := CleanupForm;
    UninstallButton.Width := ScaleX(100);
    UninstallButton.Height := ScaleY(28);
    UninstallButton.Left := CleanupForm.ClientWidth - ScaleX(220);
    UninstallButton.Top := CleanupForm.ClientHeight - ScaleY(36);
    UninstallButton.Caption := CustomMessage('UninstallCleanupAction');
    UninstallButton.ModalResult := mrOk;

    CancelButton := TNewButton.Create(CleanupForm);
    CancelButton.Parent := CleanupForm;
    CancelButton.Width := ScaleX(100);
    CancelButton.Height := ScaleY(28);
    CancelButton.Left := CleanupForm.ClientWidth - ScaleX(112);
    CancelButton.Top := UninstallButton.Top;
    CancelButton.Caption := SetupMessage(msgButtonCancel);
    CancelButton.ModalResult := mrCancel;
    CleanupForm.ActiveControl := UninstallButton;

    Result := CleanupForm.ShowModal() = mrOk;
    if Result then
    begin
      DeleteAppDataOnUninstall := AppDataCheckBox.Checked;
      DeleteMathCraftModelsOnUninstall := ModelsCheckBox.Checked;
    end;
  finally
    CleanupForm.Free;
  end;
end;

function InitializeUninstall(): Boolean;
begin
  DeleteAppDataOnUninstall := False;
  DeleteMathCraftModelsOnUninstall := False;
  Result := ConfirmUninstallCleanup();
end;

procedure CurUninstallStepChanged(CurUninstallStep: TUninstallStep);
var ResultCode: Integer;
begin
  if CurUninstallStep <> usUninstall then Exit;
  Exec(ExpandConstant('{sys}\taskkill.exe'), '/IM "LaTeXSnipper.exe" /T', '', SW_HIDE, ewWaitUntilTerminated, ResultCode);
  Sleep(1200);
  Exec(ExpandConstant('{sys}\taskkill.exe'), '/IM "LaTeXSnipper.exe" /T /F', '', SW_HIDE, ewWaitUntilTerminated, ResultCode);
  if DeleteAppDataOnUninstall then begin
    DelTree(ExpandConstant('{userprofile}\.latexsnipper'), True, True, True);
    DelTree(ExpandConstant('{tmp}\LaTeXSnipper'), True, True, True);
  end;
  if DeleteMathCraftModelsOnUninstall then
    DelTree(ExpandConstant('{userappdata}\MathCraft\models'), True, True, True);
end;
