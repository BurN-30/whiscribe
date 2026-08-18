"""
WhiScribe : paquet applicatif.

Moteur unique : faster-whisper (CTranslate2), CPU int8 partout, CUDA float16
si une carte NVIDIA est detectee. Diarisation optionnelle via pyannote.audio,
sequencee apres la transcription pour limiter le pic memoire.
"""

VERSION = "2.2.1"
NOM_APPLICATION = "WhiScribe"

# Source unique de l'adresse du depot. A ajuster une seule fois ici si le nom du
# depot change : l'interface et la recette PyInstaller la relisent. Le script
# Inno Setup la porte de son cote, dans packaging/setup.iss.
URL_PROJET = "https://github.com/BurN-30/whiscribe"
EDITEUR = "Nathan SACCOL"
