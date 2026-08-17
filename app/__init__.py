"""
Transcripteur local : paquet applicatif.

Moteur unique : faster-whisper (CTranslate2), CPU int8 partout, CUDA float16
si une carte NVIDIA est detectee. Diarisation optionnelle via pyannote.audio,
sequencee apres la transcription pour limiter le pic memoire.
"""

VERSION = "2.0.0"
NOM_APPLICATION = "Transcripteur local"
