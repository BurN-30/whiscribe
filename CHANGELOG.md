# Journal des versions

Les versions publiées sont disponibles dans l'onglet
[Releases](../../releases). Chaque entrée de ce fichier sert de notes de
version : la chaîne de publication en extrait la section correspondant au tag.

---

## 2.2.0

*Publiée le 18 août 2026.*

Relire une transcription dans l'application, repérer ce que le modèle a mal
entendu, corriger une fois pour toutes, et préparer un compte rendu. Et, tout
autour, ce qui fait gagner du temps sans rien demander : un dossier surveillé,
une reprise après coupure, une interface qui existe enfin en anglais.

**Vue de lecture**

- Une transcription s'ouvre désormais **dans l'application** : depuis l'onglet
  « Transcriptions », depuis les sorties d'un fichier qui vient de se terminer,
  ou par le bouton de relecture de la ligne. Paragraphes lisibles, locuteurs
  affichés quand ils ont été séparés, thème clair ou sombre respecté.
- Les sous-titres `.srt` et `.vtt` gardent leur aperçu brut : personne ne lit
  un fichier de sous-titres en paragraphes.

**Confiance mot à mot**

- Le moteur donne déjà la probabilité de chaque mot. Elle est maintenant
  conservée et **seuls les mots incertains sont surlignés**, en ambre discret :
  sous 0,50 la marque est légère, sous 0,30 elle est plus nette. Le reste du
  texte n'est pas décoré. Les seuils sont calés sur la distribution réelle des
  probabilités, médiane autour de 0,90 et premier décile autour de 0,48.
- **N'importe quel mot** affiche sa confiance au survol, par une infobulle
  native, posée à la volée pour ne pas alourdir un texte de plusieurs milliers
  de mots.
- Une légende sobre rappelle ce que veut dire le surlignage, avec le nombre de
  mots concernés.
- Ces données vivent dans un **fichier compagnon `.json`**, écrit à côté du
  texte, de même nom, format versionné et documenté. Il pèse quelques dizaines
  de kilooctets par heure d'audio.
- **Il est facultatif** : une transcription produite avant cette version, ou
  avec l'option coupée, s'ouvre normalement, sans surlignage, avec une phrase
  qui l'explique.

**Copier pour l'IA**

- Un bouton met dans le presse-papiers un **gabarit d'instructions**, les
  métadonnées de l'enregistrement et le texte complet, prêts à coller dans
  l'assistant de son choix. Aucune marque, aucun envoi, aucun compte.
- Le gabarit est un fichier à vous, `gabarit-ia.txt`, créé au premier usage
  dans le dossier de vos données et modifiable depuis les réglages. Variables
  reconnues : `{texte}`, `{fichier}`, `{date}`, `{duree}`, `{locuteurs}`,
  `{modele}`.
- Le gabarit **voyage avec vos données** : il est joint à l'export du panneau
  « Mes données » quand il existe, repris à l'import, et l'aperçu le signale
  avant toute écriture. Une archive produite par la version 2.1.0 s'importe
  toujours, et laisse en place le gabarit de ce poste.

**Corrections apprises**

- Sélectionner un mot ou une courte expression dans la vue de lecture propose
  de le corriger. L'application demande alors d'**ajouter la règle aux
  corrections**, applique le remplacement au texte affiché et au fichier `.txt`
  enregistré, met le compagnon à jour, et n'écrit jamais deux fois la même
  règle. L'en-tête du fichier, qui décrit la production, n'est pas touché.
- Les règles apprises sont rangées dans une section dédiée de
  `corrections.txt`, où elles restent modifiables à la main.
- Débrayable dans les réglages, active par défaut.

**Sauvegarde progressive et reprise**

- Le texte est écrit **au fil des segments**. Une coupure de courant, une
  fermeture de fenêtre ou un plantage ne fait plus perdre le calcul déjà fait.
- Au lancement suivant, l'application propose de **reprendre** : le fichier
  retourne dans la file, la transcription repart du dernier segment enregistré,
  et le **temps déjà écoulé est conservé** dans le compteur.
- Mesuré avant d'être intégré, dix passes alternées sur le même audio :
  **0,23 % du temps de transcription** avec le modèle le plus rapide, donc le
  cas le plus défavorable, environ 2 ms par segment écrit. Aucune mémoire
  supplémentaire mesurable, et environ 9 Ko de fichiers de reprise par minute
  d'audio, effacés dès qu'une transcription se termine normalement. Les traces
  de plus de trente jours, et celles dont le fichier source a disparu, sont
  purgées au démarrage.
- Débrayable dans les réglages, active par défaut.

**Dossier surveillé**

- Un dossier peut être **désigné pour être surveillé** : les enregistrements
  qui y arrivent rejoignent la file tout seuls. Pensé pour un dictaphone ou un
  enregistreur de réunion qui dépose toujours au même endroit.
- **Coupé par défaut**, et sans aucune dépendance nouvelle : le dossier est
  regardé toutes les dix secondes, uniquement quand l'option est active.
- Un fichier n'est pris que lorsque **sa taille a cessé de bouger** : une copie
  de 300 Mo en cours d'écriture n'est pas transcrite à moitié.
- Les fichiers déjà traités sont **mémorisés sur disque** : rien n'est
  retranscrit au redémarrage. Ce qui était déjà là quand vous désignez le
  dossier est considéré comme connu, et un bouton « Reprendre tout le dossier »
  remet tout en jeu.
- Un dossier supprimé, débranché ou illisible **se signale en défaut sans rien
  casser**, le dit une seule fois, et la surveillance repart d'elle-même.
- Indicateur discret dans l'en-tête quand la surveillance est active.

**Vérification des mises à jour, facultative et coupée par défaut**

- Nouveau panneau « Application ». Tant que l'option est coupée,
  **l'application ne fait aucun appel réseau sortant**, hors le téléchargement
  d'un modèle que vous demandez. C'est écrit tel quel dans le réglage.
- Activée, elle interroge la liste publique des versions du projet au
  lancement, **au plus une fois par 24 heures**, avec un délai d'attente court.
  Un échec, hors ligne ou pare-feu, ne produit **aucun message** : journal
  seulement.
- Une version plus récente affiche un bandeau discret et un bouton qui ouvre la
  page de la version dans le navigateur. Rien ne se télécharge tout seul.
- Comparaison de versions **numérique** : 2.10.0 est bien supérieur à 2.9.0, et
  une préversion précède la version finale du même numéro.
- Le mainteneur peut écrire `[reinstallation-requise]` dans les notes d'une
  version : le bandeau annonce alors la désinstallation préalable, en précisant
  que données et modèles sont conservés. Marqueur documenté dans le README et
  dans le workflow de publication.

**Espace utilisé**

- Nouveau bouton dans le panneau « Modèles » : taille et **chemin réel** des
  modèles, de vos données et du programme, avec un bouton pour ouvrir chaque
  emplacement.
- Mesure en tâche de fond, la fenêtre ne se fige pas sur un dossier de trois
  gigaoctets, et **aucune élévation de droits n'est demandée**.

**Nom des fichiers produits**

- Le nommage devient un **motif configurable**, avec quatre variables :
  `{nom}`, `{date}`, `{heure}`, `{modele}`. Aperçu du résultat sous le champ
  pendant la frappe.
- Le défaut ne change pas : champ vide, on retrouve exactement
  `AAAA-MM-JJ-nom-du-fichier`. Les caractères refusés par Windows sont
  signalés au lieu d'être avalés, et la protection contre l'écrasement reste
  la même.

**Dépôt et raccourcis**

- Déposer un **dossier** sur la fenêtre ajoute ses fichiers audio, premier
  niveau seulement, en disant combien ont été retenus et combien écartés.
- Déposer une **archive d'export WhiScribe** propose l'import, avec l'aperçu
  habituel avant toute écriture.
- `Ctrl` + `O` ouvre le sélecteur de fichiers, `Ctrl` + `Entrée` lance la
  transcription, `Échap` ferme la fenêtre du dessus. Rappelés dans l'aide.

**Progression dans la barre des tâches**

- L'icône de la barre des tâches se remplit pendant le calcul, et passe
  brièvement au rouge sur un échec avant de s'effacer. Aucune notification,
  aucun clignotement, aucune fenêtre qui passe devant. Se coupe dans les
  réglages.

**Indicateur de langue**

- Une ligne sous le sélecteur annonce la qualité à attendre, « excellente »,
  « bonne » ou « variable », d'après les taux d'erreur publiés pour
  `large-v3`. Aucune proposition d'un autre modèle : c'est déjà le meilleur
  multilingue disponible.

**Réglages et outils**

- Nouveau panneau « Relecture » : confiance des mots, corrections apprises,
  sauvegarde progressive, écoute de l'audio pendant la relecture
  (expérimentale, coupée par défaut), et accès au gabarit pour l'IA.
- Quatre harnais reproductibles dans `outils/` : la mesure du coût de la
  sauvegarde progressive, la vérification de bout en bout de la chaîne de
  relecture, celle des fonctions périphériques, qui éprouve la scrutation du
  dossier surveillé sur de vrais fichiers, la comparaison de versions, le motif
  de nommage, la mesure d'espace et l'amorce du glossaire, et celle de l'import
  et de l'export de vos données, qui rejoue un aller-retour complet, gabarit
  compris, et la relecture d'une archive de l'ancien format. Sans réseau ni
  fenêtre, dans un dossier temporaire, sans jamais toucher à vos fichiers.

**Français et anglais**

- L'interface existe désormais **en français et en anglais**, entièrement :
  libellés, aides, encarts, journal utilisateur, modales, messages d'erreur
  traduits, avertissements matériels, phrases de recommandation, presets, états
  de la file, et l'en-tête des fichiers produits.
- Au premier lancement, l'application **suit la langue de Windows** : français
  si Windows est en français, **anglais dans tous les autres cas**, y compris
  quand la locale est illisible. C'est une application publiée pour un public
  mondial, l'anglais est le repli.
- Le choix se change dans les réglages, panneau « Application », ligne
  « Langue de l'interface », et il est **appliqué tout de suite**, sans
  redémarrage : les libellés sont reposés et l'interface redemande à Python ses
  propres textes.
- **Ce réglage est sans effet sur la langue parlée.** Le sélecteur « Langue
  parlée » pilote le moteur de transcription, celui-ci pilote l'affichage : un
  anglophone transcrit du français sans rien changer.
- L'**amorce envoyée au moteur** à partir de votre glossaire suit elle aussi la
  langue parlée, pas celle de l'interface : sa phrase d'introduction est lue par
  le modèle comme un début de texte, une phrase française pousserait le décodeur
  vers le français au milieu d'un enregistrement anglais. Le budget de 224
  jetons est compté sur la forme réellement envoyée.
- **Rien de déjà écrit n'est retraduit.** L'en-tête d'un `.txt` porte la langue
  d'interface du moment de sa production, et la vue de lecture sait relire les
  en-têtes des deux langues. `vocabulaire.txt`, `corrections.txt` et
  `gabarit-ia.txt` sont créés dans la langue du moment, puis n'y touchent plus
  jamais : ces fichiers appartiennent à l'utilisateur. La section des règles
  apprises est reconnue dans les deux langues, pour qu'un `corrections.txt`
  français ne se voie pas ajouter une seconde section en anglais.
- Le **journal de bord technique de `logs/` reste en français** : il s'adresse
  au mainteneur et sert au diagnostic des incidents rapportés au dépôt. Ce que
  l'utilisateur lit dans la barre du bas, lui, suit la langue de l'interface.
- Les nombres, les unités et les dates suivent la langue : virgule décimale et
  « Go » en français, point décimal et « GB » en anglais.
- **Aucune dépendance nouvelle, aucun framework.** Deux catalogues jumelés de
  dictionnaires par langue, `app/langues.py` et `web/langues.js`, une fonction
  `t()` de substitution nommée et un pluriel explicite. Le HTML ne porte plus
  aucun texte : tout passe par des attributs `data-i18n`.
- Le **programme d'installation est bilingue** lui aussi, désinstallation
  comprise. Inno Setup retient la langue de Windows tout seul, l'anglais en
  tête de liste faisant office de repli.
- Cinquième harnais, `outils/verifier_traductions.py` : parité des clés
  français et anglais des deux côtés, existence de toute clé citée par le code,
  absence de français en dur dans `web/app.js` et `web/index.html`, égalité des
  variables de substitution entre les deux langues, et chasse aux tirets
  cadratins. Sort avec le code 0 si tout passe.

**Documentation, en vue du passage en public**

- Le README devient **anglais par défaut**, avec sa version française dans
  `README.fr.md` et un lien de bascule en tête des deux fichiers. Structure
  identique de part et d'autre, resserrée : promesse, installation en trois
  lignes, fonctionnalités, vie privée, limites connues, voie source, le détail
  technique replié dans des sections dépliables.
- Nouveau `CONTRIBUTING.md` : setup de développement, harnais de `outils/` à
  faire tourner, et le français comme langue source des chaînes avec parité
  anglaise vérifiée par `outils/verifier_traductions.py`.
- Gabarits d'issues dans `.github/ISSUE_TEMPLATE/` : rapport de bug qui demande
  la version, le mode d'installation et le **fichier de journal**, jamais
  l'audio, et demande de fonctionnalité. Les issues vides sont désactivées.
- `docs/publication-github.md` : check-list de mise en public, description et
  topics du dépôt, aperçu social, réglages recommandés, et une évaluation
  argumentée de la publication sur winget, sans manifeste à ce stade.

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
