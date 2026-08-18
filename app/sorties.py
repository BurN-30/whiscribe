"""
Écriture des fichiers de sortie : texte, SRT, VTT.

Le fichier texte porte un en-tête court et lisible (source, durée, modèle,
date) : quand on retrouve une transcription six mois plus tard, on sait tout de
suite d'où elle vient et avec quels réglages elle a été produite.

CHOIX DOCUMENTÉ : l'en-tête suit la LANGUE DE L'INTERFACE au moment où le
fichier est produit. Un fichier écrit n'est jamais réécrit, donc une bascule de
langue ne retouche pas les transcriptions déjà faites, et la vue de lecture sait
relire les en-têtes des deux langues (voir `app/lecture.py`).
"""

from __future__ import annotations

from datetime import datetime
from pathlib import Path

from . import journal, langues


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
    return langues.nombre(valeur, decimales)


def _duree_lisible(secondes: float) -> str:
    secondes = int(secondes or 0)
    heures, reste = divmod(secondes, 3600)
    minutes, sec = divmod(reste, 60)
    if heures:
        return langues.t("duree_longue.heures", h=heures, m=f"{minutes:02d}")
    return langues.t("duree_longue.minutes", m=minutes, s=f"{sec:02d}")


def nom_de_base(source: Path, horodater: bool = True, motif: str = "",
                modele: str = "") -> str:
    """
    Nom de base des sorties, sans extension.

    Sans motif, on retrouve exactement le nommage historique :
    « 2026-08-17-reunion-equipe » à partir de « reunion equipe.m4a ». Le motif
    configurable et ses variables sont décrits dans `app/nommage.py`.
    """
    from . import nommage

    if motif and str(motif).strip():
        return nommage.construire(motif, source, modele)
    propre = nommage.nettoyer_nom(source.stem)
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
    """
    En-tête encadré du fichier texte, dans la langue de l'interface.

    Les étiquettes sont alignées sur la plus longue de la langue courante, ce
    qui évite d'avoir à recompter les espaces à chaque traduction.
    """
    entrees: list[tuple[str, str]] = [
        (langues.t("ent.source"), str(source)),
        (langues.t("ent.duree"), _duree_lisible(details.get("duree", 0))),
        (langues.t("ent.modele"), langues.t(
            "ent.valeur.modele",
            modele=details.get("modele_lisible", details.get("modele", "?")),
            preset=details.get("preset_nom") or langues.t("ent.reglages_personnalises"),
        )),
        (langues.t("ent.calcul"),
         f"{details.get('peripherique', 'cpu')} / {details.get('type_calcul', 'int8')}"),
        (langues.t("ent.langue"), str(details.get("langue", "?"))),
    ]
    if details.get("nb_locuteurs"):
        entrees.append((langues.t("ent.locuteurs"),
                        langues.t("ent.valeur.locuteurs", n=details["nb_locuteurs"])))
    elif details.get("diarisation_demandee"):
        entrees.append((langues.t("ent.locuteurs"), langues.t("ent.valeur.non_separes")))
    if details.get("corrections_appliquees"):
        entrees.append((langues.t("ent.corrections"), langues.t(
            "ent.valeur.corrections", n=details["corrections_appliquees"])))
    if details.get("termes_amorce"):
        entrees.append((langues.t("ent.glossaire"), langues.t(
            "ent.valeur.glossaire", n=details["termes_amorce"])))
    entrees.append((langues.t("ent.transcrit_le"),
                    datetime.now().strftime(langues.t("format.date_heure"))))
    entrees.append((langues.t("ent.temps_calcul"), langues.t(
        "ent.valeur.temps_calcul",
        duree=_duree_lisible(details.get("temps_calcul", 0)),
        facteur=_nombre_fr(details.get("facteur_reel", 0)),
    )))

    largeur = max(len(etiquette) for etiquette, _ in entrees)
    lignes = [
        "=" * 68,
        langues.t("ent.titre", nom=source.name),
        "=" * 68,
    ]
    lignes += [f"{etiquette:<{largeur}} : {valeur}" for etiquette, valeur in entrees]
    lignes += [
        langues.t("ent.mention_locale"),
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
        return langues.t("sortie.aucune_parole") + "\n"

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


def ecrire_tout(dossier: Path, source: Path, segments, details: dict, formats: dict,
                avec_compagnon: bool = True, motif: str = "") -> list[dict]:
    """
    Écrit les formats demandés et renvoie la liste des fichiers produits.

    Le fichier compagnon `.json`, qui porte la confiance mot à mot pour la vue
    de lecture, accompagne le `.txt` quand l'option est active. Il n'apparaît
    pas dans la liste des sorties : ce n'est pas un livrable, c'est un annexe
    que l'application relit pour elle-même.
    """
    dossier.mkdir(parents=True, exist_ok=True)
    base = nom_de_base(
        source, motif=motif,
        modele=str(details.get("modele_lisible") or details.get("modele") or ""),
    )
    avec_locuteurs = bool(details.get("nb_locuteurs"))
    produits: list[dict] = []

    if formats.get("txt", True):
        chemin = chemin_libre(dossier, base, ".txt")
        entete = construire_entete(source, details)
        corps = corps_texte(segments, avec_locuteurs, formats.get("horodatage", False))
        ecrire_txt(chemin, entete, corps)
        produits.append({"format": "TXT", "nom": chemin.name, "chemin": str(chemin)})
        if avec_compagnon:
            from . import compagnon

            compagnon.ecrire(chemin, source, segments, details)

    if formats.get("srt"):
        chemin = chemin_libre(dossier, base, ".srt")
        ecrire_srt(chemin, segments, avec_locuteurs)
        produits.append({"format": "SRT", "nom": chemin.name, "chemin": str(chemin)})

    if formats.get("vtt"):
        chemin = chemin_libre(dossier, base, ".vtt")
        ecrire_vtt(chemin, segments, avec_locuteurs)
        produits.append({"format": "VTT", "nom": chemin.name, "chemin": str(chemin)})

    return produits
