"""
Vérification facultative des mises à jour.

Règle qui prime sur tout le reste : **coupée, l'application ne fait aucun appel
réseau sortant**, hors le téléchargement d'un modèle explicitement demandé par
l'utilisateur. Le réglage est donc désactivé par défaut, et rien dans ce module
n'est appelé tant qu'il ne l'est pas. C'est l'appelant, `transcriber.pyw`, qui
garantit cette condition : ce module ne se contrôle pas lui-même.

Quand elle est active, la vérification se fait au lancement, au plus une fois
par 24 heures, contre l'API publique des Releases de GitHub. Elle a un délai
d'attente court et échoue toujours en silence : un poste hors ligne, un
pare-feu ou une panne de GitHub ne doivent produire aucun message à l'écran,
seulement une ligne de journal.

RÉINSTALLATION COMPLÈTE
-----------------------
Presque toutes les versions s'installent par-dessus la précédente sans rien
perdre : c'est ce que le bandeau propose par défaut. Certaines, rarement, ne le
peuvent pas, par exemple si le programme d'installation change de mode ou si
l'arborescence installée bouge. Le mainteneur le signale alors en écrivant le
marqueur

    [reinstallation-requise]

n'importe où dans le corps (body) de la Release. Le bandeau change alors de
texte et annonce la désinstallation préalable, en précisant que les données et
les modèles, qui vivent ailleurs, sont conservés. Ce marqueur est documenté
dans le README, section « Fabriquer le programme d'installation », et rappelé
en commentaire dans `.github/workflows/release.yml`.
"""

from __future__ import annotations

import json
import re
import urllib.error
import urllib.request
from datetime import datetime, timedelta
from pathlib import Path

from . import URL_PROJET, VERSION, chemins, journal

#: Marqueur documenté, cherché dans le corps de la Release.
MARQUEUR_REINSTALLATION = "[reinstallation-requise]"

#: Délai d'attente réseau, volontairement court : cette vérification est un
#: agrément, elle n'a pas le droit de retarder le démarrage.
DELAI_SECONDES = 6

#: Au plus une vérification par jour.
INTERVALLE_HEURES = 24

#: Petit état persistant, à côté de la configuration.
FICHIER_ETAT = "maj-etat.json"


def _depot() -> str:
    """« BurN-30/whiscribe » déduit de l'adresse du dépôt, source unique."""
    correspondance = re.search(r"github\.com/([^/]+/[^/#?]+)", str(URL_PROJET or ""))
    return correspondance.group(1).rstrip("/").removesuffix(".git") if correspondance else ""


def url_api() -> str:
    depot = _depot()
    return f"https://api.github.com/repos/{depot}/releases/latest" if depot else ""


# ---------------------------------------------------------------------------
# Comparaison de versions
# ---------------------------------------------------------------------------

def _decouper(version: str) -> tuple[list[int], list[str]]:
    texte = str(version or "").strip().lstrip("vV")
    corps, _, preversion = texte.partition("-")
    nombres: list[int] = []
    for morceau in corps.split("."):
        chiffres = re.match(r"\d+", morceau.strip())
        nombres.append(int(chiffres.group()) if chiffres else 0)
    while len(nombres) < 3:
        nombres.append(0)
    marques = [m for m in preversion.replace("-", ".").split(".") if m]
    return nombres, marques


def comparer(gauche: str, droite: str) -> int:
    """
    Renvoie 1, 0 ou -1 selon que `gauche` est plus récente, égale ou plus
    ancienne que `droite`.

    Comparaison numérique, pas lexicographique : 2.10.0 est bien supérieur à
    2.9.0. Une préversion (2.2.0-beta.1) précède toujours la version finale du
    même numéro, comme le veut l'usage.
    """
    nombres_g, marques_g = _decouper(gauche)
    nombres_d, marques_d = _decouper(droite)

    taille = max(len(nombres_g), len(nombres_d))
    nombres_g += [0] * (taille - len(nombres_g))
    nombres_d += [0] * (taille - len(nombres_d))
    if nombres_g != nombres_d:
        return 1 if nombres_g > nombres_d else -1

    if not marques_g and not marques_d:
        return 0
    if not marques_g:
        return 1
    if not marques_d:
        return -1

    for a, b in zip(marques_g, marques_d):
        if a == b:
            continue
        if a.isdigit() and b.isdigit():
            return 1 if int(a) > int(b) else -1
        return 1 if a > b else -1
    if len(marques_g) == len(marques_d):
        return 0
    return 1 if len(marques_g) > len(marques_d) else -1


# ---------------------------------------------------------------------------
# État persistant : une seule vérification par jour
# ---------------------------------------------------------------------------

def _fichier_etat() -> Path:
    return chemins.RACINE / FICHIER_ETAT


def lire_etat() -> dict:
    try:
        donnees = json.loads(_fichier_etat().read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError, UnicodeDecodeError):
        return {}
    return donnees if isinstance(donnees, dict) else {}


def _ecrire_etat(etat: dict) -> None:
    try:
        chemins.RACINE.mkdir(parents=True, exist_ok=True)
        _fichier_etat().write_text(
            json.dumps(etat, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
        )
    except OSError:
        pass


def verification_due(maintenant: datetime | None = None) -> bool:
    """Vrai si la dernière vérification remonte à plus de 24 heures."""
    etat = lire_etat()
    try:
        derniere = datetime.fromisoformat(str(etat.get("derniere", "")))
    except (TypeError, ValueError):
        return True
    return (maintenant or datetime.now()) - derniere >= timedelta(hours=INTERVALLE_HEURES)


# ---------------------------------------------------------------------------
# Interrogation
# ---------------------------------------------------------------------------

def _interroger(url: str) -> dict:
    requete = urllib.request.Request(
        url,
        headers={
            "Accept": "application/vnd.github+json",
            "User-Agent": f"WhiScribe/{VERSION}",
        },
    )
    with urllib.request.urlopen(requete, timeout=DELAI_SECONDES) as reponse:
        brut = reponse.read(256 * 1024)
    donnees = json.loads(brut.decode("utf-8", errors="replace"))
    return donnees if isinstance(donnees, dict) else {}


def analyser_release(publication: dict, version_courante: str = VERSION) -> dict:
    """
    Traduit la réponse de l'API en ce que le bandeau a besoin de savoir.

    Séparé de l'appel réseau pour être vérifiable sans connexion.
    """
    etiquette = str(publication.get("tag_name") or publication.get("name") or "").strip()
    version = etiquette.lstrip("vV")
    corps = str(publication.get("body") or "")
    if not version:
        return {"disponible": False}

    return {
        "disponible": comparer(version, version_courante) > 0,
        "version": version,
        "url": str(publication.get("html_url") or ""),
        "reinstallation": MARQUEUR_REINSTALLATION.lower() in corps.lower(),
        "date": str(publication.get("published_at") or ""),
    }


def verifier(version_courante: str = VERSION, forcer: bool = False) -> dict:
    """
    Regarde s'il existe une version plus récente. N'affiche jamais rien.

    Ne doit être appelée que si l'utilisateur a activé le réglage. Renvoie
    toujours un dictionnaire ; `{"disponible": False}` couvre aussi bien
    « à jour » que « pas joignable ».
    """
    if not forcer and not verification_due():
        return {"disponible": False, "raison": "verifiee-recemment"}

    url = url_api()
    if not url:
        journal.attention("Vérification de mise à jour : adresse de dépôt inexploitable.")
        return {"disponible": False}

    _ecrire_etat({**lire_etat(), "derniere": datetime.now().isoformat(timespec="seconds")})

    try:
        publication = _interroger(url)
    except (urllib.error.URLError, OSError, TimeoutError, ValueError) as exc:
        # Hors ligne, pare-feu, GitHub en panne, réponse illisible : rien à
        # l'écran, une ligne de journal, et on réessaiera demain.
        journal.attention("Vérification de mise à jour sans réponse : %s", exc)
        return {"disponible": False}

    resultat = analyser_release(publication, version_courante)
    if resultat.get("disponible"):
        journal.info(
            "Mise à jour disponible : %s (installée : %s)%s",
            resultat.get("version"), version_courante,
            ", réinstallation demandée" if resultat.get("reinstallation") else "",
        )
        _ecrire_etat({
            **lire_etat(),
            "derniere_vue": resultat.get("version", ""),
        })
    else:
        journal.info("Vérification de mise à jour : l'application est à jour.")
    return resultat
