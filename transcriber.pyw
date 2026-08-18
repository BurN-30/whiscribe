"""
WhiScribe : point d'entrée.

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

from app import VERSION, NOM_APPLICATION, chemins, journal, langues  # noqa: E402

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
        langues.t("app.dependances.titre")
        + "\n\n  "
        + "\n  ".join(_manquants)
        + "\n\n"
        + (
            langues.t("app.dependances.installee") if chemins.EST_GELE else
            langues.t("app.dependances.sources")
            + "\n\n  pip install " + " ".join(_manquants)
        ),
    )

import webview  # noqa: E402
from webview.dom import DOMEventHandler  # noqa: E402

from app import audio as audio_module  # noqa: E402
from app import config as config_module  # noqa: E402
from app import barre_taches, diarisation, donnees, gabarit, lecture, maj  # noqa: E402
from app import materiel, nommage, presets, reprise, stockage  # noqa: E402
from app import surveillance, traitement, vocabulaire  # noqa: E402

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
        #: Dossier surveillé. Le fil ne démarre que si l'option est active.
        self.surveillant = surveillance.Surveillant(
            sur_nouveaux=self._sur_fichiers_surveilles,
            signaler=self._sur_etat_surveillance,
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
        if self.config.get("barre_taches", True):
            barre_taches.progression(int(donnees.get("pct") or 0))

    def _sur_fichier_termine(self, identifiant: str, donnees: dict) -> None:
        self._js(f"onFichierTermine({_json(identifiant)}, {_json(donnees)})")
        if donnees.get("ok"):
            self.charger_historique()

    def _sur_journal(self, niveau: str, texte: str) -> None:
        self._js(f"onJournal({_json(niveau)}, {_json(texte)})")

    def _sur_file_terminee(self, donnees: dict) -> None:
        self._js(f"onFileTerminee({_json(donnees)})")
        self._clore_barre_taches(bool(donnees.get("echecs")))

    def _clore_barre_taches(self, en_echec: bool) -> None:
        """
        Fin de file : la barre disparaît. Un échec la laisse rouge quelques
        secondes, le temps d'être vue, puis elle s'efface comme le reste.
        """
        if not self.config.get("barre_taches", True):
            return
        if not en_echec:
            barre_taches.effacer()
            return
        barre_taches.erreur()
        threading.Timer(4.0, barre_taches.effacer).start()

    def _sur_etat_surveillance(self, niveau: str, texte: str) -> None:
        """
        Le dossier surveillé change d'état : dit dans le journal, et reflété
        par l'indicateur discret de l'en-tête.
        """
        self._sur_journal(niveau, texte)
        self._js(f"onSurveillance({_json(self.surveillant.etat())})")

    def _sur_fichiers_surveilles(self, chemins_trouves: list[str]) -> None:
        """Fichiers apparus dans le dossier surveillé, ajoutés à la file."""
        ajoutes = self.file.ajouter(list(chemins_trouves))
        if not ajoutes:
            return
        self._js(f"onFichiersAjoutes({_json(ajoutes)})")
        self._sur_journal("info", langues.tn("app.veille.ajoutes", len(ajoutes)))
        self.file.mesurer_durees(
            lambda identifiant, secondes, texte:
            self._js(f"onDuree({_json(identifiant)}, {secondes}, {_json(texte)})")
        )

    # -- état initial ------------------------------------------------------

    def etat_initial(self) -> dict:
        chemins.assurer_dossiers()
        glossaire = vocabulaire.resume_glossaire(self.config.get("langue", "fr"))
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
                    "nom": presets.nom_preset(p["cle"]),
                    "resume": presets.resume_preset(p["cle"]),
                    "modele": moteur_nom_court(p["modele"]),
                    "telechargement": langues.octets(p["telechargement_go"] * 1024 ** 3),
                    "facteur": presets.facteur_temps_reel(p["cle"], self.materiel),
                    "pour_une_heure": presets.formater_duree(
                        presets.estimer_secondes(3600, p["cle"], self.materiel)
                    ),
                }
                for p in presets.PRESETS.values()
            ],
            "modeles_avances": presets.modeles_avances(),
            "langues_interface": langues.liste_langues(),
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
            "reprises": self._reprises(),
            "surveillance": self.surveillant.etat(),
            "nommage": {
                "defaut": nommage.MOTIF_DEFAUT,
                "variables": [{"cle": c, "role": r} for c, r in nommage.VARIABLES],
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
        return langues.t(
            "app.telechargement_annonce",
            modele=moteur.nom_court(modele),
            taille=moteur.taille_annoncee(modele),
            dossier=chemins.DOSSIER_MODELES,
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
                "nom": presets.nom_preset(p["cle"]),
                "modele": moteur.nom_court(p["modele"]),
                "taille": langues.octets(p["telechargement_go"] * 1024 ** 3),
                "present": present,
            })

        return {
            "dossier": str(dossier),
            "defaut": str(chemins.dossier_modeles_defaut()),
            "personnalise": chemins.FICHIER_CHOIX_MODELES.exists(),
            "occupe": langues.octets(chemins.taille_dossier_go(dossier) * 1024 ** 3),
            "libre": langues.octets(chemins.espace_libre_go(dossier) * 1024 ** 3),
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

        message = langues.t("app.modeles.range", dossier=nouveau)
        if str(nouveau) != ancien and chemins.taille_dossier_go(ancien) > 0.05:
            message += langues.t("app.modeles.ancien", ancien=ancien)
        return {
            "ok": True,
            "message": message,
            "modeles": self.infos_modeles(),
            "avertissements": self._avertissements(),
        }

    def ouvrir_dossier_modeles(self) -> None:
        chemins.assurer_dossiers()
        self.ouvrir(str(chemins.DOSSIER_MODELES))

    # -- espace occupé ------------------------------------------------------

    def mesurer_stockage(self) -> None:
        """
        Mesure l'espace occupé en tâche de fond.

        Un dossier de modèles de trois gigaoctets se parcourt en centaines de
        milliers d'appels système : le faire dans le fil de l'interface figerait
        la fenêtre. Le résultat arrive par `onStockage`.
        """
        def travail() -> None:
            try:
                mesure = stockage.mesurer()
            except Exception as exc:
                journal.exception("Mesure de l'espace occupé en échec", exc)
                mesure = {"postes": [], "total_texte": "--", "erreur": True}
            self._js(f"onStockage({_json(mesure)})")

        self._fond(travail)

    # -- nom des fichiers produits -----------------------------------------

    def apercu_motif(self, motif: str) -> dict:
        """Aperçu en direct sous le champ des réglages."""
        return nommage.apercu(motif or "")

    def enregistrer_motif(self, motif: str) -> dict:
        """
        Enregistre le motif de nommage après validation.

        Un motif refusé n'est pas écrit : l'ancien réglage reste en place, et le
        message dit pourquoi.
        """
        texte = (motif or "").strip()
        probleme = nommage.valider(texte)
        if probleme:
            return {"ok": False, "message": probleme, "motif": self.config.get("motif_sortie", "")}
        self.config["motif_sortie"] = texte
        config_module.sauver(self.config)
        journal.info("Nom des fichiers produits : %s", texte or nommage.MOTIF_DEFAUT)
        return {
            "ok": True,
            "motif": texte,
            "apercu": nommage.apercu(texte),
            "message": langues.t(
                "app.motif.defaut" if not texte else "app.motif.enregistre"),
        }

    # -- dossier surveillé --------------------------------------------------

    def configurer_surveillance(self, dossier: str, actif: bool) -> dict:
        """Applique le réglage du dossier surveillé et l'enregistre."""
        chemin = (dossier or "").strip()
        actif = bool(actif)
        if actif and not chemin:
            return {
                **self.surveillant.etat(),
                "ok": False,
                "message": langues.t("app.veille.choisir"),
            }
        if actif and not Path(chemin).expanduser().is_dir():
            return {
                **self.surveillant.etat(),
                "ok": False,
                "message": langues.t("app.veille.pas_accessible", chemin=chemin),
            }

        self.config["dossier_surveille"] = chemin
        self.config["surveillance"] = actif
        config_module.sauver(self.config)
        etat = self.surveillant.configurer(chemin, actif)
        journal.info("Surveillance %s : %s", "active" if actif else "coupée", chemin or "--")
        return {
            **etat,
            "ok": True,
            "message": (
                langues.t("app.veille.active", chemin=chemin) if actif
                else langues.t("app.veille.coupee")
            ),
        }

    def choisir_dossier_surveille(self) -> None:
        self._fond(self._dialogue_dossier_surveille)

    def _dialogue_dossier_surveille(self) -> None:
        try:
            resultat = self._fenetre.create_file_dialog(
                webview.FOLDER_DIALOG,
                directory=self.config.get("dossier_surveille", "") or str(Path.home()),
            )
        except Exception as exc:
            journal.exception("Ouverture du sélecteur de dossier impossible", exc)
            resultat = None
        if not resultat:
            # Sélection annulée : l'interface doit le savoir pour ne pas laisser
            # une bascule allumée sur un dossier qui n'existe pas.
            self._js('onDossierSurveille("")')
            return
        chemin = resultat[0] if isinstance(resultat, (list, tuple)) else resultat
        self._js(f"onDossierSurveille({_json(str(chemin))})")

    def oublier_fichiers_surveilles(self) -> dict:
        """Vide la mémoire : tout le contenu du dossier repartira en file."""
        etat = self.surveillant.oublier_tout()
        journal.info("Mémoire du dossier surveillé vidée.")
        return {
            **etat,
            "ok": True,
            "message": langues.t("app.veille.memoire_videe"),
        }

    def ouvrir_dossier_surveille(self) -> None:
        self.ouvrir(self.config.get("dossier_surveille", ""))

    # -- vérification de mise à jour ---------------------------------------

    def verifier_maj(self, forcer: bool = False) -> None:
        """
        Interroge les Releases du dépôt, uniquement si l'option est active.

        C'est ici, et nulle part ailleurs, que se garantit la promesse : option
        coupée, aucun appel réseau sortant n'est émis par l'application.
        """
        if not self.config.get("maj_verifier"):
            return

        def travail() -> None:
            try:
                resultat = maj.verifier(VERSION, forcer=bool(forcer))
            except Exception as exc:
                journal.exception("Vérification de mise à jour en échec", exc)
                return
            if resultat.get("disponible"):
                self._js(f"onMiseAJour({_json(resultat)})")

        self._fond(travail)

    # -- réglages ----------------------------------------------------------

    def sauver_config(self, partiel: dict) -> dict:
        for cle, valeur in (partiel or {}).items():
            if cle not in config_module.DEFAUTS:
                continue
            if isinstance(self.config.get(cle), dict) and isinstance(valeur, dict):
                self.config[cle].update(valeur)
            else:
                self.config[cle] = valeur
        # La langue d'interface prend effet tout de suite, y compris pour les
        # textes que Python fabrique : l'interface redemande son état juste après.
        if "langue_interface" in (partiel or {}):
            retenue = langues.definir(self.config.get("langue_interface"))
            self.config["langue_interface"] = retenue
            journal.info("Langue d'interface : %s", retenue)
        config_module.sauver(self.config)
        return {
            "config": self.config,
            "avertissements": self._avertissements(),
        }

    def sauver_glossaire(self, contenu: str) -> dict:
        vocabulaire.ecrire_glossaire(contenu or "")
        resume = vocabulaire.construire_amorce(
            contenu or "", langue=self.config.get("langue", "fr"))
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
            return {"ok": False, "message": langues.t("app.jeton.prefixe")}
        diarisation.enregistrer_jeton(valeur)
        if not valeur:
            return {"ok": True, "message": langues.t("app.jeton.efface")}
        return {"ok": True, "message": langues.t("app.jeton.enregistre")}

    # -- import et export des données personnelles -------------------------

    def _dossier_de_depart(self) -> str:
        """Dossier proposé dans les boîtes de dialogue d'import et d'export."""
        candidat = Path(self.config.get("dossier_sortie") or "")
        if candidat.is_dir():
            return str(candidat)
        documents = Path.home() / "Documents"
        return str(documents if documents.is_dir() else Path.home())

    def exporter_donnees(self) -> None:
        self._fond(self._dialogue_export)

    def _dialogue_export(self) -> None:
        try:
            resultat = self._fenetre.create_file_dialog(
                webview.SAVE_DIALOG,
                directory=self._dossier_de_depart(),
                save_filename=donnees.nom_export_propose(),
                file_types=(langues.t("arch.type"),),
            )
        except Exception as exc:
            journal.exception("Ouverture de la boîte d'enregistrement impossible", exc)
            refus = {"ok": False, "message": langues.t("app.export.fenetre")}
            self._js(f"onExportDonnees({_json(refus)})")
            return
        if not resultat:
            return
        chemin = resultat[0] if isinstance(resultat, (list, tuple)) else resultat
        self._js(f"onExportDonnees({_json(donnees.exporter(str(chemin)))})")

    def choisir_import(self) -> None:
        self._fond(self._dialogue_import)

    def _dialogue_import(self) -> None:
        try:
            resultat = self._fenetre.create_file_dialog(
                webview.OPEN_DIALOG,
                directory=self._dossier_de_depart(),
                file_types=(langues.t("arch.type"), langues.t("arch.tous_fichiers")),
            )
        except Exception as exc:
            journal.exception("Ouverture du sélecteur de fichiers impossible", exc)
            return
        if not resultat:
            return
        chemin = resultat[0] if isinstance(resultat, (list, tuple)) else resultat
        self._js(f"onApercuImport({_json(donnees.analyser(str(chemin)))})")

    def appliquer_import(self, chemin: str) -> dict:
        """Écrit réellement les données importées, après confirmation de l'utilisateur."""
        retour = donnees.importer(chemin)
        if retour.get("ok"):
            # L'objet de configuration en mémoire est périmé dès cet instant.
            self.config = config_module.charger()
            retour["config"] = self.config
            retour["avertissements"] = self._avertissements()
            retour["modeles"] = self.infos_modeles()
        return retour

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
        # Séparateur ; imposé par pywebview : « Nom (*.ext1;*.ext2) ». Avec des
        # espaces, parse_file_type refuse le filtre et le sélecteur ne s'ouvre
        # jamais (bug constaté le 18/08 : clic sur la zone de dépôt sans effet).
        extensions = ";".join(f"*{e}" for e in sorted(audio_module.EXTENSIONS_AUDIO))
        try:
            resultat = self._fenetre.create_file_dialog(
                webview.OPEN_DIALOG, allow_multiple=True,
                file_types=(langues.t("app.dialogue.audio", extensions=extensions),
                            langues.t("arch.tous_fichiers")),
            )
        except Exception as exc:
            journal.exception("Ouverture du sélecteur de fichiers impossible", exc)
            return
        if resultat:
            self._enregistrer_fichiers(list(resultat))

    def _enregistrer_depot(self, liste: list[str]) -> None:
        """
        Trie ce qui vient d'être déposé sur la fenêtre.

        Trois cas, dans cet ordre : une archive d'export WhiScribe seule propose
        l'import, un dossier livre ses fichiers audio de premier niveau, et tout
        le reste part dans la file comme avant.
        """
        chemins_deposes = [str(c) for c in liste if c]
        if not chemins_deposes:
            return

        if len(chemins_deposes) == 1 and chemins_deposes[0].lower().endswith(".zip"):
            self._js(f"onApercuImport({_json(donnees.analyser(chemins_deposes[0]))})")
            return

        fichiers: list[str] = []
        ignores = 0
        for brut in chemins_deposes:
            cible = Path(brut)
            if cible.is_dir():
                retenus, ecartes = audio_module.lister_dossier(cible)
                fichiers += retenus
                ignores += ecartes
                self._sur_journal(
                    "info" if retenus else "attention",
                    langues.t("app.depot.dossier", nom=cible.name, retenus=len(retenus))
                    + (langues.t("app.depot.ignores", n=ecartes) if ecartes else "")
                    + langues.t("app.depot.sous_dossiers"),
                )
            else:
                fichiers.append(brut)

        self._enregistrer_fichiers(fichiers)

    def _enregistrer_fichiers(self, liste: list[str]) -> None:
        ajoutes = self.file.ajouter(liste)
        if not ajoutes:
            self._sur_journal("attention", langues.t("app.depot.aucun"))
            return
        self._js(f"onFichiersAjoutes({_json(ajoutes)})")
        self._sur_journal("info", langues.tn("app.ajoutes", len(ajoutes)))
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
            return {"ok": False, "message": langues.t("app.demarrer.en_cours")}
        if not audio_module.ffmpeg_present():
            return {
                "ok": False,
                "message": langues.t(
                    "app.demarrer.ffmpeg_installee" if chemins.EST_GELE
                    else "app.demarrer.ffmpeg_sources"),
            }
        dossier = Path(self.config.get("dossier_sortie") or "")
        try:
            dossier.mkdir(parents=True, exist_ok=True)
        except OSError as exc:
            return {
                "ok": False,
                "message": langues.t("app.demarrer.sortie", erreur=exc.strerror),
            }

        refus = self._verifier_modele_disponible()
        if refus:
            return refus

        if self.config.get("diarisation"):
            manque = diarisation.indisponibilite()
            if manque:
                self._sur_journal(
                    "attention", langues.t("app.diar.ignoree", raison=manque))
            elif not diarisation.jeton_present():
                self._sur_journal("attention", langues.t("app.diar.sans_jeton"))

        lancee = self.file.demarrer(self.config, self._rappels)
        if not lancee:
            return {"ok": False, "message": langues.t("app.demarrer.file_vide")}
        self._sur_journal("info", langues.t("app.demarrer.lancee"))
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
                "message": langues.t(
                    "app.modele.dossier_inutilisable",
                    dossier=dossier, probleme=probleme),
            }

        libre = chemins.espace_libre_go(dossier)
        requis = 0.0
        for p in presets.PRESETS.values():
            if p["modele"] == modele:
                requis = p["telechargement_go"] * 1.3
        if libre and requis and libre < requis:
            return {
                "ok": False,
                "message": langues.t(
                    "app.modele.place", taille=taille,
                    libre=presets.nombre_fr(libre), dossier=dossier),
            }

        if not moteur.connexion_disponible():
            return {
                "ok": False,
                "message": langues.t("app.modele.hors_ligne", taille=taille),
            }

        self._sur_journal("attention", langues.t(
            "app.modele.premier_usage", taille=taille, dossier=dossier))
        return None

    def arreter(self) -> None:
        self.file.arreter()
        self._sur_journal("attention", langues.t("app.arret"))

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
                    "date": horodatage.strftime(langues.t("format.date_heure")),
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

    # -- vue de lecture ----------------------------------------------------

    def lire_transcription(self, chemin: str) -> dict:
        """Contenu structuré d'une transcription, pour la vue de lecture."""
        retour = lecture.charger(chemin)
        retour["lecture_audio"] = bool(self.config.get("lecture_audio"))
        return retour

    def copier_pour_ia(self, chemin: str) -> dict:
        """
        Met dans le presse-papiers le gabarit d'instructions suivi du texte.

        La copie passe par l'API Windows quand le presse-papiers du navigateur
        intégré refuse un texte de cette taille.
        """
        retour = lecture.texte_pour_ia(chemin)
        if not retour.get("ok"):
            return retour
        texte = retour["texte"]
        self.copier(texte)
        journal.info("Texte préparé pour un assistant IA : %s caractères", len(texte))
        return {
            "ok": True,
            "taille": len(texte),
            "message": langues.t("app.copie_ia", n=len(texte)),
        }

    def corriger_transcription(self, chemin: str, source: str, cible: str,
                               ajouter_regle: bool = True) -> dict:
        """Applique une correction relue au fichier, au compagnon et aux règles."""
        if not self.config.get("corrections_apprises", True):
            ajouter_regle = False
        retour = lecture.appliquer_correction(chemin, source, cible, ajouter_regle)
        if retour.get("regle_ajoutee"):
            regles, _ = vocabulaire.analyser_corrections()
            retour["nb_corrections"] = len(regles)
        return retour

    def lire_gabarit(self) -> dict:
        return {"contenu": gabarit.lire(), "chemin": str(gabarit.fichier())}

    def sauver_gabarit(self, contenu: str) -> dict:
        gabarit.ecrire(contenu or "")
        journal.info("Gabarit d'instructions enregistré.")
        return {"ok": True, "message": langues.t("app.gabarit_enregistre")}

    # -- reprise d'une transcription interrompue ---------------------------

    def _reprises(self) -> list[dict]:
        elements = []
        for item in reprise.lister():
            elements.append({
                **item,
                "position_texte": presets.formater_duree(item["position"]),
                "duree_texte": presets.formater_duree(item["duree_audio"]),
                "ecoule_texte": presets.formater_duree(item["ecoule"]),
            })
        return elements

    def liste_reprises(self) -> list[dict]:
        return self._reprises()

    def reprendre(self, cle: str) -> dict:
        """Remet en file un fichier interrompu, à l'endroit où il s'était arrêté."""
        etat = reprise.lire_etat(cle or "")
        if not etat:
            return {"ok": False, "message": langues.t("app.reprise.indisponible")}
        ajoute = self.file.ajouter_pour_reprise(etat.get("source", ""), cle)
        if not ajoute:
            return {"ok": False, "message": langues.t("app.reprise.introuvable")}
        self._js(f"onFichiersAjoutes({_json([ajoute])})")
        self._sur_journal("info", langues.t(
            "app.reprise.remise", nom=ajoute["nom"],
            position=presets.formater_duree(float(etat.get("position", 0) or 0)),
        ))
        return {"ok": True, "reprises": self._reprises()}

    def oublier_reprise(self, cle: str) -> dict:
        reprise.oublier(cle or "")
        return {"ok": True, "reprises": self._reprises()}

    def ouvrir(self, chemin: str) -> None:
        cible = Path(chemin or "")
        if not cible.exists():
            self._sur_journal("attention", langues.t("app.fichier_disparu"))
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
                passerelle._enregistrer_depot(chemins_deposes)
            else:
                passerelle._sur_journal(
                    "attention", langues.t("app.depot.chemin_illisible"))
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
    # Traces de reprise devenues sans objet : fichier source disparu, ou plus
    # vieilles que la rétention. Rien de visible, juste du ménage.
    passerelle._fond(reprise.purger)

    # Barre de progression de l'icône : la fenêtre existe maintenant, elle se
    # retrouve par son titre. Sans elle, le module reste simplement inerte.
    if passerelle.config.get("barre_taches", True):
        passerelle._fond(lambda: barre_taches.definir_fenetre(NOM_APPLICATION))

    # Dossier surveillé : le fil ne démarre que si l'utilisateur l'a demandé.
    if passerelle.config.get("surveillance") and passerelle.config.get("dossier_surveille"):
        # Sans adoption : ce qui est arrivé pendant que l'application était
        # fermée est bien nouveau, et la mémoire persistante empêche de
        # reprendre ce qui a déjà été transcrit.
        passerelle.surveillant.configurer(
            str(passerelle.config.get("dossier_surveille") or ""), True, adopter=False
        )

    # Vérification de mise à jour : seul appel réseau sortant possible, et
    # seulement si l'utilisateur l'a activée. La méthode le revérifie.
    passerelle.verifier_maj()


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
            langues.t("app.fenetre_impossible", journal=journal.nom_fichier()),
        )


if __name__ == "__main__":
    principal()
