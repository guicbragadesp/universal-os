[Setup]
AppId={{90B525BC-905E-4DF8-A6BA-65B612B20011}
AppName=Universal OS
AppVersion=1.10
AppPublisher=Despachante Universal
DefaultDirName={localappdata}\Programs\Universal OS
DefaultGroupName=Universal OS
PrivilegesRequired=lowest
OutputDir=dist
OutputBaseFilename=Instalar-Universal-OS-1.10
Compression=lzma2
SolidCompression=yes
WizardStyle=modern
MinVersion=10.0
ArchitecturesAllowed=x64compatible
DisableProgramGroupPage=yes
CloseApplications=no
RestartApplications=no
DisableWelcomePage=no
SetupIconFile=public\icon.ico
UninstallDisplayIcon={app}\Universal-OS-1.10.exe

[Languages]
Name: "brazilianportuguese"; MessagesFile: "compiler:Languages\BrazilianPortuguese.isl"

[Files]
Source: "dist\Universal-OS.exe"; DestDir: "{app}"; DestName: "Universal-OS-1.10.exe"; Flags: ignoreversion onlyifdoesntexist
Source: "INSTALAR-EM-REDE.txt"; DestDir: "{app}"; Flags: ignoreversion

[Icons]
Name: "{autodesktop}\Universal OS"; Filename: "{app}\Universal-OS-1.10.exe"; Parameters: "{code:LaunchParameters}"
Name: "{group}\Universal OS"; Filename: "{app}\Universal-OS-1.10.exe"; Parameters: "{code:LaunchParameters}"
Name: "{group}\Como usar em rede"; Filename: "{app}\INSTALAR-EM-REDE.txt"

[Run]
Filename: "{app}\Universal-OS-1.10.exe"; Parameters: "{code:LaunchParameters}"; Description: "Abrir Universal OS"; Flags: nowait postinstall skipifsilent

[Code]
var ModePage: TInputOptionWizardPage;

procedure InitializeWizard;
begin
  ModePage := CreateInputOptionPage(wpSelectDir,
    'Como este computador sera usado?', 'Escolha o papel deste computador na rede.',
    'Salve as OS antes de instalar: a versao anterior sera encerrada. Somente UM computador deve ser o principal; os demais usam acesso pela rede.', True, False);
  ModePage.Add('Acesso pela rede: este PC usa as OS do computador principal');
  ModePage.Add('Computador principal: este PC guarda as OS e atende a equipe');
  if ExpandConstant('{param:ROLE|}') = 'server' then
    ModePage.SelectedValueIndex := 1
  else if ExpandConstant('{param:ROLE|}') = 'client' then
    ModePage.SelectedValueIndex := 0
  else if FileExists(ExpandConstant('{localappdata}\UniversalOS\data\universal.sqlite3')) then
    ModePage.SelectedValueIndex := 1
  else
    ModePage.SelectedValueIndex := 0;
end;

function LaunchParameters(Param: String): String;
begin
  if ModePage.SelectedValueIndex = 0 then Result := '--cliente'
  else Result := '';
end;

procedure CurStepChanged(CurStep: TSetupStep);
var ExitCode: Integer;
begin
  if CurStep = ssInstall then
  begin
    { Fecha somente os executaveis anteriores do Universal OS. Nao altera dados. }
    Exec(ExpandConstant('{sys}\taskkill.exe'), '/F /T /IM Universal-OS.exe', '', SW_HIDE, ewWaitUntilTerminated, ExitCode);
    Exec(ExpandConstant('{sys}\taskkill.exe'), '/F /T /IM Universal-OS-1.8.exe', '', SW_HIDE, ewWaitUntilTerminated, ExitCode);
    Exec(ExpandConstant('{sys}\taskkill.exe'), '/F /T /IM Universal-OS-1.9.exe', '', SW_HIDE, ewWaitUntilTerminated, ExitCode);
  end;
end;
