"""
Moteur de transcription : faster-whisper (CTranslate2).

Choix d'architecture assumé pour la v1 : un seul moteur.
  - CPU partout en int8, c'est le meilleur rapport vitesse / mémoire / qualité ;
  - CUDA float16 uniquement si une carte NVIDIA répond.

Le modèle est chargé puis explicitement libéré : la diarisation ne démarre
jamais tant que le modèle de transcription occupe encore la mémoire. C'est ce
séquencement qui permet de faire tenir large-v3 plus pyannote dans 16 Go.

TÉLÉCHARGEMENT ET REPRISE
-------------------------
Le téléchargement des poids est celui de faster-whisper, qui appelle
`huggingface_hub.snapshot_download`. Depuis huggingface_hub 0.23, la reprise
d'un téléchargement coupé est le comportement d'origine, `resume_download` n'a
plus à être passé et ne l'est nulle part ici : chaque fichier est reçu sous un
nom « .incomplete » puis renommé une fois complet. C'est en revanche muet sur
le cas qui nous occupe, un dossier de modèle laissé sans ses poids : le dépôt
est alors vu comme présent en cache et le chargement échoue. La garde ci-dessous
(`etat_modele`, `reparer_modele`) traite ce cas au lancement suivant.
"""

from __future__ import annotations

import gc
import os
import shutil
import stat
from dataclasses import dataclass, field
from pathlib import Path
from typing import Callable

import numpy as np

from . import audio as audio_module
from . import chemins, journal, langues, presets
from .journal import ErreurLisible
from .materiel import Materiel

# Repli de température : on part de 0 pour un décodage déterministe, et on ne
# remonte que si le décodage échoue sur un segment.
REPLI_TEMPERATURE = (0.0, 0.2, 0.4, 0.6, 0.8, 1.0)


@dataclass
class Mot:
    """
    Un mot et la probabilité que le modèle lui accorde.

    faster-whisper la fournit d'origine avec `word_timestamps=True`, sans
    surcoût notable. Elle sert à signaler dans la vue de lecture les passages
    entendus avec le moins de certitude, ceux qu'il vaut mieux réécouter.
    """

    texte: str
    debut: float
    fin: float
    probabilite: float


@dataclass
class Segment:
    debut: float
    fin: float
    texte: str
    locuteur: str = ""
    mots: list[Mot] = field(default_factory=list)


def identifiant_depot(modele: str) -> str:
    """Nom du dépôt Hugging Face correspondant à un nom court de modèle."""
    try:
        from faster_whisper.utils import _MODELS  # type: ignore

        return _MODELS.get(modele, modele)
    except Exception:
        return modele


# ---------------------------------------------------------------------------
# Intégrité d'un modèle déjà présent sur le disque
#
# Un téléchargement interrompu laisse le dossier du modèle en place, sans ses
# poids. huggingface_hub considère alors le dépôt comme « en cache » et
# faster-whisper échoue à l'ouverture avec un RuntimeError sur « model.bin ».
# L'utilisateur n'y peut rien depuis l'interface : c'est donc à l'application de
# reconnaître cet état et de le réparer elle-même.
#
# Deux formes de rangement coexistent selon la version de huggingface_hub et les
# privilèges du poste : les vrais fichiers sous « blobs/ » avec des liens
# symboliques dans « snapshots/<hash>/ », ou, sous Windows sans privilège, de
# vraies copies directement dans le snapshot. On ne regarde donc jamais la seule
# existence d'un chemin, toujours la taille du fichier réellement atteint, ce
# qui traverse le lien symbolique et démasque un lien mort.
# ---------------------------------------------------------------------------

#: Fichier de poids produit par CTranslate2, dans le snapshot du dépôt.
NOM_POIDS = "model.bin"

#: Fichiers que faster-whisper lit à côté des poids, et sans lesquels il refuse
#: de démarrer aussi sûrement que sans « model.bin ».
FICHIERS_ATTENDUS = ("config.json",)

#: Taille en dessous de laquelle un « model.bin » est tenu pour tronqué. Le plus
#: petit modèle publié, « tiny », pèse déjà 75 Mo : 8 Mo laisse une marge large,
#: aucun poids réel ne passe en dessous, et un fichier amorcé puis coupé n'a
#: aucune raison de passer au-dessus par hasard.
TAILLE_MINIMALE_POIDS = 8 * 1024 * 1024

#: Préfixe des dossiers de cache de huggingface_hub. Sert aussi de garde-fou :
#: rien qui ne porte ce préfixe ne sera jamais supprimé.
PREFIXE_CACHE = "models--"

#: Suffixe posé par huggingface_hub sur un fichier en cours de réception.
SUFFIXE_INCOMPLET = ".incomplete"


def _racine_modeles(racine: str | Path | None = None) -> Path:
    return Path(str(racine)) if racine else Path(chemins.DOSSIER_MODELES)


def dossier_cache_modele(modele: str, racine: str | Path | None = None) -> Path:
    """Dossier de cache attendu pour un modèle, « models--Systran--faster-whisper-large-v3 »."""
    depot = identifiant_depot(modele)
    return _racine_modeles(racine) / (PREFIXE_CACHE + depot.replace("/", "--"))


def _taille_reelle(chemin: Path) -> int | None:
    """Taille du fichier réellement atteint, None s'il manque ou si le lien est mort."""
    try:
        return chemin.stat().st_size
    except OSError:
        return None


def _fichiers_en_cours(dossier: Path) -> int:
    """Nombre de fichiers « .incomplete » laissés par un téléchargement coupé."""
    try:
        return sum(1 for f in dossier.rglob("*" + SUFFIXE_INCOMPLET))
    except OSError:
        return 0


def _analyser_snapshot(snapshot: Path) -> tuple[str, str]:
    """(« complet » ou « incomplet », motif) pour un dossier contenant les poids."""
    poids = snapshot / NOM_POIDS
    taille = _taille_reelle(poids)
    if taille is None:
        return "incomplet", f"{NOM_POIDS} absent de « {snapshot.name} »"
    if taille < TAILLE_MINIMALE_POIDS:
        return "incomplet", f"{NOM_POIDS} tronqué, {taille} octets"
    manquants = [nom for nom in FICHIERS_ATTENDUS if _taille_reelle(snapshot / nom) is None]
    if manquants:
        return "incomplet", "fichier(s) manquant(s) : " + ", ".join(manquants)
    return "complet", ""


def _analyser_cache(dossier: Path) -> tuple[str, str]:
    """(état, motif) pour un dossier de cache huggingface déjà présent."""
    en_cours = _fichiers_en_cours(dossier)
    if en_cours:
        return "incomplet", f"{en_cours} fichier(s) encore en cours de réception"

    snapshots = dossier / "snapshots"
    try:
        candidats = sorted(d for d in snapshots.iterdir() if d.is_dir())
    except OSError:
        candidats = []
    if not candidats:
        return "incomplet", "aucun instantané téléchargé"

    motifs: list[str] = []
    for snapshot in candidats:
        etat, motif = _analyser_snapshot(snapshot)
        if etat == "complet":
            return "complet", ""
        motifs.append(motif)
    return "incomplet", " ; ".join(motifs)


def _snapshot_resolu(modele: str) -> Path | None:
    """Snapshot tel que faster-whisper le résoudrait, sans le moindre appel réseau."""
    try:
        from faster_whisper.utils import download_model

        return Path(download_model(
            modele, local_files_only=True, cache_dir=str(chemins.DOSSIER_MODELES)))
    except Exception:
        return None


def modele_supprimable(modele: str, racine: str | Path | None = None) -> bool:
    """
    L'application s'autorise-t-elle à effacer le dossier de ce modèle ?

    Oui uniquement pour un dossier de cache qu'elle a elle-même créé : le bon
    préfixe, enfant direct du dossier des modèles, et présent sur le disque.
    Jamais un dossier de modèle désigné à la main par l'utilisateur.
    """
    if Path(str(modele or "")).is_dir():
        return False
    dossier = dossier_cache_modele(modele, racine)
    if not dossier.is_dir():
        return False
    if not dossier.name.startswith(PREFIXE_CACHE) or len(dossier.name) <= len(PREFIXE_CACHE):
        return False
    try:
        return dossier.parent.resolve() == _racine_modeles(racine).resolve()
    except OSError:
        return False


def etat_modele(modele: str, racine: str | Path | None = None) -> dict:
    """
    État d'un modèle sur ce poste, avant tout chargement.

    Trois réponses possibles, et une seule demande une action :

      - « absent » : rien sur le disque, c'est le premier usage, déjà géré ;
      - « complet » : les poids sont là et utilisables, rien à faire ;
      - « incomplet » : le dossier existe mais les poids manquent ou sont
        tronqués, il faut l'effacer et retélécharger.

    `reparable` dit si l'application s'autorise à supprimer ce dossier : jamais
    un dossier de modèle désigné à la main par l'utilisateur, uniquement un
    dossier de cache qu'elle a elle-même créé sous le dossier des modèles.
    """
    fourni = Path(str(modele or ""))
    if fourni.is_dir():
        etat, motif = _analyser_snapshot(fourni)
        return {"etat": etat, "dossier": str(fourni), "motif": motif, "reparable": False}

    dossier = dossier_cache_modele(modele, racine)
    if dossier.is_dir():
        etat, motif = _analyser_cache(dossier)
        return {
            "etat": etat,
            "dossier": str(dossier),
            "motif": motif,
            "reparable": etat == "incomplet" and modele_supprimable(modele, racine),
        }

    # Le dossier n'est pas là où on l'attend : plutôt que de conclure trop vite
    # à l'absence, on laisse faster-whisper résoudre le cache à sa façon. Un
    # modèle bien présent ne doit jamais être annoncé comme à télécharger, un
    # poste hors ligne s'en trouverait bloqué pour rien.
    resolu = _snapshot_resolu(modele) if racine is None else None
    if resolu is not None and resolu.is_dir():
        etat, motif = _analyser_snapshot(resolu)
        return {"etat": etat, "dossier": str(resolu), "motif": motif, "reparable": False}

    return {"etat": "absent", "dossier": str(dossier), "motif": "", "reparable": False}


def modele_deja_telecharge(modele: str) -> bool:
    """
    Le modèle est-il sur le disque ET utilisable ?

    Raccourci de lecture sur `etat_modele`, conservé parce qu'il se lit mieux
    là où seule la réponse binaire compte. Un modèle incomplet répond non : le
    donner pour présent laisserait croire qu'il est prêt à servir.
    """
    try:
        return etat_modele(modele)["etat"] == "complet"
    except Exception:
        return False


def _forcer_suppression(fonction, chemin, _infos) -> None:
    """Deuxième chance sur un fichier en lecture seule, fréquent dans un cache."""
    try:
        os.chmod(chemin, stat.S_IWRITE)
        fonction(chemin)
    except OSError:
        pass


def supprimer_modele(modele: str, racine: str | Path | None = None) -> bool:
    """
    Efface le dossier de cache d'un seul modèle, et rien d'autre.

    Trois gardes avant le moindre effacement : le dossier porte le préfixe des
    caches huggingface, il est un enfant direct du dossier des modèles, et il
    existe. Un chemin qui manque une seule de ces conditions n'est pas touché.
    """
    dossier = dossier_cache_modele(modele, racine)
    parent = _racine_modeles(racine)
    try:
        legitime = (
            dossier.name.startswith(PREFIXE_CACHE)
            and len(dossier.name) > len(PREFIXE_CACHE)
            and dossier.parent.resolve() == parent.resolve()
        )
    except OSError:
        legitime = False
    if not legitime:
        journal.attention("Suppression refusée, chemin inattendu : %s", dossier)
        return False
    if not dossier.is_dir():
        return False

    journal.info("Suppression du modèle incomplet : %s", dossier)
    try:
        shutil.rmtree(dossier, onerror=_forcer_suppression)
    except OSError as exc:
        journal.attention("Suppression de %s impossible : %s", dossier, exc)

    # Le verrou posé par huggingface_hub à côté ne gêne personne s'il subsiste,
    # mais autant ne rien laisser derrière soi.
    verrou = parent / ".locks" / dossier.name
    if verrou.is_dir():
        shutil.rmtree(verrou, ignore_errors=True)

    return not dossier.exists()


def reparer_modele(modele: str, etat: dict | None = None,
                   signaler: Callable[[str, str], None] | None = None) -> bool:
    """
    Efface un modèle incomplet pour que le téléchargement reparte de zéro.

    Le retéléchargement lui-même est fait par faster-whisper juste après, avec
    les mêmes messages que le premier usage : il n'y a rien à dupliquer ici.
    """
    etat = etat or etat_modele(modele)
    journal.attention(
        "Modèle %s incomplet (%s), dossier %s",
        nom_court(modele), etat.get("motif") or "cause non identifiée", etat.get("dossier"),
    )
    supprime = supprimer_modele(modele)
    if signaler:
        if supprime:
            signaler("attention", langues.t(
                "moteur.modele_incomplet",
                modele=nom_court(modele), taille=taille_annoncee(modele)))
        else:
            signaler("attention", langues.t(
                "moteur.modele_incomplet_bloque",
                modele=nom_court(modele), dossier=etat.get("dossier", "")))
    return supprime


def _poids_illisible(exc: BaseException) -> bool:
    """L'exception de faster-whisper qui trahit des poids absents ou tronqués."""
    texte = f"{type(exc).__name__}: {exc}".lower()
    return NOM_POIDS in texte or "unable to open file" in texte


class MoteurTranscription:
    """Enveloppe autour de WhisperModel, avec libération explicite."""

    def __init__(self, mat: Materiel, forcer_processeur: bool = False):
        self.materiel = mat
        self.forcer_processeur = forcer_processeur
        self._modele = None
        self._nom_modele = ""

    # -- cycle de vie ------------------------------------------------------

    @property
    def peripherique(self) -> str:
        if self.forcer_processeur:
            return "cpu"
        return self.materiel.peripherique

    @property
    def type_calcul(self) -> str:
        return "float16" if self.peripherique == "cuda" else "int8"

    def charger(self, modele: str, signaler: Callable[[str, str], None] | None = None) -> None:
        if self._modele is not None and self._nom_modele == modele:
            return
        self.liberer()

        chemins.assurer_dossiers()

        # Un modèle laissé à moitié téléchargé est réparé avant tout appel à
        # faster-whisper : sans cela, il lève un RuntimeError illisible sur
        # « model.bin » et la file s'arrête sur un incident que l'utilisateur ne
        # peut résoudre que depuis un terminal.
        etat = etat_modele(modele)
        if etat["etat"] == "incomplet" and etat["reparable"]:
            reparer_modele(modele, etat, signaler)
        elif etat["etat"] == "absent" and signaler:
            signaler("attention", langues.t(
                "moteur.premier_usage", taille=taille_annoncee(modele)))

        journal.info(
            "Chargement du modèle %s (périphérique=%s, calcul=%s, fils=%s, état=%s)",
            modele, self.peripherique, self.type_calcul, self.materiel.fils_calcul,
            etat["etat"],
        )
        if signaler:
            signaler("info", langues.t("moteur.chargement", modele=_nom_court(modele)))

        try:
            self._modele = self._instancier(modele)
        except Exception as exc:
            # Filet de sécurité : une forme de cache que la détection n'aurait
            # pas su lire se trahit ici. Une seule reprise, jamais de boucle.
            if not _poids_illisible(exc) or not modele_supprimable(modele):
                journal.exception(f"Chargement du modèle {modele} impossible", exc)
                raise
            journal.attention("Poids illisibles au chargement, réparation puis nouvel essai")
            reparer_modele(modele, signaler=signaler)
            try:
                self._modele = self._instancier(modele)
            except Exception as second:
                journal.exception(f"Chargement du modèle {modele} impossible", second)
                raise
        self._nom_modele = modele

    def _instancier(self, modele: str):
        from faster_whisper import WhisperModel

        with journal.SortieMuette("chargement du modèle"):
            return WhisperModel(
                modele,
                device=self.peripherique,
                compute_type=self.type_calcul,
                cpu_threads=self.materiel.fils_calcul,
                num_workers=1,
                download_root=str(chemins.DOSSIER_MODELES),
            )

    def liberer(self) -> None:
        """Déréférence le modèle et rend la mémoire avant l'étape suivante."""
        if self._modele is None:
            return
        journal.info("Libération du modèle %s", self._nom_modele)
        self._modele = None
        self._nom_modele = ""
        gc.collect()

    @property
    def tokeniseur(self):
        return getattr(self._modele, "hf_tokenizer", None)

    # -- transcription -----------------------------------------------------

    def transcrire(
        self,
        signal: np.ndarray,
        duree_totale: float,
        langue: str,
        reglages: dict,
        amorce: str = "",
        progression: Callable[[float], None] | None = None,
        interrompu: Callable[[], bool] | None = None,
        decalage: float = 0.0,
        sur_segment: Callable[[Segment], None] | None = None,
    ) -> tuple[list[Segment], dict]:
        """
        Transcrit un signal déjà décodé.

        `decalage` déplace tous les horodatages : il vaut zéro en temps normal,
        et la position atteinte quand on reprend une transcription interrompue,
        où seule la fin du signal est repassée au modèle.

        `sur_segment` est appelé pour chaque segment dès qu'il sort du décodeur.
        C'est le point d'accroche de la sauvegarde progressive : le moteur
        produit déjà les segments un par un, rien n'est mis en tampon pour lui.
        """
        if self._modele is None:
            raise ErreurLisible(
                langues.t("moteur.non_charge.titre"),
                langues.t("moteur.non_charge.msg"),
            )

        beam = int(reglages.get("beam_size") or 5)
        options = dict(
            language=(langue or None) if langue != "auto" else None,
            task="transcribe",
            beam_size=beam,
            best_of=max(beam, int(reglages.get("best_of") or beam)),
            temperature=list(REPLI_TEMPERATURE),
            condition_on_previous_text=bool(reglages.get("condition_on_previous_text", True)),
            initial_prompt=amorce or None,
            vad_filter=bool(reglages.get("vad", True)),
            word_timestamps=True,
            no_speech_threshold=0.6,
            compression_ratio_threshold=2.4,
            hallucination_silence_threshold=2.0 if reglages.get("vad", True) else None,
        )
        if options["vad_filter"]:
            options["vad_parameters"] = {"min_silence_duration_ms": 500}

        journal.info(
            "Transcription : langue=%s, beam=%s, VAD=%s, amorce=%s caractères",
            langue, beam, options["vad_filter"], len(amorce),
        )

        with journal.SortieMuette("transcription"):
            iterateur, info = self._modele.transcribe(signal, **options)

            segments: list[Segment] = []
            for brut in iterateur:
                if interrompu is not None and interrompu():
                    journal.attention("Transcription interrompue à la demande de l'utilisateur")
                    raise Interruption()
                texte = (brut.text or "").strip()
                if texte:
                    segment = Segment(
                        debut=brut.start + decalage,
                        fin=brut.end + decalage,
                        texte=texte,
                        mots=_mots_du_segment(brut, decalage),
                    )
                    segments.append(segment)
                    if sur_segment is not None:
                        sur_segment(segment)
                if progression and duree_totale > 0:
                    progression(min(0.99, (brut.end + decalage) / duree_totale))

        if progression:
            progression(1.0)

        details = {
            "langue": getattr(info, "language", langue),
            "probabilite_langue": round(float(getattr(info, "language_probability", 0) or 0), 3),
            "duree": float(getattr(info, "duration", duree_totale) or duree_totale),
            "modele": self._nom_modele,
            "peripherique": self.peripherique,
            "type_calcul": self.type_calcul,
        }
        journal.info(
            "Transcription terminée : %s segments, langue détectée %s",
            len(segments), details["langue"],
        )
        return segments, details


def _mots_du_segment(brut, decalage: float = 0.0) -> list[Mot]:
    """
    Extrait les mots et leur probabilité d'un segment de faster-whisper.

    Le décodeur les fournit déjà, `word_timestamps` étant activé pour attribuer
    les locuteurs. Un modèle ou une version qui ne les donnerait pas renvoie
    simplement une liste vide, et la vue de lecture s'en passe.
    """
    resultat: list[Mot] = []
    for mot in getattr(brut, "words", None) or []:
        texte = (getattr(mot, "word", "") or "").strip()
        if not texte:
            continue
        resultat.append(Mot(
            texte=texte,
            debut=float(getattr(mot, "start", 0.0) or 0.0) + decalage,
            fin=float(getattr(mot, "end", 0.0) or 0.0) + decalage,
            probabilite=float(getattr(mot, "probability", 0.0) or 0.0),
        ))
    return resultat


class Interruption(Exception):
    """Levée quand l'utilisateur demande l'arrêt de la file."""


def nom_court(modele: str) -> str:
    """« deepdml/faster-whisper-large-v3-turbo-ct2 » devient « large-v3-turbo »."""
    if "/" in modele:
        nom = modele.rsplit("/", 1)[1]
        return nom.replace("faster-whisper-", "").replace("-ct2", "")
    return modele


_nom_court = nom_court  # compatibilité interne


def connexion_disponible(delai: float = 4.0) -> bool:
    """
    Teste si le dépôt de modèles est joignable, avant de lancer un téléchargement.

    Une simple ouverture de socket : pas de requête, rien d'envoyé. Cela évite de
    présenter un traceback réseau à quelqu'un dont le poste est simplement isolé.
    """
    import socket

    for hote in ("huggingface.co", "cdn-lfs.huggingface.co"):
        try:
            with socket.create_connection((hote, 443), timeout=delai):
                return True
        except OSError:
            continue
    return False


def taille_annoncee(modele: str) -> str:
    taille = presets.taille_modele_avance(modele)
    if taille:
        return taille
    for p in presets.PRESETS.values():
        if p["modele"] == modele:
            return langues.octets(p["telechargement_go"] * 1024 ** 3)
    return langues.t("moteur.taille_inconnue")


def limiter_parallelisme(fils: int) -> None:
    """Borne les bibliothèques de calcul pour que la machine reste utilisable."""
    valeur = str(max(1, fils))
    for variable in ("OMP_NUM_THREADS", "MKL_NUM_THREADS", "OPENBLAS_NUM_THREADS",
                     "NUMEXPR_NUM_THREADS"):
        os.environ.setdefault(variable, valeur)


def duree_et_signal(chemin: str, filtres_salle: bool) -> tuple[np.ndarray, float]:
    signal = audio_module.decoder(chemin, filtres_salle=filtres_salle)
    return signal, signal.size / audio_module.FREQUENCE
