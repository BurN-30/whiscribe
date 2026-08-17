"""
File de traitement séquentielle.

Un seul fichier à la fois, volontairement : la transcription sature déjà le
processeur, et le séquencement est ce qui garantit la tenue en mémoire.

Déroulé d'un fichier :
    décodage → transcription → libération du modèle → diarisation → corrections → écriture

Chaque étape informe l'interface via des rappels, et tout le détail technique
part dans le fichier de log.
"""

from __future__ import annotations

import gc
import threading
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Callable

from . import audio as audio_module
from . import config as config_module
from . import diarisation, journal, moteur, presets, sorties, vocabulaire
from .journal import ErreurLisible
from .materiel import Materiel

ETATS = ("attente", "decodage", "transcription", "locuteurs", "ecriture", "termine", "erreur", "annule")


@dataclass
class Element:
    identifiant: str
    chemin: str
    nom: str
    taille: int = 0
    duree: float = 0.0
    etat: str = "attente"

    def en_dict(self) -> dict:
        return {
            "id": self.identifiant,
            "chemin": self.chemin,
            "nom": self.nom,
            "taille": audio_module.formater_taille(self.taille) if self.taille else "",
            "duree_secs": round(self.duree, 1),
            "duree": presets.formater_duree(self.duree) if self.duree else "--",
            "etat": self.etat,
        }


@dataclass
class Rappels:
    """Fonctions d'information vers l'interface. Toutes optionnelles."""

    etat: Callable[[str, str, str], None] = lambda i, e, m: None
    progression: Callable[[str, dict], None] = lambda i, d: None
    termine: Callable[[str, dict], None] = lambda i, d: None
    journal_ui: Callable[[str, str], None] = lambda n, t: None
    file_terminee: Callable[[dict], None] = lambda d: None


class FileTraitement:
    def __init__(self, mat: Materiel):
        self.materiel = mat
        self.elements: list[Element] = []
        self._verrou = threading.Lock()
        self._arret = threading.Event()
        self._fil: threading.Thread | None = None
        self._en_cours = False

    # -- gestion de la file -------------------------------------------------

    @property
    def occupee(self) -> bool:
        return self._en_cours

    def ajouter(self, chemins_fichiers: list[str]) -> list[dict]:
        """Ajoute des fichiers, ignore les doublons et les formats non audio."""
        ajoutes: list[dict] = []
        with self._verrou:
            deja = {e.chemin.lower() for e in self.elements}
            for brut in chemins_fichiers:
                if not brut:
                    continue
                fichier = Path(brut)
                if not fichier.is_file():
                    continue
                if not audio_module.est_audio(fichier):
                    journal.attention("Format ignoré : %s", fichier.name)
                    continue
                if str(fichier).lower() in deja:
                    continue
                element = Element(
                    identifiant=f"f{int(time.time() * 1000)}{len(self.elements)}",
                    chemin=str(fichier),
                    nom=fichier.name,
                    taille=fichier.stat().st_size,
                )
                self.elements.append(element)
                deja.add(str(fichier).lower())
                ajoutes.append(element.en_dict())
        return ajoutes

    def retirer(self, identifiant: str) -> None:
        with self._verrou:
            self.elements = [
                e for e in self.elements
                if e.identifiant != identifiant or e.etat not in ("attente", "termine", "erreur", "annule")
            ]

    def vider(self) -> None:
        with self._verrou:
            self.elements = [e for e in self.elements if e.etat not in
                             ("attente", "termine", "erreur", "annule")]

    def mesurer_durees(self, rappel: Callable[[str, float, str], None]) -> None:
        """Mesure les durées en tâche de fond, sans bloquer l'interface."""
        def travail():
            for element in list(self.elements):
                if element.duree:
                    continue
                valeur = audio_module.duree(element.chemin)
                element.duree = valeur
                rappel(element.identifiant, round(valeur, 1), presets.formater_duree(valeur))

        threading.Thread(target=travail, daemon=True).start()

    # -- exécution ----------------------------------------------------------

    def demarrer(self, config: dict, rappels: Rappels) -> bool:
        if self._en_cours:
            return False
        attente = [e for e in self.elements if e.etat == "attente"]
        if not attente:
            return False
        self._arret.clear()
        self._en_cours = True
        self._fil = threading.Thread(
            target=self._boucle, args=(config, rappels), daemon=True
        )
        self._fil.start()
        return True

    def arreter(self) -> None:
        self._arret.set()

    def _interrompu(self) -> bool:
        return self._arret.is_set()

    def _boucle(self, config: dict, rappels: Rappels) -> None:
        reglages = config_module.reglages_effectifs(config)
        moteur.limiter_parallelisme(self.materiel.fils_calcul)

        instance = moteur.MoteurTranscription(
            self.materiel, forcer_processeur=reglages["forcer_processeur"]
        )

        reussis, echoues, annules = 0, 0, 0
        try:
            for element in list(self.elements):
                if element.etat != "attente":
                    continue
                if self._interrompu():
                    element.etat = "annule"
                    annules += 1
                    rappels.etat(element.identifiant, "annule", "Annulé")
                    continue
                try:
                    self._traiter(element, config, reglages, instance, rappels)
                    reussis += 1
                except moteur.Interruption:
                    element.etat = "annule"
                    annules += 1
                    rappels.etat(element.identifiant, "annule", "Arrêté")
                    rappels.termine(element.identifiant, {"ok": False, "annule": True})
                except Exception as exc:
                    echoues += 1
                    element.etat = "erreur"
                    incident = journal.formater_incident(exc, element.nom)
                    rappels.etat(element.identifiant, "erreur", incident["titre"])
                    rappels.journal_ui("erreur", f"{element.nom} : {incident['titre']}")
                    rappels.termine(element.identifiant, {"ok": False, **incident})
                finally:
                    instance.liberer()
                    gc.collect()
        finally:
            instance.liberer()
            gc.collect()
            self._en_cours = False
            rappels.file_terminee({
                "total": reussis + echoues + annules,
                "reussis": reussis,
                "echecs": echoues,
                "annules": annules,
            })

    # -- traitement d'un fichier -------------------------------------------

    def _traiter(self, element: Element, config: dict, reglages: dict,
                 instance: moteur.MoteurTranscription, rappels: Rappels) -> None:
        depart = time.time()
        source = Path(element.chemin)
        journal.info("=" * 60)
        journal.info("Fichier : %s", source)

        def signaler(niveau: str, texte: str) -> None:
            rappels.journal_ui(niveau, texte)

        # 1. Décodage
        element.etat = "decodage"
        rappels.etat(element.identifiant, "decodage", "Lecture du fichier")
        signal = audio_module.decoder(source, filtres_salle=reglages["filtres_salle"])
        duree_audio = signal.size / audio_module.FREQUENCE
        element.duree = duree_audio
        signaler("info", f"{element.nom} : {presets.formater_duree(duree_audio)} d'audio")

        if self._interrompu():
            raise moteur.Interruption()

        # 2. Transcription
        element.etat = "transcription"
        estimation = presets.estimer_secondes(
            duree_audio,
            reglages["preset"],
            self.materiel,
            diarisation=bool(config.get("diarisation")),
            modele_avance=reglages["modele"] if config.get("mode_avance") else "",
        )
        rappels.etat(element.identifiant, "transcription", "Transcription")

        instance.charger(reglages["modele"], signaler)

        amorce_info = {"amorce": "", "nb_retenus": 0, "message": ""}
        if config.get("utiliser_glossaire", True):
            amorce_info = vocabulaire.construire_amorce(tokeniseur=instance.tokeniseur)
            if amorce_info["amorce"]:
                signaler("info", amorce_info["message"])
                if amorce_info["tronque"]:
                    signaler("attention", "Glossaire tronqué pour tenir dans l'amorce du modèle.")

        def progression(part: float) -> None:
            ecoule = time.time() - depart
            part_transcription = 0.85 if config.get("diarisation") else 1.0
            pourcent = int(part * part_transcription * 100)
            restant = max(0.0, estimation - ecoule)
            rappels.progression(element.identifiant, {
                "pct": min(99, pourcent),
                "phase": "Transcription",
                "ecoule": presets.formater_duree(ecoule),
                "restant": presets.formater_duree(restant) if restant > 5 else "bientôt",
            })

        segments, details = instance.transcrire(
            signal, duree_audio, config.get("langue", "fr"), reglages,
            amorce=amorce_info["amorce"], progression=progression,
            interrompu=self._interrompu,
        )

        # 3. Libération AVANT la diarisation : c'est ce qui tient les 16 Go.
        instance.liberer()

        # 4. Diarisation, optionnelle et jamais bloquante
        nb_locuteurs = 0
        if config.get("diarisation") and segments:
            element.etat = "locuteurs"
            rappels.etat(element.identifiant, "locuteurs", "Séparation des locuteurs")
            rappels.progression(element.identifiant, {
                "pct": 88, "phase": "Locuteurs",
                "ecoule": presets.formater_duree(time.time() - depart), "restant": "",
            })
            try:
                tours = diarisation.diariser(
                    signal, audio_module.FREQUENCE,
                    nb_locuteurs=int(config.get("nb_locuteurs") or 0),
                    signaler=signaler, interrompu=self._interrompu,
                )
                nb_locuteurs = diarisation.attribuer(segments, tours)
                signaler("ok", f"{nb_locuteurs} locuteurs identifiés.")
            except ErreurLisible as exc:
                journal.attention("Diarisation abandonnée : %s", exc.message)
                signaler("attention", f"{exc.titre} : {exc.message} La transcription continue sans étiquettes.")
            except Exception as exc:
                incident = journal.formater_incident(exc, "diarisation")
                signaler("attention", f"{incident['titre']} : la transcription continue sans étiquettes.")

        del signal
        gc.collect()

        # 5. Corrections post-transcription
        remplacements = 0
        if config.get("appliquer_corrections", True):
            regles, erreurs = vocabulaire.analyser_corrections()
            for message in erreurs:
                signaler("attention", f"corrections.txt : {message}")
            if regles:
                for segment in segments:
                    segment.texte, nombre = vocabulaire.appliquer(segment.texte, regles)
                    remplacements += nombre
                if remplacements:
                    signaler("ok", f"{remplacements} corrections automatiques appliquées.")

        if self._interrompu():
            raise moteur.Interruption()

        # 6. Écriture
        element.etat = "ecriture"
        rappels.etat(element.identifiant, "ecriture", "Écriture des fichiers")
        temps_calcul = time.time() - depart
        details.update({
            "modele_lisible": moteur.nom_court(reglages["modele"]),
            "preset_nom": reglages["preset_nom"],
            "nb_locuteurs": nb_locuteurs,
            "diarisation_demandee": bool(config.get("diarisation")),
            "corrections_appliquees": remplacements,
            "termes_amorce": amorce_info["nb_retenus"],
            "temps_calcul": temps_calcul,
            "facteur_reel": temps_calcul / duree_audio if duree_audio else 0,
        })

        dossier = Path(config.get("dossier_sortie") or ".")
        libre = journal.espace_disque_libre(dossier if dossier.exists() else dossier.parent)
        if 0 <= libre < 50 * 1024 * 1024:
            raise ErreurLisible(
                "Disque plein",
                f"Il reste moins de 50 Mo sur le disque de destination. Libérez de "
                "l'espace puis relancez.",
            )

        produits = sorties.ecrire_tout(
            dossier, source, segments, details, config.get("formats", {"txt": True})
        )

        element.etat = "termine"
        rappels.progression(element.identifiant, {
            "pct": 100, "phase": "Terminé",
            "ecoule": presets.formater_duree(temps_calcul), "restant": "",
        })
        rappels.etat(element.identifiant, "termine", "Terminé")
        rappels.journal_ui(
            "ok",
            f"{element.nom} transcrit en {presets.formater_duree(temps_calcul)} "
            f"({details['facteur_reel']:.2f} x la durée de l'audio).",
        )
        rappels.termine(element.identifiant, {
            "ok": True,
            "sorties": produits,
            "duree": presets.formater_duree(temps_calcul),
            "facteur": round(details["facteur_reel"], 2),
            "locuteurs": nb_locuteurs,
            "corrections": remplacements,
        })
