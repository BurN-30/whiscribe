# Journal des versions

Les versions publiées sont disponibles dans l'onglet
[Releases](../../releases). Chaque entrée de ce fichier sert de notes de
version : la chaîne de publication en extrait la section correspondant au tag.

---

## 2.1.0

Import et export des données personnelles par fichier. Un glossaire
professionnel se construit sur des mois et n'a pas sa place dans un dépôt en
ligne : un seul fichier zip suffit désormais à le sauvegarder ou à le porter
sur un autre poste.

**Nouveau panneau « Mes données », dans les réglages**

- **Exporter mes données** écrit une archive `whiscribe-donnees-AAAA-MM-JJ.zip`
  à l'emplacement choisi : glossaire, corrections, réglages, et un manifeste
  qui note la version de l'application, la date et la liste des fichiers.
- Le **jeton Hugging Face n'est jamais exporté**, c'est un secret personnel.
  Les modèles et les journaux non plus. L'interface le dit à l'écran.
- **Importer des données** relit une archive de ce type. L'archive est
  validée avant tout : zip réellement lisible, manifeste présent et cohérent,
  aucun fichier inattendu, aucun chemin qui sortirait de l'archive, tailles
  bornées.
- Un **aperçu** s'affiche avant la moindre écriture : nombre de termes et de
  règles apportés face à ceux déjà en place, réglages qui changeraient avec
  leur valeur avant et après. Il faut confirmer pour que quoi que ce soit soit
  remplacé.
- **Sauvegarde automatique avant tout import**, dans
  `whiscribe-donnees-avant-import-AAAA-MM-JJ-HHMMSS.zip`, posée dans le
  dossier de vos données, dont l'emplacement est affiché. Si cette sauvegarde
  échoue, l'import est annulé plutôt que risqué. Elle se réimporte comme
  n'importe quel export pour revenir en arrière.
- Le **dossier de sortie et le dossier des modèles ne sont repris que s'ils
  existent** sur le poste d'arrivée. Sinon les valeurs locales sont conservées
  et l'aperçu le signale.
- L'interface se recharge seule après un import : ni redémarrage ni
  manipulation.
- Les refus sont expliqués en français, du fichier corrompu à l'archive qui
  n'est pas un export WhiScribe, et toutes les opérations sont journalisées.

---

## 2.0.0

Première version installable. Jusqu'ici, faire tourner l'outil demandait
d'installer Python et de lancer un script. Ce n'est plus le cas : un programme
d'installation unique se télécharge depuis les Releases, se double-clique, et
l'application fonctionne sur un poste où rien n'a été préparé.

**Programme d'installation**

- Fichier unique `WhiScribe-Setup-2.0.0.exe`, assistant en français.
- Installation par utilisateur, **sans droits administrateur**, dans
  `%LOCALAPPDATA%\Programs\WhiScribe`. Le dossier reste modifiable.
- Page dédiée au choix de l'emplacement des modèles de transcription : ils
  pèsent de 1,6 à 3,1 Go et peuvent partir sur un autre disque. Ce choix reste
  modifiable ensuite dans les réglages de l'application.
- Raccourci dans le menu Démarrer, icône sur le Bureau en option.
- Le composant Microsoft WebView2, nécessaire à l'affichage, est détecté et
  téléchargé depuis le site de Microsoft s'il manque.
- Réinstaller par-dessus met à jour sans rien perdre : réglages, glossaire,
  corrections et modèles sont conservés.
- La désinstallation pose deux questions distinctes, avec la taille réellement
  occupée, avant de toucher aux modèles et aux données personnelles. Répondre
  non aux deux ne retire que le programme.

**Application**

- L'application s'appelle désormais **WhiScribe**.
- La version installée écrit ses réglages, ses journaux et ses modèles dans
  `%LOCALAPPDATA%\WhiScribe`, plus dans son dossier d'installation. Lancée
  depuis les sources, elle continue de tout ranger à côté du script.
- Nouveau panneau « Modèles » dans les réglages : emplacement, place occupée,
  espace libre, modèles déjà téléchargés, et changement de dossier.
- Le téléchargement du premier modèle est annoncé avant d'être lancé, avec sa
  taille et son emplacement. Un poste sans connexion reçoit une explication au
  lieu d'une erreur technique, et un disque trop plein est signalé avant de
  commencer.
- Dans la version installée, la séparation des locuteurs indique clairement
  qu'elle n'est pas incluse, et pourquoi, au lieu d'échouer. Elle reste
  disponible dans la version source.
- Démarrage nettement plus rapide : la passerelle vers l'interface n'expose plus
  l'objet fenêtre, dont l'inspection coûtait une vingtaine de secondes au
  lancement.
- Nouveau mode `--verifier` : contrôle les composants, FFmpeg et l'écriture des
  dossiers de travail, puis sort avec un code de retour. La chaîne de
  publication le lance sur l'exécutable construit avant de fabriquer le
  programme d'installation.

**Limites assumées**

- Les modèles de transcription ne sont pas embarqués : ils se téléchargent au
  premier usage, une seule fois. Ensuite l'application n'a plus besoin d'Internet.
- La séparation des locuteurs reste hors du programme d'installation, parce
  qu'elle repose sur PyTorch, environ 2,5 Go.
- Windows 64 bits uniquement.

---

## 1.0.0

Version initiale, installation depuis les sources par `installer.bat`.

- Transcription entièrement locale par faster-whisper (CTranslate2), sans compte
  ni clé d'API, presets « Qualité maximale » et « Rapide ».
- Séparation des locuteurs optionnelle par pyannote.audio.
- Glossaire et règles de correction, sorties `.txt`, `.srt` et `.vtt`.
- Détection du matériel, estimations de durée, garde-fous mémoire.
- Diagnostic en français et journaux horodatés.
