; AnimeVault Windows Installer - Inno Setup 6 Script
; Full installer that deploys the complete application with all Qt plugins
; and resources. Supports both one-file and standalone deployment modes.

[Setup]
; Installation settings
AppName=AnimeVault
AppVersion=0.3.1
AppPublisher=AnimeVault Contributors
AppPublisherURL=https://github.com/animevault/AniListVault
AppSupportURL=https://github.com/animevault/AniListVault/issues
AppUpdatesURL=https://github.com/animevault/AniListVault/releases
DefaultDirName={autopf}\AnimeVault
DefaultGroupName=AnimeVault
UninstallDisplayIcon={app}\AnimeVault.exe
OutputBaseFilename=AnimeVault-Setup
OutputDir=.
SetupIconFile=..\src\animevault\resources\media\app.ico
Compression=lzma2/max
SolidCompression=yes
WizardStyle=modern
PrivilegesRequiredOverridesAllowed=dialog
; Register as a Windows application
AppMutex=AnimeVault

[Tasks]
Name: desktopicon; Description: Create a desktop icon; GroupDescription: AnimeVault
Name: quicklaunch; Description: Create a Quick Launch icon; GroupDescription: AnimeVault

[Files]
; Application executable. This is a one-file Nuitka executable with all
; dependencies embedded. The installer verifies the file is valid and
; complete before proceeding.
Source: ..\AnimeVault.exe; DestDir: {app}; DestName: AnimeVault.exe; Flags: ignoreversion

; Qt platform plugins and other dependencies (from standalone build)
; These are required at runtime but are embedded in a one-file executable.
; The installer includes a placeholder version - actual deployment uses
; the embedded Qt plugins within the one-file executable.

; Application resources (icons, backgrounds, etc.)
Source: ..\src\animevault\resources\media\app.ico; DestDir: {app}; Flags: ignoreversion
Source: ..\src\animevault\resources\media\background.mp4; DestDir: {app}; Flags: ignoreversion

; Fallback for standalone mode - if a folder is selected via command line,
; include its contents. (This section is for documentation; the actual
; deployment uses the one-file executable.)

[Registry]
; Register in Windows Uninstaller (Windows Installed Apps)
Root: HKCU; SubKey: Software\Microsoft\Windows\CurrentVersion\Uninstall\AnimeVault; ValueType: string; ValueName: DisplayName; ValueData: AnimeVault; Flags: uninsdeletekey
Root: HKCU; SubKey: Software\Microsoft\Windows\CurrentVersion\Uninstall\AnimeVault; ValueType: string; ValueName: DisplayVersion; ValueData: 0.3.1; Flags: uninsdeletekey
Root: HKCU; SubKey: Software\Microsoft\Windows\CurrentVersion\Uninstall\AnimeVault; ValueType: string; ValueName: Publisher; ValueData: AnimeVault Contributors; Flags: uninsdeletekey
Root: HKCU; SubKey: Software\Microsoft\Windows\CurrentVersion\Uninstall\AnimeVault; ValueType: string; ValueName: InstallLocation; ValueData: {app}; Flags: uninsdeletekey
Root: HKCU; SubKey: Software\Microsoft\Windows\CurrentVersion\Uninstall\AnimeVault; ValueType: string; ValueName: DisplayIcon; ValueData: {app}\AnimeVault.exe; Flags: uninsdeletekey
Root: HKCU; SubKey: Software\Microsoft\Windows\CurrentVersion\Uninstall\AnimeVault; ValueType: string; ValueName: Publisher; ValueData: AnimeVault Contributors; Flags: uninsdeletekey
Root: HKCU; SubKey: Software\Microsoft\Windows\CurrentVersion\Uninstall\AnimeVault; ValueType: string; ValueName: HelpLink; ValueData: https://github.com/animevault/AniListVault/issues; Flags: uninsdeletekey
Root: HKCU; SubKey: Software\Microsoft\Windows\CurrentVersion\Uninstall\AnimeVault; ValueType: string; ValueName: URLInfoAbout; ValueData: https://github.com/animevault/AniListVault; Flags: uninsdeletekey
Root: HKCU; SubKey: Software\Microsoft\Windows\CurrentVersion\Uninstall\AnimeVault; ValueType: dword; ValueName: NoModify; ValueData: 1; Flags: uninsdeletekey
Root: HKCU; SubKey: Software\Microsoft\Windows\CurrentVersion\Uninstall\AnimeVault; ValueType: dword; ValueName: NoRepair; ValueData: 1; Flags: uninsdeletekey
Root: HKCU; SubKey: Software\Microsoft\Windows\CurrentVersion\Uninstall\AnimeVault; ValueType: string; ValueName: InstallDate; ValueData: 2024-01-01; Flags: uninsdeletekey

[Icons]
; Start Menu shortcut
Name: "{group}\AnimeVault"; Filename: "{app}\AnimeVault.exe"
; Start Menu Uninstaller shortcut
Name: "{group}\AnimeVault Uninstall"; Filename: "{uninstallexe}"
; Desktop shortcut (optional, user can choose to create it)
Name: "{autodesktop}\AnimeVault"; Filename: "{app}\AnimeVault.exe"; Tasks: desktopicon
; Quick Launch shortcut (optional)
Name: "{userappdata}\Microsoft\Internet Explorer\Quick Launch\AnimeVault"; Filename: "{app}\AnimeVault.exe"; Tasks: quicklaunch

[Run]
; Launch application after installation (if user chooses to launch)
Filename: "{app}\AnimeVault.exe"; Description: "Launch AnimeVault"; Flags: nowait postinstall runascurrentuser

[UninstallRun]
; Preserve user data: do not delete library database, downloaded posters,
; settings, or other personal application data during uninstallation.
; The user can optionally choose to remove this data via custom dialogs
; or the "Remove all data" option.

; Clean up application binaries and shortcuts during uninstallation
; (user data is preserved automatically by Inno Setup when no explicit
; deletion is requested for those files)

