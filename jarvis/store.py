"""Petits fichiers chiffrés (jetons OAuth) — DPAPI sous Windows, lié à votre session."""
from __future__ import annotations

import sys
from pathlib import Path

from jarvis.config import data_dir


def _path(name: str) -> Path:
    return data_dir() / f"{name}.bin"


def _protect(raw: bytes) -> bytes:
    if sys.platform == "win32":
        import win32crypt

        return win32crypt.CryptProtectData(raw, "jarvis", None, None, None, 0)
    return raw  # hors Windows : développement uniquement


def _unprotect(blob: bytes) -> bytes:
    if sys.platform == "win32":
        import win32crypt

        return win32crypt.CryptUnprotectData(blob, None, None, None, 0)[1]
    return blob


def save(name: str, text: str) -> None:
    _path(name).write_bytes(_protect(text.encode("utf-8")))


def load(name: str) -> str | None:
    p = _path(name)
    if not p.exists():
        return None
    try:
        return _unprotect(p.read_bytes()).decode("utf-8")
    except Exception:
        return None
