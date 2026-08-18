[English](README.md) · **Français**

# WhiScribe

Transformez vos enregistrements en texte sur votre propre machine. Pas de compte, pas de cloud, aucun envoi.

[![Version](https://img.shields.io/github/v/release/BurN-30/whiscribe?label=release)](https://github.com/BurN-30/whiscribe/releases)
[![Licence : MIT](https://img.shields.io/badge/license-MIT-blue.svg)](LICENSE)
![Plateforme : Windows](https://img.shields.io/badge/platform-Windows%2064--bit-lightgrey)

WhiScribe est une application de bureau Windows bâtie sur [faster-whisper](https://github.com/SYSTRAN/faster-whisper). Vous glissez des fichiers audio sur la fenêtre, vous récupérez des fichiers texte à côté. Elle a été écrite pour les réunions : audio de salle, plusieurs voix, noms propres et jargon maison. L'interface existe en français et en anglais.

<!-- capture 1 : fenêtre principale, thème sombre, zone de dépôt vide, carte matériel visible -->

---

## Installation

1. Téléchargez **`WhiScribe-Setup-X.Y.Z.exe`** depuis la page [Releases](https://github.com/BurN-30/whiscribe/releases).
2. Lancez-le.
3. Ouvrez **WhiScribe** depuis le menu Démarrer.

Rien d'autre à installer. L'installation se fait par utilisateur, **sans droits administrateur**, dans `%LOCALAPPDATA%\Programs\WhiScribe`. Vos réglages, votre glossaire et vos journaux vivent dans `%LOCALAPPDATA%\WhiScribe`, jamais dans le dossier du programme : réinstaller une version plus récente par-dessus l'ancienne ne fait donc rien perdre.

L'assistant demande **où ranger les modèles de transcription**, de 1,6 à 3,1 Go selon le preset. Les modèles ne sont pas embarqués : ils se téléchargent une seule fois, au premier usage, et l'application annonce la taille avant de commencer. Ensuite elle fonctionne hors connexion.

Le programme d'installation n'est pas signé, SmartScreen peut donc avertir au premier lancement : « Informations complémentaires », puis « Exécuter quand même ». Voir les [limites connues](#limites-connues).

> Une fonction n'est pas dans le programme d'installation, volontairement : la **séparation des locuteurs** repose sur PyTorch, environ 2,5 Go, et vit dans l'[installation depuis les sources](#installation-depuis-les-sources). Tout le reste est là.

---

## Ce qu'elle fait

- **Glisser, lancer.** Déposez des fichiers ou un dossier sur la fenêtre, choisissez un preset, lancez. Les fichiers sont traités l'un après l'autre, et un échec n'interrompt pas la file.
- **Formats acceptés :** `m4a` (dont les enregistrements de smartphone), `mp3`, `wav`, `ogg`, `flac`, `opus`, `webm`, `wma`, `aac`, `amr`, et les vidéos courantes (`mp4`, `mkv`, `mov`), dont la piste audio est extraite.
- **Formats produits :** `.txt` avec un en-tête (source, durée, modèle, date, temps de calcul réel), plus `.srt` et `.vtt` en option. Le nom des fichiers suit un motif configurable avec `{nom}`, `{date}`, `{heure}` et `{modele}`.
- **Deux presets.** *Qualité maximale* (`large-v3`) pour tout ce qui sera relu, *Rapide* (`large-v3-turbo`) pour dégrossir. Les autres modèles Whisper restent accessibles en mode avancé.
- **Glossaire et corrections.** Une liste de noms propres oriente le modèle avant qu'il transcrive, une liste de règles nettoie les massacres récurrents après. Voir [Vocabulaire](#vocabulaire-et-corrections).
- **Relecture dans l'application.** Les mots incertains sont surlignés, n'importe quel mot affiche sa confiance au survol, et corriger une fois peut valoir pour toujours. Voir [Relire une transcription](#relire-une-transcription).
- **Copier pour l'IA.** Un bouton met votre propre gabarit d'instructions, les métadonnées et le texte complet dans le presse-papiers, prêts à coller dans l'assistant de votre choix. L'application n'envoie rien.
- **Sauvegarde progressive.** Le texte est écrit au fil des segments. Un plantage ou une coupure de courant ne fait plus perdre le travail : l'application propose de reprendre au lancement suivant.
- **Dossier surveillé**, coupé par défaut. Un dossier peut être surveillé pour que les nouveaux enregistrements rejoignent la file tout seuls, ce qui va bien à un dictaphone ou à un enregistreur de réunion qui dépose toujours au même endroit.
- **Séparation des locuteurs**, facultative, version source uniquement. Elle produit un texte étiqueté, `Locuteur 1`, `Locuteur 2`, ce qui vaut cher pour un compte rendu.
- **Progression dans la barre des tâches**, état de l'espace occupé, export et import de vos données en un seul fichier zip, thème clair ou sombre, trois raccourcis clavier et pas un de plus : `Ctrl` + `O`, `Ctrl` + `Entrée`, `Échap`.

<!-- gif : dépôt de deux fichiers, choix du preset Rapide, lancement, barre de progression qui se remplit, une ligne terminée avec son bouton de relecture (environ 15 s, sans son) -->

---

## Vie privée

**Rien de ce que vous transcrivez ne quitte votre ordinateur.** Pas de compte, pas de clé d'API, pas d'envoi vers un service en ligne, pas de télémétrie. L'audio est lu depuis votre disque, calculé par votre processeur, et le texte est écrit à côté.

Deux choses peuvent passer par le réseau, toutes deux explicites :

- **Le téléchargement d'un modèle**, une fois, au premier usage d'un preset. L'application annonce la taille avant de commencer.
- **La vérification des mises à jour**, qui est **coupée par défaut**. Tant qu'elle est coupée, l'application ne fait aucun appel réseau sortant, hors le téléchargement d'un modèle que vous demandez.

Activée, elle interroge au lancement la liste publique des versions du projet, **au plus une fois par 24 heures**. Rien n'est transmis sur vous ni sur vos fichiers, l'appel a un délai d'attente court, et un échec, qu'il vienne d'un poste hors ligne ou d'un pare-feu, ne produit aucun message : il part dans le journal et c'est tout. Si une version plus récente existe, un bandeau discret le dit, avec un bouton qui ouvre la page de la version dans votre navigateur. Rien ne se télécharge ni ne s'installe tout seul.

Le jeton Hugging Face utilisé par la séparation des locuteurs n'est jamais inclus dans un export, et jamais versionné.

---

## Vocabulaire et corrections

C'est le point faible de toute transcription automatique : les noms propres, les noms de sociétés et les termes techniques sortent massacrés. Deux leviers y répondent, complémentaires.

**Le glossaire, `vocabulaire.txt`.** Un terme par ligne. La liste est envoyée au modèle **avant** qu'il ne transcrive, comme début de contexte, ce qui l'oriente vers ces orthographes.

```
Jean Dupont
MonEntreprise
GitLab
Kubernetes
RGPD
```

L'amorce d'un modèle Whisper ne peut pas dépasser **224 jetons**, soit une petite centaine de termes courts. Au-delà, faster-whisper tronque tout seul, et silencieusement. WhiScribe tronque proprement à la place, en gardant les termes **du haut de la liste**, et vous prévient dans l'interface. Mettez donc les plus importants en premier. Le décompte est exact : il utilise le tokeniseur du modèle réellement chargé. La phrase d'introduction de l'amorce suit la **langue parlée** de l'enregistrement, jamais celle de l'interface : le modèle la lit comme un début de texte, une phrase française n'a rien à faire en tête d'un enregistrement anglais.

**Les corrections, `corrections.txt`.** Pour les massacres récurrents que l'amorce ne suffit pas à éviter. Une règle par ligne, appliquée au texte final, insensible à la casse, mot entier uniquement : la règle `git` ne touchera pas `digital`.

```
guitte lab => GitLab
cubernetes => Kubernetes
```

Les deux fichiers sont du texte brut. Ils s'éditent à la main ou depuis les panneaux de l'application. Le panneau **« Mes données »** les exporte, avec vos réglages et votre gabarit pour l'IA s'il existe, dans une archive `whiscribe-donnees-AAAA-MM-JJ.zip` que vous rangez où vous voulez, clé USB ou sauvegarde d'entreprise. Un import affiche un aperçu de ce qui va changer et n'écrit rien avant votre confirmation, l'état précédent étant sauvegardé à côté au préalable.

---

## Relire une transcription

Une transcription s'ouvre **dans l'application**, sans passer par un éditeur : cliquez sur une ligne de l'onglet « Transcriptions », ou sur le bouton de relecture d'un fichier qui vient de se terminer.

<!-- capture 2 : vue de lecture, un paragraphe avec deux ou trois mots surlignés en ambre, l'infobulle de confiance visible sur l'un d'eux -->

Whisper donne la probabilité de chaque mot qu'il écrit. La vue de lecture **surligne uniquement les mots incertains**, en ambre discret : sous 0,50 la marque est légère, sous 0,30 elle est plus nette. Survoler n'importe quel mot affiche sa confiance, surligné ou non. En pratique cela signale environ un mot sur dix dans le pire des cas, et un sur trente-cinq avec un modèle correct : une poignée d'endroits à réécouter, pas un document bariolé.

Ces valeurs vivent dans un **fichier compagnon `.json`** écrit à côté du texte, quelques dizaines de kilooctets par heure d'audio. Il est facultatif : une transcription plus ancienne, ou produite avec l'option coupée, s'ouvre normalement, simplement sans surlignage.

Sélectionner un mot ou une courte expression propose de le **corriger**. L'application applique le remplacement au texte affiché et au fichier enregistré, met le compagnon à jour, et range la règle dans une section dédiée de `corrections.txt` pour que la même erreur soit corrigée automatiquement ensuite.

**Copier pour l'IA** met dans le presse-papiers un texte d'instructions, les métadonnées de l'enregistrement et la transcription complète. Le gabarit est un fichier à vous, `gabarit-ia.txt`, créé au premier usage et modifiable depuis les réglages, où `{texte}`, `{fichier}`, `{date}`, `{duree}`, `{locuteurs}` et `{modele}` sont remplacés au moment de la copie.

---

## Vitesse

Le facteur ci-dessous est le rapport durée de calcul sur durée de l'audio. En dessous de 1, c'est plus rapide que l'écoute.

| Matériel | Qualité maximale | Rapide | Une heure d'audio, en qualité |
|---|---|---|---|
| Ultraportable, 12 à 14 fils, sans carte dédiée | environ 1,2 x | environ 0,3 x | environ 1 h 15 |
| Processeur de bureau, 16 fils et plus | environ 0,7 x | environ 0,2 x | environ 40 min |
| Portable modeste, 4 à 8 fils | environ 2 x | environ 0,5 x | environ 2 h |
| Carte NVIDIA (CUDA, float16) | environ 0,1 x | environ 0,05 x | environ 6 min |

**Ce sont des estimations, pas des garanties.** Elles sont calées sur des mesures publiques et ajustées au nombre de cœurs de votre machine. L'application affiche le **temps réellement mesuré** après chaque transcription, et l'écrit dans l'en-tête du fichier produit. La séparation des locuteurs ajoute à peu près 0,2 x sur processeur.

Ce qui est accéléré dans cette version : le **processeur, partout**, en quantification `int8`, qui est le mode par défaut et reste parfaitement utilisable, et les **cartes NVIDIA** en CUDA `float16`, automatiquement, si le pilote et les bibliothèques répondent. Les cartes AMD Radeon, les circuits graphiques intégrés Intel et les NPU sont détectés et affichés mais **pas exploités**, parce que faster-whisper repose sur [CTranslate2](https://opennmt.net/CTranslate2/hardware_support.html), qui ne supporte que le CPU x86-64 ou ARM64 et les GPU NVIDIA. L'application le dit noir sur blanc plutôt que de laisser croire à une accélération qui n'existe pas.

<details>
<summary>Ce qui pourrait changer cela, plus tard</summary>

**whisper.cpp avec le backend Vulkan** est la piste solide, et la seule réaliste pour accélérer un Radeon sous Windows : un portage C/C++ indépendant de PyTorch et de CUDA, qui fait de l'inférence GPU multi-vendeur sans code spécifique au constructeur. Les mesures publiques donnent environ 8 x le temps réel sur une RX 9070 XT, et un facteur 3 à 4 fois meilleur que le CPU seul sur un iGPU Radeon 680M. La livraison envisagée est un binaire Windows Vulkan pré-compilé, piloté en sous-processus, pour ne demander à personne d'installer une chaîne de compilation C++. Le coût est un deuxième format de modèles, GGUF au lieu de CTranslate2, et une couche d'abstraction de moteur : c'est pour cela que ce n'est pas encore là.

**OpenVINO pour l'iGPU et le NPU Intel** est intéressant mais pas mûr pour un outil clé en main : le backend réclame une version précise d'OpenVINO, et la conversion des modèles Whisper casse avec certaines versions de `transformers`. Quant au NPU lui-même, son intérêt est l'autonomie, quelques watts contre 15 à 25 pour l'iGPU, pas la vitesse brute. Si l'accélération Intel devient un objectif, passer par Vulkan est plus simple et plus robuste.

</details>

---

## Limites connues

- **Windows 64 bits uniquement.** Le code est portable, mais la détection matérielle et les scripts de lancement visent Windows. L'affichage s'appuie sur Microsoft Edge WebView2 Runtime, présent d'origine sur Windows 11 et sur les Windows 10 à jour ; l'assistant l'installe s'il manque.
- **Une seule langue parlée par enregistrement.** Le mélange de plusieurs langues dans la même conversation est mal géré : Whisper se fixe sur une langue et transcrit le reste au travers. Les termes anglais parsemés dans une discussion française sont un autre sujet, et c'est justement le rôle du glossaire.
- **Conçue d'abord pour le français**, c'est là qu'elle a été le plus éprouvée. La qualité est égale ou meilleure en anglais et dans les langues bien couvertes par Whisper, et l'application annonce sous le sélecteur de langue ce qu'il faut attendre : excellente, bonne ou variable.
- **Le premier lancement a besoin d'Internet** pour télécharger le modèle, de 1,6 à 3,1 Go selon le preset. Ensuite, plus jamais.
- **Aucune accélération AMD ou Intel.** Ces machines transcrivent sur processeur.
- **La séparation des locuteurs n'est pas dans le programme d'installation.** Elle demande la version source, environ 2,5 Go de dépendances et un jeton Hugging Face. Sans elle, tout le reste fonctionne.
- **Le programme d'installation n'est pas signé.** SmartScreen peut avertir au premier lancement. Une signature de code coûte plusieurs centaines d'euros par an, ce qui n'a pas de sens pour un outil personnel et gratuit.
- **L'audio est décodé entièrement en mémoire**, environ 230 Mo par heure d'enregistrement. Confortable jusqu'à plusieurs heures, mais ce n'est pas du traitement en flux.
- **Les étiquettes de locuteurs sont utiles, elles ne sont pas une vérité.** Les chevauchements et les voix lointaines sont les cas durs. Préciser le nombre de participants améliore nettement le découpage.

---

## Installation depuis les sources

Deux raisons seulement d'emprunter cette voie : **modifier le code**, ou obtenir la **séparation des locuteurs**. Pour un usage normal, l'installation ci-dessus suffit.

1. Installez [Python 3.9 ou plus récent](https://www.python.org/downloads/) en cochant **« Add python.exe to PATH »**.
2. Double-cliquez sur **`installer.bat`**.
3. Répondez à la question sur la séparation des locuteurs, puis laissez faire.
4. Double-cliquez sur **`lancer.bat`**.

L'installateur est relançable, ne réinstalle que ce qui manque, et crée un environnement isolé dans `.venv` sans toucher au Python du système. Il n'a besoin ni de droits administrateur, ni de winget, ni de Chocolatey : FFmpeg est posé par un paquet Python qui embarque le binaire.

| Option | Effet |
|---|---|
| `installer.bat` | Installation standard, pose la question sur les locuteurs |
| `installer.bat --locuteurs` | Ajoute la séparation des locuteurs (PyTorch et pyannote) |
| `installer.bat --sans-locuteurs` | Installation légère, sans question |
| `installer.bat --verifier` | N'affiche que le bilan de l'état du poste |

Lancée depuis les sources, l'application range tout à côté du script : `config.json`, `logs/`, `modeles/`, glossaire et corrections. C'est la seule différence de comportement avec la version installée.

<details>
<summary>Installation manuelle, pour qui préfère garder la main</summary>

```bat
python -m venv .venv
.venv\Scripts\activate

pip install -r requirements.txt

REM Seulement si une carte NVIDIA est présente : évite l'erreur
REM « cublas64_12.dll introuvable » sans toucher au PATH système.
pip install nvidia-cublas-cu12 nvidia-cudnn-cu12==9.*

REM Seulement pour la séparation des locuteurs. Sans carte NVIDIA :
pip install torch==2.8.0 torchaudio==2.8.0 --index-url https://download.pytorch.org/whl/cpu
REM Avec carte NVIDIA :
pip install torch==2.8.0 torchaudio==2.8.0 --index-url https://download.pytorch.org/whl/cu124
pip install -r requirements-locuteurs.txt

.venv\Scripts\pythonw transcriber.pyw
```

Le socle fait environ 250 Mo. La séparation des locuteurs ajoute à peu près 2,5 Go parce qu'elle tire PyTorch : c'est précisément pourquoi elle est optionnelle, et pourquoi elle reste hors du programme d'installation.

Contrôler l'état du poste, le décodeur FFmpeg, les dossiers de travail et la détection matérielle :

```bat
.venv\Scripts\python transcriber.pyw --verifier
```

</details>

<details>
<summary>Mettre en place la séparation des locuteurs</summary>

Le modèle qui reconnaît les voix, pyannote, est gratuit mais sous conditions : son auteur demande de les accepter et de s'identifier.

1. Créez un compte sur [huggingface.co](https://huggingface.co).
2. Ouvrez [pyannote/speaker-diarization-3.1](https://huggingface.co/pyannote/speaker-diarization-3.1) et acceptez les conditions.
3. Créez un jeton d'accès **Read** dans les réglages du compte.
4. Collez-le dans le panneau « Locuteurs » de l'application.

Le jeton est enregistré dans `jeton_hf.txt`, avec vos données, et n'est jamais versionné. La variable d'environnement `HF_TOKEN` est également reconnue, et prioritaire. Sans jeton, tout fonctionne quand même, simplement sans étiquettes et avec un message clair au lieu d'une erreur.

Whisper et pyannote sont **séquencés**, jamais chargés en même temps : l'application transcrit, libère explicitement le modèle Whisper, force un passage du ramasse-miettes, puis charge la diarisation. Les pics se suivent au lieu de s'additionner, et `large-v3` plus pyannote tiennent dans 16 Go.

</details>

<details>
<summary>Comment le projet est organisé</summary>

Un seul moteur, faster-whisper sur CTranslate2. whisperX a été retiré : il impose PyTorch, son alignement mot à mot ne sert pas ici, sa VAD est désormais intégrée à faster-whisper, et piloter une bibliothèque plutôt qu'un sous-processus donne la progression segment par segment, le contrôle exact de la libération mémoire entre les étapes, les erreurs typées, et l'accès au tokeniseur du modèle pour mesurer le budget de l'amorce.

```
transcriber.pyw       fenêtre, passerelle vers l'interface, mode --verifier
installer.py          installateur relançable, version source
app/
  chemins.py          emplacements, selon source ou version installée
  materiel.py         détection processeur, mémoire, GPU, NPU
  presets.py          presets, estimations, garde-fous mémoire
  audio.py            FFmpeg, durée, décodage 16 kHz mono
  moteur.py           faster-whisper, chargement et libération
  diarisation.py      pyannote, jeton, attribution des locuteurs
  vocabulaire.py      glossaire, amorce, corrections
  sorties.py          txt, srt, vtt, en-têtes
  nommage.py          motif de nom des fichiers produits
  surveillance.py     dossier surveillé, scrutation et mémoire
  stockage.py         espace occupé par les modèles, les données, le programme
  maj.py              vérification facultative des versions publiées
  barre_taches.py     progression dans la barre des tâches Windows
  compagnon.py        fichier .json de confiance mot à mot
  lecture.py          vue de lecture, corrections relues, copie pour l'IA
  gabarit.py          gabarit d'instructions pour un assistant IA
  reprise.py          sauvegarde progressive et reprise après interruption
  traitement.py       file séquentielle
  config.py           configuration
  journal.py          journalisation et traduction des incidents
  langues.py          catalogues français et anglais, côté Python
web/                  interface (HTML, CSS, JavaScript), langues.js
outils/               harnais de mesure et de vérification, hors application
packaging/            recette PyInstaller, script Inno Setup, icône
.github/workflows/    chaîne de publication
```

Où vivent les fichiers, selon la manière dont l'application est lancée :

| | Version installée | Version source |
|---|---|---|
| Programme | `%LOCALAPPDATA%\Programs\WhiScribe` | le dépôt cloné |
| Réglages, journaux, glossaire | `%LOCALAPPDATA%\WhiScribe` | à côté du script |
| Modèles | choisi à l'installation, modifiable dans les réglages | `modeles/`, modifiable dans les réglages |

</details>

<details>
<summary>Fabriquer le programme d'installation</summary>

La publication est automatisée : poser un tag `vX.Y.Z` déclenche `.github/workflows/release.yml`, qui construit, vérifie, fabrique le programme d'installation et crée la Release avec le fichier en pièce jointe. Les notes de version sont la section correspondante de [CHANGELOG.md](CHANGELOG.md). Le même workflow se lance à la main depuis l'onglet Actions, sans tag : il construit et vérifie tout, mais ne publie rien.

```bat
pip install -r requirements.txt -r requirements-build.txt
pyinstaller --noconfirm --clean --distpath dist --workpath build packaging\whiscribe.spec
dist\WhiScribe\whiscribe-verifier.exe
iscc /DVersionApp=2.2.0 packaging\setup.iss
```

Le numéro de version a une seule source, `VERSION` dans `app/__init__.py`, et le workflow refuse de publier si le tag ne lui correspond pas. PyInstaller 6.22 est le minimum : les versions antérieures ne savent pas geler numpy 2.5.

Une version qui ne peut pas se mettre à jour en place s'annonce en écrivant `[reinstallation-requise]` n'importe où dans sa section du CHANGELOG. Le bandeau de mise à jour dit alors qu'il faut désinstaller d'abord, et que les données et les modèles sont conservés, ce qui est vrai puisqu'ils vivent hors du dossier du programme.

</details>

---

## Diagnostic

Chaque échec est expliqué dans l'interface, en clair : fichier illisible, modèle à télécharger, mémoire insuffisante, jeton absent ou invalide, disque plein, bibliothèques CUDA manquantes. Aucun traceback n'apparaît à l'écran.

Le détail technique part dans un fichier horodaté du dossier `logs/`, dont le nom est cité dans le message d'erreur. Le bouton **« Ouvrir le fichier détaillé »**, dans la barre du bas, l'ouvre directement. Les 30 derniers journaux sont conservés. C'est ce fichier qu'il faut joindre à un rapport de bug, et il est écrit en français : il s'adresse au mainteneur, pas à l'utilisateur.

---

## Contribuer

Les issues et les petites pull requests sont les bienvenues. Voir [CONTRIBUTING.md](CONTRIBUTING.md), rédigé en anglais.

## Licence

MIT, voir [LICENSE](LICENSE). Historique des versions dans [CHANGELOG.md](CHANGELOG.md).

Cet outil s'appuie sur des projets libres : [faster-whisper](https://github.com/SYSTRAN/faster-whisper) et [CTranslate2](https://github.com/OpenNMT/CTranslate2), les modèles [Whisper](https://github.com/openai/whisper) d'OpenAI, [pyannote.audio](https://github.com/pyannote/pyannote-audio), [pywebview](https://pywebview.flowrl.com/) et [FFmpeg](https://ffmpeg.org/).
