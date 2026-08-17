"""
Écriture des fichiers de sortie : texte, SRT, VTT.

Le fichier texte porte un en-tête court et lisible (source, durée, modèle,
date) : quand on retrouve une transcription six mois plus tard, on sait tout de
suite d'où elle vient et avec quels réglages elle a été produite.
"""

from __future__ import annotations

from datetime import datetime
from pathlib import Path

from . import journal


def _horodatage_srt(secondes: float) -> str:
    secondes = max(0.0, secondes)
    heures, reste = divmod(int(secondes), 3600)
    minutes, sec = divmod(reste, 60)
    millisecondes = int(round((secondes - int(secondes)) * 1000))
    if millisecondes >= 1000:
        millisecondes, sec = 0, sec + 1
    return f"{heures:02d}:{minutes:02d}:{sec:02d},{millisecondes:03d}"


def _horodatage_vtt(secondes: float) -> str:
    return _horodatage_srt(secondes).replace(",", ".")


def _nombre_fr(valeur: float, decimales: int = 2) -> str:
    return f"{valeur:.{decimales}f}".replace(".", ",")


def _duree_lisible(secondes: float) -> str:
    secondes = int(secondes or 0)
    heures, reste = divmod(secondes, 3600)
    minutes, sec = divmod(reste, 60)
    if heures:
        return f"{heures} h {minutes:02d} min"
    return f"{minutes} min {sec:02d} s"


def nom_de_base(source: Path, horodater: bool = True) -> str:
    """« 2026-08-17-reunion-equipe » à partir de « reunion equipe.m4a »."""
    racine = source.stem.strip()
    propre = "".join(c if c.isalnum() or c in " -_." else "-" for c in racine)
    propre = "-".join(filter(None, propre.replace("_", "-").replace(" ", "-").split("-")))
    propre = propre.lower()[:80] or "transcription"
    if horodater:
        return f"{datetime.now():%Y-%m-%d}-{propre}"
    return propre


def chemin_libre(dossier: Path, base: str, extension: str) -> Path:
    """Évite d'écraser un fichier existant en suffixant -2, -3, etc."""
    candidat = dossier / f"{base}{extension}"
    compteur = 2
    while candidat.exists():
        candidat = dossier / f"{base}-{compteur}{extension}"
        compteur += 1
    return candidat


def construire_entete(source: Path, details: dict) -> str:
    lignes = [
        "=" * 68,
        f"Transcription : {source.name}",
        "=" * 68,
        f"Source            : {source}",
        f"Durée de l'audio  : {_duree_lisible(details.get('duree', 0))}",
        f"Modèle            : {details.get('modele_lisible', details.get('modele', '?'))}"
        f"  ({details.get('preset_nom', 'réglages personnalisés')})",
        f"Calcul            : {details.get('peripherique', 'cpu')} / {details.get('type_calcul', 'int8')}",
        f"Langue            : {details.get('langue', '?')}",
    ]
    if details.get("nb_locuteurs"):
        lignes.append(f"Locuteurs         : {details['nb_locuteurs']} détectés")
    elif details.get("diarisation_demandee"):
        lignes.append("Locuteurs         : non séparés (voir le journal)")
    if details.get("corrections_appliquees"):
        lignes.append(f"Corrections       : {details['corrections_appliquees']} remplacements automatiques")
    if details.get("termes_amorce"):
        lignes.append(f"Glossaire         : {details['termes_amorce']} termes envoyés au modèle")
    lignes += [
        f"Transcrit le      : {datetime.now():%d/%m/%Y à %H:%M}",
        f"Temps de calcul   : {_duree_lisible(details.get('temps_calcul', 0))}"
        f"  (facteur {_nombre_fr(details.get('facteur_reel', 0))} x temps réel)",
        "Produit localement, aucune donnée n'a quitté cette machine.",
        "=" * 68,
        "",
    ]
    return "\n".join(lignes)


def corps_texte(segments, avec_locuteurs: bool, avec_horodatage: bool = False) -> str:
    """
    Texte lisible. Les répliques consécutives d'un même locuteur sont regroupées,
    ce qui donne un rendu de compte rendu plutôt qu'une liste de sous-titres.
    """
    if not segments:
        return "(aucune parole détectée dans cet enregistrement)\n"

    blocs: list[str] = []
    locuteur_courant = None
    tampon: list[str] = []
    debut_bloc = segments[0].debut

    def vider():
        if not tampon:
            return
        texte = " ".join(tampon).strip()
        prefixe = ""
        if avec_horodatage:
            prefixe += f"[{_horodatage_vtt(debut_bloc)[:-4]}] "
        if avec_locuteurs and locuteur_courant:
            prefixe += f"{locuteur_courant} : "
        blocs.append(prefixe + texte)

    for segment in segments:
        etiquette = segment.locuteur if avec_locuteurs else None
        if etiquette != locuteur_courant and tampon:
            vider()
            tampon = []
            debut_bloc = segment.debut
        locuteur_courant = etiquette
        tampon.append(segment.texte)

    vider()
    return "\n\n".join(blocs) + "\n"


def ecrire_txt(chemin: Path, entete: str, corps: str) -> Path:
    chemin.write_text(entete + corps, encoding="utf-8")
    journal.info("Écrit : %s", chemin)
    return chemin


def ecrire_srt(chemin: Path, segments, avec_locuteurs: bool) -> Path:
    lignes: list[str] = []
    for index, segment in enumerate(segments, start=1):
        texte = segment.texte
        if avec_locuteurs and segment.locuteur:
            texte = f"{segment.locuteur} : {texte}"
        lignes.append(str(index))
        lignes.append(f"{_horodatage_srt(segment.debut)} --> {_horodatage_srt(segment.fin)}")
        lignes.append(texte)
        lignes.append("")
    chemin.write_text("\n".join(lignes), encoding="utf-8")
    journal.info("Écrit : %s", chemin)
    return chemin


def ecrire_vtt(chemin: Path, segments, avec_locuteurs: bool) -> Path:
    lignes = ["WEBVTT", ""]
    for segment in segments:
        texte = segment.texte
        if avec_locuteurs and segment.locuteur:
            texte = f"<v {segment.locuteur}>{texte}"
        lignes.append(f"{_horodatage_vtt(segment.debut)} --> {_horodatage_vtt(segment.fin)}")
        lignes.append(texte)
        lignes.append("")
    chemin.write_text("\n".join(lignes), encoding="utf-8")
    journal.info("Écrit : %s", chemin)
    return chemin


def ecrire_tout(dossier: Path, source: Path, segments, details: dict, formats: dict) -> list[dict]:
    """Écrit les formats demandés et renvoie la liste des fichiers produits."""
    dossier.mkdir(parents=True, exist_ok=True)
    base = nom_de_base(source)
    avec_locuteurs = bool(details.get("nb_locuteurs"))
    produits: list[dict] = []

    if formats.get("txt", True):
        chemin = chemin_libre(dossier, base, ".txt")
        entete = construire_entete(source, details)
        corps = corps_texte(segments, avec_locuteurs, formats.get("horodatage", False))
        ecrire_txt(chemin, entete, corps)
        produits.append({"format": "TXT", "nom": chemin.name, "chemin": str(chemin)})

    if formats.get("srt"):
        chemin = chemin_libre(dossier, base, ".srt")
        ecrire_srt(chemin, segments, avec_locuteurs)
        produits.append({"format": "SRT", "nom": chemin.name, "chemin": str(chemin)})

    if formats.get("vtt"):
        chemin = chemin_libre(dossier, base, ".vtt")
        ecrire_vtt(chemin, segments, avec_locuteurs)
        produits.append({"format": "VTT", "nom": chemin.name, "chemin": str(chemin)})

    return produits
