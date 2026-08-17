"""
Transcripteur local — point d'entrée.

Fenêtre pywebview, interface web dans `web/`, moteur faster-whisper.
Tout se passe sur la machine : aucun envoi vers un service en ligne.

Lancement : double-clic sur ce fichier, ou « lancer.bat ».
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
import threading
import webbrowser
from pathlib import Path

RACINE = Path(__file__).resolve().parent
if str(RACINE) not in sys.path:
    sys.path.insert(0, str(RACINE))

from app import VERSION, NOM_APPLICATION, chemins, journal  # noqa: E402

journal.demarrer()
journal.purger()
journal.silence_bibliotheques()


# ---------------------------------------------------------------------------
# Vérification des dépendances : message clair plutôt qu'un traceback
# ---------------------------------------------------------------------------

def _dependances_manquantes() -> list[str]:
    import importlib.util

    requis = {
        "webview": "pywebview",
        "faster_whisper": "faster-whisper",
        "numpy": "numpy",
    }
    return [
        paquet for module, paquet in requis.items()
        if importlib.util.find_spec(module) is None
    ]


def _abandonner(titre: str, message: str) -> None:
    journal.erreur("%s : %s", titre, message)
    try:
        import tkinter as tk
        from tkinter import messagebox

        racine = tk.Tk()
        racine.withdraw()
        messagebox.showerror(titre, message)
        racine.destroy()
    except Exception:
        print(f"{titre}\n\n{message}", file=sys.stdout)
    sys.exit(1)


_manquants = _dependances_manquantes()
if _manquants:
    _abandonner(
        NOM_APPLICATION,
        "Il manque des composants pour démarrer :\n\n  "
        + "\n  ".join(_manquants)
        + "\n\nLancez « installer.bat » à côté de l'application, il pose tout "
          "automatiquement. Installation manuelle :\n\n  pip install "
        + " ".join(_manquants),
    )

import webview  # noqa: E402
from webview.dom import DOMEventHandler  # noqa: E402

from app import audio as audio_module  # noqa: E402
from app import config as config_module  # noqa: E402
from app import diarisation, materiel, presets, traitement, vocabulaire  # noqa: E402

_SANS_FENETRE = subprocess.CREATE_NO_WINDOW if sys.platform == "win32" else 0


def _json(valeur) -> str:
    return json.dumps(valeur, ensure_ascii=False)


class Passerelle:
    """Objet exposé à l'interface web sous le nom `pywebview.api`."""

    def __init__(self):
        self.fenetre = None
        self.config = config_module.charger()
        self.materiel = materiel.detecter()
        self.file = traitement.FileTraitement(self.materiel)
        self._rappels = traitement.Rappels(
            etat=self._sur_etat,
            progression=self._sur_progression,
            termine=self._sur_fichier_termine,
            journal_ui=self._sur_journal,
            file_terminee=self._sur_file_terminee,
        )

    # -- utilitaires -------------------------------------------------------

    def _js(self, appel: str) -> None:
        try:
            if self.fenetre is not None:
                self.fenetre.evaluate_js(appel)
        except Exception as exc:
            journal.debug("Appel JavaScript ignoré : %s", exc)

    def _fond(self, fonction) -> None:
        threading.Thread(target=fonction, daemon=True).start()

    # -- rappels de la file ------------------------------------------------

    def _sur_etat(self, identifiant: str, etat: str, message: str) -> None:
        self._js(f"onEtat({_json(identifiant)}, {_json(etat)}, {_json(message)})")

    def _sur_progression(self, identifiant: str, donnees: dict) -> None:
        self._js(f"onProgression({_json(identifiant)}, {_json(donnees)})")

    def _sur_fichier_termine(self, identifiant: str, donnees: dict) -> None:
        self._js(f"onFichierTermine({_json(identifiant)}, {_json(donnees)})")
        if donnees.get("ok"):
            self.charger_historique()

    def _sur_journal(self, niveau: str, texte: str) -> None:
        self._js(f"onJournal({_json(niveau)}, {_json(texte)})")

    def _sur_file_terminee(self, donnees: dict) -> None:
        self._js(f"onFileTerminee({_json(donnees)})")

    # -- état initial ------------------------------------------------------

    def etat_initial(self) -> dict:
        chemins.assurer_dossiers()
        glossaire = vocabulaire.resume_glossaire()
        manque_diarisation = diarisation.indisponibilite()

        return {
            "version": VERSION,
            "nom": NOM_APPLICATION,
            "config": self.config,
            "materiel": self.materiel.en_dict(),
            "recommandation": presets.recommandation(self.materiel),
            "presets": [
                {
                    "cle": p["cle"],
                    "nom": p["nom"],
                    "resume": p["resume"],
                    "modele": moteur_nom_court(p["modele"]),
                    "telechargement": f"{p['telechargement_go']:.1f} Go".replace(".", ","),
                    "facteur": presets.facteur_temps_reel(p["cle"], self.materiel),
                    "pour_une_heure": presets.formater_duree(
                        presets.estimer_secondes(3600, p["cle"], self.materiel)
                    ),
                }
                for p in presets.PRESETS.values()
            ],
            "modeles_avances": presets.MODELES_AVANCES,
            "glossaire": {
                "contenu": vocabulaire.lire_glossaire(),
                "resume": glossaire,
            },
            "corrections": {
                "contenu": vocabulaire.lire_corrections(),
                "nb": glossaire.get("nb_corrections", 0),
                "erreurs": glossaire.get("erreurs_corrections", []),
            },
            "diarisation": {
                "disponible": not manque_diarisation,
                "indisponibilite": manque_diarisation,
                "jeton_present": diarisation.jeton_present(),
                "guide": diarisation.guide(),
            },
            "ffmpeg": audio_module.ffmpeg_present(),
            "journal": journal.nom_fichier(),
            "avertissements": presets.avertissements(
                self.config.get("preset", "qualite"), self.materiel,
                bool(self.config.get("diarisation")),
                self.config.get("modele_avance", "") if self.config.get("mode_avance") else "",
            ),
        }

    # -- réglages ----------------------------------------------------------

    def sauver_config(self, partiel: dict) -> dict:
        for cle, valeur in (partiel or {}).items():
            if cle not in config_module.DEFAUTS:
                continue
            if isinstance(self.config.get(cle), dict) and isinstance(valeur, dict):
                self.config[cle].update(valeur)
            else:
                self.config[cle] = valeur
        config_module.sauver(self.config)
        return {
            "config": self.config,
            "avertissements": presets.avertissements(
                self.config.get("preset", "qualite"), self.materiel,
                bool(self.config.get("diarisation")),
                self.config.get("modele_avance", "") if self.config.get("mode_avance") else "",
            ),
        }

    def sauver_glossaire(self, contenu: str) -> dict:
        vocabulaire.ecrire_glossaire(contenu or "")
        resume = vocabulaire.construire_amorce(contenu or "")
        journal.info("Glossaire enregistré : %s termes", resume["nb_termes"])
        return resume

    def sauver_corrections(self, contenu: str) -> dict:
        vocabulaire.ecrire_corrections(contenu or "")
        regles, erreurs = vocabulaire.analyser_corrections(contenu or "")
        journal.info("Corrections enregistrées : %s règles, %s erreurs", len(regles), len(erreurs))
        return {"nb": len(regles), "erreurs": erreurs}

    def enregistrer_jeton(self, valeur: str) -> dict:
        valeur = (valeur or "").strip()
        if valeur and not valeur.startswith("hf_"):
            return {
                "ok": False,
                "message": "Un jeton Hugging Face commence par « hf_ ». Vérifiez le copier-coller.",
            }
        diarisation.enregistrer_jeton(valeur)
        if not valeur:
            return {"ok": True, "message": "Jeton effacé."}
        return {
            "ok": True,
            "message": "Jeton enregistré. Il sera vérifié au premier usage de la séparation des locuteurs.",
        }

    def estimation(self, duree_secs: float, cle_preset: str, diarisation_active: bool,
                   modele_avance: str = "") -> str:
        return presets.formater_duree(
            presets.estimer_secondes(duree_secs, cle_preset, self.materiel,
                                     bool(diarisation_active), modele_avance or "")
        )

    # -- fichiers ----------------------------------------------------------

    def ajouter_fichiers(self) -> None:
        self._fond(self._dialogue_fichiers)

    def _dialogue_fichiers(self) -> None:
        extensions = " ".join(f"*{e}" for e in sorted(audio_module.EXTENSIONS_AUDIO))
        try:
            resultat = self.fenetre.create_file_dialog(
                webview.OPEN_DIALOG, allow_multiple=True,
                file_types=(f"Fichiers audio et vidéo ({extensions})", "Tous les fichiers (*.*)"),
            )
        except Exception as exc:
            journal.exception("Ouverture du sélecteur de fichiers impossible", exc)
            return
        if resultat:
            self._enregistrer_fichiers(list(resultat))

    def _enregistrer_fichiers(self, liste: list[str]) -> None:
        ajoutes = self.file.ajouter(liste)
        if not ajoutes:
            self._sur_journal("attention", "Aucun fichier audio exploitable dans ce dépôt.")
            return
        self._js(f"onFichiersAjoutes({_json(ajoutes)})")
        self._sur_journal(
            "info",
            f"{len(ajoutes)} fichier{'s' if len(ajoutes) > 1 else ''} ajouté"
            f"{'s' if len(ajoutes) > 1 else ''} à la file.",
        )
        self.file.mesurer_durees(
            lambda identifiant, secondes, texte:
            self._js(f"onDuree({_json(identifiant)}, {secondes}, {_json(texte)})")
        )

    def retirer(self, identifiant: str) -> None:
        self.file.retirer(identifiant)

    def vider_file(self) -> None:
        self.file.vider()

    def choisir_dossier_sortie(self) -> None:
        self._fond(self._dialogue_dossier)

    def _dialogue_dossier(self) -> None:
        try:
            resultat = self.fenetre.create_file_dialog(
                webview.FOLDER_DIALOG,
                directory=self.config.get("dossier_sortie", "") or str(Path.home()),
            )
        except Exception as exc:
            journal.exception("Ouverture du sélecteur de dossier impossible", exc)
            return
        if resultat:
            chemin = resultat[0] if isinstance(resultat, (list, tuple)) else resultat
            self.config["dossier_sortie"] = str(chemin)
            config_module.sauver(self.config)
            self._js(f"onDossierSortie({_json(str(chemin))})")
            self.charger_historique()

    # -- exécution ---------------------------------------------------------

    def demarrer(self) -> dict:
        if self.file.occupee:
            return {"ok": False, "message": "Une transcription est déjà en cours."}
        if not audio_module.ffmpeg_present():
            return {
                "ok": False,
                "message": "FFmpeg est introuvable. Relancez « installer.bat » pour le poser.",
            }
        dossier = Path(self.config.get("dossier_sortie") or "")
        try:
            dossier.mkdir(parents=True, exist_ok=True)
        except OSError as exc:
            return {
                "ok": False,
                "message": f"Le dossier de sortie n'est pas accessible en écriture ({exc.strerror}).",
            }

        if self.config.get("diarisation"):
            manque = diarisation.indisponibilite()
            if manque:
                self._sur_journal("attention", f"Séparation des locuteurs ignorée : {manque}")
            elif not diarisation.jeton_present():
                self._sur_journal(
                    "attention",
                    "Aucun jeton Hugging Face : la transcription se fera sans étiquettes de locuteur.",
                )

        lancee = self.file.demarrer(self.config, self._rappels)
        if not lancee:
            return {"ok": False, "message": "Aucun fichier en attente dans la file."}
        self._sur_journal("info", "Démarrage de la file.")
        return {"ok": True}

    def arreter(self) -> None:
        self.file.arreter()
        self._sur_journal("attention", "Arrêt demandé, la transcription en cours va s'interrompre.")

    # -- historique et ouverture -------------------------------------------

    def charger_historique(self) -> None:
        self._fond(self._lire_historique)

    def _lire_historique(self) -> None:
        dossier = Path(self.config.get("dossier_sortie") or "")
        elements: list[dict] = []
        if dossier.is_dir():
            fichiers = [
                f for f in dossier.iterdir()
                if f.is_file() and f.suffix.lower() in (".txt", ".srt", ".vtt")
            ]
            fichiers.sort(key=lambda f: f.stat().st_mtime, reverse=True)
            for fichier in fichiers[:40]:
                import datetime as dt

                horodatage = dt.datetime.fromtimestamp(fichier.stat().st_mtime)
                elements.append({
                    "nom": fichier.name,
                    "chemin": str(fichier),
                    "format": fichier.suffix.lstrip(".").upper(),
                    "date": f"{horodatage:%d/%m/%Y à %H:%M}",
                    "taille": audio_module.formater_taille(fichier.stat().st_size),
                })
        self._js(f"onHistorique({_json(elements)})")

    def lire_texte(self, chemin: str) -> str:
        try:
            texte = Path(chemin).read_text(encoding="utf-8")
            return texte[:200000]
        except OSError as exc:
            journal.attention("Lecture impossible de %s : %s", chemin, exc)
            return ""

    def ouvrir(self, chemin: str) -> None:
        cible = Path(chemin or "")
        if not cible.exists():
            self._sur_journal("attention", "Ce fichier n'existe plus.")
            return
        try:
            if sys.platform == "win32":
                os.startfile(str(cible))  # noqa: S606
            elif sys.platform == "darwin":
                subprocess.Popen(["open", str(cible)])
            else:
                subprocess.Popen(["xdg-open", str(cible)])
        except Exception as exc:
            journal.exception("Ouverture impossible", exc)

    def ouvrir_dossier_sortie(self) -> None:
        self.ouvrir(self.config.get("dossier_sortie", ""))

    def ouvrir_journal(self) -> None:
        self.ouvrir(str(journal.fichier()))

    def ouvrir_dossier_application(self) -> None:
        self.ouvrir(str(chemins.RACINE))

    def ouvrir_lien(self, url: str) -> None:
        if str(url).startswith(("http://", "https://")):
            webbrowser.open(url)

    def copier(self, texte: str) -> None:
        """Copie via l'API Windows, plus fiable que le presse-papiers du navigateur intégré."""
        try:
            if sys.platform == "win32":
                subprocess.run(
                    ["clip"], input=(texte or "").encode("utf-16-le"),
                    creationflags=_SANS_FENETRE, check=False,
                )
        except Exception as exc:
            journal.debug("Copie impossible : %s", exc)


def moteur_nom_court(modele: str) -> str:
    from app.moteur import nom_court

    return nom_court(modele)


# ---------------------------------------------------------------------------
# Glisser-déposer
# ---------------------------------------------------------------------------

def _installer_depot(passerelle: Passerelle, fenetre) -> None:
    """
    Branche le dépôt de fichiers sur la zone prévue.

    pywebview complète chaque fichier déposé avec `pywebviewFullPath`, seul moyen
    d'obtenir le chemin réel : un navigateur ne le donne jamais au JavaScript.
    """
    def sur_depot(evenement):
        try:
            fichiers = (evenement.get("dataTransfer") or {}).get("files") or []
            chemins_deposes = [
                f.get("pywebviewFullPath") for f in fichiers if f.get("pywebviewFullPath")
            ]
            if chemins_deposes:
                passerelle._enregistrer_fichiers(chemins_deposes)
            else:
                passerelle._sur_journal(
                    "attention",
                    "Le chemin des fichiers déposés n'a pas pu être lu. Utilisez le bouton « Parcourir ».",
                )
        except Exception as exc:
            journal.exception("Dépôt de fichiers en échec", exc)
        finally:
            passerelle._js("finDepot()")

    try:
        # Sur le corps entier : déposer n'importe où dans la fenêtre fonctionne.
        zone = fenetre.dom.body or fenetre.dom.get_element("#zone-depot")
        zone.events.drop += DOMEventHandler(sur_depot, prevent_default=True, stop_propagation=True)
        journal.info("Glisser-déposer actif")
    except Exception as exc:
        journal.exception("Activation du glisser-déposer impossible", exc)


def _au_demarrage(passerelle: Passerelle, fenetre) -> None:
    _installer_depot(passerelle, fenetre)
    passerelle.charger_historique()


def principal() -> None:
    journal.info("%s v%s", NOM_APPLICATION, VERSION)
    passerelle = Passerelle()

    fenetre = webview.create_window(
        f"{NOM_APPLICATION}",
        url=str(chemins.DOSSIER_WEB / "index.html"),
        js_api=passerelle,
        width=1180, height=780, min_size=(920, 620),
        background_color="#12151b",
        text_select=True,
    )
    passerelle.fenetre = fenetre
    fenetre.events.loaded += lambda: _au_demarrage(passerelle, fenetre)

    try:
        webview.start(debug=bool(os.environ.get("TRANSCRIPTEUR_DEBUG")))
    except Exception as exc:
        journal.exception("La fenêtre n'a pas pu s'ouvrir", exc)
        _abandonner(
            NOM_APPLICATION,
            "La fenêtre n'a pas pu s'ouvrir.\n\nSous Windows, cela vient presque "
            "toujours de « Microsoft Edge WebView2 Runtime », absent du poste. "
            "Installez-le puis relancez.\n\nDétail : "
            f"logs/{journal.nom_fichier()}",
        )


if __name__ == "__main__":
    principal()
