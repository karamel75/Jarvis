"""Les oreilles : micro permanent, « Hey Jarvis » local, fin de phrase, coupure de parole.

Un seul flux micro (16 kHz, trames de 20 ms) traité dans un fil dédié :
- le mot-clé tourne en continu (réveil et interruption) ;
- quand l'appli demande d'écouter, l'Endpointer découpe la phrase de Monsieur ;
- en mode barge_in « voice », une parole soutenue pendant que Jarvis parle le coupe.
Rien ne quitte le PC tant que le mot-clé n'a pas été entendu.
"""
from __future__ import annotations

import asyncio
import collections
import logging
import queue
import threading
import time
from typing import Callable

import numpy as np

log = logging.getLogger("jarvis.ears")

RATE = 16000
FRAME = 320            # 20 ms
WAKE_CHUNK = 1280      # 80 ms, taille attendue par openWakeWord


class Endpointer:
    """Découpe une prise de parole à partir d'une suite de trames voisées / non voisées."""

    def __init__(self, frame_ms: int = 20, end_silence_ms: int = 800, max_ms: int = 25000,
                 no_speech_ms: int = 7000, preroll_ms: int = 300, start_frames: int = 4, window: int = 10):
        self.frame_ms = frame_ms
        self.end_frames = end_silence_ms // frame_ms
        self.max_frames = max_ms // frame_ms
        self.no_speech_frames = no_speech_ms // frame_ms
        self.preroll: collections.deque = collections.deque(maxlen=max(1, preroll_ms // frame_ms))
        self.recent: collections.deque = collections.deque(maxlen=window)
        self.start_frames = start_frames
        self.started = False
        self.frames: list[bytes] = []
        self.silence = 0
        self.waited = 0

    def push(self, frame: bytes, voiced: bool) -> str | None:
        """Rend "done" (phrase finie), "timeout" (personne n'a parlé) ou None (continuer)."""
        if not self.started:
            self.preroll.append(frame)
            self.recent.append(voiced)
            self.waited += 1
            if sum(self.recent) >= self.start_frames:
                self.started = True
                self.frames = list(self.preroll)
                return None
            return "timeout" if self.waited >= self.no_speech_frames else None
        self.frames.append(frame)
        self.silence = 0 if voiced else self.silence + 1
        if self.silence >= self.end_frames or len(self.frames) >= self.max_frames:
            return "done"
        return None

    def audio(self) -> bytes:
        trim = max(0, len(self.frames) - max(0, self.silence - 10))  # garde ~200 ms de silence final
        return b"".join(self.frames[:trim])


class Vad:
    """webrtcvad + seuil d'énergie (évite que le ventilateur passe pour une voix)."""

    def __init__(self, aggressiveness: int = 2, energy_floor: float = 250.0):
        import webrtcvad

        self.vad = webrtcvad.Vad(aggressiveness)
        self.floor = energy_floor

    def __call__(self, frame: bytes) -> tuple[bool, float]:
        pcm = np.frombuffer(frame, dtype=np.int16)
        rms = float(np.sqrt(np.mean(pcm.astype(np.float32) ** 2))) if pcm.size else 0.0
        return (rms > self.floor and self.vad.is_speech(frame, RATE)), rms


class WakeWord:
    def __init__(self, threshold: float = 0.5):
        import openwakeword
        from openwakeword.model import Model

        try:
            openwakeword.utils.download_models(model_names=["hey_jarvis"])
        except Exception:
            log.warning("téléchargement du modèle « hey_jarvis » impossible (déjà présent ?)", exc_info=True)
        self.model = Model(wakeword_models=["hey_jarvis"], inference_framework="onnx")
        self.threshold = threshold
        self.buf = np.zeros(0, dtype=np.int16)
        self.cooldown_until = 0.0

    def push(self, frame: bytes) -> bool:
        self.buf = np.concatenate([self.buf, np.frombuffer(frame, dtype=np.int16)])
        hit = False
        while self.buf.size >= WAKE_CHUNK:
            chunk, self.buf = self.buf[:WAKE_CHUNK], self.buf[WAKE_CHUNK:]
            scores = self.model.predict(chunk)
            if max(scores.values(), default=0.0) >= self.threshold and time.time() > self.cooldown_until:
                hit = True
                self.cooldown_until = time.time() + 1.5
                self.model.reset()
        return hit


class Ears:
    def __init__(self, cfg, loop: asyncio.AbstractEventLoop, on_wake: Callable[[], None],
                 on_barge: Callable[[], None], on_level: Callable[[float], None]):
        self.cfg, self.loop = cfg, loop
        self.on_wake, self.on_barge, self.on_level = on_wake, on_barge, on_level
        self.q: queue.Queue[bytes] = queue.Queue(maxsize=500)
        self.speaking = False            # positionné par l'appli pendant que Jarvis parle
        self._capture: tuple[Endpointer, asyncio.Future] | None = None
        self._lock = threading.Lock()
        self._stop = threading.Event()
        self.wake = WakeWord(cfg.get_path("audio.wake_threshold", 0.5))
        self.vad = Vad()
        self._barge_window: collections.deque = collections.deque(maxlen=15)

    # ── flux micro ──
    def start(self) -> None:
        import sounddevice as sd

        def callback(indata, frames, t, status):
            try:
                self.q.put_nowait(bytes(indata))
            except queue.Full:
                pass

        self.stream = sd.RawInputStream(samplerate=RATE, channels=1, dtype="int16", blocksize=FRAME,
                                        device=self.cfg.get_path("audio.input_device"), callback=callback)
        self.stream.start()
        threading.Thread(target=self._run, name="ears", daemon=True).start()
        log.info("micro ouvert — à l'écoute de « Hey Jarvis »")

    def stop(self) -> None:
        self._stop.set()
        self.stream.stop()

    def _run(self) -> None:
        last_level = 0.0
        while not self._stop.is_set():
            try:
                frame = self.q.get(timeout=0.5)
            except queue.Empty:
                continue
            if len(frame) != FRAME * 2:
                continue
            if self.wake.push(frame):
                log.info("« Hey Jarvis » entendu")
                self.loop.call_soon_threadsafe(self.on_wake)
            voiced, rms = self.vad(frame)
            with self._lock:
                cap = self._capture
            if cap is not None:
                endpointer, fut = cap
                now = time.time()
                if now - last_level > 0.05:
                    last_level = now
                    level = min(1.0, rms / 4000)
                    self.loop.call_soon_threadsafe(self.on_level, level)
                verdict = endpointer.push(frame, voiced)
                if verdict:
                    with self._lock:
                        self._capture = None
                    result = endpointer.audio() if verdict == "done" else None
                    self.loop.call_soon_threadsafe(_resolve, fut, result)
            elif self.speaking and self.cfg.get_path("audio.barge_in", "wake_word") == "voice":
                self._barge_window.append(voiced)
                if sum(self._barge_window) >= 11:  # ~220 ms de voix sur 300 ms
                    self._barge_window.clear()
                    self.loop.call_soon_threadsafe(self.on_barge)
            else:
                self._barge_window.clear()

    # ── API asynchrone ──
    async def listen(self, wait_s: float) -> bytes | None:
        """Attend une phrase ; rend le PCM 16 kHz, ou None si personne ne parle pendant wait_s."""
        a = self.cfg.get_path
        ep = Endpointer(end_silence_ms=a("audio.end_silence_ms", 800), max_ms=int(a("audio.max_utterance_s", 25) * 1000),
                        no_speech_ms=int(wait_s * 1000))
        fut = self.loop.create_future()
        with self._lock:
            self._capture = (ep, fut)
        try:
            return await fut
        finally:
            with self._lock:
                if self._capture and self._capture[1] is fut:
                    self._capture = None

    def cancel_listen(self) -> None:
        with self._lock:
            cap, self._capture = self._capture, None
        if cap:
            self.loop.call_soon_threadsafe(_resolve, cap[1], None)


def _resolve(fut: asyncio.Future, value) -> None:
    if not fut.done():
        fut.set_result(value)
