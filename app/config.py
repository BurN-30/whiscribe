"""
Configuration de l'application.

`config.json` est propre à chaque poste, il n'est pas versionné.
`config.example.json` en donne un exemplaire neutre, sans aucun chemin réel.
"""

from __future__ import annotations

import json
from copy import deepcopy

from . import chemins, journal
from .presets import PRESET_DEFAUT

DEFAUTS: dict = {
    "preset": PRESET_DEFAUT,
    "langue": "fr",
    "dossier_sortie": "",
    "diarisation": True,
    "nb_locuteurs": 0,              # 0 = détection automatique
    "formats": {"txt": True, "srt": False, "vtt": False, "horodatage": False},
    "appliquer_corrections": True,
    "utiliser_glossaire": True,
    "filtres_salle": False,
    "mode_avance": False,
    "modele_avance": "",            # vide = modèle du preset
    "beam_size": 0,                 # 0 = valeur du preset
    "condition_on_previous_text": True,
    "forcer_processeur": False,
    "theme": "auto",                # auto | clair | sombre
    "zoom": 1.0,
    "journal_ouvert": False,
}


def _fusionner(base: dict, ajout: dict) -> dict:
    resultat = deepcopy(base)
    for cle, valeur in (ajout or {}).items():
        if cle not in resultat:
            continue
        if isinstance(resultat[cle], dict) and isinstance(valeur, dict):
            resultat[cle] = {**resultat[cle], **valeur}
        else:
            resultat[cle] = valeur
    return resultat


def charger() -> dict:
    donnees: dict = {}
    if chemins.FICHIER_CONFIG.exists():
        try:
            donnees = json.loads(chemins.FICHIER_CONFIG.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as exc:
            journal.attention("config.json illisible, valeurs par défaut utilisées : %s", exc)
            donnees = {}

    config = _fusionner(DEFAUTS, donnees)

    if not config["dossier_sortie"]:
        config["dossier_sortie"] = str(chemins.dossier_sortie_defaut())

    return config


def sauver(config: dict) -> None:
    try:
        chemins.FICHIER_CONFIG.write_text(
            json.dumps(config, indent=2, ensure_ascii=False) + "\n", encoding="utf-8"
        )
    except OSError as exc:
        journal.attention("Sauvegarde de config.json impossible : %s", exc)


def reglages_effectifs(config: dict) -> dict:
    """
    Traduit la configuration de l'interface en paramètres du moteur.

    Le mode avancé n'écrase que ce que l'utilisateur a explicitement changé :
    tout le reste continue de venir du preset.
    """
    from .presets import preset as lire_preset

    p = lire_preset(config.get("preset", PRESET_DEFAUT))
    avance = bool(config.get("mode_avance"))
    modele = (config.get("modele_avance") or p["modele"]) if avance else p["modele"]
    beam = (config.get("beam_size") or p["beam_size"]) if avance else p["beam_size"]
    personnalise = avance and (modele != p["modele"] or beam != p["beam_size"])

    return {
        "preset": p["cle"],
        "preset_nom": f"{p['nom']}, réglages personnalisés" if personnalise else p["nom"],
        "modele": modele,
        "beam_size": beam,
        "best_of": p["best_of"],
        "vad": p["vad"],
        "condition_on_previous_text": (
            bool(config.get("condition_on_previous_text", True)) if avance else True
        ),
        "filtres_salle": bool(config.get("filtres_salle")),
        "forcer_processeur": bool(config.get("forcer_processeur")) if avance else False,
    }
