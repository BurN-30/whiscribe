"""
Lecture audio : localisation de FFmpeg, mesure de durée, décodage.

On décode nous-mêmes une seule fois, en mono 16 kHz float32, pour trois raisons :
  - c'est exactement ce qu'attendent Whisper et pyannote, donc pas de double
    décodage entre les deux étapes ;
  - cela permet d'appliquer au passage les filtres « audio de salle » ;
  - cela évite de dépendre du backend audio de torchaudio, source du fameux
    avertissement torchcodec au démarrage.

Le binaire FFmpeg vient du paquet `imageio-ffmpeg`, qui l'embarque : ni PATH à
configurer, ni droits administrateur, ni winget.
"""

from __future__ import annotations

import re
import subprocess
import sys
from functools import lru_cache
from pathlib import Path

import numpy as np

from . import chemins, journal
from .journal import ErreurLisible

EXTENSIONS_AUDIO = {
    ".m4a", ".mp3", ".wav", ".ogg", ".oga", ".flac", ".webm", ".wma",
    ".aac", ".opus", ".mp4", ".mkv", ".mov", ".amr", ".aiff", ".3gp",
}

FREQUENCE = 16000

# Filtres appliqués en option pour les enregistrements de salle :
# coupe sous 100 Hz (ronflement, bruit de table), coupe au-dessus de 8 kHz
# (hors bande de la voix), puis normalisation de niveau EBU R128.
FILTRES_SALLE = "highpass=f=100,lowpass=f=8000,loudnorm=I=-18:TP=-2:LRA=11"

_SANS_FENETRE = subprocess.CREATE_NO_WINDOW if sys.platform == "win32" else 0


def _ffmpeg_livre() -> str:
    """
    Binaire FFmpeg livré avec la version installée.

    PyInstaller ne copie pas le binaire d'imageio-ffmpeg tout seul : il est ajouté
    explicitement dans le fichier .spec, sous « imageio_ffmpeg/binaries ». On le
    cherche là, puis n'importe où dans les ressources en dernier recours.
    """
    racine = chemins.DOSSIER_RESSOURCES
    candidats = [
        *(racine / "imageio_ffmpeg" / "binaries").glob("ffmpeg*.exe"),
        *(racine / "imageio_ffmpeg" / "binaries").glob("ffmpeg-*"),
        *racine.glob("ffmpeg*.exe"),
    ]
    for candidat in candidats:
        if candidat.is_file():
            return str(candidat)
    return ""


@lru_cache(maxsize=1)
def binaire_ffmpeg() -> str:
    """Chemin du binaire FFmpeg utilisable, ou lève une erreur lisible."""
    if chemins.EST_GELE:
        livre = _ffmpeg_livre()
        if livre:
            # imageio-ffmpeg respecte cette variable : les appels indirects
            # trouveront le même binaire que nous.
            import os

            os.environ.setdefault("IMAGEIO_FFMPEG_EXE", livre)
            journal.info("FFmpeg livré avec l'application : %s", livre)
            return livre

    try:
        import imageio_ffmpeg  # type: ignore

        chemin = imageio_ffmpeg.get_ffmpeg_exe()
        if chemin and Path(chemin).exists():
            journal.info("FFmpeg embarqué : %s", chemin)
            return chemin
    except Exception as exc:
        journal.debug("imageio-ffmpeg indisponible : %s", exc)

    import shutil

    systeme = shutil.which("ffmpeg")
    if systeme:
        journal.info("FFmpeg du système : %s", systeme)
        return systeme

    raise ErreurLisible(
        "FFmpeg introuvable",
        "Le décodeur audio est introuvable. "
        + (
            "Réinstallez l'application depuis son programme d'installation."
            if chemins.EST_GELE
            else "Relancez « installer.bat », ou installez-le à la main avec : "
                 "pip install imageio-ffmpeg"
        ),
    )


def ffmpeg_present() -> bool:
    try:
        binaire_ffmpeg()
        return True
    except ErreurLisible:
        return False


def est_audio(chemin: str | Path) -> bool:
    return Path(chemin).suffix.lower() in EXTENSIONS_AUDIO


_MOTIF_DUREE = re.compile(r"Duration:\s*(\d+):(\d\d):(\d\d(?:\.\d+)?)")


def duree(chemin: str | Path) -> float:
    """
    Durée du fichier en secondes, 0 si elle n'a pas pu être lue.

    On lit l'en-tête via `ffmpeg -i` : le paquet imageio-ffmpeg ne fournit pas
    ffprobe, mais ffmpeg annonce la durée sur sa sortie d'erreur.
    """
    try:
        binaire = binaire_ffmpeg()
    except ErreurLisible:
        return 0.0

    try:
        resultat = subprocess.run(
            [binaire, "-hide_banner", "-i", str(chemin)],
            capture_output=True, text=True, errors="replace", timeout=60,
            creationflags=_SANS_FENETRE,
        )
        trouve = _MOTIF_DUREE.search(resultat.stderr or "")
        if trouve:
            heures, minutes, secondes = trouve.groups()
            return int(heures) * 3600 + int(minutes) * 60 + float(secondes)
    except Exception as exc:
        journal.debug("Mesure de durée impossible pour %s : %s", chemin, exc)
    return 0.0


def decoder(chemin: str | Path, filtres_salle: bool = False) -> np.ndarray:
    """
    Décode le fichier en tableau float32 mono 16 kHz, normalisé entre -1 et 1.

    Lève une ErreurLisible si le fichier est illisible ou ne contient pas d'audio.
    """
    binaire = binaire_ffmpeg()
    fichier = Path(chemin)

    if not fichier.exists():
        raise ErreurLisible(
            "Fichier introuvable",
            f"« {fichier.name} » n'existe plus à l'emplacement indiqué.",
        )

    commande = [
        binaire, "-nostdin", "-hide_banner", "-loglevel", "error",
        "-threads", "0", "-i", str(fichier),
    ]
    if filtres_salle:
        commande += ["-af", FILTRES_SALLE]
    commande += [
        "-f", "f32le", "-acodec", "pcm_f32le",
        "-ac", "1", "-ar", str(FREQUENCE), "-",
    ]

    journal.debug("Décodage : %s", " ".join(commande[:1] + commande[-10:]))

    try:
        resultat = subprocess.run(
            commande, capture_output=True, creationflags=_SANS_FENETRE
        )
    except Exception as exc:
        raise ErreurLisible(
            "Décodage impossible",
            f"FFmpeg n'a pas pu être lancé sur « {fichier.name} ».",
            exc,
        ) from exc

    if resultat.returncode != 0 or not resultat.stdout:
        detail = (resultat.stderr or b"").decode("utf-8", "replace").strip()
        journal.erreur("FFmpeg a échoué sur %s : %s", fichier.name, detail[:2000])
        raise ErreurLisible(
            "Fichier audio illisible",
            f"« {fichier.name} » n'a pas pu être décodé : le fichier est peut-être "
            "corrompu, incomplet, ou ne contient aucune piste audio. Le détail "
            f"FFmpeg est dans logs/{journal.nom_fichier()}.",
        )

    signal = np.frombuffer(resultat.stdout, dtype=np.float32)
    if signal.size == 0:
        raise ErreurLisible(
            "Aucun son détecté",
            f"« {fichier.name} » ne contient aucune donnée audio exploitable.",
        )

    # Copie explicite : le tampon de frombuffer est en lecture seule.
    signal = np.array(signal, dtype=np.float32, copy=True)
    maximum = float(np.max(np.abs(signal))) if signal.size else 0.0
    if maximum > 1.0:
        signal /= maximum

    journal.info(
        "Audio décodé : %s, %.1f s%s",
        fichier.name, signal.size / FREQUENCE,
        " (filtres de salle appliqués)" if filtres_salle else "",
    )
    return signal


def formater_taille(octets: int) -> str:
    if octets >= 1024 ** 3:
        return f"{octets / 1024 ** 3:.1f} Go"
    if octets >= 1024 ** 2:
        return f"{octets / 1024 ** 2:.1f} Mo"
    return f"{octets / 1024:.0f} Ko"
