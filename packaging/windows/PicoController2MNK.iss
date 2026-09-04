; Inno Setup script for the PicoController2MNK Configurator.

#define RootDir AddBackslash(SourcePath) + "..\.."
#define AppVersion "0.1.2"

[Setup]
AppId={{8A7FCB95-6B9D-4A3B-8D6A-5CB8D8F52A71}
AppName=PicoController2MNK Configurator
AppVersion={#AppVersion}
AppPublisher=Xiaode2333
DefaultDirName={localappdata}\Programs\PicoController2MNK
DefaultGroupName=PicoController2MNK
OutputDir={#RootDir}\installer
OutputBaseFilename=PicoController2MNK-Setup-{#AppVersion}
Compression=lzma2
SolidCompression=yes
WizardStyle=modern
ArchitecturesAllowed=x64compatible
ArchitecturesInstallIn64BitMode=x64compatible
DisableProgramGroupPage=yes
PrivilegesRequired=lowest
SetupIconFile={#RootDir}\assets\icon.ico
UninstallDisplayIcon={app}\assets\PicoController2MNK.ico

[Languages]
Name: "english"; MessagesFile: "compiler:Default.isl"

[Tasks]
Name: "desktopicon"; Description: "Create a desktop shortcut"; GroupDescription: "Additional shortcuts:"

[Files]
Source: "{#RootDir}\dist\PicoController2MNK\*"; DestDir: "{app}"; Flags: ignoreversion recursesubdirs createallsubdirs
Source: "{#RootDir}\assets\icon.ico"; DestDir: "{app}\assets"; DestName: "PicoController2MNK.ico"; Flags: ignoreversion
Source: "{#RootDir}\build\pico_kbm_mapper.uf2"; DestDir: "{app}\firmware"; Flags: ignoreversion
Source: "{#RootDir}\README_CONFIGURATOR.md"; DestDir: "{app}"; Flags: ignoreversion
Source: "{#RootDir}\MAPPINGS.md"; DestDir: "{app}"; Flags: ignoreversion

[Icons]
Name: "{autoprograms}\PicoController2MNK Configurator"; Filename: "{app}\PicoController2MNK.exe"; IconFilename: "{app}\assets\PicoController2MNK.ico"
Name: "{autodesktop}\PicoController2MNK Configurator"; Filename: "{app}\PicoController2MNK.exe"; IconFilename: "{app}\assets\PicoController2MNK.ico"; Tasks: desktopicon

[Run]
Filename: "{app}\PicoController2MNK.exe"; Description: "Launch PicoController2MNK Configurator"; Flags: nowait postinstall skipifsilent
