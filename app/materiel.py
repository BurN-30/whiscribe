"""
Detection du materiel et recommandation.

Objectif : afficher honnetement ce que la machine sait faire, et rien de plus.
CTranslate2 (le moteur de faster-whisper) n'accelere que sur NVIDIA. Les cartes
AMD et Intel sont donc detectees et affichees, mais annoncees comme non
accelerees en v1.

Aucune dependance obligatoire : psutil est utilise s'il est present, sinon on
retombe sur la bibliotheque standard et sur l'API Windows via ctypes.
"""

from __future__ import annotations

import os
import platform
import shutil
import subprocess
import sys
from dataclasses import dataclass, field, asdict

from . import journal

_CACHE: "Materiel | None" = None

_SANS_FENETRE = subprocess.CREATE_NO_WINDOW if sys.platform == "win32" else 0

# Seuils de mémoire vive, en gigaoctets.
# 16 Go tient pour large-v3 en int8 plus la diarisation, à condition de séquencer
# les deux étapes (voir moteur.py). En dessous de 10 Go on déconseille large-v3.
SEUIL_MEMOIRE_CONFORTABLE = 20.0
SEUIL_MEMOIRE_CRITIQUE = 10.0


@dataclass
class Gpu:
    nom: str
    vendeur: str  # "nvidia" | "amd" | "intel" | "autre"
    memoire_mo: int = 0
    accelere: bool = False
    note: str = ""


@dataclass
class Accelerateur:
    """Circuit d'accélération detecte mais non exploite en v1 (NPU par exemple)."""

    nom: str
    genre: str = "npu"
    note: str = ""


@dataclass
class Materiel:
    cpu_nom: str = "Processeur inconnu"
    coeurs_physiques: int = 0
    coeurs_logiques: int = 0
    ram_go: float = 0.0
    ram_libre_go: float = 0.0
    gpus: list[Gpu] = field(default_factory=list)
    npus: list[Accelerateur] = field(default_factory=list)
    a_nvidia: bool = False
    cuda_disponible: bool = False
    systeme: str = ""

    @property
    def peripherique(self) -> str:
        return "cuda" if self.cuda_disponible else "cpu"

    @property
    def type_calcul(self) -> str:
        return "float16" if self.cuda_disponible else "int8"

    @property
    def fils_calcul(self) -> int:
        """Laisse deux coeurs au systeme pour que la machine reste utilisable."""
        total = self.coeurs_logiques or os.cpu_count() or 4
        return max(1, total - 2)

    def en_dict(self) -> dict:
        donnees = asdict(self)
        donnees["peripherique"] = self.peripherique
        donnees["type_calcul"] = self.type_calcul
        donnees["fils_calcul"] = self.fils_calcul
        donnees["resume"] = self.resume()
        donnees["memoire_serree"] = self.memoire_serree
        donnees["memoire_tres_serree"] = self.memoire_tres_serree
        return donnees

    @property
    def memoire_serree(self) -> bool:
        """Sous 20 Go, large-v3 plus diarisation demande de la prudence."""
        return 0 < self.ram_go < SEUIL_MEMOIRE_CONFORTABLE

    @property
    def memoire_tres_serree(self) -> bool:
        """Sous 10 Go, large-v3 n'est pas raisonnable."""
        return 0 < self.ram_go < SEUIL_MEMOIRE_CRITIQUE

    def resume(self) -> str:
        morceaux = [self.cpu_nom]
        if self.coeurs_logiques:
            coeurs = f"{self.coeurs_logiques} fils"
            if self.coeurs_physiques and self.coeurs_physiques != self.coeurs_logiques:
                coeurs = f"{self.coeurs_physiques} cœurs / {self.coeurs_logiques} fils"
            morceaux.append(coeurs)
        if self.ram_go:
            morceaux.append(f"{self.ram_go:.0f} Go de mémoire")
        if self.cuda_disponible:
            nvidia = next((g for g in self.gpus if g.vendeur == "nvidia"), None)
            morceaux.append(f"{nvidia.nom if nvidia else 'GPU NVIDIA'} (accéléré)")
        elif self.gpus:
            morceaux.append(f"{self.gpus[0].nom} (non accéléré en v1)")
        else:
            morceaux.append("pas de carte graphique dédiée")
        if self.npus:
            morceaux.append(f"{self.npus[0].nom} (non exploité)")
        return ", ".join(morceaux)


# ---------------------------------------------------------------------------
# Collecte
# ---------------------------------------------------------------------------

def _nom_cpu() -> str:
    if sys.platform == "win32":
        try:
            import winreg

            cle = winreg.OpenKey(
                winreg.HKEY_LOCAL_MACHINE,
                r"HARDWARE\DESCRIPTION\System\CentralProcessor\0",
            )
            valeur, _ = winreg.QueryValueEx(cle, "ProcessorNameString")
            winreg.CloseKey(cle)
            nom = " ".join(str(valeur).split())
            if nom:
                return nom
        except OSError:
            pass
    nom = platform.processor() or platform.machine()
    return nom or "Processeur inconnu"


def _coeurs() -> tuple[int, int]:
    logiques = os.cpu_count() or 0
    physiques = 0
    try:
        import psutil  # type: ignore

        physiques = psutil.cpu_count(logical=False) or 0
        logiques = psutil.cpu_count(logical=True) or logiques
    except Exception:
        pass
    return physiques, logiques


def _memoire() -> tuple[float, float]:
    """Renvoie (total, libre) en Go."""
    try:
        import psutil  # type: ignore

        memoire = psutil.virtual_memory()
        return memoire.total / 1024 ** 3, memoire.available / 1024 ** 3
    except Exception:
        pass

    if sys.platform == "win32":
        try:
            import ctypes

            class _Statut(ctypes.Structure):
                _fields_ = [
                    ("dwLength", ctypes.c_ulong),
                    ("dwMemoryLoad", ctypes.c_ulong),
                    ("ullTotalPhys", ctypes.c_ulonglong),
                    ("ullAvailPhys", ctypes.c_ulonglong),
                    ("ullTotalPageFile", ctypes.c_ulonglong),
                    ("ullAvailPageFile", ctypes.c_ulonglong),
                    ("ullTotalVirtual", ctypes.c_ulonglong),
                    ("ullAvailVirtual", ctypes.c_ulonglong),
                    ("ullAvailExtendedVirtual", ctypes.c_ulonglong),
                ]

            statut = _Statut()
            statut.dwLength = ctypes.sizeof(_Statut)
            ctypes.windll.kernel32.GlobalMemoryStatusEx(ctypes.byref(statut))
            return statut.ullTotalPhys / 1024 ** 3, statut.ullAvailPhys / 1024 ** 3
        except Exception:
            pass

    try:
        pages = os.sysconf("SC_PHYS_PAGES")
        taille = os.sysconf("SC_PAGE_SIZE")
        total = pages * taille / 1024 ** 3
        return total, total
    except (ValueError, AttributeError, OSError):
        return 0.0, 0.0


def _vendeur(nom: str, fabricant: str = "") -> str:
    texte = f"{nom} {fabricant}".lower()
    if "nvidia" in texte or "geforce" in texte or "quadro" in texte or "rtx" in texte:
        return "nvidia"
    if "advanced micro" in texte or "amd" in texte or "radeon" in texte:
        return "amd"
    if "intel" in texte or "arc(" in texte or "uhd graphics" in texte or "iris" in texte:
        return "intel"
    return "autre"


def _cartes_graphiques() -> list[Gpu]:
    cartes: list[Gpu] = []
    if sys.platform != "win32":
        return cartes

    commande = [
        "powershell", "-NoProfile", "-NonInteractive", "-Command",
        "Get-CimInstance Win32_VideoController | "
        "Select-Object Name,AdapterCompatibility,AdapterRAM | ConvertTo-Json -Compress",
    ]
    try:
        resultat = subprocess.run(
            commande, capture_output=True, text=True, timeout=20,
            creationflags=_SANS_FENETRE,
        )
        sortie = (resultat.stdout or "").strip()
        if sortie:
            import json

            donnees = json.loads(sortie)
            if isinstance(donnees, dict):
                donnees = [donnees]
            for entree in donnees:
                nom = (entree.get("Name") or "").strip()
                if not nom:
                    continue
                fabricant = (entree.get("AdapterCompatibility") or "").strip()
                ram = entree.get("AdapterRAM") or 0
                try:
                    memoire_mo = max(0, int(ram) // (1024 * 1024))
                except (TypeError, ValueError):
                    memoire_mo = 0
                cartes.append(Gpu(nom=nom, vendeur=_vendeur(nom, fabricant), memoire_mo=memoire_mo))
    except Exception as exc:  # pragma: no cover - depend du poste
        journal.debug("Detection GPU impossible : %s", exc)

    return cartes


def _accelerateurs_neuronaux() -> list[Accelerateur]:
    """
    Repere un NPU (Intel AI Boost sur Meteor Lake, AMD XDNA, Qualcomm Hexagon).

    Purement informatif : aucun de ces circuits n'est exploite en v1. On les
    affiche pour que l'utilisateur sache ce que sa machine possede.
    """
    trouves: list[Accelerateur] = []
    if sys.platform != "win32":
        return trouves

    commande = [
        "powershell", "-NoProfile", "-NonInteractive", "-Command",
        "Get-CimInstance Win32_PnPEntity | "
        # Motif volontairement strict : un « NPU » non délimité attrape « Input ».
        "Where-Object { $_.Name -match 'AI Boost|Neural Processor|\\bNPU\\b|XDNA|Hexagon NPU' } | "
        "Select-Object -ExpandProperty Name -Unique",
    ]
    try:
        resultat = subprocess.run(
            commande, capture_output=True, text=True, timeout=25,
            creationflags=_SANS_FENETRE,
        )
        for ligne in (resultat.stdout or "").splitlines():
            nom = ligne.strip()
            if not nom:
                continue
            trouves.append(Accelerateur(
                nom=nom,
                genre="npu",
                note=(
                    "Détecté, non exploité en v1. Un NPU vise surtout l'autonomie sur "
                    "batterie ; la piste OpenVINO est documentée comme évolution v1.x."
                ),
            ))
    except Exception as exc:  # pragma: no cover - depend du poste
        journal.debug("Detection NPU impossible : %s", exc)

    return trouves


def _nvidia_present() -> bool:
    """Detection sans torch : la presence de nvidia-smi signe le pilote NVIDIA."""
    if shutil.which("nvidia-smi") is None:
        return False
    try:
        resultat = subprocess.run(
            ["nvidia-smi"], capture_output=True, timeout=15, creationflags=_SANS_FENETRE
        )
        return resultat.returncode == 0
    except Exception:
        return False


def _cuda_utilisable() -> bool:
    """CTranslate2 voit-il vraiment un peripherique CUDA exploitable ?"""
    try:
        import ctranslate2  # type: ignore

        return ctranslate2.get_cuda_device_count() > 0
    except Exception:
        return False


def detecter(forcer: bool = False) -> Materiel:
    global _CACHE
    if _CACHE is not None and not forcer:
        return _CACHE

    physiques, logiques = _coeurs()
    total, libre = _memoire()
    cartes = _cartes_graphiques()
    neuronaux = _accelerateurs_neuronaux()
    nvidia = any(c.vendeur == "nvidia" for c in cartes) or _nvidia_present()
    cuda = nvidia and _cuda_utilisable()

    for carte in cartes:
        if carte.vendeur == "nvidia":
            carte.accelere = cuda
            carte.note = (
                "Accélération CUDA active." if cuda else
                "Carte NVIDIA détectée mais les bibliothèques CUDA de CTranslate2 ne "
                "répondent pas. Relancez l'installateur pour les poser."
            )
        elif carte.vendeur == "amd":
            carte.note = (
                "Non accéléré en v1 : CTranslate2 ne gère que CPU et CUDA. "
                "L'accélération AMD via whisper.cpp Vulkan est prévue en v1.x."
            )
        elif carte.vendeur == "intel":
            carte.note = (
                "Circuit graphique intégré, détecté mais non exploité en v1 : la "
                "transcription tourne sur le processeur. Pistes v1.x : whisper.cpp "
                "Vulkan, ou OpenVINO."
            )
        else:
            carte.note = "Non accéléré en v1."

    _CACHE = Materiel(
        cpu_nom=_nom_cpu(),
        coeurs_physiques=physiques,
        coeurs_logiques=logiques,
        ram_go=total,
        ram_libre_go=libre,
        gpus=cartes,
        npus=neuronaux,
        a_nvidia=nvidia,
        cuda_disponible=cuda,
        systeme=f"{platform.system()} {platform.release()}",
    )

    journal.info("Matériel : %s", _CACHE.resume())
    journal.info(
        "Profil retenu : périphérique=%s, type de calcul=%s, fils=%s",
        _CACHE.peripherique, _CACHE.type_calcul, _CACHE.fils_calcul,
    )
    return _CACHE
