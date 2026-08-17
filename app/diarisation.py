"""
Séparation des locuteurs (diarisation) via pyannote.audio.

Toujours exécutée APRÈS la transcription, une fois le modèle Whisper libéré :
les deux pics de mémoire se suivent au lieu de s'additionner, ce qui permet de
tenir dans 16 Go avec large-v3.

pyannote est optionnel. Sans torch installé, sans jeton Hugging Face, ou si les
conditions du modèle n'ont pas été acceptées, la transcription se termine
normalement, simplement sans étiquettes de locuteur.
"""

from __future__ import annotations

import gc
import inspect
import os
from typing import Callable

import numpy as np

from . import URL_PROJET as _URL_DEPOT
from . import chemins, journal
from .journal import ErreurLisible

# Dépôts essayés dans l'ordre. Le premier est la référence stable, le second
# est le nom retenu par pyannote.audio 4.x.
DEPOTS = (
    "pyannote/speaker-diarization-3.1",
    "pyannote/speaker-diarization-community-1",
)

URL_CONDITIONS = "https://huggingface.co/pyannote/speaker-diarization-3.1"
URL_JETON = "https://huggingface.co/settings/tokens"

# Le dépôt du projet, cité quand la fonction n'est pas incluse dans la version
# installée. L'ancre pointe sur la section du README qui décrit la voie source.
URL_PROJET = (
    f"{_URL_DEPOT}#installation-depuis-les-sources-"
    "développeurs-et-séparation-des-locuteurs"
)


def torch_present() -> bool:
    try:
        import importlib.util

        return importlib.util.find_spec("torch") is not None
    except Exception:
        return False


def pyannote_present() -> bool:
    try:
        import importlib.util

        return importlib.util.find_spec("pyannote.audio") is not None
    except Exception:
        return False


def disponible() -> bool:
    return torch_present() and pyannote_present()


def indisponibilite() -> str:
    """Phrase expliquant pourquoi la diarisation ne peut pas tourner, ou chaîne vide."""
    if disponible():
        return ""

    if chemins.EST_GELE:
        # La version installée ne contient pas PyTorch : il pèse à lui seul plus
        # de 2,5 Go, ce qui ferait passer le programme d'installation de 200 Mo à
        # près de 3 Go pour une fonction facultative.
        return (
            "La séparation des locuteurs n'est pas incluse dans la version installée. "
            "Elle repose sur PyTorch, environ 2,5 Go de composants supplémentaires. "
            "Elle reste disponible dans la version source du projet, voir la section "
            "« Séparation des locuteurs » du fichier README. Tout le reste de "
            "l'application fonctionne normalement."
        )

    if not torch_present():
        return (
            "PyTorch n'est pas installé. Relancez « installer.bat » et répondez oui à "
            "la question sur la séparation des locuteurs, ou lancez "
            "« installer.bat --locuteurs »."
        )
    return (
        "La bibliothèque pyannote.audio n'est pas installée. Relancez "
        "« installer.bat --locuteurs »."
    )


def jeton() -> str:
    """
    Jeton Hugging Face, cherché dans l'ordre : variable d'environnement, fichier local.

    Le fichier `jeton_hf.txt` est ignoré par Git : aucun secret ne part dans le dépôt.
    """
    for variable in ("HF_TOKEN", "HUGGING_FACE_HUB_TOKEN", "HUGGINGFACE_TOKEN"):
        valeur = (os.environ.get(variable) or "").strip()
        if valeur:
            return valeur
    try:
        return chemins.FICHIER_JETON_HF.read_text(encoding="utf-8").strip()
    except OSError:
        return ""


def enregistrer_jeton(valeur: str) -> None:
    valeur = (valeur or "").strip()
    if not valeur:
        chemins.FICHIER_JETON_HF.unlink(missing_ok=True)
        journal.info("Jeton Hugging Face effacé")
        return
    chemins.FICHIER_JETON_HF.write_text(valeur + "\n", encoding="utf-8")
    journal.info("Jeton Hugging Face enregistré (%s caractères)", len(valeur))


def jeton_present() -> bool:
    return bool(jeton())


def _charger_pipeline(cle: str, signaler: Callable[[str, str], None] | None):
    from pyannote.audio import Pipeline

    # pyannote 4.x attend `token`, les versions 3.x attendaient `use_auth_token`.
    parametres = inspect.signature(Pipeline.from_pretrained).parameters
    nom_argument = "token" if "token" in parametres else "use_auth_token"

    dernier: Exception | None = None
    for depot in DEPOTS:
        try:
            if signaler:
                signaler("info", f"Chargement du modèle de locuteurs ({depot.split('/')[-1]})...")
            with journal.SortieMuette("chargement pyannote"):
                pipeline = Pipeline.from_pretrained(
                    depot,
                    cache_dir=str(chemins.DOSSIER_MODELES),
                    **{nom_argument: cle},
                )
            if pipeline is not None:
                journal.info("Diarisation : dépôt %s chargé", depot)
                return pipeline
            dernier = ErreurLisible(
                "Modèle de locuteurs inaccessible",
                f"Le dépôt {depot} n'a rien renvoyé, généralement parce que ses "
                "conditions d'utilisation n'ont pas été acceptées avec ce compte.",
            )
        except Exception as exc:
            journal.attention("Dépôt %s indisponible : %s", depot, exc)
            dernier = exc

    if dernier is not None:
        raise dernier
    raise ErreurLisible(
        "Modèle de locuteurs inaccessible",
        "Aucun dépôt pyannote n'a pu être chargé.",
    )


def diariser(
    signal: np.ndarray,
    frequence: int,
    nb_locuteurs: int = 0,
    signaler: Callable[[str, str], None] | None = None,
    interrompu: Callable[[], bool] | None = None,
) -> list[dict]:
    """
    Renvoie une liste de tours de parole : [{debut, fin, locuteur}].

    Lève une ErreurLisible si la diarisation ne peut pas se faire. L'appelant
    décide alors de poursuivre sans étiquettes, ce qui est le comportement retenu.
    """
    manque = indisponibilite()
    if manque:
        raise ErreurLisible("Séparation des locuteurs indisponible", manque)

    cle = jeton()
    if not cle:
        raise ErreurLisible(
            "Jeton Hugging Face manquant",
            "La séparation des locuteurs a besoin d'un jeton gratuit. Ouvrez le "
            "panneau « Locuteurs » : la marche à suivre y est détaillée en trois étapes.",
        )

    import torch

    pipeline = _charger_pipeline(cle, signaler)

    try:
        if torch.cuda.is_available():
            pipeline.to(torch.device("cuda"))
            journal.info("Diarisation sur GPU NVIDIA")
    except Exception as exc:
        journal.debug("Bascule GPU impossible pour la diarisation : %s", exc)

    forme_onde = torch.from_numpy(np.ascontiguousarray(signal, dtype=np.float32)).unsqueeze(0)
    entree = {"waveform": forme_onde, "sample_rate": frequence}

    arguments: dict = {}
    if nb_locuteurs and nb_locuteurs > 0:
        arguments["num_speakers"] = int(nb_locuteurs)

    if signaler:
        signaler("info", "Analyse des voix en cours...")

    try:
        with journal.SortieMuette("diarisation"):
            annotation = pipeline(entree, **arguments)
    finally:
        del forme_onde, entree
        try:
            del pipeline
        except Exception:
            pass
        gc.collect()

    tours: list[dict] = []
    etiquettes: dict[str, int] = {}
    for periode, _, etiquette in annotation.itertracks(yield_label=True):
        if etiquette not in etiquettes:
            etiquettes[etiquette] = len(etiquettes) + 1
        tours.append({
            "debut": float(periode.start),
            "fin": float(periode.end),
            "locuteur": f"Locuteur {etiquettes[etiquette]}",
        })

    tours.sort(key=lambda t: t["debut"])
    journal.info("Diarisation terminée : %s tours, %s locuteurs", len(tours), len(etiquettes))
    return tours


def attribuer(segments, tours: list[dict]) -> int:
    """
    Attribue un locuteur à chaque segment, par recouvrement temporel majoritaire.

    Renvoie le nombre de locuteurs distincts effectivement posés. Les segments
    sans recouvrement gardent une étiquette vide plutôt qu'une étiquette fausse.
    """
    if not tours:
        return 0

    poses: set[str] = set()
    for segment in segments:
        meilleur, duree_max = "", 0.0
        for tour in tours:
            if tour["fin"] <= segment.debut:
                continue
            if tour["debut"] >= segment.fin:
                break
            recouvrement = min(segment.fin, tour["fin"]) - max(segment.debut, tour["debut"])
            if recouvrement > duree_max:
                duree_max, meilleur = recouvrement, tour["locuteur"]
        if meilleur:
            segment.locuteur = meilleur
            poses.add(meilleur)

    return len(poses)


def guide() -> dict:
    """Contenu du guide affiché dans l'interface quand le jeton manque."""
    return {
        "url_conditions": URL_CONDITIONS,
        "url_jeton": URL_JETON,
        "url_projet": URL_PROJET,
        "version_installee": chemins.EST_GELE,
        "fichier_jeton": str(chemins.FICHIER_JETON_HF),
        "etapes": [
            "Créez un compte gratuit sur huggingface.co, puis ouvrez la page du modèle "
            "pyannote/speaker-diarization-3.1 et acceptez ses conditions d'utilisation.",
            "Dans les réglages du compte, créez un jeton d'accès de type « Read ».",
            "Collez le jeton dans le champ ci-dessous. Il est enregistré dans le "
            "fichier « jeton_hf.txt » de vos données personnelles, et n'est jamais versionné.",
        ],
    }
