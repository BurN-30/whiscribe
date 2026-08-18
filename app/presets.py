"""
Presets de transcription, estimations de durée et garde-fous mémoire.

Deux presets sont exposés en façade :

  « Qualité maximale » : large-v3, int8 sur processeur, VAD actif, beam 8,
      température 0. C'est le défaut pour les réunions, quand le texte doit être
      fidèle mot à mot. On lance et on laisse tourner.

  « Rapide » : large-v3-turbo (dépôt CTranslate2 explicite), mêmes réglages,
      environ quatre fois plus rapide, qualité légèrement en retrait.

Les autres modèles restent atteignables par le mode avancé.

Les facteurs de durée sont des ESTIMATIONS calées sur des mesures publiques
(voir README). Elles sont recalibrées à chaud après chaque transcription réussie.
"""

from __future__ import annotations

from . import langues
from .materiel import Materiel, SEUIL_MEMOIRE_CRITIQUE

# Modèle turbo : on nomme le dépôt converti explicitement plutôt que l'alias
# « turbo », qui dépend de la version de faster-whisper installée.
MODELE_TURBO = "deepdml/faster-whisper-large-v3-turbo-ct2"

PRESETS: dict[str, dict] = {
    "qualite": {
        "cle": "qualite",
        "modele": "large-v3",
        "beam_size": 8,
        "best_of": 8,
        "temperature": 0.0,
        "vad": True,
        "diarisation_defaut": True,
        "telechargement_go": 3.1,
        "memoire_go": 3.5,
        # Facteur temps réel de référence (durée de calcul / durée de l'audio)
        # sur une machine repère : ultraportable 12 fils, sans carte dédiée.
        "facteur_cpu": 1.35,
        "facteur_cuda": 0.10,
    },
    "rapide": {
        "cle": "rapide",
        "modele": MODELE_TURBO,
        "beam_size": 5,
        "best_of": 5,
        "temperature": 0.0,
        "vad": True,
        "diarisation_defaut": False,
        "telechargement_go": 1.6,
        "memoire_go": 2.0,
        "facteur_cpu": 0.35,
        "facteur_cuda": 0.05,
    },
}

PRESET_DEFAUT = "qualite"

# Modèles accessibles en mode avancé, du plus léger au plus lourd.
#
# La taille est donnee en gigaoctets ou en megaoctets bruts : elle est mise en
# forme dans la langue courante par `modeles_avances()`. La qualite est une cle
# de traduction, pas un libelle.
MODELES_AVANCES: list[dict] = [
    {"cle": "tiny", "nom": "tiny", "octets": 75 * 1024 ** 2, "facteur_cpu": 0.06,
     "qualite_cle": "modele.qualite.depannage"},
    {"cle": "base", "nom": "base", "octets": 145 * 1024 ** 2, "facteur_cpu": 0.10,
     "qualite_cle": "modele.qualite.faible"},
    {"cle": "small", "nom": "small", "octets": 480 * 1024 ** 2, "facteur_cpu": 0.25,
     "qualite_cle": "modele.qualite.correcte"},
    {"cle": "medium", "nom": "medium", "octets": int(1.5 * 1024 ** 3), "facteur_cpu": 0.65,
     "qualite_cle": "modele.qualite.bonne"},
    {"cle": "large-v2", "nom": "large-v2", "octets": int(3.1 * 1024 ** 3), "facteur_cpu": 1.30,
     "qualite_cle": "modele.qualite.tres_bonne"},
    {"cle": "large-v3", "nom": "large-v3", "octets": int(3.1 * 1024 ** 3), "facteur_cpu": 1.35,
     "qualite_cle": "modele.qualite.excellente"},
    {"cle": MODELE_TURBO, "nom": "large-v3-turbo", "octets": int(1.6 * 1024 ** 3),
     "facteur_cpu": 0.35, "qualite_cle": "modele.qualite.tres_bonne"},
]

# Surcoût de la diarisation, exprimé en facteur temps réel.
FACTEUR_DIARISATION_CPU = 0.20
FACTEUR_DIARISATION_CUDA = 0.05

# Machine repère servant de base aux facteurs ci-dessus.
FILS_REFERENCE = 12


def preset(cle: str) -> dict:
    return PRESETS.get(cle, PRESETS[PRESET_DEFAUT])


def nom_preset(cle: str) -> str:
    """Nom affiché du preset, dans la langue de l'interface."""
    return langues.t(f"preset.{preset(cle)['cle']}.nom")


def resume_preset(cle: str) -> str:
    return langues.t(f"preset.{preset(cle)['cle']}.resume")


def modeles_avances() -> list[dict]:
    """Modèles du mode avancé, tailles et qualités mises en forme pour l'interface."""
    return [
        {
            "cle": m["cle"],
            "nom": m["nom"],
            "taille": langues.octets(m["octets"]),
            "qualite": langues.t(m["qualite_cle"]),
        }
        for m in MODELES_AVANCES
    ]


def taille_modele_avance(cle: str) -> str:
    for m in MODELES_AVANCES:
        if m["cle"] == cle:
            return langues.octets(m["octets"])
    return ""


def modele_du_preset(cle: str, modele_avance: str = "") -> str:
    if modele_avance:
        return modele_avance
    return preset(cle)["modele"]


def _facteur_modele(modele: str, sur_gpu: bool) -> float:
    for p in PRESETS.values():
        if p["modele"] == modele:
            return p["facteur_cuda"] if sur_gpu else p["facteur_cpu"]
    for m in MODELES_AVANCES:
        if m["cle"] == modele:
            base = m["facteur_cpu"]
            return base * 0.09 if sur_gpu else base
    return 1.0 if not sur_gpu else 0.10


def _coefficient_machine(mat: Materiel) -> float:
    """
    Ajuste le facteur de référence au nombre de fils réellement disponibles.

    L'accélération n'est pas linéaire avec le nombre de cœurs : on applique un
    exposant 0,6 et on borne le résultat pour rester honnête dans les deux sens.
    """
    fils = max(2, mat.fils_calcul + 2)
    coefficient = (FILS_REFERENCE / fils) ** 0.6
    return min(2.5, max(0.35, coefficient))


def facteur_temps_reel(cle_preset: str, mat: Materiel, diarisation: bool = False,
                       modele_avance: str = "") -> float:
    """Renvoie le rapport estimé « durée de calcul / durée de l'audio »."""
    modele = modele_du_preset(cle_preset, modele_avance)
    sur_gpu = mat.cuda_disponible
    facteur = _facteur_modele(modele, sur_gpu)
    if not sur_gpu:
        facteur *= _coefficient_machine(mat)
    if diarisation:
        facteur += FACTEUR_DIARISATION_CUDA if sur_gpu else FACTEUR_DIARISATION_CPU * _coefficient_machine(mat)
    return round(facteur, 3)


def estimer_secondes(duree_audio: float, cle_preset: str, mat: Materiel,
                     diarisation: bool = False, modele_avance: str = "") -> float:
    if not duree_audio:
        return 0.0
    return duree_audio * facteur_temps_reel(cle_preset, mat, diarisation, modele_avance)


def nombre_fr(valeur: float, decimales: int = 1) -> str:
    """Nombre décimal au séparateur de la langue d'interface courante."""
    return langues.nombre(valeur, decimales)


def formater_duree(secondes: float | None) -> str:
    if not secondes or secondes <= 0:
        return langues.t("duree.vide")
    secondes = int(secondes)
    heures, reste = divmod(secondes, 3600)
    minutes, sec = divmod(reste, 60)
    if heures:
        return langues.t("duree.heures", h=heures, m=f"{minutes:02d}")
    if minutes:
        return langues.t("duree.minutes", m=minutes, s=f"{sec:02d}")
    return langues.t("duree.secondes", s=sec)


def recommandation(mat: Materiel) -> dict:
    """
    Preset conseillé pour cette machine, avec la phrase à afficher.

    Règle : la qualité par défaut, sauf si la mémoire est trop juste pour
    large-v3, auquel cas on bascule sur le preset rapide et on le dit.
    """
    duree_reference = 3600  # une réunion d'une heure

    qualite = estimer_secondes(duree_reference, "qualite", mat)
    rapide = estimer_secondes(duree_reference, "rapide", mat)

    if mat.memoire_tres_serree:
        conseille = "rapide"
        phrase = langues.t("reco.memoire_juste", ram=f"{mat.ram_go:.0f}")
    elif mat.cuda_disponible:
        conseille = "qualite"
        phrase = langues.t("reco.cuda")
    else:
        conseille = "qualite"
        phrase = langues.t("reco.processeur")

    return {
        "preset_conseille": conseille,
        "phrase": phrase,
        "estimations": [
            {
                "preset": "qualite",
                "nom": nom_preset("qualite"),
                "facteur": facteur_temps_reel("qualite", mat),
                "pour_une_heure": formater_duree(qualite),
            },
            {
                "preset": "rapide",
                "nom": nom_preset("rapide"),
                "facteur": facteur_temps_reel("rapide", mat),
                "pour_une_heure": formater_duree(rapide),
            },
        ],
    }


def avertissements(cle_preset: str, mat: Materiel, diarisation: bool,
                   modele_avance: str = "") -> list[str]:
    """Garde-fous affichés avant de lancer la file. Liste vide si tout va bien."""
    messages: list[str] = []
    modele = modele_du_preset(cle_preset, modele_avance)
    lourd = modele in ("large-v3", "large-v2")

    if lourd and mat.memoire_tres_serree:
        messages.append(langues.t("avert.memoire_tres_serree", ram=f"{mat.ram_go:.0f}"))
    elif lourd and mat.memoire_serree and diarisation:
        messages.append(langues.t("avert.memoire_serree_diar", ram=f"{mat.ram_go:.0f}"))

    if diarisation and mat.ram_libre_go and mat.ram_libre_go < 4:
        messages.append(langues.t("avert.ram_libre", go=nombre_fr(mat.ram_libre_go)))

    if not mat.cuda_disponible:
        amd = [g for g in mat.gpus if g.vendeur == "amd"]
        if amd:
            messages.append(langues.t("avert.amd", carte=amd[0].nom))

    return messages
