; Script de Inno Setup: empaqueta Formato606.exe en un instalador amigable de
; Windows (acceso directo en Escritorio/Menú Inicio, desinstalador, ícono propio).
; Se compila en GitHub Actions con ISCC (Inno Setup Compiler) — ver
; .github/workflows/build-windows.yml

[Setup]
AppId={{18CEDA37-7522-4C94-A494-CBE68630CEE2}}
AppName=Formato 606
AppVersion=1.0
AppPublisher=Bortech
DefaultDirName={autopf}\Formato606
DefaultGroupName=Formato 606
UninstallDisplayIcon={app}\Formato606.exe
OutputDir=dist_installer
OutputBaseFilename=Formato606-Setup
Compression=lzma
SolidCompression=yes
ArchitecturesInstallIn64BitMode=x64compatible
DisableProgramGroupPage=yes
SetupIconFile=icon.ico

[Languages]
Name: "spanish"; MessagesFile: "compiler:Languages\Spanish.isl"

[Tasks]
Name: "desktopicon"; Description: "Crear un acceso directo en el Escritorio"; GroupDescription: "Accesos directos:"

[Files]
Source: "dist\Formato606.exe"; DestDir: "{app}"; Flags: ignoreversion
Source: ".env"; DestDir: "{app}"; Flags: ignoreversion

[Icons]
Name: "{group}\Formato 606"; Filename: "{app}\Formato606.exe"
Name: "{group}\Desinstalar Formato 606"; Filename: "{uninstallexe}"
Name: "{autodesktop}\Formato 606"; Filename: "{app}\Formato606.exe"; Tasks: desktopicon

[Run]
Filename: "{app}\Formato606.exe"; Description: "Abrir Formato 606 ahora"; Flags: nowait postinstall skipifsilent
