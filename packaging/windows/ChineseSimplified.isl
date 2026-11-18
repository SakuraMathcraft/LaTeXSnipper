; *** Inno Setup version 6.5.0+ 简体中文消息 ***
;
; Translation by LaTeXSnipper Team
; Based on Japanese.isl by Koichi Shirasuka

[LangOptions]
LanguageName=简体中文
LanguageID=$0804
LanguageCodePage=936

[Messages]

; *** Application titles
SetupAppTitle=安装程序
SetupWindowTitle=%1 安装程序
UninstallAppTitle=卸载程序
UninstallAppFullTitle=%1 卸载程序

; *** Misc. common
InformationTitle=信息
ConfirmTitle=确认
ErrorTitle=错误

; *** SetupLdr messages
SetupLdrStartupMessage=即将安装 %1。是否继续？
LdrCannotCreateTemp=无法创建临时文件。安装程序将中止。
LdrCannotExecTemp=无法执行临时文件夹中的文件。安装程序将中止。

; *** Startup error messages
LastErrorMessage=%1.%n%n错误 %2: %3
SetupFileMissing=安装文件夹中缺少文件 %1。请解决此问题或重新获取安装程序。
SetupFileCorrupt=安装文件已损坏。请重新获取安装程序。
SetupFileCorruptOrWrongVer=安装文件已损坏，或与此版本的安装程序不兼容。请解决此问题或重新获取安装程序。
InvalidParameter=命令行参数无效:%n%n%1
SetupAlreadyRunning=安装程序已在运行。
WindowsVersionNotSupported=此程序不支持当前 Windows 版本。
WindowsServicePackRequired=此程序需要 %1 Service Pack %2 或更高版本。
NotOnThisPlatform=此程序不能在 %1 上运行。
OnlyOnThisPlatform=此程序需要 %1 才能运行。
OnlyOnTheseArchitectures=此程序只能安装在以下处理器架构的 Windows 上:%n%n%1
WinVersionTooLowError=此程序需要 %1 %2 或更高版本。
WinVersionTooHighError=此程序不支持 %1 %2 或更高版本。
AdminPrivilegesRequired=必须以管理员身份登录才能安装此程序。
PowerUserPrivilegesRequired=必须以管理员或高级用户身份登录才能安装此程序。
SetupAppRunningError=安装程序检测到 %1 正在运行。%n%n请关闭所有正在运行的应用程序，然后单击"确定"继续，或单击"取消"退出安装。
UninstallAppRunningError=卸载程序检测到 %1 正在运行。%n%n请关闭所有正在运行的应用程序，然后单击"确定"继续，或单击"取消"退出卸载。

; *** Startup questions
PrivilegesRequiredOverrideTitle=选择安装模式
PrivilegesRequiredOverrideInstruction=请选择安装模式
PrivilegesRequiredOverrideText1=%1 可以为所有用户安装（需要管理员权限）或仅为当前用户安装。
PrivilegesRequiredOverrideText2=%1 可以为当前用户或所有用户（需要管理员权限）安装。
PrivilegesRequiredOverrideAllUsers=为所有用户安装(&A)
PrivilegesRequiredOverrideAllUsersRecommended=为所有用户安装(&A)（推荐）
PrivilegesRequiredOverrideCurrentUser=仅为当前用户安装(&M)
PrivilegesRequiredOverrideCurrentUserRecommended=仅为当前用户安装(&M)（推荐）

; *** Misc. errors
ErrorCreatingDir=创建文件夹 %1 时出错。
ErrorTooManyFilesInDir=在文件夹 %1 中创建文件时出错。文件数量过多。

; *** Setup common messages
ExitSetupTitle=退出安装程序
ExitSetupMessage=安装尚未完成。如果现在退出，程序将不会被安装。%n%n您可以稍后再次运行安装程序完成安装。%n%n确定要退出安装吗？
AboutSetupMenuItem=关于安装程序(&A)...
AboutSetupTitle=关于安装程序
AboutSetupMessage=%1 %2%n%3%n%n%1 主页:%n%4
AboutSetupNote=
TranslatorNote=

; *** Buttons
ButtonBack=< 上一步(&B)
ButtonNext=下一步(&N) >
ButtonInstall=安装(&I)
ButtonOK=确定
ButtonCancel=取消
ButtonYes=是(&Y)
ButtonYesToAll=全部是(&A)
ButtonNo=否(&N)
ButtonNoToAll=全部否(&O)
ButtonFinish=完成(&F)
ButtonBrowse=浏览(&B)...
ButtonWizardBrowse=浏览(&R)
ButtonNewFolder=新建文件夹(&M)

; *** "Select Language" dialog messages
SelectLanguageTitle=选择安装语言
SelectLanguageLabel=请选择安装过程中使用的语言。

; *** Common wizard text
ClickNext=单击"下一步"继续，或单击"取消"退出安装程序。
BeveledLabel=
BrowseDialogTitle=浏览文件夹
BrowseDialogLabel=请选择一个文件夹，然后单击"确定"。
NewFolderName=新建文件夹

; *** "Welcome" wizard page
WelcomeLabel1=[name] 安装向导
WelcomeLabel2=即将在您的计算机上安装 [name/ver]。%n%n建议您在继续安装前关闭所有其他应用程序。

; *** "Password" wizard page
WizardPassword=输入密码
PasswordLabel1=此安装程序受密码保护。
PasswordLabel3=请输入密码，然后单击"下一步"继续。密码区分大小写。
PasswordEditLabel=密码(&P):
IncorrectPassword=输入的密码不正确。请重新输入。

; *** "License Agreement" wizard page
WizardLicense=许可协议
LicenseLabel=请在继续安装前阅读以下重要信息。
LicenseLabel3=请阅读以下许可协议。您必须接受此协议中的条款才能继续安装。
LicenseAccepted=我接受协议(&A)
LicenseNotAccepted=我不接受协议(&D)

; *** "Information" wizard pages
WizardInfoBefore=信息
InfoBeforeLabel=请在继续安装前阅读以下重要信息。
InfoBeforeClickLabel=准备好继续安装后，请单击"下一步"。
WizardInfoAfter=信息
InfoAfterLabel=请在继续安装前阅读以下重要信息。
InfoAfterClickLabel=准备好继续安装后，请单击"下一步"。

; *** "User Information" wizard page
WizardUserInfo=用户信息
UserInfoDesc=请输入您的用户信息。
UserInfoName=用户名(&U):
UserInfoOrg=组织(&O):
UserInfoSerial=序列号(&S):
UserInfoNameRequired=请输入用户名。

; *** "Select Destination Location" wizard page
WizardSelectDir=选择安装位置
SelectDirDesc=请选择 [name] 的安装位置。
SelectDirLabel3=安装程序将把 [name] 安装到以下文件夹。%n%n要选择其他位置，请单击"浏览"，然后选择其他文件夹。
SelectDirBrowseLabel=单击"下一步"继续。如要选择其他文件夹，请单击"浏览"。
DiskSpaceGBLabel=至少需要 [gb] GB 可用磁盘空间。
DiskSpaceMBLabel=至少需要 [mb] MB 可用磁盘空间。
CannotInstallToNetworkDrive=无法安装到网络驱动器。
CannotInstallToUNCPath=无法安装到 UNC 路径。
InvalidPath=请输入包含驱动器号的完整路径。%n%n例如: C:\APP%n%n或输入 UNC 路径。%n%n例如: \\server\share
InvalidDrive=指定的驱动器或 UNC 路径不存在或无法访问。请选择其他路径。
DiskSpaceWarningTitle=磁盘空间不足
DiskSpaceWarning=安装至少需要 %1 KB 可用磁盘空间，但所选驱动器只有 %2 KB 可用空间。%n%n是否继续安装？
DirNameTooLong=驱动器名或路径过长。
InvalidDirName=文件夹名无效。
BadDirName32=文件夹名不能包含以下字符:%n%n%1
DirExistsTitle=文件夹已存在
DirExists=文件夹 %n%n%1%n%n已存在。是否安装到该文件夹？
DirDoesntExistTitle=文件夹不存在
DirDoesntExist=文件夹 %n%n%1%n%n不存在。是否创建该文件夹？

; *** "Select Components" wizard page
WizardSelectComponents=选择组件
SelectComponentsDesc=请选择要安装的组件。
SelectComponentsLabel2=请选择要安装的组件；不需要的组件请取消勾选。准备好后单击"下一步"。
FullInstallation=完全安装
CompactInstallation=简洁安装
CustomInstallation=自定义安装
NoUninstallWarningTitle=组件已存在
NoUninstallWarning=安装程序检测到以下组件已安装在您的计算机上:%n%n%1%n%n取消选择这些组件不会将其卸载。%n%n是否继续？
ComponentSize1=%1 KB
ComponentSize2=%1 MB
ComponentsDiskSpaceGBLabel=当前选择至少需要 [gb] GB 可用磁盘空间。
ComponentsDiskSpaceMBLabel=当前选择至少需要 [mb] MB 可用磁盘空间。

; *** "Select Additional Tasks" wizard page
WizardSelectTasks=选择附加任务
SelectTasksDesc=请选择要执行的附加任务。
SelectTasksLabel2=请选择在安装 [name] 时要执行的附加任务，然后单击"下一步"。

; *** "Select Start Menu Folder" wizard page
WizardSelectProgramGroup=选择开始菜单文件夹
SelectStartMenuFolderDesc=请选择程序快捷方式的创建位置。
SelectStartMenuFolderLabel3=安装程序将在以下开始菜单文件夹中创建程序快捷方式。
SelectStartMenuFolderBrowseLabel=单击"下一步"继续。如要选择其他文件夹，请单击"浏览"。
MustEnterGroupName=请输入文件夹名。
GroupNameTooLong=文件夹名或路径过长。
InvalidGroupName=文件夹名无效。
BadGroupName=文件夹名不能包含以下字符:%n%n%1
NoProgramGroupCheck2=不创建开始菜单文件夹(&D)

; *** "Ready to Install" wizard page
WizardReady=准备安装
ReadyLabel1=安装程序已准备好在您的计算机上安装 [name]。
ReadyLabel2a=单击"安装"开始安装，或单击"上一步"查看或更改设置。
ReadyLabel2b=单击"安装"开始安装。
ReadyMemoUserInfo=用户信息:
ReadyMemoDir=安装位置:
ReadyMemoType=安装类型:
ReadyMemoComponents=选择组件:
ReadyMemoGroup=开始菜单文件夹:
ReadyMemoTasks=附加任务:

; *** TDownloadWizardPage wizard page and DownloadTemporaryFile
DownloadingLabel2=正在下载文件...
ButtonStopDownload=停止下载(&S)
StopDownload=确定要停止下载吗？
ErrorDownloadAborted=下载已中止
ErrorDownloadFailed=下载失败: %1 %2
ErrorDownloadSizeFailed=获取文件大小失败: %1 %2
ErrorProgress=进度无效: %1 / %2
ErrorFileSize=文件大小无效: 预期 %1，实际 %2

; *** TExtractionWizardPage wizard page and ExtractArchive
ExtractingLabel=正在解压文件...
ButtonStopExtraction=停止解压(&S)
StopExtraction=确定要停止解压吗？
ErrorExtractionAborted=解压已中止
ErrorExtractionFailed=解压失败: %1

; *** Archive extraction failure details
ArchiveIncorrectPassword=密码错误
ArchiveIsCorrupted=压缩文件已损坏
ArchiveUnsupportedFormat=不支持的压缩格式

; *** "Preparing to Install" wizard page
WizardPreparing=正在准备安装
PreparingDesc=安装程序正在准备将 [name] 安装到您的计算机上。
PreviousInstallNotCompleted=之前的程序安装或卸载尚未完成。需要重启计算机才能完成。%n%n要完成 [name] 的安装，请重启计算机后再次运行安装程序。
CannotContinue=安装程序无法继续。请单击"取消"退出安装。
ApplicationsFound=以下应用程序正在使用安装程序需要更新的文件。建议您允许安装程序自动关闭这些应用程序。
ApplicationsFound2=以下应用程序正在使用安装程序需要更新的文件。建议您允许安装程序自动关闭这些应用程序。安装完成后，安装程序将尝试重新启动这些应用程序。
CloseApplications=自动关闭应用程序(&A)
DontCloseApplications=不关闭应用程序(&D)
ErrorCloseApplications=安装程序无法自动关闭所有应用程序。建议您在继续安装前手动关闭所有使用需要更新的文件的应用程序。
PrepareToInstallNeedsRestart=安装程序需要重启您的计算机。重启后，请再次运行安装程序以完成 [name] 的安装。%n%n是否立即重启？

; *** "Installing" wizard page
WizardInstalling=正在安装
InstallingLabel=正在将 [name] 安装到您的计算机上，请稍候...

; *** "Setup Completed" wizard page
FinishedHeadingLabel=[name] 安装完成
FinishedLabelNoIcons=已成功将 [name] 安装到您的计算机上。
FinishedLabel=已成功将 [name] 安装到您的计算机上。可以通过已安装的快捷方式启动应用程序。
ClickFinish=单击"完成"退出安装程序。
FinishedRestartLabel=要完成 [name] 的安装，需要重启您的计算机。是否立即重启？
FinishedRestartMessage=要完成 [name] 的安装，需要重启您的计算机。%n%n是否立即重启？
ShowReadmeCheck=查看 README 文件
YesRadio=立即重启(&Y)
NoRadio=稍后手动重启(&N)
; used for example as 'Run MyProg.exe'
RunEntryExec=运行 %1
; used for example as 'View Readme.txt'
RunEntryShellExec=查看 %1

; *** "Setup Needs the Next Disk" stuff
ChangeDiskTitle=请插入磁盘
SelectDiskLabel2=请插入磁盘 %1，然后单击"确定"。%n%n如果此磁盘上的文件位于其他文件夹，请输入正确的路径或单击"浏览"。
PathLabel=路径(&P):
FileNotInDir2=在 %2 中找不到文件 %1。请插入正确的磁盘或选择其他文件夹。
SelectDirectoryLabel=请指定下一个磁盘的位置。

; *** Installation phase messages
SetupAborted=安装未完成。%n%n请解决此问题后再次运行安装程序。
AbortRetryIgnoreSelectAction=请选择操作
AbortRetryIgnoreRetry=重试(&T)
AbortRetryIgnoreIgnore=忽略错误并继续(&I)
AbortRetryIgnoreCancel=取消安装
RetryCancelSelectAction=请选择操作
RetryCancelRetry=重试(&T)
RetryCancelCancel=取消

; *** Installation status messages
StatusClosingApplications=正在关闭应用程序...
StatusCreateDirs=正在创建文件夹...
StatusExtractFiles=正在解压文件...
StatusDownloadFiles=正在下载文件...
StatusCreateIcons=正在创建快捷方式...
StatusCreateIniEntries=正在写入 INI 配置...
StatusCreateRegistryEntries=正在写入注册表...
StatusRegisterFiles=正在注册文件...
StatusSavingUninstall=正在保存卸载信息...
StatusRunProgram=正在完成安装...
StatusRestartingApplications=正在重启应用程序...
StatusRollback=正在撤销更改...

; *** Misc. errors
ErrorInternal2=内部错误: %1
ErrorFunctionFailedNoCode=%1 失败
ErrorFunctionFailed=%1 失败: 代码 %2
ErrorFunctionFailedWithMessage=%1 失败: 代码 %2.%n%3
ErrorExecutingProgram=执行程序出错:%n%1

; *** Registry errors
ErrorRegOpenKey=打开注册表项出错:%n%1\%2
ErrorRegCreateKey=创建注册表项出错:%n%1\%2
ErrorRegWriteKey=写入注册表项出错:%n%1\%2

; *** INI errors
ErrorIniEntry=创建 INI 条目出错: 文件 %1

; *** File copying errors
FileAbortRetryIgnoreSkipNotRecommended=跳过此文件(&S)（不推荐）
FileAbortRetryIgnoreIgnoreNotRecommended=忽略错误并继续(&I)（不推荐）
SourceIsCorrupted=源文件已损坏。
SourceDoesntExist=源文件 %1 不存在。
SourceVerificationFailed=源文件验证失败: %1
VerificationSignatureDoesntExist=签名文件 "%1" 不存在
VerificationSignatureInvalid=签名文件 "%1" 无效
VerificationKeyNotFound=签名文件 "%1" 使用了未知密钥
VerificationFileNameIncorrect=文件名不正确
VerificationFileTagIncorrect=文件标签不正确
VerificationFileSizeIncorrect=文件大小不正确
VerificationFileHashIncorrect=文件哈希不正确
ExistingFileReadOnly2=无法替换现有文件，该文件为只读。
ExistingFileReadOnlyRetry=移除只读属性并重试(&R)
ExistingFileReadOnlyKeepExisting=保留现有文件(&K)
ErrorReadingExistingDest=读取现有文件时出错:
FileExistsSelectAction=请选择操作
FileExists2=文件已存在。
FileExistsOverwriteExisting=替换现有文件(&O)
FileExistsKeepExisting=保留现有文件(&K)
FileExistsOverwriteOrKeepAll=以后遇到相同情况时执行相同操作(&D)
ExistingFileNewerSelectAction=请选择操作
ExistingFileNewer2=现有文件比安装程序将要安装的文件更新。
ExistingFileNewerOverwriteExisting=替换现有文件(&O)
ExistingFileNewerKeepExisting=保留现有文件(&K)（推荐）
ExistingFileNewerOverwriteOrKeepAll=以后遇到相同情况时执行相同操作(&D)
ErrorChangingAttr=修改现有文件属性时出错:
ErrorCreatingTemp=在目标文件夹中创建文件时出错:
ErrorReadingSource=读取源文件时出错:
ErrorCopying=复制文件时出错:
ErrorDownloading=下载文件时出错:
ErrorExtracting=解压文件时出错:
ErrorReplacingExistingFile=替换现有文件时出错:
ErrorRestartReplace=重启替换失败:
ErrorRenamingTemp=重命名目标文件夹中的文件时出错:
ErrorRegisterServer=无法注册 DLL/OCX: %1
ErrorRegSvr32Failed=RegSvr32 退出代码为 %1
ErrorRegisterTypeLib=无法注册类型库: %1

; *** Uninstall display name markings
UninstallDisplayNameMark=%1 (%2)
UninstallDisplayNameMarks=%1 (%2, %3)
UninstallDisplayNameMark32Bit=32 位
UninstallDisplayNameMark64Bit=64 位
UninstallDisplayNameMarkAllUsers=所有用户
UninstallDisplayNameMarkCurrentUser=当前用户

; *** Post-installation errors
ErrorOpeningReadme=打开 README 文件时出错。
ErrorRestartingComputer=重启计算机失败。请手动重启。

; *** Uninstaller messages
UninstallNotFound=找不到文件 "%1"。无法卸载。
UninstallOpenError=无法打开文件 "%1"。无法卸载。
UninstallUnsupportedVer=卸载日志文件 "%1" 的格式无法被此版本的卸载程序识别。无法卸载。
UninstallUnknownEntry=卸载日志中发现未知条目 (%1)。
ConfirmUninstall=确定要从您的计算机上完全移除 %1 及其所有组件吗？
UninstallOnlyOnWin64=此程序只能在 64 位 Windows 上卸载。
OnlyAdminCanUninstall=必须以管理员身份登录才能卸载此程序。
UninstallStatusLabel=正在从您的计算机上卸载 %1，请稍候...
UninstalledAll=%1 已成功从您的计算机上移除。
UninstalledMost=%1 的卸载已完成。%n%n某些项目无法删除。请手动删除它们。
UninstalledAndNeedsRestart=要完成 %1 的卸载，需要重启您的计算机。是否立即重启？
UninstallDataCorrupted=文件 "%1" 已损坏。无法卸载。

; *** Uninstallation phase messages
ConfirmDeleteSharedFileTitle=删除共享文件
ConfirmDeleteSharedFile2=系统显示以下共享文件已不再被任何程序使用。是否删除这些共享文件？%n%n如果仍有程序使用这些文件，删除后可能导致这些程序无法正常运行。如果不确定，请选择"否"。在系统中保留这些文件不会造成任何问题。
SharedFileNameLabel=文件名:
SharedFileLocationLabel=位置:
WizardUninstalling=正在卸载
StatusUninstalling=正在卸载 %1...

; *** Shutdown block reasons
ShutdownBlockReasonInstallingApp=正在安装 %1。
ShutdownBlockReasonUninstallingApp=正在卸载 %1。

; The custom messages below aren't used by Setup itself, but if you make
; use of them in your scripts, you'll want to translate them.

[CustomMessages]

NameAndVersion=%1 版本 %2
AdditionalIcons=附加图标:
CreateDesktopIcon=创建桌面快捷方式(&D)
CreateQuickLaunchIcon=创建快速启动图标(&Q)
ProgramOnTheWeb=%1 官方网站
UninstallProgram=卸载 %1
LaunchProgram=运行 %1
AssocFileExtension=将 %1 与文件扩展名 %2 关联
AssocingFileExtension=正在将 %1 与文件扩展名 %2 关联...
AutoStartProgramGroupDescription=启动:
AutoStartProgram=启动时自动运行 %1
AddonHostProgramNotFound=在所选文件夹中找不到 %1。%n%n是否继续?
