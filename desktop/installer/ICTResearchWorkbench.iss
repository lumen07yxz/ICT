#define AppName "ICT Research Workbench"
#define AppVersion "0.1.53"

[Setup]
AppId={{D2B998A6-6A25-4F4C-9656-B022F462B572}
AppName={#AppName}
AppVersion={#AppVersion}
AppPublisher=ICT Research Team
DefaultDirName={localappdata}\Programs\ICT Research Workbench
DefaultGroupName={#AppName}
OutputDir=..\dist\installer
OutputBaseFilename=ICTResearchWorkbench-Setup-{#AppVersion}
Compression=lzma2
SolidCompression=yes
PrivilegesRequired=lowest
Uninstallable=yes
WizardStyle=modern
SetupIconFile=..\assets\ict-workbench.ico

[Files]
Source: "..\dist\ICTResearchWorkbench-0.1.53.exe"; DestDir: "{app}"; DestName: "ICTResearchWorkbench.exe"; Flags: ignoreversion

[Icons]
Name: "{group}\{#AppName}"; Filename: "{app}\ICTResearchWorkbench.exe"
Name: "{autodesktop}\{#AppName}"; Filename: "{app}\ICTResearchWorkbench.exe"; Tasks: desktopicon

[Tasks]
Name: "desktopicon"; Description: "创建桌面快捷方式"; GroupDescription: "附加快捷方式："; Flags: unchecked

[Run]
Filename: "{app}\ICTResearchWorkbench.exe"; Description: "启动 {#AppName}"; Flags: postinstall nowait skipifsilent
