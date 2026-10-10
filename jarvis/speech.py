"""Texte → phrases prononçables : découpe en flux et nettoyage pour la synthèse vocale."""
from __future__ import annotations

import re
import unicodedata

_URL = re.compile(r"https?://\S+|www\.\S+")
_MD = re.compile(r"(\*\*|__|`+|^#+\s*|^\s*[-*•]\s+|^\s*\d+\.\s+)", re.MULTILINE)
_LINK = re.compile(r"\[([^\]]+)\]\([^)]+\)")
_EMOJI = re.compile("[\U0001F300-\U0001FAFF\U00002700-\U000027BF\U0001F000-\U0001F2FF]")
_SPACES = re.compile(r"\s+")
# fin de phrase : . ! ? … ou ; suivi d'un espace — sans couper « M. », « 3.5 », « etc. »
_END = re.compile(r"(?:(?<!\bM)(?<!\bMme)(?<!\bDr)(?<!\betc)(?<!\d)\.|[!?…;:])\s+")


def clean(text: str) -> str:
    text = _LINK.sub(r"\1", text)
    text = _URL.sub("", text)
    text = _MD.sub("", text)
    text = _EMOJI.sub("", text)
    text = text.replace("&", " et ").replace("%", " pour cent").replace("€", " euros")
    return _SPACES.sub(" ", text).strip()


class SentenceSplitter:
    """Reçoit des fragments de texte en flux, rend des phrases complètes dès qu'elles le sont.

    La première phrase part dès ~25 caractères pour que Jarvis commence à parler vite ;
    les suivantes sont regroupées jusqu'à ~180 caractères pour une prosodie naturelle.
    """

    def __init__(self, first_min: int = 25, max_len: int = 180):
        self.buf = ""
        self.first = True
        self.first_min = first_min
        self.max_len = max_len

    def feed(self, chunk: str) -> list[str]:
        self.buf += chunk
        out: list[str] = []
        while True:
            cut = self._find_cut()
            if cut is None:
                break
            piece, self.buf = self.buf[:cut], self.buf[cut:]
            piece = clean(piece)
            if piece:
                out.append(piece)
                self.first = False
        return out

    def _find_cut(self) -> int | None:
        minimum = self.first_min if self.first else 60
        best = None
        for m in _END.finditer(self.buf):
            if m.end() >= minimum:
                best = m.end()
                if self.first or best >= self.max_len * 0.6:
                    return best
        if best is not None and len(self.buf) > self.max_len:
            return best
        if len(self.buf) > self.max_len * 1.6:  # phrase interminable : couper à une virgule
            comma = self.buf.rfind(", ", 0, self.max_len)
            if comma > 0:
                return comma + 2
        return None

    def flush(self) -> list[str]:
        piece, self.buf = clean(self.buf), ""
        return [piece] if piece else []


def normalize(text: str) -> str:
    """minuscules, sans accents ni ponctuation — pour comparer des réponses orales."""
    text = unicodedata.normalize("NFD", text.lower())
    text = "".join(c for c in text if unicodedata.category(c) != "Mn")
    return _SPACES.sub(" ", re.sub(r"[^a-z0-9' ]+", " ", text)).strip()
