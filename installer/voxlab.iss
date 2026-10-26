; VoxLab Windows installer — Inno Setup 6 script.
;
; WHY INNO, NOT WiX/MSI (documented decision, 2026-10-27):
; The user asked for a real installer like Voicebox's .msi (518 MB).
; A WiX MSI for this app would need heat-harvested components for
; EVERY file in the PyInstaller folder (thousands of files: torch,
; transformers, _internal/*.pyd/*.dll) with a GUID per component, plus
; WiX v4 + WixUI extension plumbing — fragile to maintain for a
; folder whose contents change every release. Inno Setup does the
; same job with one recursive [Files] entry, and it still gives the
; user everything an MSI gives in practice: a wizard, Start Menu +
; desktop shortcuts, an Add/Remove Programs (Settings > Apps)
; uninstall entry with a real uninstaller, and an upgrade path via a
; stable AppId. The output is VoxLab-Setup-x64.exe, not .msi — that
; difference is stated honestly in PARITY.md and on the release page;
; it is NOT a .msi file and must never be renamed to .msi.
;
; WHY PER-USER, NOT PROGRAM FILES (deliberate, 2026-10-27):
; server.py (frozen) writes all output to <exe-dir>/output and
; makedirs() it at startup. A Program Files install would make that
; directory non-writable for a normal user, so Generate would fail
; after a "successful" install. A per-user install to
; %LOCALAPPDATA%\VoxLab needs no admin prompt and keeps output
; writable. Trade-off, stated honestly: this is a per-user install,
; not a per-machine MSI — other Windows accounts on the same PC do
; not get VoxLab from this install.
;
; Build (GitHub Actions windows-latest, after the smoke test):
;   choco install innosetup -y
;   iscc installer\voxlab.iss /DMyAppVersion=1.0.6
; The workflow passes the version from the git tag (vX.Y.Z -> X.Y.Z);
; without /DMyAppVersion the default below (0.0.0) is used, so a
; locally compiled installer is never mistaken for a release build.
; The script is written for the PyInstaller onedir layout:
; dist\VoxLab\VoxLab.exe + dist\VoxLab\_internal\ — it must run AFTER
; the PyInstaller build and smoke test, never before them.
; PATH NOTE (critical): Inno resolves relative build-time paths
; from the SCRIPT's directory (installer/), NOT the repo root, so
; every repo-root file below is written as ..\... — writing
; dist\VoxLab\* here would look for installer\dist\VoxLab and fail
; the build. OutputDir is likewise ..\installer-output so the
; workflow finds installer-output\VoxLab-Setup-x64.exe at repo root.

#ifndef MyAppVersion
  #define MyAppVersion "0.0.0"
#endif
#define MyAppName "VoxLab"
#define MyAppExeName "VoxLab.exe"
#define MyAppPublisher "Ishtiaque Hasib"

[Setup]
AppId={{7608EC24-8A02-4072-BBE9-25FBE92E7670}
AppName={#MyAppName}
AppVersion={#MyAppVersion}
AppVerName={#MyAppName} {#MyAppVersion}
AppPublisher={#MyAppPublisher}
AppPublisherURL=https://voxlabapp.blogspot.com/
AppSupportURL=https://github.com/ishtiaquehasib/VoxLab
AppUpdatesURL=https://github.com/ishtiaquehasib/VoxLab/releases
DefaultDirName={localappdata}\{#MyAppName}
DefaultGroupName={#MyAppName}
DisableProgramGroupPage=no
ArchitecturesAllowed=x64compatible
ArchitecturesInstallIn64BitMode=x64compatible
PrivilegesRequired=lowest
OutputDir=..\installer-output
OutputBaseFilename=VoxLab-Setup-x64
SetupIconFile=..\assets\voxlab-logo.ico
UninstallDisplayIcon={app}\{#MyAppExeName}
Compression=lzma2
SolidCompression=yes
WizardStyle=modern
LicenseFile=..\LICENSE
; No code signing: VoxLab is unsigned, so Windows SmartScreen will
; still warn on first run. Signing needs a paid code-signing
; certificate, which the zero-cost rule forbids — do not claim
; SmartScreen will not appear.

[Languages]
Name: "english"; MessagesFile: "compiler:Default.isl"

[Tasks]
Name: "desktopicon"; Description: "{cm:CreateDesktopIcon}"; GroupDescription: "{cm:AdditionalIcons}";

[Files]
; The whole PyInstaller folder, recursively. _internal/ holds the
; bundled Python runtime and all app data (app/, assets/).
Source: "..\dist\VoxLab\*"; DestDir: "{app}"; Flags: ignoreversion recursesubdirs createallsubdirs

[Icons]
Name: "{autoprograms}\{#MyAppName}\{#MyAppName}"; Filename: "{app}\{#MyAppExeName}"; WorkingDir: "{app}"; IconFilename: "{app}\{#MyAppExeName}"
Name: "{autoprograms}\{#MyAppName}\Uninstall {#MyAppName}"; Filename: "{uninstallexe}"
Name: "{autodesktop}\{#MyAppName}"; Filename: "{app}\{#MyAppExeName}"; WorkingDir: "{app}"; IconFilename: "{app}\{#MyAppExeName}"; Tasks: desktopicon

[Run]
; Launch after install: VoxLab.exe opens http://127.0.0.1:8000 in the
; default browser via its own 1.5 s timer (server.py __main__).
Filename: "{app}\{#MyAppExeName}"; Description: "{cm:LaunchProgram,{#MyAppName}}"; Flags: nowait postinstall skipifsilent

[UninstallDelete]
; Only remove the install dir if it is empty after uninstall, so a
; user's generated output/ files are never deleted by uninstall.
Type: dirifempty; Name: "{app}"
