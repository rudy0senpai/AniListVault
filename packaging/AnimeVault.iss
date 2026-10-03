; AnimeVault installer script (Inno Setup 6)
;
; Produces dist\AnimeVault-Setup.exe, which installs the application and
; registers an uninstaller (AnimeVault Uninstall) in Windows.
;
; Build with:
;     packaging\build_windows.ps1
; or directly:
;     iscc packaging\AnimeVault.iss

#define AppName "AnimeVault"
#define AppVersion "0.3.0"
#define AppPublisher "AnimeVault"
#define AppExeName "AnimeVault.exe"
#define SourceDir "..\dist\AnimeVault"

[Setup]
AppId={{7B2C9E14-6A3D-4F58-9C21-5E8D4A6F1B93}
AppName={#AppName}
AppVersion={#AppVersion}
AppVerName={#AppName} {#AppVersion}
AppPublisher={#AppPublisher}
DefaultDirName={autopf}\{#AppName}
DefaultGroupName={#AppName}
DisableProgramGroupPage=yes
OutputDir=..\dist
OutputBaseFilename=AnimeVault-Setup
Compression=lzma2/max
SolidCompression=yes
WizardStyle=modern
; Per-user install by default — no admin rights required.
PrivilegesRequiredOverridesAllowed=dialog
UninstallDisplayIcon={app}\{#AppExeName}
UninstallDisplayName={#AppName}
SetupIconFile=..\src\animevault\resources\media\app.ico
ArchitecturesAllowed=x64compatible
ArchitecturesInstallIn64BitMode=x64compatible

[Languages]
Name: "english"; MessagesFile: "compiler:Default.isl"

[Tasks]
Name: "desktopicon"; Description: "Create a desktop shortcut"; \
    GroupDescription: "Additional shortcuts:"; Flags: unchecked

[Files]
; The frozen application and everything PyInstaller collected.
Source: "{#SourceDir}\*"; DestDir: "{app}"; Flags: ignoreversion recursesubdirs createallsubdirs

[Icons]
Name: "{group}\{#AppName}"; Filename: "{app}\{#AppExeName}"
Name: "{group}\{#AppName} Uninstall"; Filename: "{uninstallexe}"
Name: "{autodesktop}\{#AppName}"; Filename: "{app}\{#AppExeName}"; Tasks: desktopicon

[Run]
Filename: "{app}\{#AppExeName}"; Description: "Launch {#AppName}"; \
    Flags: nowait postinstall skipifsilent

[UninstallDelete]
; Cached data and downloads live outside the install folder, so they are
; removed explicitly on uninstall.
Type: filesandordirs; Name: "{userappdata}\AnimeVault\cache"
Type: filesandordirs; Name: "{userappdata}\AnimeVault\posters"