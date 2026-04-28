; ============================================================================
;  VozAssistente — script Inno Setup
;  Gera VozAssistente-Setup-<versao>.exe a partir de dist\VozAssistente.exe
;
;  Pré-requisito: Inno Setup 6+ (https://jrsoftware.org/isinfo.php)
;
;  Para compilar manualmente:
;      "C:\Program Files (x86)\Inno Setup 6\ISCC.exe" installer.iss
;
;  Ou rode `build_installer.bat` que faz tudo (PyInstaller + Inno Setup).
; ============================================================================

#define MyAppName        "VozAssistente"
#define MyAppVersion     "1.0.0"
#define MyAppPublisher   "Nicolas Victor"
#define MyAppExeName     "VozAssistente.exe"
#define MyAppId          "{{B5C9D8A2-7E4F-4F6B-9A1A-1234ABCD5678}"
#define MyAppDescription "Assistente pessoal por voz pt-BR (Windows)"

[Setup]
AppId={#MyAppId}
AppName={#MyAppName}
AppVersion={#MyAppVersion}
AppPublisher={#MyAppPublisher}
AppVerName={#MyAppName} {#MyAppVersion}
DefaultDirName={autopf}\{#MyAppName}
DefaultGroupName={#MyAppName}
DisableProgramGroupPage=yes
DisableDirPage=auto
OutputDir=installer_output
OutputBaseFilename=VozAssistente-Setup-{#MyAppVersion}
Compression=lzma2/ultra64
SolidCompression=yes
WizardStyle=modern
ArchitecturesInstallIn64BitMode=x64
PrivilegesRequired=lowest
PrivilegesRequiredOverridesAllowed=dialog
UninstallDisplayName={#MyAppName}
UninstallDisplayIcon={app}\{#MyAppExeName}
ShowLanguageDialog=auto
SetupIconFile=
LicenseFile=
;ChangesEnvironment=yes

[Languages]
Name: "brazilianportuguese"; MessagesFile: "compiler:Languages\BrazilianPortuguese.isl"
Name: "english";             MessagesFile: "compiler:Default.isl"

[Tasks]
Name: "desktopicon"; Description: "{cm:CreateDesktopIcon}"; GroupDescription: "{cm:AdditionalIcons}"; Flags: unchecked
Name: "startupicon"; Description: "Iniciar o {#MyAppName} junto com o Windows"; GroupDescription: "Inicialização:"; Flags: unchecked

[Files]
Source: "dist\{#MyAppExeName}"; DestDir: "{app}"; Flags: ignoreversion
; Copia o config padrão para um arquivo "modelo" ao lado do exe (para fallback portátil)
Source: "assistant\config.json"; DestDir: "{app}"; DestName: "config.default.json"; Flags: ignoreversion
; A cópia editável vai para %APPDATA%\VozAssistente\config.json — feita só se não existir
Source: "assistant\config.json"; DestDir: "{userappdata}\{#MyAppName}"; DestName: "config.json"; Flags: onlyifdoesntexist uninsneveruninstall
Source: "README.md"; DestDir: "{app}"; Flags: ignoreversion isreadme

[Icons]
Name: "{autoprograms}\{#MyAppName}";  Filename: "{app}\{#MyAppExeName}"; Comment: "{#MyAppDescription}"
Name: "{autodesktop}\{#MyAppName}";   Filename: "{app}\{#MyAppExeName}"; Comment: "{#MyAppDescription}"; Tasks: desktopicon
Name: "{userstartup}\{#MyAppName}";   Filename: "{app}\{#MyAppExeName}"; Tasks: startupicon
Name: "{autoprograms}\{#MyAppName} (Editar configuração)"; Filename: "notepad.exe"; Parameters: """{userappdata}\{#MyAppName}\config.json"""

[Run]
Filename: "{app}\{#MyAppExeName}"; Description: "Executar {#MyAppName} agora"; Flags: nowait postinstall skipifsilent

[UninstallDelete]
; logs e modelos baixados ficam em LOCALAPPDATA — removemos só os logs.
; Mantemos %APPDATA%\VozAssistente\config.json para preservar a config do usuário.
Type: filesandordirs; Name: "{localappdata}\{#MyAppName}\logs"
