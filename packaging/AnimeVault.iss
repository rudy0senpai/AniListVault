; AnimeVault installer script (Inno Setup 6)
;
; Produces dist\AnimeVault-Setup.exe, which installs the application and
; registers an uninstaller (AnimeVault Uninstall) in Windows.
;
; Build with:
;     packaging\build_windows.ps1
; (the build script reads the canonical version and uses a fresh staging path).

#define AppName "AnimeVault"
#define AppVersion GetEnv("ANIMEVAULT_VERSION")
#if AppVersion == ""
  #error "Run packaging/build_windows.ps1 to supply the version from src/animevault/_version.py"
#endif
#define AppPublisher "rudy0senpai"
#define AppExeName "AnimeVault.exe"
#ifndef SourceDir
  #error "Run packaging/build_windows.ps1; direct builds may package stale output."
#endif
#ifndef OutputDir
  #error "Run packaging/build_windows.ps1 to set the versioned output directory."
#endif

[Setup]
AppId={{7B2C9E14-6A3D-4F58-9C21-5E8D4A6F1B93}
AppName={#AppName}
AppVersion={#AppVersion}
AppVerName={#AppName} {#AppVersion}
AppPublisher={#AppPublisher}
DefaultDirName={autopf}\{#AppName}
DefaultGroupName={#AppName}
DisableProgramGroupPage=yes
OutputDir={#OutputDir}
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
