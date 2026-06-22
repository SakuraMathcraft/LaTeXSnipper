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
CloseApplications=yes
CloseApplicationsFilter={#MyAppExeName}

[Languages]
Name: "english"; MessagesFile: "compiler:Default.isl"
Name: "chinesesimplified"; MessagesFile: "{#MyRepoRoot}\Inno\ChineseSimplified.isl"

[CustomMessages]
english.UninstallCleanupTitle=Optional cleanup
english.UninstallCleanupDetail=LaTeXSnipper preserves user data by default so upgrades and reinstalls keep settings, history, dependencies, and downloaded MathCraft models.
english.UninstallCleanupAppData=Remove LaTeXSnipper settings, history, logs, dependency state, and temporary files
english.UninstallCleanupDependencies=Remove dependency environments from recorded roots and shared tools
english.UninstallCleanupModels=Remove MathCraft model weights from %APPDATA%\MathCraft\models
english.UninstallCleanupAction=Uninstall
chinesesimplified.UninstallCleanupTitle=可选清理
chinesesimplified.UninstallCleanupDetail=LaTeXSnipper 默认保留用户数据，方便升级或重装后继续使用原配置、历史记录、依赖环境和已下载的 MathCraft 模型。
chinesesimplified.UninstallCleanupAppData=删除 LaTeXSnipper 设置、历史记录、日志、依赖状态和临时文件
chinesesimplified.UninstallCleanupDependencies=删除已记录依赖根目录中的依赖环境和共享工具
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

procedure EnsureApplicationClosed();
var
  ResultCode: Integer;
begin
  Exec(ExpandConstant('{sys}\taskkill.exe'), '/IM "{#MyAppExeName}" /T', '', SW_HIDE, ewWaitUntilTerminated, ResultCode);
  Sleep(1200);
  Exec(ExpandConstant('{sys}\taskkill.exe'), '/IM "{#MyAppExeName}" /T /F', '', SW_HIDE, ewWaitUntilTerminated, ResultCode);
  Sleep(800);
end;

procedure CleanupDependencyRootsWithPowerShell();
var
  ScriptPath: String;
  ScriptText: String;
  ResultCode: Integer;
begin
  ScriptPath := ExpandConstant('{tmp}\latexsnipper-clean-deps.ps1');
  ScriptText :=
    '$ErrorActionPreference = ''SilentlyContinue''' + #13#10 +
    '$app = ''' + ExpandConstant('{app}') + '''' + #13#10 +
    '$config = Join-Path $env:USERPROFILE ''.latexsnipper\LaTeXSnipper_config.json''' + #13#10 +
    'function Remove-ManagedPath([string]$Path) {' + #13#10 +
    '  if ([string]::IsNullOrWhiteSpace($Path)) { return }' + #13#10 +
    '  $item = Get-Item -LiteralPath $Path -Force -ErrorAction SilentlyContinue' + #13#10 +
    '  if ($null -ne $item) { Remove-Item -LiteralPath $item.FullName -Recurse -Force -ErrorAction SilentlyContinue }' + #13#10 +
    '}' + #13#10 +
    'function Is-UnsafeRoot([string]$Path) {' + #13#10 +
    '  if ([string]::IsNullOrWhiteSpace($Path)) { return $true }' + #13#10 +
    '  try { $full = [System.IO.Path]::GetFullPath($Path).TrimEnd(''\'') } catch { return $true }' + #13#10 +
    '  $profile = [System.IO.Path]::GetFullPath($env:USERPROFILE).TrimEnd(''\'')' + #13#10 +
    '  return ($full.Length -le 3 -or $full.Equals($profile, [System.StringComparison]::OrdinalIgnoreCase))' + #13#10 +
    '}' + #13#10 +
    'function Is-PythonEnvironmentRoot([string]$Root) {' + #13#10 +
    '  foreach ($rel in @(''pyvenv.cfg'', ''python.exe'', ''pythonw.exe'', ''Scripts\python.exe'', ''bin\python'')) {' + #13#10 +
    '    if (Test-Path -LiteralPath (Join-Path $Root $rel) -PathType Leaf) { return $true }' + #13#10 +
    '  }' + #13#10 +
    '  return $false' + #13#10 +
    '}' + #13#10 +
    'function Cleanup-DependencyRoot([string]$Root) {' + #13#10 +
    '  if (Is-UnsafeRoot $Root) { return }' + #13#10 +
    '  if (Is-PythonEnvironmentRoot $Root) { Remove-ManagedPath $Root; return }' + #13#10 +
    '  foreach ($rel in @(''.deps_state.json'', ''python311'', ''Python311'', ''python_full'', ''venv'', ''.venv'')) {' + #13#10 +
    '    Remove-ManagedPath (Join-Path $Root $rel)' + #13#10 +
    '  }' + #13#10 +
    '  Remove-Item -LiteralPath $Root -Force -ErrorAction SilentlyContinue' + #13#10 +
    '}' + #13#10 +
    '$roots = New-Object System.Collections.Generic.List[string]' + #13#10 +
    '$roots.Add($app)' + #13#10 +
    'if (Test-Path -LiteralPath $config -PathType Leaf) {' + #13#10 +
    '  try {' + #13#10 +
    '    $data = Get-Content -LiteralPath $config -Raw -Encoding UTF8 | ConvertFrom-Json' + #13#10 +
    '    if ($data.install_base_dir) { $roots.Add([string]$data.install_base_dir) }' + #13#10 +
    '    $history = $data.install_base_dir_cleanup_roots' + #13#10 +
    '    if ($history -is [string]) { foreach ($item in $history -split ''\|'') { if ($item.Trim()) { $roots.Add($item.Trim()) } } }' + #13#10 +
    '    elseif ($history) { foreach ($item in $history) { if ([string]$item) { $roots.Add([string]$item) } } }' + #13#10 +
    '  } catch {}' + #13#10 +
    '}' + #13#10 +
    '$seen = @{}' + #13#10 +
    'foreach ($root in $roots) {' + #13#10 +
    '  if ([string]::IsNullOrWhiteSpace($root)) { continue }' + #13#10 +
    '  $key = $root.ToLowerInvariant()' + #13#10 +
    '  if ($seen.ContainsKey($key)) { continue }' + #13#10 +
    '  $seen[$key] = $true' + #13#10 +
    '  Cleanup-DependencyRoot $root' + #13#10 +
    '}' + #13#10 +
    'Remove-ManagedPath (Join-Path $env:USERPROFILE ''.latexsnipper\tools'')' + #13#10;

  if SaveStringToFile(ScriptPath, ScriptText, False) then
    Exec(ExpandConstant('{sys}\WindowsPowerShell\v1.0\powershell.exe'), '-NoLogo -NoProfile -ExecutionPolicy Bypass -File "' + ScriptPath + '"', '', SW_HIDE, ewWaitUntilTerminated, ResultCode);
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
  if Result then
    EnsureApplicationClosed();
end;

procedure CurUninstallStepChanged(CurUninstallStep: TUninstallStep);
begin
  if CurUninstallStep <> usPostUninstall then
    Exit;

  if DeleteDependencyEnvsOnUninstall then
  begin
    CleanupDependencyRootsWithPowerShell();
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
