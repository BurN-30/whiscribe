"""
Glossaire de vocabulaire et table de corrections.

Deux leviers complémentaires contre les noms propres écorchés :

1. AMORCE (initial_prompt). La liste des termes de `vocabulaire.txt` est injectée
   au décodeur comme début de contexte. Whisper est alors biaisé vers ces
   orthographes. Limite dure : l'amorce ne peut pas dépasser la moitié de la
   fenêtre de contexte du modèle, soit 224 jetons. Au-delà, faster-whisper
   tronque par la fin, donc silencieusement. On tronque nous-mêmes, proprement,
   en gardant les termes du DÉBUT de la liste, et on le signale dans l'interface.

2. CORRECTIONS (`corrections.txt`). Table `forme_erronée => forme_correcte`
   appliquée au texte final, mot entier, insensible à la casse. Pour les
   massacres récurrents que l'amorce ne suffit pas à corriger.
"""

from __future__ import annotations

import re
from pathlib import Path

from . import chemins, journal

# Whisper réserve la moitié de ses 448 jetons de contexte à l'amorce.
LIMITE_JETONS_AMORCE = 224
# Marge pour la phrase d'introduction et le jeton de début de contexte.
MARGE_JETONS = 24
# Estimation utilisée quand aucun tokeniseur n'est disponible : le français et
# les noms propres tournent autour de 3 caractères par jeton, on reste prudent.
CARACTERES_PAR_JETON = 3.0

ENTETE_AMORCE = "Vocabulaire de cet enregistrement : "


# ---------------------------------------------------------------------------
# Glossaire
# ---------------------------------------------------------------------------

def lire_glossaire(fichier: Path | None = None) -> str:
    fichier = fichier or chemins.FICHIER_VOCABULAIRE
    try:
        return fichier.read_text(encoding="utf-8")
    except FileNotFoundError:
        return ""
    except OSError as exc:
        journal.attention("Lecture du glossaire impossible : %s", exc)
        return ""


def ecrire_glossaire(contenu: str, fichier: Path | None = None) -> None:
    fichier = fichier or chemins.FICHIER_VOCABULAIRE
    fichier.write_text(contenu.rstrip() + "\n", encoding="utf-8")


def termes(contenu: str | None = None) -> list[str]:
    """Un terme par ligne, lignes vides et commentaires « # » ignorés."""
    brut = contenu if contenu is not None else lire_glossaire()
    resultat: list[str] = []
    vus: set[str] = set()
    for ligne in brut.splitlines():
        terme = ligne.strip()
        if not terme or terme.startswith("#"):
            continue
        cle = terme.lower()
        if cle in vus:
            continue
        vus.add(cle)
        resultat.append(terme)
    return resultat


def _compter_jetons(texte: str, tokeniseur=None) -> int:
    if tokeniseur is not None:
        try:
            return len(tokeniseur.encode(texte).ids)
        except Exception:
            try:
                return len(tokeniseur.encode(texte))
            except Exception:
                pass
    return int(len(texte) / CARACTERES_PAR_JETON) + 1


def construire_amorce(contenu: str | None = None, tokeniseur=None) -> dict:
    """
    Fabrique l'amorce à passer en `initial_prompt`.

    Renvoie un dictionnaire : `amorce`, `nb_termes`, `nb_retenus`, `tronque`,
    `jetons`, `message`. La troncature garde l'ordre du fichier : les premiers
    termes sont les plus importants, c'est écrit dans l'en-tête de
    `vocabulaire.txt` et rappelé dans l'interface.
    """
    liste = termes(contenu)
    if not liste:
        return {
            "amorce": "",
            "nb_termes": 0,
            "nb_retenus": 0,
            "tronque": False,
            "jetons": 0,
            "message": "Glossaire vide : aucune amorce envoyée au modèle.",
        }

    budget = LIMITE_JETONS_AMORCE - MARGE_JETONS
    retenus: list[str] = []
    for terme in liste:
        candidat = ENTETE_AMORCE + ", ".join(retenus + [terme]) + "."
        if _compter_jetons(candidat, tokeniseur) > budget and retenus:
            break
        retenus.append(terme)
        if _compter_jetons(ENTETE_AMORCE + ", ".join(retenus) + ".", tokeniseur) > budget:
            retenus.pop()
            break

    if not retenus:
        return {
            "amorce": "",
            "nb_termes": len(liste),
            "nb_retenus": 0,
            "tronque": True,
            "jetons": 0,
            "message": "Le premier terme dépasse déjà la limite de l'amorce.",
        }

    amorce = ENTETE_AMORCE + ", ".join(retenus) + "."
    jetons = _compter_jetons(amorce, tokeniseur)
    tronque = len(retenus) < len(liste)

    if tronque:
        message = (
            f"{len(retenus)} termes sur {len(liste)} tiennent dans l'amorce "
            f"({jetons} jetons sur {LIMITE_JETONS_AMORCE} possibles). Les suivants "
            "sont ignorés : placez les plus importants en haut du fichier."
        )
    else:
        message = (
            f"{len(retenus)} termes envoyés au modèle ({jetons} jetons sur "
            f"{LIMITE_JETONS_AMORCE})."
        )

    return {
        "amorce": amorce,
        "nb_termes": len(liste),
        "nb_retenus": len(retenus),
        "tronque": tronque,
        "jetons": jetons,
        "message": message,
    }


# ---------------------------------------------------------------------------
# Corrections
# ---------------------------------------------------------------------------

class Correction:
    __slots__ = ("source", "cible", "motif")

    def __init__(self, source: str, cible: str):
        self.source = source
        self.cible = cible
        # Frontières de mot tolérantes aux accents et aux termes multi-mots :
        # on interdit simplement qu'un caractère de mot colle de part et d'autre.
        echappe = re.escape(source)
        echappe = re.sub(r"\\?\s+", r"\\s+", echappe)
        self.motif = re.compile(rf"(?<!\w){echappe}(?!\w)", re.IGNORECASE | re.UNICODE)


def lire_corrections(fichier: Path | None = None) -> str:
    fichier = fichier or chemins.FICHIER_CORRECTIONS
    try:
        return fichier.read_text(encoding="utf-8")
    except FileNotFoundError:
        return ""
    except OSError as exc:
        journal.attention("Lecture des corrections impossible : %s", exc)
        return ""


def ecrire_corrections(contenu: str, fichier: Path | None = None) -> None:
    fichier = fichier or chemins.FICHIER_CORRECTIONS
    fichier.write_text(contenu.rstrip() + "\n", encoding="utf-8")


def analyser_corrections(contenu: str | None = None) -> tuple[list[Correction], list[str]]:
    """Renvoie (règles valides, lignes en erreur formulées en français)."""
    brut = contenu if contenu is not None else lire_corrections()
    regles: list[Correction] = []
    erreurs: list[str] = []

    for numero, ligne in enumerate(brut.splitlines(), start=1):
        texte = ligne.strip()
        if not texte or texte.startswith("#"):
            continue
        if "=>" not in texte:
            erreurs.append(f"Ligne {numero} : il manque la flèche « => ».")
            continue
        source, _, cible = texte.partition("=>")
        source, cible = source.strip(), cible.strip()
        if not source:
            erreurs.append(f"Ligne {numero} : la forme à corriger est vide.")
            continue
        if not cible:
            erreurs.append(f"Ligne {numero} : la forme correcte est vide.")
            continue
        try:
            regles.append(Correction(source, cible))
        except re.error as exc:
            erreurs.append(f"Ligne {numero} : règle illisible ({exc}).")

    return regles, erreurs


def appliquer(texte: str, regles: list[Correction]) -> tuple[str, int]:
    """Applique les règles au texte, renvoie (texte corrigé, nombre de remplacements)."""
    if not regles or not texte:
        return texte, 0
    total = 0
    for regle in regles:
        texte, nombre = regle.motif.subn(regle.cible, texte)
        total += nombre
    return texte, total


def resume_glossaire() -> dict:
    """État affiché dans le panneau de réglages, sans charger de modèle."""
    info = construire_amorce()
    regles, erreurs = analyser_corrections()
    info["nb_corrections"] = len(regles)
    info["erreurs_corrections"] = erreurs
    return info
