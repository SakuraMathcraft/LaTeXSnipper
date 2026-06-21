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
english.UninstallCleanupDependencies=Remove dependency environments from recorded dependency roots
english.UninstallCleanupModels=Remove MathCraft model weights from %APPDATA%\MathCraft\models
english.UninstallCleanupAction=Uninstall
chinesesimplified.UninstallCleanupTitle=可选清理
chinesesimplified.UninstallCleanupDetail=LaTeXSnipper 默认保留用户数据，方便升级或重装后继续使用原配置、历史记录、依赖环境和已下载的 MathCraft 模型。
chinesesimplified.UninstallCleanupAppData=删除 LaTeXSnipper 设置、历史记录、日志、依赖状态和临时文件
chinesesimplified.UninstallCleanupDependencies=删除已记录依赖根目录中的依赖环境
chinesesimplified.UninstallCleanupModels=删除 %APPDATA%\MathCraft\models 中的 MathCraft 模型权重
chinesesimplified.UninstallCleanupAction=卸载

[Tasks]
Name: "desktopicon"; Description: "{cm:CreateDesktopIcon}"; GroupDescription: "{cm:AdditionalIcons}"; Flags: unchecked

[Files]
Source: "{#MyBuildDir}\*"; DestDir: "{app}"; Flags: ignoreversion recursesubdirs createallsubdirs

[Icons]
Name: "{autoprograms}\{#MyAppName}"; Filename: "{app}\{#MyAppExeName}"
Name: "{autodesktop}\{#MyAppName}"; Filename: "{app}\{#MyAppExeName}"; Tasks: desktopicon

[Run]
Filename: "{app}\{#MyAppExeName}"; Description: "{cm:LaunchProgram,{#StringChange(MyAppName, '&', '&&')}}"; Flags: nowait postinstall skipifsilent

[UninstallDelete]
Type: filesandordirs; Name: "{app}\_internal"

[Code]
var
  DeleteAppDataOnUninstall: Boolean;
  DeleteDependencyEnvsOnUninstall: Boolean;
  DeleteMathCraftModelsOnUninstall: Boolean;

function CleanupPath(Path: String): Boolean;
begin
  Result := False;
  if Path = '' then
    Exit;
  if DirExists(Path) then
    Result := DelTree(Path, True, True, True);
end;

function CleanupFile(Path: String): Boolean;
begin
  Result := False;
  if Path = '' then
    Exit;
  if FileExists(Path) then
    Result := DeleteFile(Path);
end;

function IsUnsafeDependencyRoot(Path: String): Boolean;
var
  Normalized: String;
begin
  Normalized := Lowercase(RemoveBackslashUnlessRoot(Path));
  Result :=
    (Normalized = '') or
    (Normalized = Lowercase(RemoveBackslashUnlessRoot(ExpandConstant('{%USERPROFILE}')))) or
    (Length(Normalized) <= 3);
end;

function IsPythonEnvironmentRoot(Path: String): Boolean;
begin
  Result :=
    FileExists(AddBackslash(Path) + 'pyvenv.cfg') or
    FileExists(AddBackslash(Path) + 'python.exe') or
    FileExists(AddBackslash(Path) + 'pythonw.exe') or
    FileExists(AddBackslash(Path) + 'Scripts\python.exe') or
    FileExists(AddBackslash(Path) + 'bin\python');
end;

procedure CleanupDependencyRootChildren(Root: String);
begin
  if IsUnsafeDependencyRoot(Root) then
    Exit;

  if IsPythonEnvironmentRoot(Root) then
  begin
    CleanupPath(Root);
    Exit;
  end;

  CleanupFile(AddBackslash(Root) + '.deps_state.json');
  CleanupPath(AddBackslash(Root) + 'python311');
  CleanupPath(AddBackslash(Root) + 'Python311');
  CleanupPath(AddBackslash(Root) + 'python_full');
  CleanupPath(AddBackslash(Root) + 'venv');
  CleanupPath(AddBackslash(Root) + '.venv');
  CleanupPath(AddBackslash(Root) + 'pandoc');
  CleanupPath(AddBackslash(Root) + 'translation_env');
  RemoveDir(Root);
end;

function JsonStringValue(Json: String; Key: String): String;
var
  Marker: String;
  StartPos: Integer;
  EndPos: Integer;
  Cursor: Integer;
  Ch: String;
begin
  Result := '';
  Marker := '"' + Key + '"';
  StartPos := Pos(Marker, Json);
  if StartPos = 0 then
    Exit;

  StartPos := Pos(':', Copy(Json, StartPos + Length(Marker), Length(Json)));
  if StartPos = 0 then
    Exit;
  StartPos := Pos(Marker, Json) + Length(Marker) + StartPos;

  while (StartPos <= Length(Json)) and ((Copy(Json, StartPos, 1) = ' ') or (Copy(Json, StartPos, 1) = #9) or (Copy(Json, StartPos, 1) = #13) or (Copy(Json, StartPos, 1) = #10)) do
    StartPos := StartPos + 1;
  if Copy(Json, StartPos, 1) <> '"' then
    Exit;

  StartPos := StartPos + 1;
  Cursor := StartPos;
  while Cursor <= Length(Json) do
  begin
    Ch := Copy(Json, Cursor, 1);
    if (Ch = '"') and ((Cursor = StartPos) or (Copy(Json, Cursor - 1, 1) <> '\')) then
    begin
      EndPos := Cursor;
      Result := Copy(Json, StartPos, EndPos - StartPos);
      StringChangeEx(Result, '\\', '\', True);
      StringChangeEx(Result, '\/', '/', True);
      Exit;
    end;
    Cursor := Cursor + 1;
  end;
end;

function ConfiguredDependencyRoot(): String;
var
  ConfigPath: String;
  ConfigText: AnsiString;
begin
  Result := '';
  ConfigPath := ExpandConstant('{%USERPROFILE}\.latexsnipper\LaTeXSnipper_config.json');
  if LoadStringFromFile(ConfigPath, ConfigText) then
    Result := JsonStringValue(String(ConfigText), 'install_base_dir');
end;

procedure CleanupDependencyRootHistory();
var
  ConfigPath: String;
  ConfigText: AnsiString;
  Roots: String;
  Separator: Integer;
  Root: String;
begin
  ConfigPath := ExpandConstant('{%USERPROFILE}\.latexsnipper\LaTeXSnipper_config.json');
  if not LoadStringFromFile(ConfigPath, ConfigText) then
    Exit;

  Roots := JsonStringValue(String(ConfigText), 'install_base_dir_cleanup_roots');
  while Roots <> '' do
  begin
    Separator := Pos('|', Roots);
    if Separator > 0 then
    begin
      Root := Copy(Roots, 1, Separator - 1);
      Delete(Roots, 1, Separator);
    end
    else
    begin
      Root := Roots;
      Roots := '';
    end;
    CleanupDependencyRootChildren(Root);
  end;
end;

function ConfirmUninstallCleanup(): Boolean;
var
  CleanupForm: TSetupForm;
  TitleLabel: TNewStaticText;
  DetailLabel: TNewStaticText;
  AppDataCheckBox: TNewCheckBox;
  DependenciesCheckBox: TNewCheckBox;
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
    AppDataCheckBox.Caption := CustomMessage('UninstallCleanupAppData');

    DependenciesCheckBox := TNewCheckBox.Create(CleanupForm);
    DependenciesCheckBox.Parent := CleanupForm;
    DependenciesCheckBox.Left := ScaleX(14);
    DependenciesCheckBox.Top := AppDataCheckBox.Top + ScaleY(26);
    DependenciesCheckBox.Width := CleanupForm.ClientWidth - ScaleX(28);
    DependenciesCheckBox.Height := ScaleY(20);
    DependenciesCheckBox.Caption := CustomMessage('UninstallCleanupDependencies');

    ModelsCheckBox := TNewCheckBox.Create(CleanupForm);
    ModelsCheckBox.Parent := CleanupForm;
    ModelsCheckBox.Left := ScaleX(14);
    ModelsCheckBox.Top := DependenciesCheckBox.Top + ScaleY(26);
    ModelsCheckBox.Width := CleanupForm.ClientWidth - ScaleX(28);
    ModelsCheckBox.Height := ScaleY(20);
    ModelsCheckBox.Caption := CustomMessage('UninstallCleanupModels');

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
      DeleteDependencyEnvsOnUninstall := DependenciesCheckBox.Checked;
      DeleteMathCraftModelsOnUninstall := ModelsCheckBox.Checked;
    end;
  finally
    CleanupForm.Free;
  end;
end;

function InitializeUninstall(): Boolean;
begin
  DeleteAppDataOnUninstall := False;
  DeleteDependencyEnvsOnUninstall := False;
  DeleteMathCraftModelsOnUninstall := False;
  Result := ConfirmUninstallCleanup();
end;

procedure CurUninstallStepChanged(CurUninstallStep: TUninstallStep);
begin
  if CurUninstallStep <> usPostUninstall then
    Exit;

  if DeleteDependencyEnvsOnUninstall then
  begin
    CleanupDependencyRootChildren(ExpandConstant('{app}'));
    CleanupDependencyRootChildren(ConfiguredDependencyRoot());
    CleanupDependencyRootHistory();
  end;

  if DeleteAppDataOnUninstall then
  begin
    CleanupPath(ExpandConstant('{%USERPROFILE}\.latexsnipper'));
    CleanupPath(ExpandConstant('{localappdata}\LaTeXSnipper'));
    CleanupPath(ExpandConstant('{tmp}\LaTeXSnipper'));
  end;

  if DeleteMathCraftModelsOnUninstall then
    CleanupPath(ExpandConstant('{userappdata}\MathCraft\models'));
end;
