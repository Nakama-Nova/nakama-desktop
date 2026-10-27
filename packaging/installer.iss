; Inno Setup script. Build:  ISCC /DAppVersion=1.2.3 packaging\installer.iss
; Expects the PyInstaller folder at dist\VrikshaDesk and THIRD_PARTY_LICENSES.txt at the repo root.
#define AppName "Vriksha Studios Desk"
#ifndef AppVersion
  #define AppVersion "0.0.0"
#endif

[Setup]
AppId={{5C0B6E52-8F47-4C1D-9A53-7D1E2B9A6F31}
AppName={#AppName}
AppVersion={#AppVersion}
AppPublisher=Nakama Nova
AppPublisherURL=https://github.com/Nakama-Nova/nakama-desktop
AppSupportURL=https://github.com/Nakama-Nova/nakama-desktop/issues
DefaultDirName={autopf}\{#AppName}
DefaultGroupName={#AppName}
; Per-user install: no administrator password needed, and updates keep working.
PrivilegesRequired=lowest
ArchitecturesInstallIn64BitMode=x64compatible
LicenseFile=..\LICENSE
OutputDir=..\dist-installer
OutputBaseFilename=VrikshaStudiosDesk-Setup-{#AppVersion}
Compression=lzma2
SolidCompression=yes
WizardStyle=modern
UninstallDisplayIcon={app}\VrikshaDesk.exe

[Tasks]
Name: "desktopicon"; Description: "Create a desktop shortcut"; Flags: unchecked

[Files]
Source: "..\dist\VrikshaDesk\*"; DestDir: "{app}"; Flags: recursesubdirs ignoreversion
Source: "..\LICENSE"; DestDir: "{app}"; Flags: ignoreversion
Source: "..\THIRD_PARTY_LICENSES.txt"; DestDir: "{app}"; Flags: ignoreversion

[Icons]
Name: "{group}\{#AppName}"; Filename: "{app}\VrikshaDesk.exe"
Name: "{group}\Licences"; Filename: "{app}\THIRD_PARTY_LICENSES.txt"
Name: "{autodesktop}\{#AppName}"; Filename: "{app}\VrikshaDesk.exe"; Tasks: desktopicon

[Run]
Filename: "{app}\VrikshaDesk.exe"; Description: "Start {#AppName}"; Flags: nowait postinstall skipifsilent
; An update started from inside the app runs silently: open the app again when it is done.
Filename: "{app}\VrikshaDesk.exe"; Flags: nowait runasoriginaluser; Check: WizardSilent

; Shop data (local database, invoices, settings) lives in %LOCALAPPDATA%\VrikshaStudios and is
; deliberately NOT removed on uninstall.

[Code]
var
  ServerPage: TInputQueryWizardPage;

function EnvFile: string;
begin
  Result := ExpandConstant('{localappdata}\VrikshaStudios\.env');
end;

procedure InitializeWizard;
begin
  ServerPage := CreateInputQueryPage(wpSelectTasks, 'Server address',
    'Where is the Vriksha Studios server?',
    'Leave this as it is if the server runs on this computer. Otherwise type its address, for example https://shop.example.com');
  ServerPage.Add('Server address:', False);
  ServerPage.Values[0] := 'http://127.0.0.1:8000';
end;

function ShouldSkipPage(PageID: Integer): Boolean;
begin
  { an upgrade keeps the address already saved }
  Result := (PageID = ServerPage.ID) and FileExists(EnvFile);
end;

function NextButtonClick(CurPageID: Integer): Boolean;
var
  V: string;
begin
  Result := True;
  if CurPageID = ServerPage.ID then
  begin
    V := LowerCase(Trim(ServerPage.Values[0]));
    if (Pos('http://', V) <> 1) and (Pos('https://', V) <> 1) then
    begin
      MsgBox('The address must start with http:// or https://', mbError, MB_OK);
      Result := False;
    end;
  end;
end;

procedure CurStepChanged(CurStep: TSetupStep);
begin
  if (CurStep = ssPostInstall) and (not FileExists(EnvFile)) then
  begin
    ForceDirectories(ExtractFileDir(EnvFile));
    SaveStringToFile(EnvFile, 'API_BASE_URL=' + Trim(ServerPage.Values[0]) + #13#10, False);
  end;
end;
