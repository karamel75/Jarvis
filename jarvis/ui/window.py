"""Fenêtre plein écran sans bordure (pywebview / WebView2), sur l'écran externe.

pywebview doit tenir le fil principal : l'appli asyncio tourne dans un fil secondaire
et pilote la fenêtre via show() / hide(), qui sont sûrs entre fils.
"""
from __future__ import annotations

import logging

log = logging.getLogger("jarvis.window")


def pick_screen(screens, index: int = -1):
    """index ≥ 0 : écran imposé ; -1 : le premier écran qui n'est pas le principal."""
    if not screens:
        return None
    if 0 <= index < len(screens):
        return screens[index]
    for s in screens:
        if (s.x, s.y) != (0, 0):
            return s
    return screens[0]


class Window:
    def __init__(self, url: str, screen_index: int = -1):
        import webview

        self.webview = webview
        screen = pick_screen(webview.screens, screen_index)
        geo = dict(x=screen.x, y=screen.y, width=screen.width, height=screen.height) if screen else {}
        self.win = webview.create_window(
            "JARVIS", url, frameless=True, on_top=True, background_color="#000000",
            easy_drag=False, focus=False, hidden=True, **geo,
        )
        self.geo = geo

    def run(self, on_ready) -> None:
        """Bloquant : démarre WebView2 sur le fil principal ; on_ready est lancé dans un fil à part."""
        self.webview.start(on_ready, gui="edgechromium", private_mode=True)

    def show(self) -> None:
        try:
            self.win.show()
            if self.geo:  # Windows peut replacer la fenêtre : on la recale à chaque apparition
                self.win.move(self.geo["x"], self.geo["y"])
                self.win.resize(self.geo["width"], self.geo["height"])
        except Exception:
            log.exception("affichage de la fenêtre impossible")

    def hide(self) -> None:
        try:
            self.win.hide()
        except Exception:
            log.exception("masquage de la fenêtre impossible")

    def close(self) -> None:
        try:
            self.win.destroy()
        except Exception:
            pass
