"""
WhiScribe — point d'entrée.

Fenêtre pywebview, interface web dans `web/`, moteur faster-whisper.
Tout se passe sur la machine : aucun envoi vers un service en ligne.

Lancement : double-clic sur ce fichier, ou « lancer.bat ».

Option de diagnostic, utilisée par la chaîne de publication :

    transcriber.pyw --verifier

vérifie les imports, la présence de FFmpeg et l'écriture des dossiers de
travail, affiche un bilan, et sort avec le code 0 si tout va bien.
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
import threading
import webbrowser
from pathlib import Path

if not getattr(sys, "frozen", False):
    RACINE = Path(__file__).resolve().parent
    if str(RACINE) not in sys.path:
        sys.path.insert(0, str(RACINE))

from app import VERSION, NOM_APPLICATION, chemins, journal  # noqa: E402

journal.demarrer()
journal.purger()
journal.silence_bibliotheques()


# ---------------------------------------------------------------------------
# Mode « --verifier » : bilan en ligne de commande, sans ouvrir de fenêtre
# ---------------------------------------------------------------------------

def verification() -> int:
    """
    Contrôle que l'installation est complète et utilisable.

    Sert à valider une version installée sans aucune interaction : imports,
    binaire FFmpeg, interface web présente, et écriture réelle dans les dossiers
    de travail. Renvoie 0 si tout est en ordre, 1 sinon.
    """
    lignes: list[str] = []
    tout_va_bien = True

    def resultat(reussi: bool, etiquette: str, detail: str = "") -> None:
        nonlocal tout_va_bien
        if not reussi:
            tout_va_bien = False
        marque = "OK   " if reussi else "ECHEC"
        lignes.append(f"  {marque}  {etiquette}" + (f" : {detail}" if detail else ""))

    lignes.append(f"{NOM_APPLICATION} v{VERSION}")
    lignes.append(f"  Mode          : {'version installée' if chemins.EST_GELE else 'sources'}")
    lignes.append(f"  Ressources    : {chemins.DOSSIER_RESSOURCES}")
    lignes.append(f"  Données       : {chemins.RACINE}")
    lignes.append(f"  Modèles       : {chemins.DOSSIER_MODELES}")
    lignes.append("")

    for module, etiquette in (
        ("webview", "interface de fenêtre (pywebview)"),
        ("faster_whisper", "moteur de transcription (faster-whisper)"),
        ("ctranslate2", "calcul (CTranslate2)"),
        ("numpy", "calcul numérique (numpy)"),
        ("tokenizers", "tokeniseur (tokenizers)"),
        ("huggingface_hub", "téléchargement des modèles (huggingface_hub)"),
        ("psutil", "détection du matériel (psutil)"),
    ):
        try:
            __import__(module)
            resultat(True, etiquette)
        except Exception as exc:
            resultat(False, etiquette, f"{type(exc).__name__}: {exc}")

    # Interface web : sans elle la fenêtre s'ouvrirait vide.
    page = chemins.DOSSIER_WEB / "index.html"
    resultat(page.is_file(), "interface web (web/index.html)", "" if page.is_file() else str(page))

    # FFmpeg : présence du binaire, puis exécution réelle.
    try:
        from app import audio as audio_verif

        binaire = audio_verif.binaire_ffmpeg()
        sortie = subprocess.run(
            [binaire, "-version"], capture_output=True, text=True, errors="replace",
            timeout=30, creationflags=(subprocess.CREATE_NO_WINDOW if sys.platform == "win32" else 0),
        )
        premiere = (sortie.stdout or "").splitlines()[0] if sortie.stdout else ""
        resultat(sortie.returncode == 0, "décodeur audio (FFmpeg)", premiere or binaire)
    except Exception as exc:
        resultat(False, "décodeur audio (FFmpeg)", f"{type(exc).__name__}: {exc}")

    # Écriture des dossiers de travail : c'est le point qui casse quand une
    # version installée essaie encore d'écrire dans son dossier de programme.
    try:
        chemins.assurer_dossiers()
        temoin = chemins.DOSSIER_LOGS / "verification.tmp"
        temoin.write_text("ok", encoding="utf-8")
        temoin.unlink(missing_ok=True)
        resultat(True, "écriture des journaux", str(chemins.DOSSIER_LOGS))
    except Exception as exc:
        resultat(False, "écriture des journaux", f"{type(exc).__name__}: {exc}")

    message = chemins.dossier_modeles_inscriptible(chemins.DOSSIER_MODELES)
    resultat(not message, "écriture du dossier des modèles", message or str(chemins.DOSSIER_MODELES))

    try:
        config_verif = __import__("app.config", fromlist=["charger"])
        config_verif.charger()
        config_verif.sauver(config_verif.charger())
        resultat(True, "lecture et écriture de la configuration", str(chemins.FICHIER_CONFIG))
    except Exception as exc:
        resultat(False, "configuration", f"{type(exc).__name__}: {exc}")

    # Détection matérielle et presets : ce sont les premiers appels de l'interface.
    try:
        from app import materiel as materiel_verif
        from app import presets as presets_verif

        mat = materiel_verif.detecter()
        presets_verif.recommandation(mat)
        resultat(True, "détection du matériel", f"{mat.fils_calcul} fils, {mat.ram_go:.0f} Go")
    except Exception as exc:
        resultat(False, "détection du matériel", f"{type(exc).__name__}: {exc}")

    lignes.append("")
    lignes.append("  Bilan : tout est en place." if tout_va_bien
                  else "  Bilan : installation incomplète, voir les lignes ECHEC.")
    lignes.append("")

    texte = "\n".join(lignes)
    try:
        print(texte)
    except Exception:
        pass
    journal.info("Vérification :\n%s", texte)
    # Toujours un double du bilan sur disque : sous pythonw.exe, il n'y a pas de console.
    try:
        (chemins.DOSSIER_LOGS / "verification.txt").write_text(texte + "\n", encoding="utf-8")
    except OSError:
        pass
    return 0 if tout_va_bien else 1


# L'exécutable « whiscribe-verifier.exe » produit par PyInstaller n'a pas d'autre
# raison d'être : il déclenche la vérification même sans argument.
_NOM_EXECUTABLE = Path(sys.argv[0] if sys.argv else "").stem.lower()
if "--verifier" in sys.argv or _NOM_EXECUTABLE.endswith("verifier"):
    sys.exit(verification())


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
        + (
            "\n\nL'installation est incomplète ou abîmée. Réinstallez "
            "l'application depuis son programme d'installation."
            if chemins.EST_GELE else
            "\n\nLancez « installer.bat » à côté de l'application, il pose tout "
            "automatiquement. Installation manuelle :\n\n  pip install "
            + " ".join(_manquants)
        ),
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
        self._fenetre = None
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
            if self._fenetre is not None:
                self._fenetre.evaluate_js(appel)
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
            "modeles": self.infos_modeles(),
            "version_installee": chemins.EST_GELE,
            "avertissements": self._avertissements(),
        }

    def _avertissements(self) -> list[str]:
        """Garde-fous matériels, plus l'annonce du téléchargement à venir."""
        messages = presets.avertissements(
            self.config.get("preset", "qualite"), self.materiel,
            bool(self.config.get("diarisation")),
            self.config.get("modele_avance", "") if self.config.get("mode_avance") else "",
        )
        annonce = self._annonce_telechargement()
        if annonce:
            messages.insert(0, annonce)
        return messages

    def _modele_courant(self) -> str:
        avance = self.config.get("modele_avance", "") if self.config.get("mode_avance") else ""
        return presets.modele_du_preset(self.config.get("preset", "qualite"), avance)

    def _annonce_telechargement(self) -> str:
        """
        Phrase affichée quand le modèle choisi n'est pas encore sur la machine.

        C'est le seul moment où l'application a besoin d'Internet : il faut le
        dire avant, avec la taille, et pas au milieu d'une transcription.
        """
        from app import moteur

        modele = self._modele_courant()
        try:
            if moteur.modele_deja_telecharge(modele):
                return ""
        except Exception:
            return ""
        taille = moteur.taille_annoncee(modele)
        return (
            f"Le modèle « {moteur.nom_court(modele)} » n'est pas encore sur cette machine. "
            f"Il sera téléchargé une seule fois au lancement de la première transcription, "
            f"environ {taille}, dans « {chemins.DOSSIER_MODELES} ». Une connexion Internet "
            "est nécessaire pour cette étape, et pour elle seulement : ensuite l'application "
            "fonctionne entièrement hors ligne."
        )

    # -- dossier des modèles ------------------------------------------------

    def infos_modeles(self) -> dict:
        """État du dossier des modèles, pour le panneau des réglages."""
        dossier = chemins.DOSSIER_MODELES
        from app import moteur

        etat_presets = []
        for p in presets.PRESETS.values():
            try:
                present = moteur.modele_deja_telecharge(p["modele"])
            except Exception:
                present = False
            etat_presets.append({
                "cle": p["cle"],
                "nom": p["nom"],
                "modele": moteur.nom_court(p["modele"]),
                "taille": f"{p['telechargement_go']:.1f} Go".replace(".", ","),
                "present": present,
            })

        return {
            "dossier": str(dossier),
            "defaut": str(chemins.dossier_modeles_defaut()),
            "personnalise": chemins.FICHIER_CHOIX_MODELES.exists(),
            "occupe": presets.nombre_fr(chemins.taille_dossier_go(dossier)) + " Go",
            "libre": presets.nombre_fr(chemins.espace_libre_go(dossier)) + " Go",
            "presets": etat_presets,
        }

    def choisir_dossier_modeles(self) -> None:
        self._fond(self._dialogue_dossier_modeles)

    def _dialogue_dossier_modeles(self) -> None:
        try:
            resultat = self._fenetre.create_file_dialog(
                webview.FOLDER_DIALOG, directory=str(chemins.DOSSIER_MODELES),
            )
        except Exception as exc:
            journal.exception("Ouverture du sélecteur de dossier impossible", exc)
            return
        if not resultat:
            return
        chemin = resultat[0] if isinstance(resultat, (list, tuple)) else resultat
        self._js(f"onDossierModeles({_json(self.definir_dossier_modeles(str(chemin)))})")

    def definir_dossier_modeles(self, chemin: str) -> dict:
        """
        Change l'emplacement des modèles. Les modèles déjà téléchargés ne sont
        pas déplacés : ils seront simplement retéléchargés au besoin, et l'ancien
        dossier reste sur le disque, à l'utilisateur de le vider s'il le souhaite.
        """
        texte = (chemin or "").strip()
        ancien = str(chemins.DOSSIER_MODELES)

        if texte:
            probleme = chemins.dossier_modeles_inscriptible(texte)
            if probleme:
                return {"ok": False, "message": probleme, "modeles": self.infos_modeles()}

        nouveau = chemins.definir_dossier_modeles(texte, memoriser=True)
        chemins.assurer_dossiers()
        journal.info("Dossier des modèles : %s (était %s)", nouveau, ancien)

        message = f"Les modèles seront rangés dans « {nouveau} »."
        if str(nouveau) != ancien and chemins.taille_dossier_go(ancien) > 0.05:
            message += (
                f" L'ancien dossier « {ancien} » n'a pas été touché, vous pouvez le "
                "supprimer si vous n'en avez plus besoin."
            )
        return {
            "ok": True,
            "message": message,
            "modeles": self.infos_modeles(),
            "avertissements": self._avertissements(),
        }

    def ouvrir_dossier_modeles(self) -> None:
        chemins.assurer_dossiers()
        self.ouvrir(str(chemins.DOSSIER_MODELES))

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
            "avertissements": self._avertissements(),
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
            resultat = self._fenetre.create_file_dialog(
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
            resultat = self._fenetre.create_file_dialog(
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
                "message": (
                    "Le décodeur audio FFmpeg est introuvable. "
                    + ("Réinstallez l'application depuis son programme d'installation."
                       if chemins.EST_GELE
                       else "Relancez « installer.bat » pour le poser.")
                ),
            }
        dossier = Path(self.config.get("dossier_sortie") or "")
        try:
            dossier.mkdir(parents=True, exist_ok=True)
        except OSError as exc:
            return {
                "ok": False,
                "message": f"Le dossier de sortie n'est pas accessible en écriture ({exc.strerror}).",
            }

        refus = self._verifier_modele_disponible()
        if refus:
            return refus

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

    def _verifier_modele_disponible(self) -> dict | None:
        """
        Contrôles préalables au premier téléchargement d'un modèle.

        Renvoie un refus expliqué si le modèle manque et que rien ne permet de
        l'obtenir (pas de réseau, pas de place), sinon None. Quand le modèle
        manque mais que tout est réuni, on se contente d'annoncer la taille.
        """
        from app import moteur

        modele = self._modele_courant()
        try:
            if moteur.modele_deja_telecharge(modele):
                return None
        except Exception:
            return None

        taille = moteur.taille_annoncee(modele)
        dossier = chemins.DOSSIER_MODELES

        probleme = chemins.dossier_modeles_inscriptible(dossier)
        if probleme:
            return {
                "ok": False,
                "message": (
                    f"Le modèle doit être téléchargé, mais le dossier prévu « {dossier} » "
                    f"n'est pas utilisable. {probleme} Choisissez un autre emplacement dans "
                    "les réglages, section « Modèles »."
                ),
            }

        libre = chemins.espace_libre_go(dossier)
        requis = 0.0
        for p in presets.PRESETS.values():
            if p["modele"] == modele:
                requis = p["telechargement_go"] * 1.3
        if libre and requis and libre < requis:
            return {
                "ok": False,
                "message": (
                    f"Il faut environ {taille} pour télécharger ce modèle, et il ne reste "
                    f"que {presets.nombre_fr(libre)} Go sur le disque de « {dossier} ». "
                    "Libérez de la place, ou rangez les modèles sur un autre disque dans "
                    "les réglages, section « Modèles »."
                ),
            }

        if not moteur.connexion_disponible():
            return {
                "ok": False,
                "message": (
                    f"Ce modèle n'est pas encore sur la machine, il pèse environ {taille} et "
                    "doit être téléchargé une première fois. Or aucune connexion Internet "
                    "n'a été trouvée. Connectez le poste le temps de ce téléchargement, "
                    "ensuite l'application fonctionnera définitivement hors ligne. "
                    "Si un modèle plus léger vous suffit, le preset « Rapide » demande "
                    "1,6 Go au lieu de 3,1 Go."
                ),
            }

        self._sur_journal(
            "attention",
            f"Premier usage de ce modèle : téléchargement d'environ {taille} vers "
            f"« {dossier} ». Cela n'arrive qu'une fois, ensuite tout reste sur la machine.",
        )
        return None

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
    passerelle._fenetre = fenetre
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
