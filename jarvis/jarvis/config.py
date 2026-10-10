"""Chargement de config.yaml (fusionné sur config.example.yaml) et chemins."""
from __future__ import annotations

import copy
import os
import sys
from pathlib import Path
from typing import Any

import yaml

ROOT = Path(__file__).resolve().parent.parent
EXAMPLE = ROOT / "config.example.yaml"
CONFIG = ROOT / "config.yaml"
WEB_DIR = Path(__file__).resolve().parent / "ui" / "web"


def data_dir() -> Path:
    """Dossier local des jetons chiffrés, journaux et caches (hors dépôt)."""
    if sys.platform == "win32":
        base = Path(os.environ.get("LOCALAPPDATA", Path.home() / "AppData" / "Local"))
    else:
        base = Path.home() / ".local" / "share"
    d = base / "Jarvis"
    d.mkdir(parents=True, exist_ok=True)
    return d


def _merge(base: dict, over: dict) -> dict:
    out = copy.deepcopy(base)
    for k, v in (over or {}).items():
        if isinstance(v, dict) and isinstance(out.get(k), dict):
            out[k] = _merge(out[k], v)
        else:
            out[k] = v
    return out


class Config(dict):
    """dict avec accès par chemin : cfg.get_path("voice.voice_id")."""

    def get_path(self, path: str, default: Any = None) -> Any:
        node: Any = self
        for part in path.split("."):
            if not isinstance(node, dict) or part not in node:
                return default
            node = node[part]
        return node


def expand(p: str) -> Path:
    return Path(os.path.expandvars(os.path.expanduser(p)))


def load(path: Path | None = None) -> Config:
    base = yaml.safe_load(EXAMPLE.read_text(encoding="utf-8")) or {}
    target = path or CONFIG
    user = {}
    if target.exists():
        user = yaml.safe_load(target.read_text(encoding="utf-8")) or {}
    return Config(_merge(base, user))


def save_value(path: str, value: Any, target: Path | None = None) -> None:
    """Écrit une valeur dans config.yaml (créé depuis l'exemple si absent)."""
    target = target or CONFIG
    if not target.exists():
        target.write_text(EXAMPLE.read_text(encoding="utf-8"), encoding="utf-8")
    data = yaml.safe_load(target.read_text(encoding="utf-8")) or {}
    node = data
    parts = path.split(".")
    for part in parts[:-1]:
        node = node.setdefault(part, {})
    node[parts[-1]] = value
    target.write_text(yaml.safe_dump(data, allow_unicode=True, sort_keys=False), encoding="utf-8")
