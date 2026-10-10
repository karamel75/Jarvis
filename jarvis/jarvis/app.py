"""La machine à états de Jarvis.

veille ──(« Hey Jarvis » / raccourci)──▶ conversation ──(silence / « merci Jarvis »)──▶ veille
                                          │
                     écoute ─▶ transcription ─▶ cerveau + voix ─▶ écoute de relance
                                          ▲                │
                                          └─ « Hey Jarvis » pendant qu'il parle : il se tait (barge-in)
"""
from __future__ import annotations

import asyncio
import logging
import os
import random
import threading
import time

from jarvis import config, keys, tools
from jarvis.audio.voice import Mouth, Player, Voice, chime
from jarvis.brain import Brain
from jarvis.confirm import parse_answer
from jarvis.speech import normalize
from jarvis.tools import ToolContext
from jarvis.tools import memory as obsidian
from jarvis.ui.server import UIBridge

log = logging.getLogger("jarvis.app")

# « Merci Jarvis » clôt la conversation — mais pas « merci Jarvis, et la météo demain ? » :
# la phrase ne doit contenir QUE des mots de politesse / de clôture, dont au moins une formule de fin.
_BYE_CORE = ("merci", "c'est tout", "ce sera tout", "ca sera tout", "au revoir", "bonne nuit", "a plus",
             "a demain", "tu peux disposer", "bonne soiree", "bonne journee")
_BYE_WORDS = set("""merci beaucoup bien jarvis c'est ce ca sera tout pour aujourd'hui maintenant le moment soir
    au revoir bonne nuit soiree journee a plus tard demain tu peux disposer rien non oui ok parfait super top
    bon nickel cool genial impeccable""".split())
_BYE_LINES = ("À votre service, Monsieur.", "Je reste à portée de voix, Monsieur.", "Très bien, Monsieur.", "Je me retire, Monsieur.")


def is_goodbye(text: str) -> bool:
    t = normalize(text.replace("’", "'"))
    words = t.split()
    if not words or len(words) > 7 or any(w not in _BYE_WORDS for w in words):
        return False
    return any(f" {c} " in f" {t} " for c in _BYE_CORE)


def goodbye_line(text: str, title: str = "Monsieur") -> str:
    if "nuit" in normalize(text):
        return f"Bonne nuit, {title}."
    return random.choice(_BYE_LINES).replace("Monsieur", title)


class App:
    def __init__(self, cfg: config.Config):
        self.cfg = cfg
        self.ready = threading.Event()        # serveur d'interface prêt (pour créer la fenêtre)
        self.wake = asyncio.Event()
        self.typed: asyncio.Queue[str] = asyncio.Queue()
        self.in_conversation = False
        self.listening = False
        self.turn: asyncio.Task | None = None
        self.barged = False
        self.title = cfg.get_path("user.title", "Monsieur")

    # ── démarrage ────────────────────────────────────────────────────────

    async def main(self) -> None:
        cfg, a = self.cfg, self.cfg.get_path
        self.loop = asyncio.get_running_loop()
        self.ui = UIBridge(a("ui.port", 8765), on_text=self._typed, card_seconds=a("ui.card_seconds", 14))
        await self.ui.start()
        self.ready.set()

        self.player = Player(a("audio.output_device"), on_level=self.ui.level)
        self.player.start()
        self.mouth = Mouth(Voice(cfg), self.player)
        self.mouth.start()
        self.ctx = ToolContext(cfg, self.ui)
        self.brain = Brain(cfg, self.ctx, speak=self.mouth.say, confirm=self.confirm)

        from jarvis.audio.ears import Ears
        from jarvis.audio.stt import Transcriber

        self.stt = await asyncio.to_thread(Transcriber, cfg)
        self.ears = await asyncio.to_thread(Ears, cfg, self.loop, self._on_wake, self._on_barge, self.ui.mic)
        self.ears.start()
        self._hotkey()
        asyncio.create_task(self._locate_forever())
        names = ", ".join(t.name for t in tools.available(cfg))
        log.info("Jarvis prêt. Outils actifs : %s", names)
        if not keys.has("elevenlabs") or not a("voice.voice_id"):
            log.warning("ElevenLabs non configuré : voix de secours Edge (jarvis setup pour la vraie voix)")

        while True:
            await self.wake.wait()
            self.wake.clear()
            try:
                await self.conversation()
            except Exception:
                log.exception("conversation interrompue par une erreur")
                self.in_conversation = False
                self.ui.set_state("idle")
                self.ui.hide()

    def _hotkey(self) -> None:
        combo = self.cfg.get_path("ui.hotkey")
        if not combo:
            return
        try:
            from pynput import keyboard

            keyboard.GlobalHotKeys({combo: lambda: self.loop.call_soon_threadsafe(self._on_wake)}).start()
            log.info("raccourci %s actif", combo)
        except Exception:
            log.warning("raccourci clavier indisponible", exc_info=True)

    async def _locate_forever(self) -> None:
        from jarvis.tools.weather import locate

        while True:
            try:
                self.brain.city = (await locate(self.cfg))["city"]
            except Exception:
                log.debug("localisation impossible", exc_info=True)
            await asyncio.sleep(3600)

    # ── événements (boucle asyncio) ──────────────────────────────────────

    def _busy(self) -> bool:
        return (self.turn is not None and not self.turn.done()) or not self.player.idle.is_set()

    def _on_wake(self) -> None:
        if not self.in_conversation:
            self.wake.set()
        elif self._busy():
            self._barge()  # « Hey Jarvis » pendant qu'il parle : il se tait et écoute

    def _on_barge(self) -> None:
        if self.in_conversation and self._busy():
            self._barge()

    def _barge(self) -> None:
        log.info("coupé par %s", self.title)
        self.barged = True
        self.mouth.cut()
        if self.turn and not self.turn.done():
            self.turn.cancel()

    def _typed(self, text: str) -> None:
        self.typed.put_nowait(text)
        if not self.in_conversation:
            self.wake.set()

    def _set(self, state: str) -> None:
        self.ui.set_state(state)

    # ── conversation ─────────────────────────────────────────────────────

    async def conversation(self) -> None:
        a = self.cfg.get_path
        self.in_conversation = True
        self.brain.refresh_profile()
        self.ctx.hide_requested = False
        self.ui.show()
        self._set("listen")
        if a("audio.chime", True) and self.typed.empty():
            await self.mouth.play(chime())
        wait, misses = 8.0, 0
        try:
            while True:
                text = await self.hear(wait)
                if text is None:
                    break                          # silence : retour en veille
                if text == "":
                    misses += 1                    # bruit, toux, mot isolé : on retend l'oreille
                    if misses >= 2:
                        break
                    continue
                misses = 0
                log.info("%s : %s", self.title, text)
                if is_goodbye(text):
                    await self.mouth.say(goodbye_line(text, self.title))
                    self._set("speak")
                    await self.mouth.wait_done()
                    break
                obsidian.journal(self.cfg, self.title, text)
                await self.answer(text)
                wait = a("audio.follow_up_seconds", 7)
                self._set("listen")
        finally:
            self.in_conversation = False
            self.listening = False
            self._set("idle")
            self.ui.hide()

    async def answer(self, text: str) -> None:
        """Un tour : le cerveau parle au fil de l'eau ; Monsieur peut couper à tout moment."""
        self.barged = False
        self._set("think")
        self.turn = asyncio.create_task(self.brain.respond(text))
        while not self.turn.done() or not self.player.idle.is_set() or self.mouth.pending:
            if self.barged:
                break
            if self.ctx.hide_requested:     # une appli / une page s'ouvre : le globe s'efface
                self.ctx.hide_requested = False
                self.ui.hide()
            speaking = not self.player.idle.is_set()
            self.ears.speaking = speaking
            if not self.listening:
                self._set("speak" if speaking else "think" if not self.turn.done() else "listen")
            await asyncio.sleep(0.05)
        self.ears.speaking = False
        if self.barged and not self.turn.done():
            await asyncio.wait({self.turn}, timeout=3)   # laisse le cerveau ranger son historique
        if self.turn.done() and not self.turn.cancelled() and self.turn.exception() is None:
            obsidian.journal(self.cfg, "Jarvis", self.turn.result())
        elif self.turn.done() and not self.turn.cancelled():
            log.error("tour en échec", exc_info=self.turn.exception())
        await self.player.drain()

    async def hear(self, wait_s: float) -> str | None:
        """Une phrase de Monsieur (voix ou clavier). None = silence ; "" = rien de compréhensible."""
        if not self.typed.empty():
            return self.typed.get_nowait()
        self.listening = True
        self._set("listen")
        voice = asyncio.create_task(self.ears.listen(wait_s))
        typed = asyncio.create_task(self.typed.get())
        try:
            done, _ = await asyncio.wait({voice, typed}, return_when=asyncio.FIRST_COMPLETED)
            if typed in done:
                return typed.result()
            pcm = voice.result()
        finally:
            self.listening = False
            for t in (voice, typed):
                if not t.done():
                    t.cancel()
            self.ears.cancel_listen()
        if pcm is None:
            return None
        self._set("think")
        started = time.time()
        text = await asyncio.to_thread(self.stt.transcribe, pcm)
        log.debug("transcription en %.2f s : %r", time.time() - started, text)
        return text

    # ── confirmation orale (appelée par le cerveau) ──────────────────────

    async def confirm(self, phrase: str) -> bool:
        await self.mouth.say(phrase)
        await self.mouth.wait_done()
        for attempt in range(2):
            text = await self.hear(6)
            answer = parse_answer(text) if text else None
            if answer is not None:
                log.info("confirmation : %s → %s", text, answer)
                return answer
            if attempt == 0:
                await self.mouth.say(f"Oui ou non, {self.title} ?")
                await self.mouth.wait_done()
        return False  # dans le doute, on ne fait rien


def run(cfg: config.Config, window: bool = True) -> None:
    """Point d'entrée : la fenêtre tient le fil principal (WebView2 l'exige), asyncio tourne à côté."""
    if not keys.has("anthropic"):
        raise SystemExit("Clé Anthropic absente : lancez d'abord `jarvis setup`.")
    app = App(cfg)
    if not window:
        asyncio.run(app.main())
        return

    from jarvis.ui.window import Window

    def backend():
        try:
            asyncio.run(app.main())
        except Exception:
            log.exception("Jarvis s'est arrêté sur une erreur")
        finally:
            app.ready.set()
            win = getattr(getattr(app, "ui", None), "window", None)
            if win is not None:
                win.close()

    threading.Thread(target=backend, name="jarvis", daemon=True).start()
    if not app.ready.wait(30) or not hasattr(app, "ui"):
        raise SystemExit("L'interface n'a pas démarré (port déjà pris ? voir ui.port).")
    win = Window(app.ui.url, cfg.get_path("ui.screen", -1))
    app.ui.window = win
    win.run(lambda: None)  # bloque jusqu'à la fermeture de la fenêtre
    os._exit(0)            # fils audio et boucle asyncio : on ne traîne pas
