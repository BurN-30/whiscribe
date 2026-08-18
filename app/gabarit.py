"""
Gabarit d'instructions pour un assistant IA : « gabarit-ia.txt ».

Transcrire n'est qu'une moitié du travail. L'autre, quand on veut un compte
rendu, consiste à recoller les instructions, les métadonnées et le texte avant
de les donner à un assistant. Le bouton « Copier pour l'IA » de la vue de
lecture le fait d'un clic.

Le gabarit est un simple fichier texte, dans le dossier des données de
l'utilisateur, créé au premier usage avec un contenu par défaut commenté, et
modifiable ensuite comme `vocabulaire.txt` ou `corrections.txt`. Rien n'est
envoyé nulle part : le résultat va dans le presse-papiers, l'utilisateur le
colle où il veut, dans l'assistant de son choix.

Les lignes commençant par « # » sont des commentaires : elles servent à
documenter le fichier et ne sont jamais copiées.
"""

from __future__ import annotations

from pathlib import Path

from . import chemins, journal, langues

#: Variables reconnues dans le gabarit. Toute autre accolade est laissée telle
#: quelle : un gabarit qui parle de « {} » ne doit pas se transformer en erreur.
VARIABLES = ("texte", "fichier", "date", "duree", "locuteurs", "modele")

def contenu_defaut() -> str:
    """
    Contenu du gabarit créé au premier usage, dans la langue de l'interface.

    Il n'est écrit qu'une fois. Un fichier existant n'est jamais retraduit ni
    réécrit, même si l'utilisateur change de langue ensuite : ce fichier lui
    appartient. Le texte vit dans `app/langues.py`, clé « gabarit.defaut ».
    """
    return langues.t("gabarit.defaut")


def fichier() -> Path:
    return chemins.FICHIER_GABARIT_IA


def assurer() -> Path:
    """Crée le gabarit au premier usage. Un fichier existant n'est jamais touché."""
    cible = fichier()
    if cible.exists():
        return cible
    try:
        cible.parent.mkdir(parents=True, exist_ok=True)
        cible.write_text(contenu_defaut(), encoding="utf-8")
        journal.info("Gabarit d'instructions créé : %s", cible)
    except OSError as exc:
        journal.attention("Création du gabarit impossible : %s", exc)
    return cible


def lire() -> str:
    assurer()
    try:
        return fichier().read_text(encoding="utf-8")
    except (OSError, UnicodeDecodeError) as exc:
        journal.attention("Lecture du gabarit impossible : %s", exc)
        return contenu_defaut()


def ecrire(contenu: str) -> None:
    try:
        fichier().write_text((contenu or "").rstrip() + "\n", encoding="utf-8")
    except OSError as exc:
        journal.attention("Enregistrement du gabarit impossible : %s", exc)


def corps(contenu: str | None = None) -> str:
    """Le gabarit sans ses lignes de commentaire."""
    brut = contenu if contenu is not None else lire()
    lignes = [l for l in brut.splitlines() if not l.lstrip().startswith("#")]
    return "\n".join(lignes).strip("\n")


def appliquer(valeurs: dict, contenu: str | None = None) -> str:
    """
    Remplace les variables du gabarit par les valeurs de la transcription.

    Le remplacement est littéral, pas un `format()` : un gabarit contenant une
    accolade isolée ou une variable inconnue doit produire un texte, pas une
    exception.
    """
    texte = corps(contenu)
    if not texte.strip():
        texte = corps(contenu_defaut())
    for nom in VARIABLES:
        texte = texte.replace("{" + nom + "}", str(valeurs.get(nom, "")))
    return texte.strip() + "\n"
