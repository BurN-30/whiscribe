"""
Nom des fichiers produits.

Jusqu'ici le nommage était figé : « AAAA-MM-JJ-nom-du-fichier ». C'est un bon
défaut, ce n'est pas le bon défaut pour tout le monde. Un motif configurable
règle la question sans rien casser : le motif vide, celui d'une installation
qui n'a jamais touché au réglage, produit exactement l'ancien nom.

Quatre variables, et volontairement pas plus :

    {nom}     nom du fichier d'origine, sans son extension
    {date}    date du jour, AAAA-MM-JJ
    {heure}   heure, HHMMSS
    {modele}  modèle utilisé, par exemple large-v3

Le résultat est un NOM DE FICHIER, jamais un chemin : les séparateurs et tous
les caractères que Windows refuse sont rejetés à la validation, pas nettoyés en
douce. Un motif accepté produit toujours un fichier écrivable, et la protection
contre l'écrasement (suffixes -2, -3) reste celle de `app/sorties.py`.
"""

from __future__ import annotations

from datetime import datetime
from pathlib import Path

from . import langues

#: Motif appliqué quand le réglage est vide, c'est-à-dire le comportement
#: historique de l'application.
MOTIF_DEFAUT = "{date}-{nom}"

#: Variables reconnues, dans l'ordre où l'interface les présente.
VARIABLES: tuple[tuple[str, str], ...] = (
    ("{nom}", "nom du fichier d'origine, sans son extension"),
    ("{date}", "date du jour, AAAA-MM-JJ"),
    ("{heure}", "heure, HHMMSS"),
    ("{modele}", "modèle utilisé, par exemple large-v3"),
)

#: Interdits par Windows dans un nom de fichier. Les séparateurs en font partie :
#: un motif ne doit pas pouvoir fabriquer un sous-dossier ni sortir du dossier
#: de sortie choisi.
CARACTERES_INTERDITS = '<>:"/\\|?*'

#: Noms réservés par MS-DOS, toujours refusés par Windows aujourd'hui.
NOMS_RESERVES = frozenset(
    ["con", "prn", "aux", "nul"]
    + [f"com{n}" for n in range(1, 10)]
    + [f"lpt{n}" for n in range(1, 10)]
)

#: Au-delà, on approche des limites de chemin de Windows pour rien.
LONGUEUR_MAX = 110


def nettoyer_nom(brut: str) -> str:
    """
    « Réunion équipe (2).m4a » devient « reunion-equipe-2 ».

    C'est le nettoyage historique du nom de source : minuscules, tirets, pas de
    ponctuation exotique. Il ne s'applique qu'à la variable `{nom}`, pas au
    texte que l'utilisateur écrit lui-même dans son motif.
    """
    racine = str(brut or "").strip()
    propre = "".join(c if c.isalnum() or c in " -_." else "-" for c in racine)
    propre = "-".join(filter(None, propre.replace("_", "-").replace(" ", "-").split("-")))
    return propre.lower()[:80] or langues.t("nom.repli")


def valider(motif: str) -> str:
    """
    Renvoie un message d'erreur en français, ou une chaîne vide si le motif est
    utilisable. Un motif vide est valable : c'est le retour au défaut.
    """
    texte = str(motif or "").strip()
    if not texte:
        return ""

    fautifs = sorted({c for c in texte if c in CARACTERES_INTERDITS})
    if fautifs:
        return langues.t("nom.caracteres_interdits", liste=" ".join(fautifs))
    if any(ord(c) < 32 for c in texte):
        return langues.t("nom.caractere_controle")

    essai = _appliquer(texte, Path("exemple.m4a"), "large-v3", datetime.now())
    if not essai:
        return langues.t("nom.aucun_nom")
    if essai.split(".")[0].lower() in NOMS_RESERVES:
        return langues.t("nom.nom_reserve", nom=essai)
    return ""


def _appliquer(motif: str, source: Path, modele: str, quand: datetime) -> str:
    """
    Substitution brute des variables, sans filet de sécurité.

    Le résultat peut être vide ou porter un nom réservé : c'est justement ce que
    la validation doit pouvoir constater. `construire` s'occupe du repli.
    """
    fichier = Path(str(source or ""))
    valeurs = {
        "{nom}": nettoyer_nom(fichier.stem),
        "{date}": f"{quand:%Y-%m-%d}",
        "{heure}": f"{quand:%H%M%S}",
        "{modele}": nettoyer_nom(modele) if modele else "",
    }

    texte = str(motif or "").strip() or MOTIF_DEFAUT
    for cle, valeur in valeurs.items():
        texte = texte.replace(cle, valeur)

    texte = "".join(c for c in texte if c not in CARACTERES_INTERDITS and ord(c) >= 32)
    # Un « {modele} » vide laisse des tirets orphelins, on les referme.
    while "--" in texte:
        texte = texte.replace("--", "-")
    return texte.strip(" .-")[:LONGUEUR_MAX].strip(" .-")


def construire(motif: str, source: Path, modele: str = "",
               horodatage: datetime | None = None) -> str:
    """
    Nom de base, sans extension, pour un fichier source donné.

    Le motif est supposé déjà validé. Par prudence, un motif abîmé à la main
    dans `config.json` retombe sur le nom du fichier d'origine : un réglage
    fautif ne doit jamais empêcher d'écrire une transcription.
    """
    texte = _appliquer(motif, source, modele, horodatage or datetime.now())
    if not texte or texte.split(".")[0].lower() in NOMS_RESERVES:
        return nettoyer_nom(Path(str(source or "")).stem)
    return texte


def apercu(motif: str, exemple: str = "", modele: str = "large-v3") -> dict:
    """Aperçu affiché sous le champ des réglages, pendant la frappe."""
    exemple = exemple or langues.t("nom.exemple")
    probleme = valider(motif)
    retenu = str(motif or "").strip() or MOTIF_DEFAUT
    if probleme:
        return {"ok": False, "message": probleme, "exemple": "", "defaut": not str(motif or "").strip()}

    base = construire(retenu, Path(exemple), modele)
    note = ""
    if not any(cle in retenu for cle, _ in VARIABLES):
        note = langues.t("nom.sans_variable")
    return {
        "ok": True,
        "message": note,
        "exemple": base + ".txt",
        "defaut": not str(motif or "").strip(),
    }
