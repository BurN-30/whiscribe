# WhisperScribe

Application de bureau pour transcrire des enregistrements audio en texte, **entièrement sur votre machine**. Pensée pour les réunions : audio de salle, plusieurs voix, noms propres et jargon maison.

Windows, interface en français, installation automatisée.

---

## Vie privée : c'est tout l'intérêt

**Rien de ce que vous transcrivez ne quitte votre ordinateur.** Pas de compte, pas de clé d'API, pas d'envoi vers un service en ligne, pas de télémétrie. L'audio est lu depuis votre disque, calculé par votre processeur, et le texte est écrit à côté.

La seule chose qui transite par Internet est le **téléchargement initial du modèle** (1,6 ou 3,1 Go selon le preset), une fois pour toutes. Ensuite l'application fonctionne hors connexion, y compris sur un poste isolé.

C'est la différence de fond avec les services de transcription en ligne : un compte rendu de réunion, un entretien, une conversation client ne sont pas des données que l'on téléverse sans y penser.

---

## Installation

### Automatique, recommandée

1. Installez [Python 3.9 ou plus récent](https://www.python.org/downloads/) en cochant **« Add python.exe to PATH »**.
2. Double-cliquez sur **`installer.bat`**.
3. Répondez à la question sur la séparation des locuteurs (voir plus bas), puis laissez faire.
4. Double-cliquez sur **`lancer.bat`**.

L'installateur est **relançable** : il ne réinstalle que ce qui manque. Il crée un environnement Python isolé dans `.venv`, sans toucher au Python du système.

Il n'a besoin **ni de droits administrateur, ni de winget, ni de Chocolatey**. FFmpeg est posé par un paquet Python qui embarque le binaire, donc rien à ajouter au `PATH`.

| Option | Effet |
|---|---|
| `installer.bat` | Installation standard, pose la question sur les locuteurs |
| `installer.bat --locuteurs` | Ajoute la séparation des locuteurs (PyTorch + pyannote) |
| `installer.bat --sans-locuteurs` | Installation légère, sans question |
| `installer.bat --verifier` | N'affiche que le bilan de l'état du poste |

### Manuelle

Pour qui préfère garder la main.

```bat
python -m venv .venv
.venv\Scripts\activate

pip install -r requirements.txt

REM Seulement si une carte NVIDIA est présente : évite l'erreur
REM « cublas64_12.dll introuvable » sans toucher au PATH système.
pip install nvidia-cublas-cu12 nvidia-cudnn-cu12==9.*

REM Seulement si vous voulez la séparation des locuteurs.
REM Sans carte NVIDIA :
pip install torch==2.8.0 torchaudio==2.8.0 --index-url https://download.pytorch.org/whl/cpu
REM Avec carte NVIDIA :
pip install torch==2.8.0 torchaudio==2.8.0 --index-url https://download.pytorch.org/whl/cu124
pip install -r requirements-locuteurs.txt

.venv\Scripts\pythonw transcriber.pyw
```

Le socle fait environ 250 Mo. La séparation des locuteurs ajoute à peu près 2,5 Go, parce qu'elle tire PyTorch : c'est précisément pourquoi elle est optionnelle.

### Si la fenêtre ne s'ouvre pas

Sous Windows, l'interface s'appuie sur **Microsoft Edge WebView2 Runtime**, présent d'origine sur Windows 11 et sur les Windows 10 à jour. S'il manque, installez-le depuis le site de Microsoft, puis relancez. L'application affiche ce message plutôt qu'une erreur technique.

---

## Utilisation

1. **Glissez** un ou plusieurs fichiers audio sur la fenêtre, ou cliquez sur la zone de dépôt.
2. Choisissez le preset : **Qualité maximale** ou **Rapide**.
3. Cliquez sur **Lancer la transcription**. Les fichiers sont traités l'un après l'autre.

Formats acceptés : `.m4a` (dont les enregistrements de smartphone), `.mp3`, `.wav`, `.ogg`, `.flac`, `.opus`, `.webm`, `.wma`, `.aac`, `.amr`, et les vidéos courantes (`.mp4`, `.mkv`, `.mov`), dont la piste audio est extraite.

Les sorties sont écrites dans le dossier que vous choisissez, nommées `AAAA-MM-JJ-nom-du-fichier.txt`. Les formats `.srt` et `.vtt` sont disponibles en option.

Chaque fichier texte porte un en-tête rappelant la source, la durée, le modèle utilisé, la date, le temps de calcul réel et le nombre de locuteurs détectés.

---

## Les deux presets

| Preset | Modèle | Téléchargement | Pour quoi |
|---|---|---|---|
| **Qualité maximale** (défaut) | `large-v3` | 3,1 Go | Réunions, entretiens, tout ce qui sera relu ou résumé. On lance et on laisse tourner. |
| **Rapide** | `large-v3-turbo` | 1,6 Go | Environ quatre fois plus rapide, qualité un cran en dessous. Pour dégrossir. |

Les deux utilisent la détection d'activité vocale (VAD), une température de 0 pour un décodage déterministe, et un faisceau élargi. Les modèles `tiny`, `base`, `small`, `medium`, `large-v2` restent accessibles par le **mode avancé**.

### Pourquoi `large-v3` et pas seulement le turbo

Le turbo réduit le décodeur de 32 à 4 couches. Il paie ce gain de vitesse par environ 1 à 2 points de WER en plus, avec une dégradation un peu plus marquée sur les langues autres que l'anglais. Sur du français de réunion (voix multiples, micro éloigné, chevauchements), cela se traduit par des mots mal transcrits, des noms propres écorchés, des négations perdues. Quand le texte doit rester fidèle, `large-v3` vaut son temps de calcul.

### Vitesses observées et estimées

Le facteur donné est le rapport **durée de calcul / durée de l'audio**. En dessous de 1, c'est plus rapide que l'écoute.

| Matériel | Qualité maximale | Rapide | Une heure d'audio, en qualité |
|---|---|---|---|
| Ultraportable, 12 à 14 fils, sans carte dédiée (type Core Ultra 7 155U) | environ 1,2 x | environ 0,3 x | environ 1 h 15 |
| Processeur de bureau costaud, 16 fils et plus | environ 0,7 x | environ 0,2 x | environ 40 min |
| Portable modeste, 4 à 8 fils | environ 2 x | environ 0,5 x | environ 2 h |
| Carte NVIDIA (CUDA, float16) | environ 0,1 x | environ 0,05 x | environ 6 min |

La séparation des locuteurs ajoute à peu près 0,2 x sur processeur.

**Ce sont des estimations, pas des garanties.** Elles sont calées sur des mesures publiques et ajustées au nombre de cœurs de votre machine. L'application affiche le **temps réellement mesuré** après chaque transcription, et l'écrit dans l'en-tête du fichier produit.

---

## Vocabulaire et corrections

C'est le point faible de toute transcription automatique : les noms propres, les noms de sociétés et les termes anglais sortent massacrés. Deux leviers y répondent, complémentaires.

### Le glossaire, `vocabulaire.txt`

Un terme par ligne : prénoms, sociétés, produits, sigles. Cette liste est envoyée au modèle **avant** qu'il ne transcrive, comme début de contexte (`initial_prompt`). Whisper est alors orienté vers ces orthographes.

```
Jean Dupont
MonEntreprise
GitLab
Kubernetes
RGPD
```

**Limite à connaître.** L'amorce d'un modèle Whisper ne peut pas dépasser **224 jetons**, soit une petite centaine de termes courts. Au-delà, faster-whisper tronque tout seul, et silencieusement. L'application tronque proprement à votre place, en gardant les termes **du haut de la liste**, et vous prévient dans l'interface quand la liste est trop longue : mettez donc les plus importants en premier.

Le décompte des jetons est exact : il utilise le tokeniseur du modèle réellement chargé, pas une estimation.

### Les corrections, `corrections.txt`

Pour les massacres récurrents que l'amorce ne suffit pas à éviter. Une règle par ligne :

```
guitte lab => GitLab
cubernetes => Kubernetes
er gé pé dé => RGPD
```

Appliquées au texte final. **Insensible à la casse**, **mot entier uniquement** : la règle `git` ne touchera pas `digital`. Les expressions de plusieurs mots fonctionnent, et les espaces multiples sont tolérés.

Les deux fichiers s'éditent directement, ou depuis les panneaux de l'application. Les exemples livrés sont génériques : remplacez-les par votre vocabulaire.

---

## Séparation des locuteurs

Facultative, activée par défaut sur le preset Qualité. Elle produit un texte étiqueté :

```
Locuteur 1 : On reprend le point d'hier sur le déploiement.

Locuteur 2 : C'est calé, la bascule est prévue jeudi.
```

Pour un compte rendu, ou pour un résumé produit ensuite par une IA, cette structure conversationnelle est une information de premier ordre : qui répond à qui, qui s'engage sur quoi.

### Ce qu'il faut faire une fois

Le modèle qui reconnaît les voix (pyannote) est gratuit mais **sous conditions** : son auteur demande de les accepter et de s'identifier.

1. Créez un compte sur [huggingface.co](https://huggingface.co).
2. Ouvrez [pyannote/speaker-diarization-3.1](https://huggingface.co/pyannote/speaker-diarization-3.1) et acceptez les conditions.
3. Créez un jeton d'accès **Read** dans les réglages du compte.
4. Collez-le dans le panneau « Locuteurs » de l'application.

Le jeton est enregistré dans `jeton_hf.txt`, à côté de l'application, et **jamais versionné** (il est dans le `.gitignore`). La variable d'environnement `HF_TOKEN` est également reconnue et prioritaire.

**Sans jeton, tout fonctionne quand même** : la transcription se termine normalement, simplement sans étiquettes, avec un message clair et aucune erreur.

### Tenir dans 16 Go de mémoire

Le vrai risque n'est pas la taille d'un modèle isolé, c'est le **pic simultané** des deux. L'application **séquence** donc strictement : elle transcrit, libère explicitement le modèle Whisper, force un passage du ramasse-miettes, puis charge la diarisation. Les pics se suivent au lieu de s'additionner, et `large-v3` plus pyannote tiennent dans 16 Go.

Si la mémoire détectée est trop juste, l'application le dit avant de lancer et conseille le preset Rapide.

### Honnêteté sur la qualité

pyannote sur un enregistrement mono de salle, micro unique, voix qui se chevauchent, n'est pas infaillible. Les chevauchements et les voix lointaines sont les cas durs. Les étiquettes sont utiles, elles ne sont pas une vérité. Préciser le **nombre de participants** dans les réglages améliore nettement le découpage.

---

## Matériel

Au lancement, l'application détecte le processeur, la mémoire, les cartes graphiques et les circuits neuronaux (NPU), puis affiche une recommandation. La carte « Votre matériel » se déplie pour tout le détail.

**Ce qui est accéléré en v1 :**

- **Processeur, partout** : quantification `int8`, le meilleur rapport vitesse / mémoire / qualité. C'est le mode par défaut et il est parfaitement utilisable, y compris sur un ultraportable.
- **Cartes NVIDIA** : CUDA en `float16`, automatiquement, si le pilote et les bibliothèques répondent.

**Ce qui est détecté et affiché mais pas exploité :** cartes AMD Radeon, circuits graphiques intégrés Intel, NPU. L'application le dit noir sur blanc plutôt que de laisser croire à une accélération qui n'existe pas.

La raison est structurelle : faster-whisper repose sur **CTranslate2**, dont la [documentation matérielle](https://opennmt.net/CTranslate2/hardware_support.html) ne supporte que le CPU x86-64 / ARM64 et les GPU NVIDIA. Ni ROCm, ni Vulkan, ni Metal, ni DirectML. Sur un Radeon, faster-whisper tourne en CPU pur, et le GPU ne sert à rien.

### Ouvertures matérielles prévues

Deux pistes existent pour exploiter le matériel non-NVIDIA. Elles sont documentées ici avec leur maturité réelle, pas comme des promesses.

**1. whisper.cpp + Vulkan — la piste solide, prévue en v1.x**

whisper.cpp est un portage C/C++ indépendant de PyTorch et de CUDA. Son backend Vulkan fait de l'inférence GPU multi-vendeur (AMD, Intel, NVIDIA) sans code spécifique au constructeur. C'est le seul chemin réaliste pour accélérer un Radeon sous Windows.

Mesures publiques : environ 8 x le temps réel sur une RX 9070 XT, et un facteur 3 à 4 fois meilleur que le CPU seul sur un iGPU Radeon 680M. Un GPU dédié récent y gagne franchement.

Livraison envisagée : un binaire Windows Vulkan pré-compilé, piloté en sous-processus, pour ne demander à personne d'installer une chaîne de compilation C++. Coût : un deuxième format de modèles (GGUF au lieu de CTranslate2) et une couche d'abstraction de moteur. C'est pour cela que ce n'est pas dans la v1.

**2. OpenVINO pour l'iGPU et le NPU Intel — intéressant, pas encore mûr**

whisper.cpp dispose aussi d'un backend OpenVINO, et OpenVINO sait piloter l'iGPU Arc comme le NPU des processeurs Meteor Lake. Sur un Core Ultra 7 155H, Whisper atteint un facteur temps réel 3 à 4 fois meilleur que le CPU seul.

Mais la maturité opérationnelle est faible pour un outil clé en main : le backend réclame une version précise d'OpenVINO, et la conversion des modèles Whisper casse avec certaines versions de `transformers`. C'est fragile et versionné au petit soin.

Quant au NPU lui-même, son intérêt est surtout **l'autonomie** (quelques watts contre 15 à 25 pour l'iGPU), pas la vitesse brute. Pour transcrire des fichiers en lot sur secteur, le gain est faible.

Conclusion honnête : si l'accélération d'un iGPU Intel devient un objectif, passer par **Vulkan** (le même chemin que pour l'AMD) est plus simple et plus robuste que toute la chaîne OpenVINO.

---

## Diagnostic

Chaque échec est expliqué **en français, dans l'interface** : fichier illisible, modèle à télécharger, mémoire insuffisante, jeton absent ou invalide, disque plein, bibliothèques CUDA manquantes. Aucun traceback n'apparaît à l'écran.

Le détail technique complet part dans un fichier horodaté du dossier `logs/`, dont le nom est cité dans le message d'erreur. Le bouton **« Ouvrir le fichier détaillé »**, dans la barre du bas, l'ouvre directement. Les 30 derniers journaux sont conservés, les plus anciens sont purgés.

Un fichier en échec **n'interrompt pas la file** : les suivants sont traités normalement.

Les avertissements bruyants des dépendances (notamment le message `torchcodec` / FFmpeg au démarrage de pyannote) sont interceptés et rangés dans le journal plutôt qu'affichés.

---

## Choix d'architecture

**Un seul moteur : faster-whisper (CTranslate2). whisperX a été retiré.**

La version précédente de cet outil pilotait whisperX en ligne de commande. Le remplacement se justifie sur quatre points :

1. **whisperX impose PyTorch**, faster-whisper non : il n'utilise que CTranslate2. Cela permet une installation par défaut d'environ 250 Mo au lieu de près de 3 Go, et de ne poser PyTorch que si l'on veut la séparation des locuteurs.
2. **L'alignement mot à mot par wav2vec**, principal apport de whisperX, ne sert pas ici : l'objectif est la fidélité du texte, pas le sous-titrage à la milliseconde. faster-whisper fournit déjà des horodatages par mot, largement suffisants pour attribuer les locuteurs, écrire des `.srt` et des `.vtt`.
3. **La VAD, l'autre apport de whisperX**, est intégrée à faster-whisper depuis la version 1.x (`vad_filter`).
4. **Piloter une bibliothèque plutôt qu'un sous-processus** donne la progression segment par segment, le contrôle exact de la libération mémoire entre les étapes (indispensable pour tenir dans 16 Go), les erreurs typées, et l'accès au tokeniseur du modèle pour mesurer exactement le budget de l'amorce.

pyannote est appelé directement, sans passer par whisperX, ce qui donne la main sur le moment précis du chargement et de la libération.

Le format d'organisation reste volontairement simple : une application de bureau mono-utilisateur, un paquet `app/` de modules courts, une interface web dans `web/`.

```
transcriber.pyw       fenêtre et passerelle vers l'interface
installer.py          installateur relançable
app/
  materiel.py         détection processeur, mémoire, GPU, NPU
  presets.py          presets, estimations, garde-fous mémoire
  audio.py            FFmpeg, durée, décodage 16 kHz mono
  moteur.py           faster-whisper, chargement et libération
  diarisation.py      pyannote, jeton, attribution des locuteurs
  vocabulaire.py      glossaire, amorce, corrections
  sorties.py          txt, srt, vtt, en-têtes
  traitement.py       file séquentielle
  config.py           configuration
  journal.py          journalisation et traduction des incidents
web/                  interface (HTML, CSS, JavaScript)
```

---

## Limites connues

- **Windows uniquement** en pratique. Le code est portable, mais la détection matérielle et les scripts de lancement visent Windows.
- **Aucune accélération AMD ou Intel en v1.** Ces machines transcrivent sur processeur. Voir « Ouvertures matérielles prévues ».
- **La séparation des locuteurs exige un jeton Hugging Face** et environ 2,5 Go de dépendances. Sans elle, tout le reste fonctionne.
- **Le premier lancement a besoin d'Internet** pour télécharger le modèle. Ensuite, plus jamais.
- **L'audio est décodé entièrement en mémoire** : environ 230 Mo par heure d'enregistrement. Confortable jusqu'à plusieurs heures, mais ce n'est pas du traitement en flux.
- **Les estimations de durée sont des estimations.** Le temps réel mesuré est affiché après coup.
- **La diarisation n'est pas infaillible** sur les chevauchements et les voix lointaines.

---

## Licence

MIT, voir [LICENSE](LICENSE).

Cet outil s'appuie sur des projets libres : [faster-whisper](https://github.com/SYSTRAN/faster-whisper) et [CTranslate2](https://github.com/OpenNMT/CTranslate2), les modèles [Whisper](https://github.com/openai/whisper) d'OpenAI, [pyannote.audio](https://github.com/pyannote/pyannote-audio), [pywebview](https://pywebview.flowrl.com/) et [FFmpeg](https://ffmpeg.org/).
