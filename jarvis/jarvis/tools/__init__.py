"""Registre des outils que Claude peut appeler.

Chaque outil déclare son schéma JSON, sa fonction (sync ou async) et, s'il modifie
quelque chose, une phrase de confirmation. La confirmation est imposée par le code
(jarvis.brain), jamais laissée au bon vouloir du modèle. Aucun outil ne supprime.
"""
from __future__ import annotations

import asyncio
import importlib
import inspect
import json
import logging
from dataclasses import dataclass, field
from typing import Any, Callable, Optional

from jarvis.config import Config

log = logging.getLogger("jarvis.tools")


@dataclass
class Tool:
    name: str
    description: str
    schema: dict
    func: Callable[..., Any]
    confirm: Optional[Callable[["ToolContext", dict], str]] = None  # phrase lue avant d'agir ; vide = pas besoin
    enabled: Callable[[Config], bool] = lambda cfg: True
    hides_ui: bool = False  # l'outil emmène Monsieur ailleurs (app, page, fichier) : le globe s'efface

    def definition(self) -> dict:
        return {
            "name": self.name,
            "description": self.description,
            "input_schema": self.schema,
            "eager_input_streaming": True,
        }


REGISTRY: dict[str, Tool] = {}


def tool(
    name: str,
    description: str,
    properties: dict | None = None,
    required: tuple[str, ...] | list[str] = (),
    confirm: Callable[[ToolContext, dict], str] | None = None,
    enabled: Callable[[Config], bool] | None = None,
    hides_ui: bool = False,
):
    schema = {"type": "object", "properties": properties or {}, "required": list(required)}

    def deco(fn):
        REGISTRY[name] = Tool(
            name=name,
            description=description,
            schema=schema,
            func=fn,
            confirm=confirm,
            enabled=enabled or (lambda cfg: True),
            hides_ui=hides_ui,
        )
        return fn

    return deco


@dataclass
class ToolContext:
    cfg: Config
    ui: Any = None  # jarvis.ui.server.UIBridge
    refs: dict[str, Any] = field(default_factory=dict)  # m1 → id de mail, f1 → chemin…
    hide_requested: bool = False

    def card(self, kind: str, title: str, **data: Any) -> None:
        if self.ui is not None:
            self.ui.card({"kind": kind, "title": title, **data})

    def remember_refs(self, prefix: str, items: list[Any]) -> list[str]:
        """Donne des références courtes (m1, m2…) faciles à manipuler à l'oral."""
        keys = []
        for i, item in enumerate(items, 1):
            key = f"{prefix}{i}"
            self.refs[key] = item
            keys.append(key)
        return keys

    def ref(self, key: str) -> Any:
        if key not in self.refs:
            raise ToolError(f"Référence « {key} » inconnue : relancez la recherche ou la liste d'abord.")
        return self.refs[key]


class ToolError(Exception):
    """Erreur attendue, renvoyée telle quelle à Claude (pas de trace)."""


_TYPES = {
    "string": str,
    "integer": int,
    "number": (int, float),
    "boolean": bool,
    "array": list,
    "object": dict,
}


def validate(schema: dict, args: Any) -> str | None:
    """Validation minimale du schéma (le flux « eager » ne valide pas côté serveur)."""
    if not isinstance(args, dict):
        return "l'entrée doit être un objet JSON"
    props = schema.get("properties", {})
    for key in schema.get("required", []):
        if key not in args:
            return f"paramètre requis manquant : {key}"
    for key, value in args.items():
        spec = props.get(key)
        if spec is None:
            return f"paramètre inconnu : {key}"
        expected = _TYPES.get(spec.get("type", ""))
        if expected is not None:
            if isinstance(value, bool) and spec.get("type") in ("integer", "number"):
                return f"{key} doit être un nombre"
            if not isinstance(value, expected):
                return f"{key} doit être de type {spec['type']}"
        if "enum" in spec and value not in spec["enum"]:
            return f"{key} doit valoir l'une de : {', '.join(map(str, spec['enum']))}"
        if spec.get("type") == "array" and "items" in spec:
            item_type = _TYPES.get(spec["items"].get("type", ""))
            if item_type and not all(isinstance(v, item_type) for v in value):
                return f"{key} contient un élément du mauvais type"
    return None


MODULES = ("system", "files", "media", "weather", "markets", "memory", "hologram", "outlook", "google", "home", "brief")


def load_all() -> dict[str, Tool]:
    for mod in MODULES:
        importlib.import_module(f"jarvis.tools.{mod}")
    return REGISTRY


def available(cfg: Config) -> list[Tool]:
    load_all()
    out = []
    for t in REGISTRY.values():
        try:
            if t.enabled(cfg):
                out.append(t)
        except Exception:
            log.exception("enabled() a échoué pour %s", t.name)
    return out


async def run(t: Tool, ctx: ToolContext, args: dict) -> Any:
    if inspect.iscoroutinefunction(t.func):
        return await t.func(ctx, **args)
    return await asyncio.to_thread(t.func, ctx, **args)


def to_content(result: Any) -> Any:
    """Résultat Python → contenu de tool_result (texte, JSON ou blocs image)."""
    if isinstance(result, list) and result and isinstance(result[0], dict) and "type" in result[0]:
        return result
    if isinstance(result, str):
        return result
    return json.dumps(result, ensure_ascii=False, default=str)
