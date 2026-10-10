"""Cartes holographiques à côté du globe, pour tout ce qui se montre mieux qu'il ne se dit."""
from __future__ import annotations

from jarvis.tools import ToolContext, tool


@tool(
    "show_hologram",
    "Affiche une carte holographique à côté du globe : un chiffre clé, une liste, une définition, "
    "un itinéraire, un comparatif… Météo, marchés, mails et agenda en affichent déjà une seuls. "
    "Gardez-la courte : un titre, quelques lignes, pas de paragraphes.",
    {
        "kind": {"type": "string", "enum": ["info", "list", "stat"]},
        "title": {"type": "string"},
        "lines": {"type": "array", "items": {"type": "string"}, "description": "pour info : 1 à 6 lignes courtes"},
        "items": {
            "type": "array",
            "items": {"type": "object"},
            "description": "pour list : [{label, value}] (8 max)",
        },
        "value": {"type": "string", "description": "pour stat : le chiffre en grand"},
        "caption": {"type": "string", "description": "pour stat : la légende"},
    },
    required=["kind", "title"],
)
def show_hologram(ctx: ToolContext, kind: str, title: str, lines=None, items=None, value: str = "", caption: str = ""):
    ctx.card(kind, title, lines=lines or [], items=(items or [])[:8], value=value, caption=caption)
    return "Carte affichée."
