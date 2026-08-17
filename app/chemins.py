"""Emplacements de fichiers de l'application. Aucun chemin personnel en dur."""

from pathlib import Path

RACINE = Path(__file__).resolve().parent.parent

DOSSIER_WEB = RACINE / "web"
DOSSIER_LOGS = RACINE / "logs"
DOSSIER_MODELES = RACINE / "modeles"

FICHIER_CONFIG = RACINE / "config.json"
FICHIER_CONFIG_EXEMPLE = RACINE / "config.example.json"
FICHIER_VOCABULAIRE = RACINE / "vocabulaire.txt"
FICHIER_CORRECTIONS = RACINE / "corrections.txt"
FICHIER_JETON_HF = RACINE / "jeton_hf.txt"


def dossier_sortie_defaut() -> Path:
    """Dossier de sortie propose au premier lancement : Documents/Transcriptions."""
    documents = Path.home() / "Documents"
    base = documents if documents.is_dir() else Path.home()
    return base / "Transcriptions"


def assurer_dossiers() -> None:
    DOSSIER_LOGS.mkdir(parents=True, exist_ok=True)
    DOSSIER_MODELES.mkdir(parents=True, exist_ok=True)
