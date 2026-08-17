# -*- mode: python ; coding: utf-8 -*-
"""
Recette PyInstaller de WhiScribe.

Mode « onedir » et non « onefile », volontairement :
  - le démarrage est immédiat, alors qu'un onefile se décompresse dans un dossier
    temporaire à chaque lancement, ce qui coûte plusieurs secondes avec des
    bibliothèques de calcul de cette taille ;
  - les antivirus se méfient beaucoup moins d'un dossier de DLL lisibles que d'un
    exécutable unique qui s'auto-extrait ;
  - le programme d'installation, lui, présente bien un seul fichier à télécharger.

Deux exécutables sortent de la même analyse :
  - WhiScribe.exe          l'application, sans console ;
  - whiscribe-verifier.exe le même programme lancé avec « --verifier », avec
                           console, pour valider une version construite sans
                           aucune interaction. C'est ce que fait la chaîne de
                           publication avant de fabriquer le programme d'installation.

Construction :
    .venv\\Scripts\\pyinstaller.exe --noconfirm --clean packaging\\whiscribe.spec
"""

import sys
from pathlib import Path

from PyInstaller.utils.hooks import collect_data_files, collect_dynamic_libs, collect_submodules

# SPECPATH est fourni par PyInstaller : le dossier de ce fichier .spec.
RACINE = Path(SPECPATH).resolve().parent
PAQUET = RACINE / "packaging"

sys.path.insert(0, str(RACINE))
from app import EDITEUR, NOM_APPLICATION, URL_PROJET as DEPOT, VERSION  # noqa: E402

ICONE = PAQUET / "whiscribe.ico"


# ---------------------------------------------------------------------------
# Propriétés Windows de l'exécutable, écrites depuis app/__init__.py
#
# Le fichier est généré plutôt que versionné : la version ne peut pas diverger
# de celle de l'application, qui reste la seule source de vérité.
# ---------------------------------------------------------------------------

def _ressource_version() -> str:
    morceaux = [int(m) for m in VERSION.split(".")]
    while len(morceaux) < 4:
        morceaux.append(0)
    quadruplet = tuple(morceaux[:4])

    contenu = f"""# Généré par packaging/whiscribe.spec, ne pas modifier à la main.
VSVersionInfo(
  ffi=FixedFileInfo(
    filevers={quadruplet}, prodvers={quadruplet},
    mask=0x3f, flags=0x0, OS=0x40004, fileType=0x1, subtype=0x0, date=(0, 0)
  ),
  kids=[
    StringFileInfo([
      StringTable('040C04B0', [
        StringStruct('CompanyName', {EDITEUR!r}),
        StringStruct('FileDescription', 'WhiScribe, transcription audio locale'),
        StringStruct('FileVersion', {VERSION!r}),
        StringStruct('InternalName', 'WhiScribe'),
        StringStruct('LegalCopyright', 'Licence MIT, {EDITEUR}'),
        StringStruct('OriginalFilename', 'WhiScribe.exe'),
        StringStruct('ProductName', 'WhiScribe'),
        StringStruct('ProductVersion', {VERSION!r}),
        StringStruct('Comments', {DEPOT!r}),
      ])
    ]),
    # 0x040C : français, 0x04B0 : Unicode.
    VarFileInfo([VarStruct('Translation', [0x040C, 1200])])
  ]
)
"""
    destination = RACINE / "build" / "version_exe.txt"
    destination.parent.mkdir(parents=True, exist_ok=True)
    destination.write_text(contenu, encoding="utf-8")
    return str(destination)


VERSION_EXE = _ressource_version()


# ---------------------------------------------------------------------------
# Ressources livrées avec le programme
# ---------------------------------------------------------------------------

donnees = [
    # L'interface complète. Sans elle, la fenêtre s'ouvre vide.
    (str(RACINE / "web"), "web"),
    # Exemples recopiés dans l'espace utilisateur au premier lancement.
    (str(RACINE / "config.example.json"), "."),
    (str(RACINE / "vocabulaire.txt"), "."),
    (str(RACINE / "corrections.txt"), "."),
    (str(RACINE / "LICENSE"), "."),
    (str(RACINE / "README.md"), "."),
]

# faster-whisper embarque le modèle de détection d'activité vocale (silero, ONNX)
# dans son dossier « assets ». Il n'est pas téléchargé : il doit être livré.
donnees += collect_data_files("faster_whisper")

# Le binaire FFmpeg d'imageio-ffmpeg. Le hook officiel le copie déjà, on le
# redemande explicitement pour ne pas dépendre d'une version du hook.
donnees += collect_data_files("imageio_ffmpeg", subdir="binaries")

# tokenizers et huggingface_hub emportent quelques fichiers de données.
donnees += collect_data_files("tokenizers")
donnees += collect_data_files("huggingface_hub")

# CTranslate2 est une bibliothèque native : ses DLL vivent dans le paquet et
# aucun hook ne les ramasse. C'est le point qui casse le plus souvent un gel.
binaires = collect_dynamic_libs("ctranslate2")
binaires += collect_dynamic_libs("onnxruntime")
binaires += collect_dynamic_libs("tokenizers")


# ---------------------------------------------------------------------------
# Imports que l'analyse statique ne voit pas
# ---------------------------------------------------------------------------

imports_caches = [
    "ctranslate2",
    "ctranslate2._ext",
    "faster_whisper",
    "tokenizers",
    "huggingface_hub",
    "onnxruntime",
    "av",
    "numpy",
    "psutil",
    # Sélecteurs de fichiers et boîtes de message de secours.
    "tkinter",
    "tkinter.messagebox",
]
imports_caches += collect_submodules("app")
# Les plateformes de pywebview sont choisies à l'exécution.
imports_caches += collect_submodules("webview.platforms")


# La séparation des locuteurs reste hors du programme d'installation : PyTorch
# pèse à lui seul plus de 2,5 Go. L'application le dit proprement à l'utilisateur.
exclusions = [
    "torch",
    "torchaudio",
    "pyannote",
    "pyannote.audio",
    "speechbrain",
    "lightning",
    "pytorch_lightning",
    "matplotlib",
    "pandas",
    "scipy",
    "sklearn",
    "IPython",
    "pytest",
    "setuptools",
    "pip",
]


a = Analysis(
    [str(RACINE / "transcriber.pyw")],
    pathex=[str(RACINE)],
    binaries=binaires,
    datas=donnees,
    hiddenimports=imports_caches,
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=exclusions,
    noarchive=False,
    optimize=0,
)

pyz = PYZ(a.pure)

application = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name=NOM_APPLICATION,
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=False,          # UPX déclenche des faux positifs antivirus, on s'en passe.
    console=False,      # L'application a sa propre fenêtre.
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
    icon=str(ICONE),
    version=VERSION_EXE,
)

verificateur = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name="whiscribe-verifier",
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=False,
    console=True,       # Bilan lisible dans les journaux d'intégration continue.
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
    icon=str(ICONE),
    version=VERSION_EXE,
)

coll = COLLECT(
    application,
    verificateur,
    a.binaries,
    a.datas,
    strip=False,
    upx=False,
    upx_exclude=[],
    name=NOM_APPLICATION,
)
