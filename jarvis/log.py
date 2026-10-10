from __future__ import annotations

import logging
from logging.handlers import RotatingFileHandler

from jarvis.config import data_dir


def setup(verbose: bool = False) -> None:
    fmt = logging.Formatter("%(asctime)s %(levelname)-7s %(name)s · %(message)s", "%H:%M:%S")
    root = logging.getLogger()
    root.setLevel(logging.DEBUG if verbose else logging.INFO)
    fh = RotatingFileHandler(data_dir() / "jarvis.log", maxBytes=2_000_000, backupCount=3, encoding="utf-8")
    fh.setFormatter(fmt)
    sh = logging.StreamHandler()
    sh.setFormatter(fmt)
    root.handlers[:] = [fh, sh]
    for noisy in ("httpx", "httpcore", "aiohttp.access", "urllib3", "comtypes", "faster_whisper", "yfinance", "pywebview"):
        logging.getLogger(noisy).setLevel(logging.WARNING)
