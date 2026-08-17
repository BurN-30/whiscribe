; ===========================================================================
;  WhiScribe, programme d'installation
;
;  Prend la sortie « onedir » de PyInstaller (dist\WhiScribe) et produit un
;  fichier unique WhiScribe-Setup-X.Y.Z.exe.
;
;  Partis pris :
;    - installation PAR UTILISATEUR, sans droits administrateur, dans
;      {localappdata}\Programs\WhiScribe. C'est ce qui permet de poser
;      l'application sur un poste d'entreprise verrouillé ;
;    - les modèles de transcription, de 1,6 à 3,1 Go, ont leur propre page de
;      choix d'emplacement : on doit pouvoir les envoyer sur un autre disque ;
;    - rien n'est téléchargé pendant l'installation, sauf le runtime WebView2
;      de Microsoft s'il manque, et depuis le site de Microsoft uniquement ;
;    - une réinstallation par-dessus met à jour sans rien perdre : ni la
;      configuration, ni le glossaire, ni les corrections, ni les modèles.
;
;  Compilation :
;      iscc /DVersionApp=2.0.0 packaging\setup.iss
;
;  Le dossier « dist\WhiScribe » doit exister au préalable.
; ===========================================================================

#ifndef VersionApp
  #define VersionApp "2.0.0"
#endif

#define NomApp        "WhiScribe"
#define Editeur       "Nathan SACCOL"
#define UrlProjet     "https://github.com/BurN-30/whiscribe"
#define ExeApp        "WhiScribe.exe"
#define DossierSource "..\dist\WhiScribe"

; Lien officiel et permanent de Microsoft vers le programme d'amorçage WebView2.
; Aucun binaire tiers n'est embarqué : c'est Microsoft qui sert le fichier.
#define UrlWebView2   "https://go.microsoft.com/fwlink/p/?LinkId=2124703"

[Setup]
; Identifiant figé : c'est lui qui fait qu'une nouvelle version se pose
; par-dessus l'ancienne au lieu de créer une deuxième entrée.
AppId={{4E1B7C86-8F2A-4B5D-9C31-6D0A4F7E2B93}
AppName={#NomApp}
AppVersion={#VersionApp}
AppVerName={#NomApp} {#VersionApp}
VersionInfoVersion={#VersionApp}
VersionInfoProductVersion={#VersionApp}
VersionInfoProductName={#NomApp}
VersionInfoDescription=Programme d'installation de {#NomApp}
VersionInfoCompany={#Editeur}
VersionInfoCopyright=Licence MIT, {#Editeur}
AppPublisher={#Editeur}
AppPublisherURL={#UrlProjet}
AppSupportURL={#UrlProjet}/issues
AppUpdatesURL={#UrlProjet}/releases
AppReadmeFile={app}\README.md

DefaultDirName={localappdata}\Programs\{#NomApp}
DefaultGroupName={#NomApp}
UninstallDisplayName={#NomApp}
UninstallDisplayIcon={app}\{#ExeApp}
LicenseFile=..\LICENSE

; Sans droits administrateur par défaut. Si l'utilisateur désigne malgré tout un
; emplacement système, Windows demandera l'élévation au lieu d'échouer.
PrivilegesRequired=lowest
PrivilegesRequiredOverridesAllowed=dialog

; Pages laissées visibles : l'utilisateur choisit son dossier et son groupe.
DisableDirPage=no
DisableProgramGroupPage=no
DisableWelcomePage=no
AllowNoIcons=yes

; Une instance ouverte pendant une mise à jour est fermée proprement, puis
; relancée, plutôt que de faire échouer la copie des fichiers.
CloseApplications=yes
CloseApplicationsFilter=*.exe,*.dll,*.pyd
RestartApplications=yes

Compression=lzma2/max
SolidCompression=yes
LZMAUseSeparateProcess=yes
ArchitecturesAllowed=x64compatible
ArchitecturesInstallIn64BitMode=x64compatible
MinVersion=10.0

OutputDir=sortie
OutputBaseFilename={#NomApp}-Setup-{#VersionApp}
SetupIconFile=whiscribe.ico
WizardStyle=modern
WizardSizePercent=110
ShowLanguageDialog=no

[Languages]
Name: "french"; MessagesFile: "compiler:Languages\French.isl"

[CustomMessages]
french.PageModelesTitre=Emplacement des modèles de transcription
french.PageModelesDescription=Où faut-il ranger les fichiers de reconnaissance vocale ?
french.PageModelesTexte=Les modèles sont volumineux et se téléchargent une seule fois, au premier usage de l'application, pas pendant cette installation.%n%n    Preset « Rapide » : environ 1,6 Go%n    Preset « Qualité maximale » : environ 3,1 Go%n%nSi votre disque système est à l'étroit, choisissez un autre disque. Cet emplacement reste modifiable plus tard, dans les réglages de l'application, section « Modèles ».
french.PageModelesLibelle=Ranger les modèles dans ce dossier :
french.TacheBureau=Créer une icône sur le &Bureau
french.LancerApp=Lancer {#NomApp}
french.WebView2Titre=Composant Microsoft WebView2
french.WebView2Description=Téléchargement du composant d'affichage depuis le site de Microsoft
french.WebView2Manquant=L'affichage de {#NomApp} s'appuie sur « Microsoft Edge WebView2 Runtime », qui n'est pas présent sur ce poste.%n%nIl va être téléchargé depuis le site de Microsoft, puis installé. Comptez quelques dizaines de mégaoctets.%n%nVoulez-vous continuer ?
french.WebView2Echec=Le composant WebView2 n'a pas pu être installé automatiquement.%n%nL'installation de {#NomApp} va se poursuivre, mais la fenêtre ne s'ouvrira pas tant que ce composant manquera. Vous pourrez le poser depuis :%n%n{#UrlWebView2}
french.EspaceInsuffisant=Il ne reste qu'environ %1 Go de libre sur ce disque.%n%nLe modèle de qualité maximale en demande 3,1 à lui seul. Voulez-vous quand même garder cet emplacement ?
french.DossierModelesRefuse=Ce dossier n'a pas pu être créé, ou n'est pas accessible en écriture.%n%nChoisissez un autre emplacement.
french.DesinstallerModeles=Supprimer aussi les modèles de transcription ?%n%nIls occupent %1 dans :%n%2%n%nRépondez Non pour les conserver : une réinstallation les retrouvera et n'aura rien à retélécharger.
french.DesinstallerDonnees=Supprimer aussi vos données personnelles de {#NomApp} ?%n%nCela effacerait définitivement votre glossaire, vos règles de correction, vos réglages et les journaux, dans :%n%1%n%nRépondez Non pour les conserver.

[Tasks]
; Décochée par défaut : on ne pose pas d'icône sur le bureau sans le demander.
Name: "desktopicon"; Description: "{cm:TacheBureau}"; GroupDescription: "{cm:AdditionalIcons}"; Flags: unchecked

[Files]
Source: "{#DossierSource}\*"; DestDir: "{app}"; Flags: ignoreversion recursesubdirs createallsubdirs

[Icons]
Name: "{group}\{#NomApp}"; Filename: "{app}\{#ExeApp}"; WorkingDir: "{app}"; Comment: "Transcription audio, entièrement sur votre machine"
Name: "{group}\{cm:UninstallProgram,{#NomApp}}"; Filename: "{uninstallexe}"
Name: "{autodesktop}\{#NomApp}"; Filename: "{app}\{#ExeApp}"; WorkingDir: "{app}"; Tasks: desktopicon

[Run]
Filename: "{app}\{#ExeApp}"; Description: "{cm:LancerApp}"; Flags: nowait postinstall skipifsilent

[UninstallDelete]
; Fichier écrit après l'installation, donc inconnu de la liste [Files].
Type: files; Name: "{app}\emplacement-modeles.txt"
Type: dirifempty; Name: "{app}"

[Code]
var
  PageModeles: TInputDirWizardPage;
  PageTelechargement: TDownloadWizardPage;

{ --------------------------------------------------------------------------
  Emplacements partagés avec l'application, voir app/chemins.py
  -------------------------------------------------------------------------- }

function DossierDonnees(): String;
begin
  Result := ExpandConstant('{localappdata}') + '\WhiScribe';
end;

function FichierChoixModeles(): String;
begin
  Result := DossierDonnees() + '\dossier-modeles.txt';
end;

function DossierModelesDefaut(): String;
begin
  Result := DossierDonnees() + '\modeles';
end;

{ Emplacement effectif au moment où l'on parle : celui que l'application utilise
  réellement, éventuellement changé depuis l'installation précédente. }
function DossierModelesEffectif(): String;
var
  Lignes: TArrayOfString;
  Valeur: String;
begin
  Result := DossierModelesDefaut();
  if FileExists(FichierChoixModeles()) then
  begin
    if LoadStringsFromFile(FichierChoixModeles(), Lignes) and (GetArrayLength(Lignes) > 0) then
    begin
      Valeur := Trim(Lignes[0]);
      if Valeur <> '' then
        Result := Valeur;
    end;
  end;
end;

{ --------------------------------------------------------------------------
  Utilitaires
  -------------------------------------------------------------------------- }

{ Taille occupée par un dossier, récursivement. Sert à annoncer à la
  désinstallation ce que la suppression des modèles libérerait réellement. }
function TailleDossier(Dossier: String): Int64;
var
  Recherche: TFindRec;
begin
  Result := 0;
  if not DirExists(Dossier) then
    Exit;
  if FindFirst(Dossier + '\*', Recherche) then
  begin
    try
      repeat
        if (Recherche.Name <> '.') and (Recherche.Name <> '..') then
        begin
          if (Recherche.Attributes and FILE_ATTRIBUTE_DIRECTORY) <> 0 then
            Result := Result + TailleDossier(Dossier + '\' + Recherche.Name)
          else
            { Pas de décalage binaire : la multiplication est acceptée partout. }
            Result := Result + Int64(Recherche.SizeHigh) * 4294967296 + Int64(Recherche.SizeLow);
        end;
      until not FindNext(Recherche);
    finally
      FindClose(Recherche);
    end;
  end;
end;

function TailleLisible(Octets: Int64): String;
begin
  if Octets >= 1073741824 then
    Result := Format('%.1f Go', [Octets / 1073741824.0])
  else if Octets >= 1048576 then
    Result := Format('%.0f Mo', [Octets / 1048576.0])
  else
    { Toujours un flottant : Format n'accepte pas un Int64 sur « %d ». }
    Result := Format('%.0f Ko', [Octets / 1024.0]);
  StringChangeEx(Result, '.', ',', True);
end;

function EspaceLibreGo(Chemin: String): Extended;
var
  Racine: String;
  Libre, Total: Int64;
begin
  Result := 0;
  Racine := ExtractFileDrive(Chemin);
  if Racine = '' then
    Exit;
  if GetSpaceOnDisk64(Racine + '\', Libre, Total) then
    Result := Libre / 1073741824.0;
end;

{ Le runtime WebView2 s'annonce dans la base de registre, par machine ou par
  utilisateur. Une clé « pv » non vide et différente de 0.0.0.0 vaut présence. }
function VersionWebView2(Racine: Integer; Cle: String): String;
begin
  if not RegQueryStringValue(Racine, Cle, 'pv', Result) then
    Result := '';
end;

function WebView2Present(): Boolean;
const
  CleClient = 'Software\Microsoft\EdgeUpdate\Clients\{F3017226-FE2A-4295-8BDF-00C3A9A7E4C5}';
  CleClient32 = 'Software\WOW6432Node\Microsoft\EdgeUpdate\Clients\{F3017226-FE2A-4295-8BDF-00C3A9A7E4C5}';
var
  Version: String;
begin
  Version := VersionWebView2(HKEY_LOCAL_MACHINE, CleClient32);
  if Version = '' then
    Version := VersionWebView2(HKEY_LOCAL_MACHINE, CleClient);
  if Version = '' then
    Version := VersionWebView2(HKEY_CURRENT_USER, CleClient);
  Result := (Version <> '') and (Version <> '0.0.0.0');
end;

{ --------------------------------------------------------------------------
  Assistant
  -------------------------------------------------------------------------- }

function SurProgressionTelechargement(NomFichier, UrlFichier: String; Recus, Total: Int64): Boolean;
begin
  if Total > 0 then
    PageTelechargement.SetProgress(Recus, Total);
  Result := True;
end;

procedure InitializeWizard();
begin
  PageModeles := CreateInputDirPage(
    wpSelectDir,
    ExpandConstant('{cm:PageModelesTitre}'),
    ExpandConstant('{cm:PageModelesDescription}'),
    ExpandConstant('{cm:PageModelesTexte}'),
    False, '');
  PageModeles.Add(ExpandConstant('{cm:PageModelesLibelle}'));
  { Pré-rempli avec l'emplacement réellement utilisé : une mise à jour ne
    déplace rien tant que l'utilisateur ne touche pas au champ. }
  PageModeles.Values[0] := DossierModelesEffectif();

  PageTelechargement := CreateDownloadPage(
    ExpandConstant('{cm:WebView2Titre}'),
    ExpandConstant('{cm:WebView2Description}'),
    @SurProgressionTelechargement);
end;

function InstallerWebView2(): Boolean;
var
  Code: Integer;
begin
  Result := False;
  PageTelechargement.Clear;
  PageTelechargement.Add('{#UrlWebView2}', 'MicrosoftEdgeWebview2Setup.exe', '');
  PageTelechargement.Show;
  try
    try
      PageTelechargement.Download;
      { Installation par utilisateur, sans interface : cohérent avec le reste. }
      Result := Exec(ExpandConstant('{tmp}\MicrosoftEdgeWebview2Setup.exe'),
                     '/silent /install', '', SW_HIDE, ewWaitUntilTerminated, Code)
                and (Code = 0);
    except
      Result := False;
    end;
  finally
    PageTelechargement.Hide;
  end;
end;

function NextButtonClick(CurPageID: Integer): Boolean;
var
  Cible: String;
  Libre: Extended;
  Texte: String;
begin
  Result := True;

  if CurPageID = PageModeles.ID then
  begin
    Cible := Trim(PageModeles.Values[0]);
    if Cible = '' then
    begin
      PageModeles.Values[0] := DossierModelesDefaut();
      Cible := PageModeles.Values[0];
    end;
    if not ForceDirectories(Cible) then
    begin
      MsgBox(ExpandConstant('{cm:DossierModelesRefuse}'), mbError, MB_OK);
      Result := False;
      Exit;
    end;
    Libre := EspaceLibreGo(Cible);
    if (Libre > 0) and (Libre < 4.0) then
    begin
      Texte := Format('%.1f', [Libre]);
      StringChangeEx(Texte, '.', ',', True);
      Result := MsgBox(FmtMessage(ExpandConstant('{cm:EspaceInsuffisant}'), [Texte]),
                       mbConfirmation, MB_YESNO) = IDYES;
    end;
    Exit;
  end;

  if CurPageID = wpReady then
  begin
    if not WebView2Present() then
    begin
      if MsgBox(ExpandConstant('{cm:WebView2Manquant}'), mbConfirmation, MB_YESNO) = IDYES then
      begin
        if not InstallerWebView2() then
          MsgBox(ExpandConstant('{cm:WebView2Echec}'), mbInformation, MB_OK);
      end
      else
        MsgBox(ExpandConstant('{cm:WebView2Echec}'), mbInformation, MB_OK);
    end;
  end;
end;

procedure CurStepChanged(CurStep: TSetupStep);
var
  Cible: String;
begin
  if CurStep <> ssPostInstall then
    Exit;

  Cible := Trim(PageModeles.Values[0]);
  if Cible = '' then
    Cible := DossierModelesDefaut();
  ForceDirectories(Cible);
  ForceDirectories(DossierDonnees());

  { Deux traces du même choix, lues dans cet ordre par l'application :
    celle de l'espace utilisateur fait foi, celle du dossier de programme sert
    de secours si les données utilisateur sont effacées. }
  SaveStringToFile(FichierChoixModeles(), Cible + #13#10, False);
  SaveStringToFile(ExpandConstant('{app}\emplacement-modeles.txt'), Cible + #13#10, False);
end;

{ --------------------------------------------------------------------------
  Désinstallation : deux questions distinctes, aucune suppression silencieuse
  -------------------------------------------------------------------------- }

{ Efface les données personnelles sans toucher aux modèles quand ceux-ci sont
  rangés à l'intérieur, ce qui est le cas de l'emplacement par défaut. Sans
  cette précaution, répondre « garder les modèles » puis « supprimer les
  données » les effacerait quand même. }
procedure SupprimerDonnees(PreserverModeles: Boolean);
var
  Base: String;
begin
  Base := DossierDonnees();
  if not PreserverModeles then
  begin
    DelTree(Base, True, True, True);
    Exit;
  end;

  DeleteFile(Base + '\config.json');
  DeleteFile(Base + '\jeton_hf.txt');
  DeleteFile(Base + '\dossier-modeles.txt');
  DeleteFile(Base + '\vocabulaire.txt');
  DeleteFile(Base + '\corrections.txt');
  DelTree(Base + '\logs', True, True, True);
  { Ne part que si les modèles n'y sont plus, donc jamais dans ce cas de figure. }
  RemoveDir(Base);
end;

procedure CurUninstallStepChanged(CurUninstallStep: TUninstallStep);
var
  DossierModeles: String;
  Occupe: Int64;
  ModelesGardes: Boolean;
  ModelesDansLesDonnees: Boolean;
begin
  if CurUninstallStep <> usPostUninstall then
    Exit;
  { Une désinstallation silencieuse ne pose aucune question et ne détruit rien
    d'autre que le programme : c'est le comportement le moins surprenant. }
  if UninstallSilent then
    Exit;

  DossierModeles := DossierModelesEffectif();
  ModelesDansLesDonnees := Pos(Lowercase(DossierDonnees()), Lowercase(DossierModeles)) = 1;
  ModelesGardes := True;

  Occupe := TailleDossier(DossierModeles);
  if Occupe > 0 then
  begin
    { Le crochet ne doit jamais ouvrir la ligne : Inno Setup y verrait un début de section, même dans [Code]. }
    if MsgBox(FmtMessage(ExpandConstant('{cm:DesinstallerModeles}'), [
                TailleLisible(Occupe), DossierModeles]),
              mbConfirmation, MB_YESNO or MB_DEFBUTTON2) = IDYES then
    begin
      DelTree(DossierModeles, True, True, True);
      ModelesGardes := False;
    end;
  end
  else
    ModelesGardes := False;

  if DirExists(DossierDonnees()) then
  begin
    if MsgBox(FmtMessage(ExpandConstant('{cm:DesinstallerDonnees}'), [DossierDonnees()]),
              mbConfirmation, MB_YESNO or MB_DEFBUTTON2) = IDYES then
      SupprimerDonnees(ModelesGardes and ModelesDansLesDonnees);
  end;
end;
