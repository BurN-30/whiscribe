"""
Import et export des données personnelles, par fichier zip.

Le besoin : emporter son glossaire professionnel d'un poste à l'autre, ou le
sauvegarder, sans passer par un dépôt Git. Un dépôt privé rendrait le service,
mais il faut un compte, un client, une convention de branches, et surtout le
glossaire d'une entreprise n'a rien à faire en ligne. Un fichier suffit.

Ce qui part dans l'archive :

  - `vocabulaire.txt`  : le glossaire ;
  - `corrections.txt`  : la table de corrections ;
  - `config.json`      : les réglages ;
  - `manifeste.json`   : version de l'application, date, liste des fichiers.

Ce qui n'y va JAMAIS :

  - `jeton_hf.txt`, le jeton Hugging Face. C'est un secret personnel, il ne
    doit pas se promener dans une pièce jointe ni dans un partage réseau ;
  - les modèles, plusieurs gigaoctets qui se retéléchargent tout seuls ;
  - les journaux, qui ne décrivent que la machine où ils ont été écrits.

À l'import, rien n'est écrit avant que l'utilisateur ait vu l'aperçu et
confirmé, et l'état courant est systématiquement sauvegardé d'abord.
"""

from __future__ import annotations

import json
import os
import zipfile
from datetime import datetime
from pathlib import Path

from . import VERSION, NOM_APPLICATION, chemins, journal, vocabulaire

NOM_MANIFESTE = "manifeste.json"

#: Version du format d'archive. Un export produit par une version future de
#: l'application sera refusé plutôt que mal interprété.
FORMAT_ARCHIVE = 1

#: Les seuls membres acceptés dans une archive. Tout le reste la fait rejeter.
FICHIERS_TEXTE = ("vocabulaire.txt", "corrections.txt")
FICHIER_CONFIG = "config.json"
MEMBRES_AUTORISES = (NOM_MANIFESTE, FICHIER_CONFIG, *FICHIERS_TEXTE)

#: Bornes de sécurité. Ces fichiers pèsent quelques kilooctets : au-delà de ces
#: seuils, on a affaire à autre chose qu'un export WhiScribe.
TAILLE_MAX_ARCHIVE = 8 * 1024 * 1024
TAILLE_MAX_MEMBRE = 2 * 1024 * 1024
TAILLE_MAX_TOTALE = 8 * 1024 * 1024

#: Libellés des réglages, pour l'aperçu affiché avant écriture.
LIBELLES_REGLAGES = {
    "preset": "Qualité de transcription",
    "langue": "Langue parlée",
    "dossier_sortie": "Dossier de sortie",
    "diarisation": "Séparer les locuteurs",
    "nb_locuteurs": "Nombre de participants",
    "formats": "Formats produits",
    "appliquer_corrections": "Appliquer les corrections",
    "utiliser_glossaire": "Souffler le glossaire au modèle",
    "filtres_salle": "Audio de salle",
    "mode_avance": "Mode avancé",
    "modele_avance": "Modèle du mode avancé",
    "beam_size": "Largeur de faisceau",
    "condition_on_previous_text": "Garder le contexte",
    "forcer_processeur": "Forcer le processeur",
    "theme": "Thème",
    "zoom": "Zoom de l'interface",
    "journal_ouvert": "Journal déplié",
}

#: Réglages dont l'aperçu ne parle pas : ils changent à chaque clic et ne
#: renseignent personne sur ce qu'un import va vraiment modifier.
REGLAGES_DISCRETS = ("zoom", "journal_ouvert")


# ---------------------------------------------------------------------------
# Petits utilitaires
# ---------------------------------------------------------------------------

class ErreurArchive(Exception):
    """Refus d'une archive, déjà formulé en français."""


def _horodatage_jour() -> str:
    return f"{datetime.now():%Y-%m-%d}"


def _horodatage_seconde() -> str:
    return f"{datetime.now():%Y-%m-%d-%H%M%S}"


def nom_export_propose() -> str:
    """Nom de fichier proposé dans la boîte d'enregistrement."""
    return f"whiscribe-donnees-{_horodatage_jour()}.zip"


def nom_sauvegarde_avant_import() -> str:
    return f"whiscribe-donnees-avant-import-{_horodatage_seconde()}.zip"


def _lire_texte(fichier: Path) -> str:
    try:
        return fichier.read_text(encoding="utf-8")
    except FileNotFoundError:
        return ""
    except (OSError, UnicodeDecodeError) as exc:
        journal.attention("Lecture impossible de %s : %s", fichier, exc)
        return ""


def _ecrire_atomique(fichier: Path, contenu: str) -> None:
    """
    Écrit par un fichier temporaire puis remplace.

    Une coupure de courant au mauvais moment laisserait sinon un glossaire
    tronqué, c'est-à-dire pire que pas de glossaire du tout.
    """
    fichier.parent.mkdir(parents=True, exist_ok=True)
    provisoire = fichier.with_suffix(fichier.suffix + ".tmp-import")
    provisoire.write_text(contenu, encoding="utf-8")
    os.replace(str(provisoire), str(fichier))


def _config_courante() -> dict:
    from . import config as config_module

    return config_module.charger()


def _cles_config() -> tuple[str, ...]:
    from . import config as config_module

    return tuple(config_module.DEFAUTS.keys())


def _formater_valeur(cle: str, valeur) -> str:
    if isinstance(valeur, bool):
        return "oui" if valeur else "non"
    if cle == "formats" and isinstance(valeur, dict):
        actifs = [nom for nom, actif in valeur.items() if actif]
        return ", ".join(actifs) if actifs else "aucun"
    if cle == "nb_locuteurs" and not valeur:
        return "détection automatique"
    if cle in ("beam_size", "modele_avance") and not valeur:
        return "valeur du preset"
    if isinstance(valeur, float):
        return f"{valeur:.2f}".replace(".", ",")
    texte = str(valeur)
    return texte if texte else "vide"


# ---------------------------------------------------------------------------
# Export
# ---------------------------------------------------------------------------

def _contenu_a_exporter() -> tuple[dict, dict]:
    """Renvoie (fichiers du zip, manifeste) pour l'état courant."""
    fichiers = {
        "vocabulaire.txt": _lire_texte(chemins.FICHIER_VOCABULAIRE),
        "corrections.txt": _lire_texte(chemins.FICHIER_CORRECTIONS),
        FICHIER_CONFIG: json.dumps(_config_courante(), indent=2, ensure_ascii=False) + "\n",
    }
    manifeste = {
        "application": NOM_APPLICATION,
        "format": FORMAT_ARCHIVE,
        "version": VERSION,
        "date": datetime.now().isoformat(timespec="seconds"),
        "fichiers": sorted(fichiers.keys()),
        # Informatif : le dossier des modèles ne vit pas dans config.json, il est
        # partagé avec le programme d'installation. Il n'est repris à l'import
        # que s'il existe sur le poste d'arrivée.
        "dossier_modeles": str(chemins.DOSSIER_MODELES),
        "exclus": ["jeton_hf.txt", "logs", "modeles"],
    }
    return fichiers, manifeste


def exporter(destination: str | Path) -> dict:
    """
    Écrit l'archive d'export à l'emplacement demandé.

    Renvoie un dictionnaire `{ok, message, chemin, fichiers}`. Aucun écrasement
    n'a lieu ici sans que la boîte d'enregistrement de Windows n'ait déjà posé
    la question : c'est elle qui gère la confirmation de remplacement.
    """
    cible = Path(str(destination or "")).expanduser()
    if not cible.name:
        return {"ok": False, "message": "Aucun emplacement d'enregistrement choisi."}
    if cible.suffix.lower() != ".zip":
        cible = cible.with_suffix(".zip")

    fichiers, manifeste = _contenu_a_exporter()
    provisoire = cible.with_name(cible.name + ".tmp-export")

    try:
        cible.parent.mkdir(parents=True, exist_ok=True)
        with zipfile.ZipFile(provisoire, "w", zipfile.ZIP_DEFLATED) as archive:
            archive.writestr(
                NOM_MANIFESTE, json.dumps(manifeste, indent=2, ensure_ascii=False) + "\n"
            )
            for nom, contenu in fichiers.items():
                archive.writestr(nom, contenu)
        os.replace(str(provisoire), str(cible))
    except OSError as exc:
        try:
            provisoire.unlink(missing_ok=True)
        except OSError:
            pass
        titre, message = journal.expliquer(exc, "export des données")
        journal.exception("Export des données en échec", exc)
        return {"ok": False, "message": f"{titre} : {message}"}

    resume = vocabulaire.termes(fichiers["vocabulaire.txt"])
    regles, _ = vocabulaire.analyser_corrections(fichiers["corrections.txt"])
    journal.info(
        "Export des données vers %s (%s termes, %s règles)", cible, len(resume), len(regles)
    )
    return {
        "ok": True,
        "chemin": str(cible),
        "fichiers": manifeste["fichiers"],
        "message": (
            f"{len(resume)} terme(s) de glossaire, {len(regles)} règle(s) de correction et "
            f"vos réglages ont été enregistrés dans « {cible} ». Le jeton Hugging Face, "
            "les journaux et les modèles n'y sont pas."
        ),
    }


# ---------------------------------------------------------------------------
# Lecture et validation d'une archive
# ---------------------------------------------------------------------------

def _verifier_nom_membre(nom: str) -> None:
    """Refuse tout ce qui ressemble à une sortie de l'archive."""
    if nom not in MEMBRES_AUTORISES:
        raise ErreurArchive(
            f"L'archive contient un élément inattendu (« {nom} »). Ce n'est pas un "
            "export WhiScribe, ou il a été modifié."
        )
    if nom.endswith("/") or "\\" in nom or ".." in Path(nom).parts or Path(nom).is_absolute():
        raise ErreurArchive("L'archive contient un chemin de fichier invalide, elle est refusée.")


def _ouvrir_archive(chemin: str | Path) -> tuple[dict, dict]:
    """
    Ouvre, valide et lit une archive. Renvoie (membres décodés, manifeste).

    Lève `ErreurArchive` avec un message déjà rédigé pour l'utilisateur.
    """
    source = Path(str(chemin or "")).expanduser()
    if not source.is_file():
        raise ErreurArchive("Ce fichier n'existe plus, ou n'est pas lisible.")

    try:
        taille = source.stat().st_size
    except OSError as exc:
        raise ErreurArchive(f"Ce fichier n'a pas pu être lu ({exc.strerror or exc}).") from exc

    if taille == 0:
        raise ErreurArchive("Ce fichier est vide.")
    if taille > TAILLE_MAX_ARCHIVE:
        raise ErreurArchive(
            "Ce fichier est bien trop gros pour un export WhiScribe "
            f"({taille / 1024 / 1024:.1f} Mo). Un export pèse quelques kilooctets."
        )
    if not zipfile.is_zipfile(str(source)):
        raise ErreurArchive(
            "Ce fichier n'est pas une archive zip lisible. Il est peut-être abîmé, "
            "ou ce n'est pas le bon fichier."
        )

    membres: dict[str, str] = {}
    try:
        with zipfile.ZipFile(str(source)) as archive:
            abime = archive.testzip()
            if abime:
                raise ErreurArchive(
                    f"L'archive est abîmée : le fichier « {abime} » qu'elle contient est illisible."
                )

            infos = archive.infolist()
            if not infos:
                raise ErreurArchive("Cette archive est vide.")

            total = 0
            for info in infos:
                _verifier_nom_membre(info.filename)
                if info.file_size > TAILLE_MAX_MEMBRE:
                    raise ErreurArchive(
                        f"Le fichier « {info.filename} » de l'archive est anormalement gros, "
                        "l'import est refusé."
                    )
                total += info.file_size
            if total > TAILLE_MAX_TOTALE:
                raise ErreurArchive(
                    "Le contenu de cette archive est anormalement volumineux, l'import est refusé."
                )

            for info in infos:
                brut = archive.read(info.filename)
                try:
                    membres[info.filename] = brut.decode("utf-8")
                except UnicodeDecodeError as exc:
                    raise ErreurArchive(
                        f"Le fichier « {info.filename} » de l'archive n'est pas du texte "
                        "lisible (encodage attendu : UTF-8)."
                    ) from exc
    except zipfile.BadZipFile as exc:
        raise ErreurArchive(
            "Cette archive zip est corrompue et n'a pas pu être ouverte."
        ) from exc
    except OSError as exc:
        raise ErreurArchive(f"Ce fichier n'a pas pu être lu ({exc.strerror or exc}).") from exc

    if NOM_MANIFESTE not in membres:
        raise ErreurArchive(
            "Ce fichier n'est pas un export WhiScribe : son manifeste est absent."
        )

    try:
        manifeste = json.loads(membres[NOM_MANIFESTE])
    except json.JSONDecodeError as exc:
        raise ErreurArchive("Le manifeste de cette archive est illisible.") from exc
    if not isinstance(manifeste, dict):
        raise ErreurArchive("Le manifeste de cette archive n'a pas la forme attendue.")
    if str(manifeste.get("application", "")).strip().lower() != NOM_APPLICATION.lower():
        raise ErreurArchive(
            "Ce fichier n'est pas un export WhiScribe : son manifeste annonce "
            f"« {manifeste.get('application') or 'application inconnue'} »."
        )

    try:
        format_archive = int(manifeste.get("format", 0))
    except (TypeError, ValueError):
        format_archive = 0
    if format_archive < 1:
        raise ErreurArchive("Le manifeste de cette archive n'indique pas de format valide.")
    if format_archive > FORMAT_ARCHIVE:
        raise ErreurArchive(
            f"Cet export a été produit par une version plus récente de {NOM_APPLICATION} "
            f"(format {format_archive}, cette version lit le format {FORMAT_ARCHIVE}). "
            "Mettez l'application à jour avant de l'importer."
        )

    declares = manifeste.get("fichiers")
    if not isinstance(declares, list) or not declares:
        raise ErreurArchive("Le manifeste de cette archive ne déclare aucun fichier.")
    for nom in declares:
        if not isinstance(nom, str) or nom not in MEMBRES_AUTORISES:
            raise ErreurArchive(
                f"Le manifeste déclare un fichier inattendu (« {nom} »), l'import est refusé."
            )
        if nom not in membres:
            raise ErreurArchive(
                f"Le manifeste annonce « {nom} », mais l'archive ne le contient pas."
            )

    if FICHIER_CONFIG in membres:
        try:
            valeur = json.loads(membres[FICHIER_CONFIG])
        except json.JSONDecodeError as exc:
            raise ErreurArchive(
                "Les réglages de cette archive (config.json) sont illisibles."
            ) from exc
        if not isinstance(valeur, dict):
            raise ErreurArchive("Les réglages de cette archive n'ont pas la forme attendue.")

    return membres, manifeste


# ---------------------------------------------------------------------------
# Aperçu avant écriture
# ---------------------------------------------------------------------------

def analyser(chemin: str | Path) -> dict:
    """
    Valide l'archive et décrit ce qu'un import changerait. N'écrit rien.

    Renvoie `{ok: False, message}` en cas de refus, sinon `{ok: True, apercu}`.
    """
    try:
        membres, manifeste = _ouvrir_archive(chemin)
    except ErreurArchive as exc:
        journal.attention("Import refusé (%s) : %s", chemin, exc)
        return {"ok": False, "message": str(exc)}

    glossaire = membres.get("vocabulaire.txt", "")
    corrections = membres.get("corrections.txt", "")
    termes_import = vocabulaire.termes(glossaire)
    regles_import, erreurs_import = vocabulaire.analyser_corrections(corrections)

    termes_actuels = vocabulaire.termes(_lire_texte(chemins.FICHIER_VOCABULAIRE))
    regles_actuelles, _ = vocabulaire.analyser_corrections(
        _lire_texte(chemins.FICHIER_CORRECTIONS)
    )

    config_actuelle = _config_courante()
    config_import: dict = json.loads(membres[FICHIER_CONFIG]) if FICHIER_CONFIG in membres else {}

    changements: list[dict] = []
    for cle in _cles_config():
        if cle in REGLAGES_DISCRETS or cle not in config_import:
            continue
        avant, apres = config_actuelle.get(cle), config_import.get(cle)
        if cle == "dossier_sortie":
            continue  # traité à part, c'est un chemin propre à la machine
        if avant == apres:
            continue
        changements.append({
            "cle": cle,
            "libelle": LIBELLES_REGLAGES.get(cle, cle),
            "avant": _formater_valeur(cle, avant),
            "apres": _formater_valeur(cle, apres),
        })

    chemins_machine = _examiner_chemins(config_import, manifeste, config_actuelle)

    return {
        "ok": True,
        "chemin": str(Path(str(chemin)).expanduser()),
        "nom": Path(str(chemin)).name,
        "manifeste": {
            "version": manifeste.get("version", "inconnue"),
            "date": _date_lisible(manifeste.get("date", "")),
            "fichiers": manifeste.get("fichiers", []),
        },
        "glossaire": {"nb": len(termes_import), "nb_actuel": len(termes_actuels)},
        "corrections": {
            "nb": len(regles_import),
            "nb_actuel": len(regles_actuelles),
            "erreurs": erreurs_import,
        },
        "reglages": changements,
        "chemins": chemins_machine,
        "sauvegarde": nom_sauvegarde_avant_import(),
        "dossier_sauvegarde": str(chemins.RACINE),
    }


def _date_lisible(iso: str) -> str:
    try:
        return f"{datetime.fromisoformat(str(iso)):%d/%m/%Y à %H:%M}"
    except (TypeError, ValueError):
        return str(iso or "date inconnue")


def _examiner_chemins(config_import: dict, manifeste: dict, config_actuelle: dict) -> list[dict]:
    """
    Décide du sort des chemins propres à la machine, sans rien écrire.

    Un dossier de sortie ou un dossier de modèles venu d'un autre poste n'a
    aucune raison d'exister ici. On ne le reprend que s'il existe vraiment,
    sinon on garde la valeur locale et on le dit.
    """
    resultat: list[dict] = []

    def examiner(libelle: str, valeur, actuel: str) -> None:
        texte = str(valeur or "").strip()
        if not texte:
            return
        existe = Path(texte).expanduser().is_dir()
        if existe and texte == str(actuel or ""):
            return
        resultat.append({
            "libelle": libelle,
            "valeur": texte,
            "repris": existe,
            "actuel": str(actuel or ""),
            "message": (
                f"{libelle} : « {texte} » sera repris."
                if existe else
                f"{libelle} : « {texte} » n'existe pas sur ce poste, "
                f"votre réglage actuel est conservé."
            ),
        })

    examiner(
        "Dossier de sortie",
        config_import.get("dossier_sortie"),
        config_actuelle.get("dossier_sortie", ""),
    )
    examiner(
        "Dossier des modèles",
        manifeste.get("dossier_modeles"),
        str(chemins.DOSSIER_MODELES),
    )
    return resultat


# ---------------------------------------------------------------------------
# Sauvegarde automatique et import
# ---------------------------------------------------------------------------

def sauvegarder_etat_courant(nom: str | None = None) -> Path:
    """
    Écrit un export de l'état courant dans le dossier de données.

    Appelée juste avant tout import. Lève `ErreurArchive` si elle échoue :
    sans filet, on n'écrase rien.
    """
    cible = chemins.RACINE / (nom or nom_sauvegarde_avant_import())
    resultat = exporter(cible)
    if not resultat.get("ok"):
        raise ErreurArchive(
            "La sauvegarde de vos données actuelles a échoué, l'import est annulé pour ne "
            f"rien écraser. {resultat.get('message', '')}".strip()
        )
    return cible


def importer(chemin: str | Path) -> dict:
    """
    Applique un import, après validation et sauvegarde automatique.

    L'archive est revalidée ici : l'aperçu affiché à l'utilisateur ne fait pas
    autorité, le fichier a pu changer entre-temps.
    """
    try:
        membres, manifeste = _ouvrir_archive(chemin)
    except ErreurArchive as exc:
        journal.attention("Import refusé (%s) : %s", chemin, exc)
        return {"ok": False, "message": str(exc)}

    config_actuelle = _config_courante()

    try:
        sauvegarde = sauvegarder_etat_courant()
    except ErreurArchive as exc:
        journal.erreur("Import annulé : %s", exc)
        return {"ok": False, "message": str(exc)}

    notes: list[str] = []
    try:
        if "vocabulaire.txt" in membres:
            _ecrire_atomique(
                chemins.FICHIER_VOCABULAIRE, membres["vocabulaire.txt"].rstrip() + "\n"
            )
        if "corrections.txt" in membres:
            _ecrire_atomique(
                chemins.FICHIER_CORRECTIONS, membres["corrections.txt"].rstrip() + "\n"
            )

        config_finale = dict(config_actuelle)
        if FICHIER_CONFIG in membres:
            config_import = json.loads(membres[FICHIER_CONFIG])
            for cle in _cles_config():
                if cle not in config_import or cle == "dossier_sortie":
                    continue
                valeur = config_import[cle]
                if isinstance(config_finale.get(cle), dict) and isinstance(valeur, dict):
                    config_finale[cle] = {**config_finale[cle], **valeur}
                else:
                    config_finale[cle] = valeur

            demande = str(config_import.get("dossier_sortie", "") or "").strip()
            if demande and Path(demande).expanduser().is_dir():
                config_finale["dossier_sortie"] = demande
                notes.append(f"Dossier de sortie repris : « {demande} ».")
            elif demande and demande != str(config_actuelle.get("dossier_sortie", "")):
                notes.append(
                    f"Le dossier de sortie de l'export, « {demande} », n'existe pas sur ce "
                    f"poste : votre dossier « {config_actuelle.get('dossier_sortie', '')} » "
                    "est conservé."
                )

        from . import config as config_module

        config_module.sauver(config_finale)

        demande_modeles = str(manifeste.get("dossier_modeles", "") or "").strip()
        if demande_modeles and demande_modeles != str(chemins.DOSSIER_MODELES):
            if Path(demande_modeles).expanduser().is_dir():
                chemins.definir_dossier_modeles(demande_modeles, memoriser=True)
                notes.append(f"Dossier des modèles repris : « {demande_modeles} ».")
            else:
                notes.append(
                    f"Le dossier des modèles de l'export, « {demande_modeles} », n'existe pas "
                    f"sur ce poste : « {chemins.DOSSIER_MODELES} » est conservé."
                )
    except (OSError, json.JSONDecodeError) as exc:
        titre, message = journal.expliquer(exc, "import des données")
        journal.exception("Import des données en échec", exc)
        return {
            "ok": False,
            "message": (
                f"{titre} : {message} Vos données d'avant l'import ont été sauvegardées "
                f"dans « {sauvegarde} »."
            ),
            "sauvegarde": str(sauvegarde),
        }

    termes_importes = vocabulaire.termes(membres.get("vocabulaire.txt", ""))
    regles_importees, _ = vocabulaire.analyser_corrections(membres.get("corrections.txt", ""))
    journal.info(
        "Import depuis %s : %s termes, %s règles, sauvegarde préalable %s",
        chemin, len(termes_importes), len(regles_importees), sauvegarde,
    )

    return {
        "ok": True,
        "message": (
            f"Import terminé : {len(termes_importes)} terme(s) de glossaire, "
            f"{len(regles_importees)} règle(s) de correction et vos réglages ont été remplacés."
        ),
        "sauvegarde": str(sauvegarde),
        "message_sauvegarde": (
            f"Vos données d'avant l'import ont été enregistrées dans « {sauvegarde} ». "
            "Ce fichier se réimporte de la même façon si vous voulez revenir en arrière."
        ),
        "notes": notes,
        "glossaire": len(termes_importes),
        "corrections": len(regles_importees),
    }
