; Aurora ARGB Studio 安装脚本（Inno Setup 6）
; 编译：ISCC.exe install.iss
; 产物：installer\AuroraARGB-Setup-<版本>.exe

#define AppName "Aurora ARGB Studio"
#define AppShortName "AuroraARGB"
#define AppVersion "1.6.0"
#define AppPublisher "Aurora"
#define AppExe "AuroraARGB.exe"

[Setup]
AppId={{8F3A2C41-7B6E-4D19-9E52-3C7A1B8D4E60}
AppName={#AppName}
AppVersion={#AppVersion}
AppPublisher={#AppPublisher}
DefaultDirName={autopf}\{#AppShortName}
DefaultGroupName={#AppName}
DisableProgramGroupPage=yes
OutputDir=installer
OutputBaseFilename={#AppShortName}-Setup-{#AppVersion}
SetupIconFile=app.ico
UninstallDisplayIcon={app}\{#AppExe}
Compression=lzma2/ultra64
SolidCompression=yes
WizardStyle=modern
PrivilegesRequired=admin
ArchitecturesAllowed=x64compatible
ArchitecturesInstallIn64BitMode=x64compatible
MinVersion=10.0
; 卸载时保留用户配置目录，避免误删灯效设置
UninstallDisplayName={#AppName}

[Languages]
Name: "english"; MessagesFile: "compiler:Default.isl"

[Messages]
; 官方包没带中文语言文件，这里直接覆盖关键文案，界面基本是中文
SetupAppTitle=安装
SetupWindowTitle=安装 - %1
WelcomeLabel1=欢迎使用 [name] 安装向导
WelcomeLabel2=现在将安装 [name/ver] 到你的电脑。%n%n建议关闭其它正在运行的程序，然后点「下一步」继续。
SelectDirDesc=选择安装位置
SelectDirLabel3=安装程序会把 [name] 装到下面的文件夹。
SelectDirBrowseLabel=点「浏览」可以换个位置；想用默认位置就直接点「下一步」。
DiskSpaceMBLabel=至少需要 [mb] MB 磁盘空间。
SelectTasksDesc=附加任务
SelectTasksLabel2=安装 [name] 时还要做哪些事？按需勾选，然后点「下一步」。
ReadyLabel1=一切就绪，可以开始安装了。
ReadyLabel2a=点「安装」开始；想改什么就点「上一步」。
PreparingDesc=正在准备安装……
InstallingLabel=正在安装 [name]，请稍候……
FinishedHeadingLabel=[name] 安装完成
FinishedLabelNoIcons=安装完成，可以从开始菜单启动 [name]。
FinishedLabel=安装完成。桌面和开始菜单都能找到 [name] 的快捷方式。
ClickFinish=点「完成」退出安装程序。
ButtonNext=下一步(&N) >
ButtonBack=< 上一步(&B)
ButtonInstall=安装(&I)
ButtonCancel=取消(&C)
ButtonFinish=完成(&F)
ButtonBrowse=浏览(&R)...
ButtonYes=是(&Y)
ButtonNo=否(&N)
ExitSetupTitle=退出安装
ExitSetupMessage=安装还没完成，现在退出的话不会装上。%n%n确定要退出吗？
UninstalledAll=已从你的电脑卸载 %1。
ConfirmUninstall=确定要卸载 %1 及其组件吗？
UninstallAppFullTitle=卸载 %1
UninstallStatusLabel=正在移除 %1，请稍候……
StatusUninstalling=正在卸载 %1……

[Tasks]
Name: "desktopicon"; Description: "创建桌面快捷方式"; GroupDescription: "附加任务："; Flags: checkedonce
Name: "autostart"; Description: "开机自动启动（登录后静默运行）"; GroupDescription: "附加任务："; Flags: checkedonce

[Files]
Source: "dist\{#AppExe}"; DestDir: "{app}"; Flags: ignoreversion
Source: "dist\使用说明.txt"; DestDir: "{app}"; Flags: ignoreversion isreadme

[Icons]
Name: "{group}\{#AppName}"; Filename: "{app}\{#AppExe}"
Name: "{group}\使用说明"; Filename: "{app}\使用说明.txt"
Name: "{group}\卸载 {#AppName}"; Filename: "{uninstallexe}"
Name: "{autodesktop}\{#AppName}"; Filename: "{app}\{#AppExe}"; Tasks: desktopicon

[Registry]
; 必须用 HKCU：HKA 是「按权限自动选」，admin 安装时会落到 HKLM，
; 导致自启写到机器级、普通用户注销后不生效。
; 注意：[Registry] 段不支持反斜杠续行，只能写成单行。
Root: HKCU; Subkey: "Software\Microsoft\Windows\CurrentVersion\Run"; ValueType: string; ValueName: "{#AppShortName}"; ValueData: """{app}\{#AppExe}"""; Flags: uninsdeletevalue; Tasks: autostart

[Run]
; shellexec 必须加：exe 带 requireAdministrator 清单，
; Inno Setup 默认的 CreateProcess 会直接返回 740（请求的操作需要提升）。
; shellexec 走 ShellExecuteEx，能正确处理提权。
Filename: "{app}\{#AppExe}"; Description: "立即运行 {#AppName}"; Flags: nowait postinstall skipifsilent shellexec

[UninstallRun]
Filename: "{sys}\taskkill.exe"; Parameters: "/F /IM {#AppExe}"; Flags: runhidden; RunOnceId: "KillApp"

[Code]
// 安装完成后如果勾了自启，顺手把可能存在的旧计划任务清掉，
// 免得注册表 Run 与计划任务同时触发、起两个实例互相抢 HID。
procedure CurStepChanged(CurStep: TSetupStep);
var
  ResultCode: Integer;
begin
  if CurStep = ssPostInstall then
  begin
    if WizardIsTaskSelected('autostart') then
    begin
      Exec('schtasks.exe', '/delete /tn "AuroraARGB Boot" /f',
           '', SW_HIDE, ewWaitUntilTerminated, ResultCode);
      Exec('schtasks.exe', '/delete /tn "AuroraARGB Logon" /f',
           '', SW_HIDE, ewWaitUntilTerminated, ResultCode);
    end;
  end;
end;
