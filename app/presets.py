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

from .materiel import Materiel, SEUIL_MEMOIRE_CRITIQUE

# Modèle turbo : on nomme le dépôt converti explicitement plutôt que l'alias
# « turbo », qui dépend de la version de faster-whisper installée.
MODELE_TURBO = "deepdml/faster-whisper-large-v3-turbo-ct2"

PRESETS: dict[str, dict] = {
    "qualite": {
        "cle": "qualite",
        "nom": "Qualité maximale",
        "resume": "Le meilleur texte possible. Pour les réunions et tout ce qui sera relu.",
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
        "nom": "Rapide",
        "resume": "Environ quatre fois plus rapide, qualité un cran en dessous.",
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
MODELES_AVANCES: list[dict] = [
    {"cle": "tiny", "nom": "tiny", "taille": "75 Mo", "facteur_cpu": 0.06, "qualite": "Dépannage"},
    {"cle": "base", "nom": "base", "taille": "145 Mo", "facteur_cpu": 0.10, "qualite": "Faible"},
    {"cle": "small", "nom": "small", "taille": "480 Mo", "facteur_cpu": 0.25, "qualite": "Correcte"},
    {"cle": "medium", "nom": "medium", "taille": "1,5 Go", "facteur_cpu": 0.65, "qualite": "Bonne"},
    {"cle": "large-v2", "nom": "large-v2", "taille": "3,1 Go", "facteur_cpu": 1.30, "qualite": "Très bonne"},
    {"cle": "large-v3", "nom": "large-v3", "taille": "3,1 Go", "facteur_cpu": 1.35, "qualite": "Excellente"},
    {"cle": MODELE_TURBO, "nom": "large-v3-turbo", "taille": "1,6 Go", "facteur_cpu": 0.35, "qualite": "Très bonne"},
]

# Surcoût de la diarisation, exprimé en facteur temps réel.
FACTEUR_DIARISATION_CPU = 0.20
FACTEUR_DIARISATION_CUDA = 0.05

# Machine repère servant de base aux facteurs ci-dessus.
FILS_REFERENCE = 12


def preset(cle: str) -> dict:
    return PRESETS.get(cle, PRESETS[PRESET_DEFAUT])


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
    """Nombre décimal à la française : la virgule, pas le point."""
    return f"{valeur:.{decimales}f}".replace(".", ",")


def formater_duree(secondes: float | None) -> str:
    if not secondes or secondes <= 0:
        return "--"
    secondes = int(secondes)
    heures, reste = divmod(secondes, 3600)
    minutes, sec = divmod(reste, 60)
    if heures:
        return f"{heures} h {minutes:02d}"
    if minutes:
        return f"{minutes} min {sec:02d}"
    return f"{sec} s"


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
        phrase = (
            f"Mémoire vive détectée : {mat.ram_go:.0f} Go. C'est trop juste pour "
            "large-v3, le preset « Rapide » est conseillé."
        )
    elif mat.cuda_disponible:
        conseille = "qualite"
        phrase = (
            "Carte NVIDIA exploitée : le preset « Qualité maximale » passe largement "
            "plus vite que le temps réel."
        )
    else:
        conseille = "qualite"
        phrase = (
            "Transcription sur processeur : le preset « Qualité maximale » est le bon "
            "choix pour les réunions, il suffit de le lancer et de laisser tourner."
        )

    return {
        "preset_conseille": conseille,
        "phrase": phrase,
        "estimations": [
            {
                "preset": "qualite",
                "nom": PRESETS["qualite"]["nom"],
                "facteur": facteur_temps_reel("qualite", mat),
                "pour_une_heure": formater_duree(qualite),
            },
            {
                "preset": "rapide",
                "nom": PRESETS["rapide"]["nom"],
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
        messages.append(
            f"Cette machine annonce {mat.ram_go:.0f} Go de mémoire vive. Le modèle "
            "large-v3 risque de saturer : préférez le preset « Rapide »."
        )
    elif lourd and mat.memoire_serree and diarisation:
        messages.append(
            f"Mémoire vive : {mat.ram_go:.0f} Go. La combinaison large-v3 plus "
            "séparation des locuteurs tient, parce que les deux étapes sont "
            "enchaînées et jamais chargées en même temps. Fermez tout de même les "
            "applications lourdes avant de lancer une longue réunion."
        )

    if diarisation and mat.ram_libre_go and mat.ram_libre_go < 4:
        messages.append(
            f"Il ne reste qu'environ {nombre_fr(mat.ram_libre_go)} Go de mémoire libre. "
            "Fermez quelques applications avant de lancer la file."
        )

    if not mat.cuda_disponible:
        amd = [g for g in mat.gpus if g.vendeur == "amd"]
        if amd:
            messages.append(
                f"{amd[0].nom} détectée mais non utilisée : en v1, seul le processeur "
                "travaille sur les cartes non NVIDIA."
            )

    return messages
