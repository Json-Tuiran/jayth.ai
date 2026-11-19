; Instalador de Jayth para Windows (Inno Setup 6). Lo genera packaging\windows\build.ps1:
;   ISCC /DMyAppVersion=0.2.0 packaging\windows\jayth.iss
; Se instala para el usuario actual (sin permisos de administrador) en %LOCALAPPDATA%\Programs\Jayth.
; Los datos (ajustes, conversaciones, modelos) estan en %LOCALAPPDATA%\Jayth y no se tocan al actualizar ni al desinstalar.

#ifndef MyAppVersion
  #define MyAppVersion "0.0.0"
#endif
#define MyAppName "Jayth"
#define MyAppExe "Jayth.exe"
#define MyRepo "https://github.com/Json-Tuiran/jayth.ai"

[Setup]
AppId={{8E5B2C61-4D7A-4F0E-9C3B-6A1D2F7E9B40}
AppName={#MyAppName}
AppVersion={#MyAppVersion}
AppVerName={#MyAppName} {#MyAppVersion}
AppPublisher={#MyAppName}
AppPublisherURL={#MyRepo}
AppSupportURL={#MyRepo}/issues
AppUpdatesURL={#MyRepo}/releases
VersionInfoVersion={#MyAppVersion}
DefaultDirName={localappdata}\Programs\{#MyAppName}
DefaultGroupName={#MyAppName}
DisableProgramGroupPage=yes
DisableDirPage=auto
DisableReadyPage=yes
PrivilegesRequired=lowest
ArchitecturesAllowed=x64compatible
ArchitecturesInstallIn64BitMode=x64compatible
MinVersion=10.0.17763
OutputDir=..\..\dist
OutputBaseFilename=Jayth-Setup-{#MyAppVersion}-x64
SetupIconFile=..\..\assets\icon.ico
UninstallDisplayIcon={app}\{#MyAppExe}
UninstallDisplayName={#MyAppName}
Compression=lzma2/max
SolidCompression=yes
WizardStyle=modern
CloseApplications=yes
RestartApplications=no

[Languages]
Name: "es"; MessagesFile: "compiler:Languages\Spanish.isl"
Name: "en"; MessagesFile: "compiler:Default.isl"

[Tasks]
Name: "desktopicon"; Description: "{cm:CreateDesktopIcon}"; GroupDescription: "{cm:AdditionalIcons}"

[InstallDelete]
; al actualizar, se quitan las bibliotecas de la version anterior para no mezclar versiones
Type: filesandordirs; Name: "{app}\_internal"

[Files]
Source: "..\..\dist\Jayth\*"; DestDir: "{app}"; Flags: ignoreversion recursesubdirs createallsubdirs

[Icons]
Name: "{autoprograms}\{#MyAppName}"; Filename: "{app}\{#MyAppExe}"
Name: "{autodesktop}\{#MyAppName}"; Filename: "{app}\{#MyAppExe}"; Tasks: desktopicon

[Run]
Filename: "{app}\{#MyAppExe}"; Description: "{cm:LaunchProgram,{#MyAppName}}"; Flags: nowait postinstall skipifsilent
; actualizacion automatica desde la app (/SILENT /RELAUNCH=1): se vuelve a abrir al terminar
Filename: "{app}\{#MyAppExe}"; Flags: nowait; Check: IsRelaunch

[UninstallDelete]
Type: files; Name: "{userstartup}\{#MyAppName}.lnk"

[Code]
function IsRelaunch: Boolean;
begin
  Result := ExpandConstant('{param:RELAUNCH|0}') = '1';
end;
