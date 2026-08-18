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
from dataclasses import dataclass, field
from pathlib import Path
from typing import Callable

import numpy as np

from . import audio as audio_module
from . import chemins, journal, langues, presets
from .journal import ErreurLisible
from .materiel import Materiel

# Repli de température : on part de 0 pour un décodage déterministe, et on ne
# remonte que si le décodage échoue sur un segment.
REPLI_TEMPERATURE = (0.0, 0.2, 0.4, 0.6, 0.8, 1.0)


@dataclass
class Mot:
    """
    Un mot et la probabilité que le modèle lui accorde.

    faster-whisper la fournit d'origine avec `word_timestamps=True`, sans
    surcoût notable. Elle sert à signaler dans la vue de lecture les passages
    entendus avec le moins de certitude, ceux qu'il vaut mieux réécouter.
    """

    texte: str
    debut: float
    fin: float
    probabilite: float


@dataclass
class Segment:
    debut: float
    fin: float
    texte: str
    locuteur: str = ""
    mots: list[Mot] = field(default_factory=list)


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
            taille = taille_annoncee(modele)
            signaler("attention", langues.t("moteur.premier_usage", taille=taille))

        journal.info(
            "Chargement du modèle %s (périphérique=%s, calcul=%s, fils=%s)",
            modele, self.peripherique, self.type_calcul, self.materiel.fils_calcul,
        )
        if signaler:
            signaler("info", langues.t("moteur.chargement", modele=_nom_court(modele)))

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
        decalage: float = 0.0,
        sur_segment: Callable[[Segment], None] | None = None,
    ) -> tuple[list[Segment], dict]:
        """
        Transcrit un signal déjà décodé.

        `decalage` déplace tous les horodatages : il vaut zéro en temps normal,
        et la position atteinte quand on reprend une transcription interrompue,
        où seule la fin du signal est repassée au modèle.

        `sur_segment` est appelé pour chaque segment dès qu'il sort du décodeur.
        C'est le point d'accroche de la sauvegarde progressive : le moteur
        produit déjà les segments un par un, rien n'est mis en tampon pour lui.
        """
        if self._modele is None:
            raise ErreurLisible(
                langues.t("moteur.non_charge.titre"),
                langues.t("moteur.non_charge.msg"),
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
                    segment = Segment(
                        debut=brut.start + decalage,
                        fin=brut.end + decalage,
                        texte=texte,
                        mots=_mots_du_segment(brut, decalage),
                    )
                    segments.append(segment)
                    if sur_segment is not None:
                        sur_segment(segment)
                if progression and duree_totale > 0:
                    progression(min(0.99, (brut.end + decalage) / duree_totale))

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


def _mots_du_segment(brut, decalage: float = 0.0) -> list[Mot]:
    """
    Extrait les mots et leur probabilité d'un segment de faster-whisper.

    Le décodeur les fournit déjà, `word_timestamps` étant activé pour attribuer
    les locuteurs. Un modèle ou une version qui ne les donnerait pas renvoie
    simplement une liste vide, et la vue de lecture s'en passe.
    """
    resultat: list[Mot] = []
    for mot in getattr(brut, "words", None) or []:
        texte = (getattr(mot, "word", "") or "").strip()
        if not texte:
            continue
        resultat.append(Mot(
            texte=texte,
            debut=float(getattr(mot, "start", 0.0) or 0.0) + decalage,
            fin=float(getattr(mot, "end", 0.0) or 0.0) + decalage,
            probabilite=float(getattr(mot, "probability", 0.0) or 0.0),
        ))
    return resultat


class Interruption(Exception):
    """Levée quand l'utilisateur demande l'arrêt de la file."""


def nom_court(modele: str) -> str:
    """« deepdml/faster-whisper-large-v3-turbo-ct2 » devient « large-v3-turbo »."""
    if "/" in modele:
        nom = modele.rsplit("/", 1)[1]
        return nom.replace("faster-whisper-", "").replace("-ct2", "")
    return modele


_nom_court = nom_court  # compatibilité interne


def connexion_disponible(delai: float = 4.0) -> bool:
    """
    Teste si le dépôt de modèles est joignable, avant de lancer un téléchargement.

    Une simple ouverture de socket : pas de requête, rien d'envoyé. Cela évite de
    présenter un traceback réseau à quelqu'un dont le poste est simplement isolé.
    """
    import socket

    for hote in ("huggingface.co", "cdn-lfs.huggingface.co"):
        try:
            with socket.create_connection((hote, 443), timeout=delai):
                return True
        except OSError:
            continue
    return False


def taille_annoncee(modele: str) -> str:
    taille = presets.taille_modele_avance(modele)
    if taille:
        return taille
    for p in presets.PRESETS.values():
        if p["modele"] == modele:
            return langues.octets(p["telechargement_go"] * 1024 ** 3)
    return langues.t("moteur.taille_inconnue")


def limiter_parallelisme(fils: int) -> None:
    """Borne les bibliothèques de calcul pour que la machine reste utilisable."""
    valeur = str(max(1, fils))
    for variable in ("OMP_NUM_THREADS", "MKL_NUM_THREADS", "OPENBLAS_NUM_THREADS",
                     "NUMEXPR_NUM_THREADS"):
        os.environ.setdefault(variable, valeur)


def duree_et_signal(chemin: str, filtres_salle: bool) -> tuple[np.ndarray, float]:
    signal = audio_module.decoder(chemin, filtres_salle=filtres_salle)
    return signal, signal.size / audio_module.FREQUENCE
