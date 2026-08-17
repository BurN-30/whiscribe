"""
Moteur de transcription : faster-whisper (CTranslate2).

Choix d'architecture assumé pour la v1 : un seul moteur.
  - CPU partout en int8, c'est le meilleur rapport vitesse / mémoire / qualité ;
  - CUDA float16 uniquement si une carte NVIDIA répond.

Le modèle est chargé puis explicitement libéré : la diarisation ne démarre
jamais tant que le modèle de transcription occupe encore la mémoire. C'est ce
séquencement qui permet de faire tenir large-v3 plus pyannote dans 16 Go.
"""

from __future__ import annotations

import gc
import os
from dataclasses import dataclass
from pathlib import Path
from typing import Callable

import numpy as np

from . import audio as audio_module
from . import chemins, journal, presets
from .journal import ErreurLisible
from .materiel import Materiel

# Repli de température : on part de 0 pour un décodage déterministe, et on ne
# remonte que si le décodage échoue sur un segment.
REPLI_TEMPERATURE = (0.0, 0.2, 0.4, 0.6, 0.8, 1.0)


@dataclass
class Segment:
    debut: float
    fin: float
    texte: str
    locuteur: str = ""


def identifiant_depot(modele: str) -> str:
    """Nom du dépôt Hugging Face correspondant à un nom court de modèle."""
    try:
        from faster_whisper.utils import _MODELS  # type: ignore

        return _MODELS.get(modele, modele)
    except Exception:
        return modele


def modele_deja_telecharge(modele: str) -> bool:
    """Le modèle est-il déjà sur le disque ? Sert à prévenir avant un gros téléchargement."""
    if Path(modele).is_dir():
        return True
    try:
        from faster_whisper.utils import download_model

        download_model(modele, local_files_only=True, cache_dir=str(chemins.DOSSIER_MODELES))
        return True
    except Exception:
        return False


class MoteurTranscription:
    """Enveloppe autour de WhisperModel, avec libération explicite."""

    def __init__(self, mat: Materiel, forcer_processeur: bool = False):
        self.materiel = mat
        self.forcer_processeur = forcer_processeur
        self._modele = None
        self._nom_modele = ""

    # -- cycle de vie ------------------------------------------------------

    @property
    def peripherique(self) -> str:
        if self.forcer_processeur:
            return "cpu"
        return self.materiel.peripherique

    @property
    def type_calcul(self) -> str:
        return "float16" if self.peripherique == "cuda" else "int8"

    def charger(self, modele: str, signaler: Callable[[str, str], None] | None = None) -> None:
        if self._modele is not None and self._nom_modele == modele:
            return
        self.liberer()

        from faster_whisper import WhisperModel

        chemins.assurer_dossiers()

        if signaler and not modele_deja_telecharge(modele):
            taille = _taille_annoncee(modele)
            signaler(
                "attention",
                f"Premier usage de ce modèle : téléchargement d'environ {taille}. "
                "Cela n'arrive qu'une fois, ensuite tout reste sur la machine.",
            )

        journal.info(
            "Chargement du modèle %s (périphérique=%s, calcul=%s, fils=%s)",
            modele, self.peripherique, self.type_calcul, self.materiel.fils_calcul,
        )
        if signaler:
            signaler("info", f"Chargement du modèle {_nom_court(modele)}...")

        try:
            with journal.SortieMuette("chargement du modèle"):
                self._modele = WhisperModel(
                    modele,
                    device=self.peripherique,
                    compute_type=self.type_calcul,
                    cpu_threads=self.materiel.fils_calcul,
                    num_workers=1,
                    download_root=str(chemins.DOSSIER_MODELES),
                )
        except Exception as exc:
            journal.exception(f"Chargement du modèle {modele} impossible", exc)
            raise
        self._nom_modele = modele

    def liberer(self) -> None:
        """Déréférence le modèle et rend la mémoire avant l'étape suivante."""
        if self._modele is None:
            return
        journal.info("Libération du modèle %s", self._nom_modele)
        self._modele = None
        self._nom_modele = ""
        gc.collect()

    @property
    def tokeniseur(self):
        return getattr(self._modele, "hf_tokenizer", None)

    # -- transcription -----------------------------------------------------

    def transcrire(
        self,
        signal: np.ndarray,
        duree_totale: float,
        langue: str,
        reglages: dict,
        amorce: str = "",
        progression: Callable[[float], None] | None = None,
        interrompu: Callable[[], bool] | None = None,
    ) -> tuple[list[Segment], dict]:
        if self._modele is None:
            raise ErreurLisible(
                "Modèle non chargé",
                "La transcription a été demandée avant le chargement du modèle.",
            )

        beam = int(reglages.get("beam_size") or 5)
        options = dict(
            language=(langue or None) if langue != "auto" else None,
            task="transcribe",
            beam_size=beam,
            best_of=max(beam, int(reglages.get("best_of") or beam)),
            temperature=list(REPLI_TEMPERATURE),
            condition_on_previous_text=bool(reglages.get("condition_on_previous_text", True)),
            initial_prompt=amorce or None,
            vad_filter=bool(reglages.get("vad", True)),
            word_timestamps=True,
            no_speech_threshold=0.6,
            compression_ratio_threshold=2.4,
            hallucination_silence_threshold=2.0 if reglages.get("vad", True) else None,
        )
        if options["vad_filter"]:
            options["vad_parameters"] = {"min_silence_duration_ms": 500}

        journal.info(
            "Transcription : langue=%s, beam=%s, VAD=%s, amorce=%s caractères",
            langue, beam, options["vad_filter"], len(amorce),
        )

        with journal.SortieMuette("transcription"):
            iterateur, info = self._modele.transcribe(signal, **options)

            segments: list[Segment] = []
            for brut in iterateur:
                if interrompu is not None and interrompu():
                    journal.attention("Transcription interrompue à la demande de l'utilisateur")
                    raise Interruption()
                texte = (brut.text or "").strip()
                if texte:
                    segments.append(Segment(debut=brut.start, fin=brut.end, texte=texte))
                if progression and duree_totale > 0:
                    progression(min(0.99, brut.end / duree_totale))

        if progression:
            progression(1.0)

        details = {
            "langue": getattr(info, "language", langue),
            "probabilite_langue": round(float(getattr(info, "language_probability", 0) or 0), 3),
            "duree": float(getattr(info, "duration", duree_totale) or duree_totale),
            "modele": self._nom_modele,
            "peripherique": self.peripherique,
            "type_calcul": self.type_calcul,
        }
        journal.info(
            "Transcription terminée : %s segments, langue détectée %s",
            len(segments), details["langue"],
        )
        return segments, details


class Interruption(Exception):
    """Levée quand l'utilisateur demande l'arrêt de la file."""


def nom_court(modele: str) -> str:
    """« deepdml/faster-whisper-large-v3-turbo-ct2 » devient « large-v3-turbo »."""
    if "/" in modele:
        nom = modele.rsplit("/", 1)[1]
        return nom.replace("faster-whisper-", "").replace("-ct2", "")
    return modele


_nom_court = nom_court  # compatibilité interne


def _taille_annoncee(modele: str) -> str:
    for entree in presets.MODELES_AVANCES:
        if entree["cle"] == modele:
            return entree["taille"]
    for p in presets.PRESETS.values():
        if p["modele"] == modele:
            return f"{p['telechargement_go']:.1f} Go".replace(".", ",")
    return "quelques centaines de Mo à 3 Go"


def limiter_parallelisme(fils: int) -> None:
    """Borne les bibliothèques de calcul pour que la machine reste utilisable."""
    valeur = str(max(1, fils))
    for variable in ("OMP_NUM_THREADS", "MKL_NUM_THREADS", "OPENBLAS_NUM_THREADS",
                     "NUMEXPR_NUM_THREADS"):
        os.environ.setdefault(variable, valeur)


def duree_et_signal(chemin: str, filtres_salle: bool) -> tuple[np.ndarray, float]:
    signal = audio_module.decoder(chemin, filtres_salle=filtres_salle)
    return signal, signal.size / audio_module.FREQUENCE
