; Script de Inno Setup 6 para ContFactu (https://jrsoftware.org/isinfo.php)
; Compilar DESPUÉS de PyInstaller:  "C:\Program Files (x86)\Inno Setup 6\ISCC.exe" instalador\ContFactu.iss
; Genera: instalador\Output\ContFactu-Setup-<versión>.exe
; La versión la pasa construir.bat con /DMyAppVersion=... leyéndola de app\__init__.py (único origen).
; El AppId NO debe cambiar nunca: así una versión nueva se instala encima de la anterior y conserva %APPDATA%\ContFactu.
; Desde la 0.0.3 se instala para todo el equipo en C:\Program Files\ContFactu (pide permiso de administrador).
; Las versiones 0.0.1 y 0.0.2 se instalaban por usuario (%LOCALAPPDATA%\Programs\ContFactu, registro en HKCU):
; al actualizar se desinstala esa copia antigua en silencio (programa, accesos y entrada de «Aplicaciones»),
; SIN tocar los datos de %APPDATA%\ContFactu.
; El instalador solo lleva el programa (dist\ContFactu). Los datos de cada usuario viven en %APPDATA%\ContFactu,
; se crean en el primer arranque con el asistente de importación y NO se borran al desinstalar.

#define MyAppName "ContFactu"
#ifndef MyAppVersion
  #error Compile con construir.bat (pasa /DMyAppVersion=x.y.z leído de app\__init__.py)
#endif
#define MyAppExe "ContFactu.exe"

[Setup]
AppId={{6B1E3C1A-4C7D-4F2B-9C1E-C0F7AC7F0A01}
AppName={#MyAppName}
AppVersion={#MyAppVersion}
AppPublisher=LomoXSoft
AppVerName={#MyAppName} {#MyAppVersion}
VersionInfoVersion={#MyAppVersion}
VersionInfoProductVersion={#MyAppVersion}
VersionInfoCompany=LomoXSoft
VersionInfoDescription=Instalador de ContFactu
; Actualizar encima: cierra ContFactu si está abierto y reutiliza carpeta y accesos
CloseApplications=yes
RestartApplications=no
; Siempre en Archivos de programa (no reutilizar la carpeta por usuario de la 0.0.1/0.0.2)
UsePreviousAppDir=no
UsePreviousGroup=yes
UsePreviousTasks=yes
DisableDirPage=auto
DisableProgramGroupPage=auto
DefaultDirName={autopf}\{#MyAppName}
DefaultGroupName={#MyAppName}
; Instalación para todo el equipo en Archivos de programa (64 bits): pide permiso de administrador (UAC)
PrivilegesRequired=admin
ArchitecturesAllowed=x64compatible
ArchitecturesInstallIn64BitMode=x64compatible
MinVersion=10.0
OutputDir=Output
OutputBaseFilename=ContFactu-Setup-{#MyAppVersion}
Compression=lzma2
SolidCompression=yes
WizardStyle=modern
UninstallDisplayIcon={app}\{#MyAppExe}

[Languages]
Name: "es"; MessagesFile: "compiler:Languages\Spanish.isl"

[Messages]
; %% se ve como %. La página de carpeta no sale al actualizar (DisableDirPage=auto): el texto va en la bienvenida.
WelcomeLabel2=Se va a instalar [name/ver] en este equipo.%n%nPara actualizar ContFactu, instale la versión nueva en la misma carpeta. Los datos de cada usuario están en su carpeta personal (%%APPDATA%%\ContFactu) y no se tocan.
SelectDirDesc=Dónde debe instalarse [name]. Para actualizar, use la misma carpeta. Los datos de %%APPDATA%%\ContFactu no se modifican.

[Tasks]
Name: "escritorio"; Description: "Crear un acceso directo en el escritorio"; GroupDescription: "Accesos directos:"

[InstallDelete]
; Al actualizar, quitar las bibliotecas de la versión anterior (NO toca los datos de %APPDATA%\ContFactu)
Type: filesandordirs; Name: "{app}\_internal"

[Files]
; SOLO el programa empaquetado por PyInstaller (sin bases de datos ni PDFs)
Source: "..\dist\ContFactu\*"; DestDir: "{app}"; Flags: ignoreversion recursesubdirs createallsubdirs

[Icons]
Name: "{group}\{#MyAppName}"; Filename: "{app}\{#MyAppExe}"
Name: "{group}\Desinstalar {#MyAppName}"; Filename: "{uninstallexe}"
Name: "{autodesktop}\{#MyAppName}"; Filename: "{app}\{#MyAppExe}"; Tasks: escritorio

[Run]
; runasoriginaluser: ContFactu se abre como el usuario (sus datos en SU %APPDATA%), no como administrador
Filename: "{app}\{#MyAppExe}"; Description: "Abrir ContFactu ahora"; Flags: nowait postinstall skipifsilent runasoriginaluser

[Code]
const
  CLAVE_DESINST = 'Software\Microsoft\Windows\CurrentVersion\Uninstall\{6B1E3C1A-4C7D-4F2B-9C1E-C0F7AC7F0A01}_is1';

{ ¿Hay una instalación por usuario (0.0.1/0.0.2) registrada en HKCU? }
function InstalacionPorUsuario(var Desinstalador, Carpeta: String): Boolean;
begin
  Result := RegQueryStringValue(HKCU, CLAVE_DESINST, 'UninstallString', Desinstalador);
  if Result then
  begin
    Desinstalador := RemoveQuotes(Desinstalador);
    if not RegQueryStringValue(HKCU, CLAVE_DESINST, 'InstallLocation', Carpeta) then
      Carpeta := ExtractFileDir(Desinstalador);
  end;
end;

{ Desinstala la copia por usuario antes de copiar la nueva. El desinstalador de Inno solo borra lo que instaló
  (programa en %LOCALAPPDATA%\Programs\ContFactu, accesos directos del usuario y su entrada en HKCU);
  los datos de %APPDATA%\ContFactu nunca formaron parte de la instalación y no se tocan. }
function QuitarInstalacionPorUsuario(): String;
var
  Desinstalador, Carpeta, Valor: String;
  Codigo, Espera: Integer;
begin
  Result := '';
  if not InstalacionPorUsuario(Desinstalador, Carpeta) then
    Exit;
  Log('Instalación por usuario anterior en: ' + Carpeta);
  if CompareText(RemoveBackslashUnlessRoot(Carpeta), RemoveBackslashUnlessRoot(ExpandConstant('{app}'))) = 0 then
    Exit;
  if FileExists(Desinstalador) then
  begin
    if not Exec(Desinstalador, '/VERYSILENT /SUPPRESSMSGBOXES /NORESTART', '', SW_HIDE, ewWaitUntilTerminated, Codigo) then
      Log('No se pudo lanzar el desinstalador anterior: ' + SysErrorMessage(Codigo));
    { El desinstalador de Inno se copia a %TEMP% y termina antes de acabar: esperar a que desaparezca su registro }
    Espera := 0;
    while RegQueryStringValue(HKCU, CLAVE_DESINST, 'UninstallString', Valor) and (Espera < 60) do
    begin
      Sleep(500);
      Espera := Espera + 1;
    end;
  end;
  { Si el desinstalador faltaba o falló, limpiar a mano solo lo que es del programa (nunca %APPDATA%) }
  if RegKeyExists(HKCU, CLAVE_DESINST) then
  begin
    Log('Limpieza manual de la instalación por usuario anterior');
    if (Carpeta <> '') and FileExists(AddBackslash(Carpeta) + '{#MyAppExe}') then
      DelTree(Carpeta, True, True, True);
    DeleteFile(ExpandConstant('{userdesktop}\{#MyAppName}.lnk'));
    DelTree(ExpandConstant('{userprograms}\{#MyAppName}'), True, True, True);
    RegDeleteKeyIncludingSubkeys(HKCU, CLAVE_DESINST);
  end;
end;

{ ¿Está ContFactu abierto (de cualquier carpeta)? Sus archivos no se podrían reemplazar ni desinstalar. }
function ContFactuAbierto(): Boolean;
var
  Localizador, Servicio, Lista: Variant;
begin
  Result := False;
  try
    Localizador := CreateOleObject('WbemScripting.SWbemLocator');
    Servicio := Localizador.ConnectServer('.', 'root\CIMV2');
    Lista := Servicio.ExecQuery('SELECT ProcessId FROM Win32_Process WHERE Name = ''{#MyAppExe}''');
    Result := Lista.Count > 0;
  except
    Log('No se pudo comprobar si ContFactu está abierto');
  end;
end;

function PrepareToInstall(var NeedsRestart: Boolean): String;
begin
  if ContFactuAbierto() then
  begin
    Result := 'ContFactu está abierto. Ciérrelo (sus datos ya están guardados) y vuelva a ejecutar el instalador.';
    Exit;
  end;
  Result := QuitarInstalacionPorUsuario();
end;
