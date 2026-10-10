"""Transcription locale (faster-whisper sur CPU) — votre voix ne part pas chez un tiers."""
from __future__ import annotations

import logging
import os
import re

import numpy as np

log = logging.getLogger("jarvis.stt")

# phrases que Whisper « entend » dans le silence ou le bruit (artefacts d'entraînement)
HALLUCINATIONS = (
    "sous-titres réalisés par", "sous-titrage", "amara.org", "merci d'avoir regardé", "abonnez-vous",
    "sous titres", "transcription par", "radio-canada", "merci de votre attention",
)
PROMPT = "Hey Jarvis. Bonjour Jarvis, ouvre Deezer, mets la météo, lis mes mails Outlook et Gmail, Obsidian, Monsieur."


def clean_transcript(text: str) -> str:
    t = re.sub(r"\s+", " ", text).strip()
    low = t.lower()
    if any(h in low for h in HALLUCINATIONS):
        return ""
    if len(re.sub(r"[^\w]", "", t)) < 2:
        return ""
    # retire le mot-clé resté en tête (« Hey Jarvis, quelle heure est-il ? »)
    t = re.sub(r"^(h?ey|hé|eh|ok|dis)[\s,]+jarvis[\s,.!?]*", "", t, flags=re.IGNORECASE).strip()
    return t


class Transcriber:
    def __init__(self, cfg):
        from faster_whisper import WhisperModel

        size = cfg.get_path("stt.model", "small")
        self.beam = cfg.get_path("stt.beam_size", 1)
        log.info("chargement de Whisper « %s » (CPU)…", size)
        self.model = WhisperModel(size, device="cpu", compute_type=cfg.get_path("stt.compute_type", "int8"),
                                  cpu_threads=max(2, (os.cpu_count() or 4) - 2))

    def transcribe(self, pcm: bytes) -> str:
        audio = np.frombuffer(pcm, dtype=np.int16).astype(np.float32) / 32768.0
        if audio.size < 16000 * 0.3:
            return ""
        segments, _ = self.model.transcribe(audio, language="fr", beam_size=self.beam, vad_filter=False,
                                            condition_on_previous_text=False, initial_prompt=PROMPT)
        return clean_transcript(" ".join(s.text for s in segments if s.no_speech_prob < 0.7))
