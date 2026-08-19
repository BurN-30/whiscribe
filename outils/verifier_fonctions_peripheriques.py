"""
Vérification en ligne de commande des fonctions périphériques.

Huit sujets, tous vérifiables sans ouvrir de fenêtre, sans transcrire quoi que
ce soit et **sans le moindre appel réseau** :

  1. la scrutation du dossier surveillé, avec de vrais fichiers déposés dans un
     dossier temporaire : détection, stabilité, mémoire persistante ;
  2. la comparaison de numéros de version, dont le cas 2.10.0 contre 2.9.0 et
     les préversions ;
  3. le motif de nommage des sorties : variables, caractères interdits, retour
     au défaut, non-régression du nom historique ;
  4. la mesure de l'espace occupé, sur une arborescence fabriquée pour
     l'occasion ;
  5. la garde des 24 heures entre deux vérifications de mise à jour ;
  6. la plomberie COM en ctypes pur de la barre des tâches Windows, jusqu'à
     l'initialisation de l'objet ;
  7. l'amorce du glossaire, dont l'en-tête suit la langue parlée et non celle
     de l'interface, et son budget de jetons ;
  8. l'autoréparation d'un modèle laissé incomplet par un téléchargement
     interrompu : de faux dossiers de cache sont fabriqués pour l'occasion, la
     détection les reconnaît, la suppression n'emporte que le bon dossier, et
     le chargement enchaîne sur un nouveau téléchargement. Rien n'est
     réellement téléchargé, le moteur est simulé.

Rien de ce que fait ce script ne touche à l'installation : tout se passe dans
un dossier temporaire, effacé à la fin.

    .venv\\Scripts\\python outils\\verifier_fonctions_peripheriques.py

Sort avec le code 0 si tout passe, 1 sinon.
"""

from __future__ import annotations

import sys
import tempfile
from datetime import datetime, timedelta
from pathlib import Path

RACINE = Path(__file__).resolve().parent.parent
if str(RACINE) not in sys.path:
    sys.path.insert(0, str(RACINE))

from app import langues, maj, nommage, stockage, surveillance, vocabulaire  # noqa: E402

# Ces contrôles comparent des chaînes produites par l'application : ils fixent
# donc la langue d'interface, sans quoi leur résultat dépendrait de la langue de
# Windows sur le poste qui les exécute. La bascule elle-même est vérifiée à part,
# dans `essai_langues`, et par `outils/verifier_traductions.py`.
langues.definir("fr")

_echecs: list[str] = []
_reussites = 0


def verifier(condition: bool, libelle: str, detail: str = "") -> None:
    global _reussites
    if condition:
        _reussites += 1
        print(f"  OK    {libelle}")
    else:
        _echecs.append(libelle)
        print(f"  ECHEC {libelle}" + (f" : {detail}" if detail else ""))


def titre(texte: str) -> None:
    print(f"\n{texte}\n" + "-" * len(texte))


# ---------------------------------------------------------------------------
# 1. Dossier surveillé
# ---------------------------------------------------------------------------

def essai_surveillance(base: Path) -> None:
    titre("Dossier surveillé : scrutation, stabilité, mémoire")

    dossier = base / "surveille"
    dossier.mkdir()
    memoire: dict = {}

    # Premier passage sur un dossier vide.
    p = surveillance.scruter(dossier, memoire, {})
    verifier(p["nouveaux"] == [] and p["probleme"] == "", "dossier vide, rien à prendre")

    # Un fichier apparaît : premier passage, il n'a pas encore de taille connue,
    # donc il n'est pas retenu. C'est exactement la garde anti-copie en cours.
    (dossier / "reunion.m4a").write_bytes(b"x" * 1000)
    p1 = surveillance.scruter(dossier, memoire, {})
    verifier(p1["nouveaux"] == [], "un fichier tout juste apparu n'est pas pris")

    # Deuxième passage, taille inchangée : il est stable, donc retenu.
    p2 = surveillance.scruter(dossier, memoire, p1["tailles"])
    verifier(
        [Path(c).name for c in p2["nouveaux"]] == ["reunion.m4a"],
        "un fichier stable est retenu au passage suivant",
        str(p2["nouveaux"]),
    )

    # Fichier en cours de copie : la taille bouge entre deux passages.
    grossissant = dossier / "copie-en-cours.mp3"
    grossissant.write_bytes(b"y" * 500)
    p3 = surveillance.scruter(dossier, memoire, p2["tailles"])
    grossissant.write_bytes(b"y" * 5000)
    p4 = surveillance.scruter(dossier, memoire, p3["tailles"])
    verifier(
        all(Path(c).name != "copie-en-cours.mp3" for c in p4["nouveaux"]),
        "un fichier dont la taille bouge n'est jamais pris",
        str(p4["nouveaux"]),
    )
    p5 = surveillance.scruter(dossier, memoire, p4["tailles"])
    verifier(
        any(Path(c).name == "copie-en-cours.mp3" for c in p5["nouveaux"]),
        "la copie terminée est prise au passage d'après",
        str(p5["nouveaux"]),
    )

    # Mémoire : un fichier déjà pris ne repart pas.
    for chemin in p2["nouveaux"] + p5["nouveaux"]:
        memoire[surveillance.empreinte(Path(chemin))] = 0
    p6 = surveillance.scruter(dossier, memoire, p5["tailles"])
    verifier(p6["nouveaux"] == [], "un fichier déjà traité n'est pas repris", str(p6["nouveaux"]))

    # Redémarrage simulé : mémoire relue, rien ne doit repartir.
    p7 = surveillance.scruter(dossier, dict(memoire), p6["tailles"])
    verifier(p7["nouveaux"] == [], "rien n'est retranscrit après un redémarrage")

    # Un fichier réenregistré sous le même nom est bien un fichier nouveau.
    import time as _time
    _time.sleep(1.1)                       # l'horodatage a une seconde de grain
    (dossier / "reunion.m4a").write_bytes(b"z" * 4321)
    p8 = surveillance.scruter(dossier, memoire, {})
    p9 = surveillance.scruter(dossier, memoire, p8["tailles"])
    verifier(
        any(Path(c).name == "reunion.m4a" for c in p9["nouveaux"]),
        "un enregistrement refait sous le même nom repart en transcription",
        str(p9["nouveaux"]),
    )

    # Formats non audio et sous-dossiers : ignorés.
    (dossier / "notes.txt").write_text("bonjour", encoding="utf-8")
    (dossier / "sous-dossier").mkdir()
    (dossier / "sous-dossier" / "cache.mp3").write_bytes(b"a" * 900)
    q1 = surveillance.scruter(dossier, memoire, {})
    q2 = surveillance.scruter(dossier, memoire, q1["tailles"])
    noms = [Path(c).name for c in q2["nouveaux"]]
    verifier("notes.txt" not in noms, "un fichier non audio est ignoré")
    verifier("cache.mp3" not in noms, "les sous-dossiers ne sont pas parcourus")

    # Dossier disparu : défaut annoncé, pas d'exception.
    absent = surveillance.scruter(base / "nulle-part", {}, {})
    verifier(
        absent["probleme"] != "" and absent["nouveaux"] == [],
        "un dossier introuvable se signale sans casser",
        str(absent),
    )
    verifier(
        surveillance.scruter("", {}, {})["probleme"] == "",
        "aucun dossier choisi, aucun défaut signalé",
    )

    # Le fichier vide n'est pas un enregistrement.
    (dossier / "vide.wav").write_bytes(b"")
    v1 = surveillance.scruter(dossier, memoire, {})
    v2 = surveillance.scruter(dossier, memoire, v1["tailles"])
    verifier(
        all(Path(c).name != "vide.wav" for c in v2["nouveaux"]),
        "un fichier de taille nulle est écarté",
    )


# ---------------------------------------------------------------------------
# 2. Comparaison de versions
# ---------------------------------------------------------------------------

def essai_versions() -> None:
    titre("Mise à jour : comparaison de versions")

    cas = [
        ("2.10.0", "2.9.0", 1, "2.10.0 est plus récent que 2.9.0"),
        ("2.9.0", "2.10.0", -1, "2.9.0 est plus ancien que 2.10.0"),
        ("2.2.0", "2.2.0", 0, "deux versions identiques"),
        ("v2.3.0", "2.2.9", 1, "le v du tag est ignoré"),
        ("3.0.0", "2.99.99", 1, "changement de version majeure"),
        ("2.2.1", "2.2.0", 1, "correctif plus récent"),
        ("2.2.0-beta.1", "2.2.0", -1, "une préversion précède la version finale"),
        ("2.2.0", "2.2.0-rc.2", 1, "la version finale suit sa préversion"),
        ("2.2.0-rc.2", "2.2.0-rc.10", -1, "préversions comparées en nombres"),
        ("2.2", "2.2.0", 0, "un numéro court vaut le même complété de zéros"),
        ("2.2.0", "", 1, "une version absente en face ne bloque pas"),
    ]
    for gauche, droite, attendu, libelle in cas:
        obtenu = maj.comparer(gauche, droite)
        verifier(obtenu == attendu, f"{libelle} ({gauche} / {droite})", f"obtenu {obtenu}")

    # Lecture d'une réponse de l'API, sans réseau.
    publication = {
        "tag_name": "v2.3.0",
        "html_url": "https://github.com/exemple/whiscribe/releases/tag/v2.3.0",
        "body": "Des nouveautés.",
    }
    lu = maj.analyser_release(publication, "2.2.0")
    verifier(lu["disponible"] and lu["version"] == "2.3.0", "une version plus récente est vue")
    verifier(not lu["reinstallation"], "sans marqueur, mise à jour par-dessus")

    publication["body"] = "Attention.\n\n[reinstallation-requise]\n\nSuite."
    verifier(
        maj.analyser_release(publication, "2.2.0")["reinstallation"],
        "le marqueur [reinstallation-requise] est reconnu",
    )
    verifier(
        maj.analyser_release({"tag_name": "v2.0.0", "body": ""}, "2.2.0")["disponible"] is False,
        "une version plus ancienne n'annonce rien",
    )
    verifier(
        maj.analyser_release({}, "2.2.0")["disponible"] is False,
        "une réponse vide n'annonce rien",
    )
    verifier(
        maj.url_api().startswith("https://api.github.com/repos/"),
        "l'adresse de l'API est déduite du dépôt",
        maj.url_api(),
    )


# ---------------------------------------------------------------------------
# 3. Motif de nommage
# ---------------------------------------------------------------------------

def essai_nommage() -> None:
    titre("Nom des fichiers produits")

    quand = datetime(2026, 8, 18, 14, 32, 5)
    source = Path(r"C:\Enregistrements\Réunion équipe.m4a")

    verifier(
        nommage.construire("", source, "large-v3", quand) == "2026-08-18-réunion-équipe",
        "motif vide : nommage historique inchangé",
        nommage.construire("", source, "large-v3", quand),
    )
    verifier(
        nommage.construire("{nom}", source, "", quand) == "réunion-équipe",
        "{nom} seul, accents conservés comme avant",
        nommage.construire("{nom}", source, "", quand),
    )
    verifier(
        nommage.construire("{date}-{heure}-{nom}", source, "", quand)
        == "2026-08-18-143205-réunion-équipe",
        "date et heure",
        nommage.construire("{date}-{heure}-{nom}", source, "", quand),
    )
    verifier(
        nommage.construire("{nom}-{modele}", source, "large-v3", quand)
        == "réunion-équipe-large-v3",
        "modèle repris dans le nom",
        nommage.construire("{nom}-{modele}", source, "large-v3", quand),
    )
    verifier(
        nommage.construire("CR {nom} du {date}", source, "", quand)
        == "CR réunion-équipe du 2026-08-18",
        "le texte de l'utilisateur garde sa casse",
        nommage.construire("CR {nom} du {date}", source, "", quand),
    )

    for interdit in '<>:"/\\|?*':
        message = nommage.valider(f"compte{interdit}rendu")
        verifier(bool(message), f"le caractère {interdit!r} est refusé")
    verifier(nommage.valider("") == "", "un motif vide est accepté, c'est le défaut")
    verifier(nommage.valider("{date}-{nom}") == "", "le motif par défaut est accepté")
    verifier(bool(nommage.valider("nul")), "un nom réservé de Windows est refusé")

    apercu_defaut = nommage.apercu("")
    verifier(
        apercu_defaut["ok"] and apercu_defaut["defaut"] and apercu_defaut["exemple"].endswith(".txt"),
        "aperçu du défaut",
        str(apercu_defaut),
    )
    apercu_fixe = nommage.apercu("transcription")
    verifier(
        apercu_fixe["ok"] and apercu_fixe["message"] == langues.t("nom.sans_variable"),
        "un motif sans variable est signalé sans être refusé",
        str(apercu_fixe),
    )
    verifier(
        nommage.apercu("a/b")["ok"] is False,
        "un séparateur de chemin est refusé dans l'aperçu",
    )
    verifier(
        len(nommage.construire("{nom}" * 40, source, "", quand)) <= nommage.LONGUEUR_MAX,
        "un motif démesuré est borné",
    )
    verifier(
        nommage.construire("{modele}", Path("son.wav"), "", quand) == "son",
        "un motif qui ne produirait rien retombe sur le nom du fichier",
        nommage.construire("{modele}", Path("son.wav"), "", quand),
    )

    # Non-régression : l'ancien code de app/sorties.py et le nouveau doivent
    # produire exactement le même nom quand aucun motif n'est réglé.
    from app import sorties

    for exemple in ("Réunion équipe.m4a", "notes_du_12 mars.mp3", "@@@.wav", "CR-final.m4a"):
        attendu = f"{datetime.now():%Y-%m-%d}-" + nommage.nettoyer_nom(Path(exemple).stem)
        verifier(
            sorties.nom_de_base(Path(exemple)) == attendu,
            f"nom historique préservé pour « {exemple} »",
            sorties.nom_de_base(Path(exemple)),
        )


# ---------------------------------------------------------------------------
# 4. Espace occupé
# ---------------------------------------------------------------------------

def essai_stockage(base: Path) -> None:
    titre("Espace utilisé")

    verifier(stockage.formater_octets(0) == "0 octet", "zéro octet",
             stockage.formater_octets(0))
    verifier(stockage.formater_octets(1536) == "1,5 Ko", "kilooctets",
             stockage.formater_octets(1536))
    verifier(stockage.formater_octets(3.1 * 1024 ** 3).endswith("Go"), "gigaoctets",
             stockage.formater_octets(3.1 * 1024 ** 3))

    arbre = base / "mesure"
    (arbre / "sous" / "encore").mkdir(parents=True)
    (arbre / "a.bin").write_bytes(b"0" * 1000)
    (arbre / "sous" / "b.bin").write_bytes(b"0" * 2000)
    (arbre / "sous" / "encore" / "c.bin").write_bytes(b"0" * 3000)
    (arbre / ".venv").mkdir()
    (arbre / ".venv" / "gros.bin").write_bytes(b"0" * 999000)

    octets, nombre = stockage.taille(arbre)
    verifier(octets == 1000 + 2000 + 3000 + 999000, "somme récursive complète", str(octets))
    verifier(nombre == 4, "nombre de fichiers", str(nombre))

    octets_hors_venv, _ = stockage.taille(arbre, exclus=stockage.EXCLUS_SOURCE)
    verifier(octets_hors_venv == 6000, "le .venv est exclu à la demande", str(octets_hors_venv))

    verifier(stockage.taille(base / "inexistant") == (0, 0), "un dossier absent vaut zéro")
    verifier(stockage.taille(arbre / "a.bin") == (1000, 1), "un fichier seul se mesure aussi")

    mesure = stockage.mesurer()
    cles = [p["cle"] for p in mesure["postes"]]
    verifier(cles == ["modeles", "donnees", "programme"], "trois postes annoncés", str(cles))
    verifier(
        all(p["chemin"] and p["taille"] for p in mesure["postes"]),
        "chaque poste porte un chemin et une taille lisible",
    )
    verifier(
        mesure["total"] == sum(p["octets"] for p in mesure["postes"]),
        "le total est la somme des postes",
    )
    verifier(bool(mesure["libre"]), "l'espace libre est renseigné", mesure["libre"])


# ---------------------------------------------------------------------------
# 5. Garde des 24 heures, et plomberie COM de la barre des tâches
# ---------------------------------------------------------------------------

def essai_cadence_maj() -> None:
    titre("Mise à jour : une vérification par jour au plus")

    fichier = maj._fichier_etat()
    existait = fichier.exists()
    sauvegarde = fichier.read_text(encoding="utf-8") if existait else ""
    try:
        fichier.unlink(missing_ok=True)
        verifier(maj.verification_due(), "sans état, la vérification est due")

        maj._ecrire_etat({"derniere": datetime.now().isoformat(timespec="seconds")})
        verifier(not maj.verification_due(), "juste après, elle ne l'est plus")

        hier = datetime.now() - timedelta(hours=25)
        maj._ecrire_etat({"derniere": hier.isoformat(timespec="seconds")})
        verifier(maj.verification_due(), "au-delà de 24 heures, elle l'est de nouveau")

        maj._ecrire_etat({"derniere": "n'importe quoi"})
        verifier(maj.verification_due(), "un état illisible ne bloque pas la vérification")

        essai_maj_indisponible()
    finally:
        if existait:
            fichier.write_text(sauvegarde, encoding="utf-8")
        else:
            fichier.unlink(missing_ok=True)


def essai_maj_indisponible() -> None:
    """
    Un dépôt privé répond 404 à l'API publique, un quota atteint répond 403.
    Ni l'un ni l'autre n'est un incident : le journal doit rester en INFO, et
    l'interface ne rien recevoir. Aucun appel réseau ici, l'interrogation est
    remplacée par l'exception qu'elle produirait.
    """
    import urllib.error

    from app import journal

    traces: dict[str, list[str]] = {"info": [], "attention": []}
    interrogation = maj._interroger
    ecrire_info, ecrire_attention = journal.info, journal.attention

    def echec(code: int):
        def lever(_url: str) -> dict:
            raise urllib.error.HTTPError(_url, code, "Not Found", {}, None)  # type: ignore[arg-type]
        return lever

    try:
        journal.info = lambda message, *args: traces["info"].append(str(message) % args if args else str(message))
        journal.attention = lambda message, *args: traces["attention"].append(str(message) % args if args else str(message))

        for code in (404, 403):
            traces["info"].clear()
            traces["attention"].clear()
            maj._interroger = echec(code)
            resultat = maj.verifier("2.0.0", forcer=True)
            verifier(not resultat.get("disponible"),
                     f"HTTP {code} : rien n'est proposé à l'utilisateur", str(resultat))
            verifier(not traces["attention"],
                     f"HTTP {code} : aucun avertissement dans le journal",
                     " | ".join(traces["attention"]))
            verifier(any(str(code) in ligne for ligne in traces["info"]),
                     f"HTTP {code} : une simple ligne d'information",
                     " | ".join(traces["info"]))

        traces["attention"].clear()
        maj._interroger = echec(500)
        maj.verifier("2.0.0", forcer=True)
        verifier(bool(traces["attention"]),
                 "une vraie panne de GitHub reste un avertissement")
    finally:
        maj._interroger = interrogation
        journal.info, journal.attention = ecrire_info, ecrire_attention


def essai_barre_taches() -> None:
    titre("Barre des tâches : plomberie COM en ctypes pur")

    from app import barre_taches

    if sys.platform != "win32":
        print("  (hors Windows, sans objet)")
        return

    objet = barre_taches._objet()
    verifier(objet is not None, "l'objet ITaskbarList3 se crée et s'initialise")

    # Sans fenêtre déclarée, tout doit rester inerte et silencieux.
    verifier(not barre_taches.disponible(), "sans fenêtre connue, le module est inerte")
    barre_taches.progression(50)
    barre_taches.erreur()
    barre_taches.effacer()
    verifier(True, "les appels sans fenêtre ne lèvent rien")

    verifier(
        barre_taches.definir_fenetre("WhiScribe-fenetre-qui-n-existe-pas") == 0,
        "une fenêtre introuvable renvoie zéro sans erreur",
    )


# ---------------------------------------------------------------------------
# 7. Langue de l'interface
# ---------------------------------------------------------------------------

def essai_langues() -> None:
    titre("Langue de l'interface : détection, bascule, indépendance")

    from app import presets

    verifier(langues.normaliser("fr-FR") == "fr", "une locale complète est ramenée au code")
    verifier(langues.normaliser("en_US") == "en", "le tiret bas est accepté")
    verifier(langues.normaliser("de-DE") == "", "une langue non prise en charge est refusée")
    verifier(langues.normaliser(None) == "", "une valeur absente ne casse rien")
    verifier(langues.detecter_systeme() in langues.LANGUES,
             "la détection système rend toujours une langue connue",
             langues.detecter_systeme())
    verifier(langues.LANGUE_DEFAUT == "en",
             "hors francophonie, le repli documenté est l'anglais")

    try:
        langues.definir("fr")
        verifier(presets.nom_preset("qualite") == "Qualité maximale",
                 "les presets parlent français", presets.nom_preset("qualite"))
        verifier(stockage.formater_octets(1536) == "1,5 Ko",
                 "le séparateur décimal français s'applique")
        verifier(presets.formater_duree(3725).startswith("1 h"),
                 "les durées sont formatées", presets.formater_duree(3725))

        langues.definir("en")
        verifier(presets.nom_preset("qualite") == "Highest quality",
                 "la bascule change les textes produits par Python",
                 presets.nom_preset("qualite"))
        verifier(stockage.formater_octets(1536) == "1.5 KB",
                 "le séparateur décimal et les unités suivent la langue",
                 stockage.formater_octets(1536))
        verifier(langues.t("cle.qui.nexiste.pas") == "cle.qui.nexiste.pas",
                 "une clé absente se voit au lieu de planter")
        verifier(langues.tn("lect.remplacements", 1) == "1 replacement in the file.",
                 "le singulier est choisi", langues.tn("lect.remplacements", 1))
        verifier(langues.tn("lect.remplacements", 3) == "3 replacements in the file.",
                 "le pluriel est choisi", langues.tn("lect.remplacements", 3))
        verifier("{" not in langues.t("app.copie_ia", n=42),
                 "toutes les variables nommées sont substituées")
        verifier("{texte}" in langues.t("gabarit.defaut"),
                 "les accolades du gabarit ne sont pas consommées par la substitution")
    finally:
        langues.definir("fr")


# ---------------------------------------------------------------------------
# 8. Modèle laissé incomplet par un téléchargement interrompu
#
# Aucun modèle réel n'est téléchargé : on fabrique de fausses arborescences de
# cache huggingface dans un dossier temporaire, ce qui suffit à prouver la
# détection, la suppression ciblée, et le fait que le chargement bascule bien
# vers un nouveau téléchargement.
# ---------------------------------------------------------------------------

DEPOT_ABIME = "Systran/faster-whisper-large-v3"
DEPOT_SAIN = "Systran/faster-whisper-small"
DEPOT_TRONQUE = "Systran/faster-whisper-medium"
DEPOT_EN_COURS = "Systran/faster-whisper-base"


def _fabriquer_modele(racine: Path, depot: str, poids: int | None,
                      config: bool = True, en_cours: bool = False) -> Path:
    """
    Fabrique un dossier de cache huggingface. `poids` à None laisse le snapshot
    sans « model.bin », c'est exactement ce que laisse une coupure.
    """
    from app import moteur

    dossier = racine / (moteur.PREFIXE_CACHE + depot.replace("/", "--"))
    snapshot = dossier / "snapshots" / ("0" * 40)
    snapshot.mkdir(parents=True)
    (dossier / "refs").mkdir()
    (dossier / "refs" / "main").write_text("0" * 40, encoding="utf-8")
    if config:
        (snapshot / "config.json").write_text("{}", encoding="utf-8")
    if poids is not None:
        (snapshot / moteur.NOM_POIDS).write_bytes(b"0" * poids)
    if en_cours:
        (dossier / "blobs").mkdir(exist_ok=True)
        (dossier / "blobs" / ("a" * 16 + moteur.SUFFIXE_INCOMPLET)).write_bytes(b"0" * 128)
    return dossier


def essai_modele_incomplet(base: Path) -> None:
    titre("Modèle incomplet : détection, suppression ciblée, retéléchargement")

    from types import SimpleNamespace

    from app import chemins, moteur

    racine = base / "modeles-fictifs"
    racine.mkdir()

    complet = _fabriquer_modele(racine, DEPOT_SAIN, moteur.TAILLE_MINIMALE_POIDS + 1)
    abime = _fabriquer_modele(racine, DEPOT_ABIME, None)
    tronque = _fabriquer_modele(racine, DEPOT_TRONQUE, 4096)
    en_cours = _fabriquer_modele(racine, DEPOT_EN_COURS,
                                 moteur.TAILLE_MINIMALE_POIDS + 1, en_cours=True)
    voisin = racine / "mes-affaires"
    voisin.mkdir()
    (voisin / "note.txt").write_text("a garder", encoding="utf-8")

    # -- détection ---------------------------------------------------------
    etat = moteur.etat_modele(DEPOT_SAIN, racine)
    verifier(etat["etat"] == "complet", "un modèle entier est vu comme complet", str(etat))

    etat = moteur.etat_modele(DEPOT_ABIME, racine)
    verifier(etat["etat"] == "incomplet" and etat["reparable"],
             "un snapshot sans model.bin est vu comme incomplet et réparable", str(etat))
    verifier(moteur.NOM_POIDS in etat["motif"], "le motif nomme le fichier absent",
             etat["motif"])

    etat = moteur.etat_modele(DEPOT_TRONQUE, racine)
    verifier(etat["etat"] == "incomplet", "un model.bin tronqué est vu comme incomplet",
             str(etat))

    etat = moteur.etat_modele(DEPOT_EN_COURS, racine)
    verifier(etat["etat"] == "incomplet",
             "un fichier « .incomplete » suffit à déclasser le modèle", str(etat))

    etat = moteur.etat_modele("Systran/faster-whisper-tiny", racine)
    verifier(etat["etat"] == "absent", "un modèle jamais téléchargé reste « absent »",
             str(etat))

    # -- suppression, et rien d'autre --------------------------------------
    verifier(moteur.supprimer_modele(DEPOT_ABIME, racine), "le modèle incomplet est supprimé")
    verifier(not abime.exists(), "son dossier a bien disparu")
    verifier(complet.is_dir() and tronque.is_dir() and en_cours.is_dir(),
             "les autres modèles sont intacts")
    verifier(voisin.is_dir() and (voisin / "note.txt").exists(),
             "un dossier voisin étranger au cache n'est pas touché")
    verifier(len(list(racine.iterdir())) == 4, "un seul dossier en moins",
             str(sorted(p.name for p in racine.iterdir())))

    verifier(not moteur.supprimer_modele(DEPOT_ABIME, racine),
             "supprimer deux fois ne lève rien et ne prétend rien")
    verifier(not moteur.supprimer_modele("", racine),
             "un nom de modèle vide n'efface rien")
    verifier(racine.is_dir() and len(list(racine.iterdir())) == 4,
             "le dossier des modèles est toujours là")

    # -- après réparation, le chemin du téléchargement -----------------------
    verifier(moteur.etat_modele(DEPOT_ABIME, racine)["etat"] == "absent",
             "une fois réparé, le modèle est simplement « absent », donc à télécharger")

    # -- le chargement enchaîne réparation puis téléchargement ---------------
    ancien = chemins.DOSSIER_MODELES
    chemins.DOSSIER_MODELES = racine
    appels: list[str] = []
    messages: list[tuple[str, str]] = []
    try:
        instance = moteur.MoteurTranscription(
            SimpleNamespace(peripherique="cpu", fils_calcul=4), forcer_processeur=True)
        instance._instancier = lambda modele: appels.append(modele) or "modele-simule"

        instance.charger(DEPOT_TRONQUE, lambda niveau, texte: messages.append((niveau, texte)))
        verifier(not tronque.exists(), "au chargement, le modèle tronqué est effacé")
        verifier(appels == [DEPOT_TRONQUE], "le téléchargement est bien enchaîné une fois",
                 str(appels))
        verifier(any("incomplet" in texte for _, texte in messages),
                 "l'interface est prévenue que le modèle était incomplet",
                 " | ".join(texte for _, texte in messages))

        # Filet de sécurité : des poids que la détection croit sains mais que
        # faster-whisper refuse. Une seule reprise, après réparation.
        essais = {"n": 0}

        def instancier_capricieux(modele: str):
            essais["n"] += 1
            if essais["n"] == 1:
                raise RuntimeError(
                    f"Unable to open file 'model.bin' in model '{complet}'")
            return "modele-simule"

        instance.liberer()
        instance._instancier = instancier_capricieux
        instance.charger(DEPOT_SAIN, lambda niveau, texte: messages.append((niveau, texte)))
        verifier(essais["n"] == 2, "un refus sur model.bin déclenche une seule reprise",
                 str(essais["n"]))
        verifier(not complet.exists(), "le dossier fautif a été renouvelé au passage")
    finally:
        chemins.DOSSIER_MODELES = ancien
        chemins.confiner_cache_huggingface()

    verifier(moteur._poids_illisible(RuntimeError("Unable to open file 'model.bin'")),
             "l'erreur de faster-whisper est reconnue")
    verifier(not moteur._poids_illisible(OSError("disque plein")),
             "une erreur sans rapport ne déclenche pas de réparation")


def essai_amorce() -> None:
    """
    L'amorce du glossaire suit la langue PARLÉE, jamais celle de l'interface.

    C'est un prompt : le décodeur la lit comme un début de texte. Une phrase
    française en tête d'un enregistrement anglais pousse le modèle vers le
    français, ce qui est exactement l'inverse du service rendu.
    """
    titre("Amorce du glossaire, dans la langue parlée")

    glossaire = "Valenciennes\nCTranslate2\nWhiScribe"
    try:
        # Interface en anglais, enregistrement en français : c'est la langue
        # parlée qui décide, l'en-tête doit rester français.
        langues.definir("en")
        francais = vocabulaire.construire_amorce(glossaire, langue="fr")
        langues.definir("fr")
        anglais = vocabulaire.construire_amorce(glossaire, langue="en")
    finally:
        langues.definir("fr")

    verifier(francais["amorce"].startswith("Vocabulaire de cet enregistrement"),
             "langue parlée « fr » : en-tête français", francais["amorce"][:48])
    verifier(anglais["amorce"].startswith("Vocabulary for this recording"),
             "langue parlée « en » : en-tête anglais", anglais["amorce"][:48])
    verifier(vocabulaire.construire_amorce(glossaire, langue="de")["amorce"]
             .startswith("Vocabulary for this recording"),
             "toute autre langue parlée prend l'anglais")
    verifier(vocabulaire.construire_amorce(glossaire, langue="")["amorce"]
             .startswith("Vocabulary for this recording"),
             "détection automatique : anglais, on ne présume de rien")
    verifier("Valenciennes" in francais["amorce"] and "Valenciennes" in anglais["amorce"],
             "les termes du glossaire sont les mêmes des deux côtés")

    # Le budget se compte sur la forme réellement envoyée, en-tête compris.
    long_glossaire = "\n".join(f"Terminologie{n}" for n in range(400))
    tronquee = vocabulaire.construire_amorce(long_glossaire, langue="fr")
    verifier(tronquee["tronque"] is True, "un glossaire trop long est tronqué")
    verifier(tronquee["jetons"] < vocabulaire.LIMITE_JETONS_AMORCE,
             "le décompte reste sous la limite de 224 jetons", str(tronquee["jetons"]))
    verifier(tronquee["jetons"] == vocabulaire._compter_jetons(tronquee["amorce"]),
             "le décompte porte sur la chaîne réellement envoyée")


def principal() -> int:
    print(f"Vérification des fonctions périphériques de WhiScribe\n{'=' * 54}")
    with tempfile.TemporaryDirectory(prefix="whiscribe-verif-") as brut:
        base = Path(brut)
        essai_surveillance(base)
        essai_versions()
        essai_nommage()
        essai_stockage(base)
        essai_cadence_maj()
        essai_barre_taches()
        essai_langues()
        essai_amorce()
        essai_modele_incomplet(base)

    print(f"\n{'=' * 54}")
    if _echecs:
        print(f"{_reussites} vérifications passées, {len(_echecs)} en échec :")
        for libelle in _echecs:
            print(f"  - {libelle}")
        return 1
    print(f"{_reussites} vérifications passées, aucune en échec.")
    return 0


if __name__ == "__main__":
    sys.exit(principal())
