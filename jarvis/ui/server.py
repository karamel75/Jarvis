"""Pont Python ↔ globe : aiohttp sert l'interface et pousse l'état par WebSocket.

Messages vers la page : {"t": "hello"|"state"|"level"|"mic"|"card"|"show"|"hide", ...}
Messages depuis la page : {"t": "text", "v": "..."} (saisie clavier, mode démo)
"""
from __future__ import annotations

import asyncio
import json
import logging
from typing import Callable

from aiohttp import WSMsgType, web

from jarvis.config import WEB_DIR

log = logging.getLogger("jarvis.ui")


class UIBridge:
    def __init__(self, port: int = 8765, on_text: Callable[[str], None] = lambda s: None, card_seconds: float = 14):
        self.port, self.on_text, self.card_seconds = port, on_text, card_seconds
        self.clients: set[web.WebSocketResponse] = set()
        self.loop: asyncio.AbstractEventLoop | None = None
        self.state = "idle"
        self.visible = False
        self.window = None  # jarvis.ui.window.Window, branchée par l'appli

    @property
    def url(self) -> str:
        return f"http://127.0.0.1:{self.port}/"

    async def start(self) -> None:
        self.loop = asyncio.get_running_loop()
        app = web.Application()
        app.router.add_get("/ws", self._ws)
        app.router.add_get("/", lambda r: web.FileResponse(WEB_DIR / "index.html"))
        app.router.add_static("/", WEB_DIR, follow_symlinks=False)
        runner = web.AppRunner(app, access_log=None)
        await runner.setup()
        await web.TCPSite(runner, "127.0.0.1", self.port).start()  # jamais exposé au réseau
        log.info("interface sur %s", self.url)

    async def _ws(self, request: web.Request) -> web.WebSocketResponse:
        ws = web.WebSocketResponse(heartbeat=20)
        await ws.prepare(request)
        self.clients.add(ws)
        await ws.send_json({"t": "hello", "state": self.state, "visible": self.visible,
                            "card_seconds": self.card_seconds})
        try:
            async for msg in ws:
                if msg.type != WSMsgType.TEXT:
                    continue
                try:
                    data = json.loads(msg.data)
                except ValueError:
                    continue
                if data.get("t") == "text" and str(data.get("v", "")).strip():
                    self.on_text(str(data["v"]).strip())
        finally:
            self.clients.discard(ws)
        return ws

    # ── diffusion (appelable depuis n'importe quel fil) ──
    def send(self, msg: dict) -> None:
        if self.loop is None or not self.clients:
            return
        payload = json.dumps(msg, ensure_ascii=False)

        def go():
            for ws in list(self.clients):
                if not ws.closed:
                    asyncio.ensure_future(ws.send_str(payload))

        try:
            if asyncio.get_running_loop() is self.loop:
                go()
                return
        except RuntimeError:
            pass
        self.loop.call_soon_threadsafe(go)

    def set_state(self, state: str) -> None:
        if state != self.state:
            self.state = state
            self.send({"t": "state", "v": state})

    def level(self, value: float, bands: list[float]) -> None:
        self.send({"t": "level", "v": round(value, 3), "bands": bands})

    def mic(self, value: float) -> None:
        self.send({"t": "mic", "v": round(value, 3)})

    def card(self, card: dict) -> None:
        self.send({"t": "card", **card})

    def show(self) -> None:
        self.visible = True
        if self.window:
            self.window.show()
        self.send({"t": "show"})

    def hide(self, delay: float = 0.75) -> None:
        """Le globe se disperse (animation côté page), puis la fenêtre disparaît."""
        if not self.visible:
            return
        self.visible = False
        self.send({"t": "hide"})
        if self.window and self.loop:
            self.loop.call_later(delay, lambda: (not self.visible) and self.window.hide())
