"""La voix : ElevenLabs en flux (PCM 24 kHz), repli edge-tts, lecture interruptible.

Le lecteur mesure l'amplitude et le spectre de ce qu'il joue et les envoie au globe :
c'est la vraie voix qui fait vibrer les particules.
"""
from __future__ import annotations

import asyncio
import logging
import threading
import time
from typing import Callable

import httpx
import numpy as np

from jarvis import keys

log = logging.getLogger("jarvis.voice")

RATE = 24000
BLOCK = 960  # 40 ms
BANDS = 24


def spectrum(pcm: np.ndarray, bands: int = BANDS) -> list[float]:
    """Bandes de fréquence log-espacées, normalisées 0..1, pour l'anneau du globe."""
    if pcm.size < 64:
        return [0.0] * bands
    win = pcm.astype(np.float32) * np.hanning(pcm.size)
    mag = np.abs(np.fft.rfft(win)) / pcm.size
    freqs = np.fft.rfftfreq(pcm.size, 1 / RATE)
    edges = np.geomspace(80, 8000, bands + 1)
    out = []
    for lo, hi in zip(edges[:-1], edges[1:]):
        sel = mag[(freqs >= lo) & (freqs < hi)]
        out.append(float(sel.mean()) if sel.size else 0.0)
    arr = np.clip(np.log1p(np.array(out) / 20) / 3.0, 0, 1)
    return [round(float(x), 3) for x in arr]


def chime() -> bytes:
    """Petit son holographique au réveil : deux notes cristallines montantes, 220 ms."""
    t = np.linspace(0, 0.22, int(RATE * 0.22), endpoint=False)
    f = np.where(t < 0.09, 880.0, 1318.5)
    env = np.exp(-((t % 0.11) * 28)) * np.minimum(1, t * 400)
    wave = (np.sin(2 * np.pi * f * t) + 0.3 * np.sin(4 * np.pi * f * t)) * env * 0.16
    return (wave * 32767).astype(np.int16).tobytes()


class Player:
    def __init__(self, device=None, on_level: Callable[[float, list[float]], None] = lambda a, b: None):
        self.device, self.on_level = device, on_level
        self.buf = bytearray()
        self.lock = threading.Lock()
        self.idle = threading.Event()
        self.idle.set()
        self._last = 0.0

    def start(self) -> None:
        import sounddevice as sd

        self.stream = sd.RawOutputStream(samplerate=RATE, channels=1, dtype="int16", blocksize=BLOCK,
                                         device=self.device, callback=self._cb, latency="low")
        self.stream.start()

    def _cb(self, outdata, frames, t, status):
        need = frames * 2
        with self.lock:
            chunk = bytes(self.buf[:need])
            del self.buf[:need]
            empty = not self.buf
        if len(chunk) < need:
            chunk += b"\x00" * (need - len(chunk))
        outdata[:] = chunk
        pcm = np.frombuffer(chunk, dtype=np.int16)
        now = time.time()
        if now - self._last > 0.03:
            self._last = now
            level = min(1.0, float(np.sqrt(np.mean(pcm.astype(np.float32) ** 2))) / 6000)
            self.on_level(level, spectrum(pcm) if level > 0.01 else [0.0] * BANDS)
        if empty:
            self.idle.set()

    def feed(self, pcm: bytes) -> None:
        if not pcm:
            return
        with self.lock:
            self.buf.extend(pcm)
            self.idle.clear()

    def stop(self) -> None:
        with self.lock:
            self.buf.clear()
        self.idle.set()

    async def drain(self) -> None:
        while not self.idle.is_set():
            await asyncio.sleep(0.03)
        await asyncio.sleep(0.08)  # laisse finir le dernier bloc matériel


class Voice:
    """Synthèse d'une phrase → PCM 24 kHz poussé au lecteur au fil de l'eau."""

    def __init__(self, cfg):
        self.cfg = cfg
        self.http = httpx.AsyncClient(timeout=httpx.Timeout(20, connect=5))
        self.failed_until = 0.0

    async def synth(self, text: str, feed: Callable[[bytes], None], previous: str = "") -> None:
        use_el = (self.cfg.get_path("voice.provider", "elevenlabs") == "elevenlabs" and keys.has("elevenlabs")
                  and self.cfg.get_path("voice.voice_id") and time.time() > self.failed_until)
        if use_el:
            try:
                await self._elevenlabs(text, feed, previous)
                return
            except asyncio.CancelledError:
                raise
            except Exception as exc:
                log.warning("ElevenLabs indisponible (%s) — voix de secours pendant 5 min", exc)
                self.failed_until = time.time() + 300
        await self._edge(text, feed)

    async def _elevenlabs(self, text: str, feed, previous: str) -> None:
        c = self.cfg.get_path
        model = c("voice.model_id", "eleven_flash_v2_5")
        body = {
            "text": text,
            "model_id": model,
            "voice_settings": {"stability": c("voice.stability", 0.45), "similarity_boost": c("voice.similarity_boost", 0.8),
                               "style": c("voice.style", 0.15), "use_speaker_boost": True, "speed": c("voice.speed", 1.0)},
        }
        if previous:
            body["previous_text"] = previous[-300:]
        if "v2_5" in model:  # seuls Flash/Turbo v2.5 acceptent le forçage de langue
            body["language_code"] = "fr"
        url = f"https://api.elevenlabs.io/v1/text-to-speech/{c('voice.voice_id')}/stream"
        headers = {"xi-api-key": keys.get("elevenlabs"), "accept": "audio/pcm"}
        async with self.http.stream("POST", url, params={"output_format": "pcm_24000"}, json=body, headers=headers) as r:
            if r.status_code != 200:
                raise RuntimeError(f"HTTP {r.status_code} {(await r.aread())[:200]!r}")
            carry = b""
            async for chunk in r.aiter_bytes():
                data = carry + chunk
                cut = len(data) - (len(data) % 2)  # échantillons 16 bits entiers
                feed(data[:cut])
                carry = data[cut:]

    async def _edge(self, text: str, feed) -> None:
        import edge_tts
        import miniaudio

        mp3 = bytearray()
        async for part in edge_tts.Communicate(text, self.cfg.get_path("voice.edge_voice", "fr-FR-HenriNeural")).stream():
            if part["type"] == "audio":
                mp3.extend(part["data"])
        if mp3:
            decoded = miniaudio.decode(bytes(mp3), output_format=miniaudio.SampleFormat.SIGNED16,
                                       nchannels=1, sample_rate=RATE)
            feed(decoded.samples.tobytes())


class Mouth:
    """File de phrases → voix → lecteur. `cut()` coupe net (barge-in)."""

    def __init__(self, voice: Voice, player: Player, on_start: Callable[[], None] = lambda: None):
        self.voice, self.player, self.on_start = voice, player, on_start
        self.q: asyncio.Queue[str] = asyncio.Queue()
        self.current: asyncio.Task | None = None
        self.pending = 0
        self.previous = ""

    def start(self) -> None:
        self.worker = asyncio.create_task(self._work())

    async def say(self, text: str) -> None:
        if text.strip():
            self.pending += 1
            await self.q.put(text)

    async def _work(self) -> None:
        while True:
            text = await self.q.get()
            self.on_start()
            self.current = asyncio.create_task(self.voice.synth(text, self.player.feed, self.previous))
            try:
                await self.current
                self.previous = (self.previous + " " + text)[-400:]
            except asyncio.CancelledError:
                if asyncio.current_task().cancelling():  # type: ignore[attr-defined]
                    raise
            except Exception:
                log.exception("synthèse vocale impossible")
            finally:
                self.current = None
                self.pending = max(0, self.pending - 1)

    @property
    def busy(self) -> bool:
        return self.pending > 0 or not self.player.idle.is_set()

    async def wait_done(self) -> None:
        while self.pending > 0:
            await asyncio.sleep(0.03)
        await self.player.drain()

    def cut(self) -> None:
        while not self.q.empty():
            self.q.get_nowait()
            self.pending = max(0, self.pending - 1)
        if self.current:
            self.current.cancel()
        self.player.stop()
        self.previous = ""

    async def play(self, pcm: bytes) -> None:
        self.player.feed(pcm)
        await self.player.drain()
