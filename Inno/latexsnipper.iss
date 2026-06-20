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

function CleanupPath(Path: String): Boolean;
begin
  Result := False;
  if Path = '' then
    Exit;
  if DirExists(Path) then
    Result := DelTree(Path, True, True, True);
end;

function InitializeUninstall(): Boolean;
var
  Form: TSetupForm;
  TitleLabel: TNewStaticText;
  DetailLabel: TNewStaticText;
  AppDataCheckBox: TNewCheckBox;
  ModelsCheckBox: TNewCheckBox;
  OKButton: TNewButton;
  CancelButton: TNewButton;
begin
  Result := True;
  DeleteAppDataOnUninstall := False;
  DeleteMathCraftModelsOnUninstall := False;

  if UninstallSilent then
    Exit;

  Form := CreateCustomForm(ScaleX(500), ScaleY(230), False, True);
  try
    Form.Caption := 'Uninstall LaTeXSnipper';

    TitleLabel := TNewStaticText.Create(Form);
    TitleLabel.Parent := Form;
    TitleLabel.Left := ScaleX(16);
    TitleLabel.Top := ScaleY(16);
    TitleLabel.Width := ScaleX(468);
    TitleLabel.Height := ScaleY(28);
    TitleLabel.Font.Style := [fsBold];
    TitleLabel.Caption := 'Choose whether to remove user data';

    DetailLabel := TNewStaticText.Create(Form);
    DetailLabel.Parent := Form;
    DetailLabel.Left := ScaleX(16);
    DetailLabel.Top := ScaleY(48);
    DetailLabel.Width := ScaleX(468);
    DetailLabel.Height := ScaleY(64);
    DetailLabel.WordWrap := True;
    DetailLabel.Caption :=
      'LaTeXSnipper keeps settings, history, dependency state, logs, temporary files, and MathCraft model weights outside the installation directory. ' +
      'These files are preserved by default so upgrades and reinstalls keep working.';

    AppDataCheckBox := TNewCheckBox.Create(Form);
    AppDataCheckBox.Parent := Form;
    AppDataCheckBox.Left := ScaleX(16);
    AppDataCheckBox.Top := ScaleY(120);
    AppDataCheckBox.Width := ScaleX(468);
    AppDataCheckBox.Height := ScaleY(24);
    AppDataCheckBox.Caption := 'Remove LaTeXSnipper user data, logs, dependency state, and temporary files';
    AppDataCheckBox.Checked := False;

    ModelsCheckBox := TNewCheckBox.Create(Form);
    ModelsCheckBox.Parent := Form;
    ModelsCheckBox.Left := ScaleX(16);
    ModelsCheckBox.Top := ScaleY(150);
    ModelsCheckBox.Width := ScaleX(468);
    ModelsCheckBox.Height := ScaleY(24);
    ModelsCheckBox.Caption := 'Remove MathCraft model weights from %APPDATA%\MathCraft\models';
    ModelsCheckBox.Checked := False;

    OKButton := TNewButton.Create(Form);
    OKButton.Parent := Form;
    OKButton.Left := Form.ClientWidth - ScaleX(172);
    OKButton.Top := Form.ClientHeight - ScaleY(40);
    OKButton.Width := ScaleX(80);
    OKButton.Height := ScaleY(26);
    OKButton.Caption := 'Uninstall';
    OKButton.ModalResult := mrOk;

    CancelButton := TNewButton.Create(Form);
    CancelButton.Parent := Form;
    CancelButton.Left := Form.ClientWidth - ScaleX(80);
    CancelButton.Top := Form.ClientHeight - ScaleY(40);
    CancelButton.Width := ScaleX(80);
    CancelButton.Height := ScaleY(26);
    CancelButton.Caption := 'Cancel';
    CancelButton.ModalResult := mrCancel;

    if Form.ShowModal = mrCancel then
    begin
      Result := False;
      Exit;
    end;

    DeleteAppDataOnUninstall := AppDataCheckBox.Checked;
    DeleteMathCraftModelsOnUninstall := ModelsCheckBox.Checked;
  finally
    Form.Free;
  end;
end;

procedure CurUninstallStepChanged(CurUninstallStep: TUninstallStep);
begin
  if CurUninstallStep <> usPostUninstall then
    Exit;

  if DeleteAppDataOnUninstall then
  begin
    CleanupPath(ExpandConstant('{userprofile}\.latexsnipper'));
    CleanupPath(ExpandConstant('{localappdata}\LaTeXSnipper\logs'));
    CleanupPath(ExpandConstant('{tmp}\LaTeXSnipper'));
  end;

  if DeleteMathCraftModelsOnUninstall then
    CleanupPath(ExpandConstant('{userappdata}\MathCraft\models'));
end;
