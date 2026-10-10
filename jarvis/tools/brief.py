"""« Jarvis, le brief » — rassemble en parallèle météo, agenda, mails et marchés."""
from __future__ import annotations

import asyncio
import logging

from jarvis.tools import REGISTRY, ToolContext, run, tool

log = logging.getLogger("jarvis.brief")


async def _try(ctx: ToolContext, name: str, **args):
    t = REGISTRY.get(name)
    if t is None or not t.enabled(ctx.cfg):
        return None
    try:
        return await run(t, ctx, args)
    except Exception as exc:  # une source en panne ne gâche pas le brief
        log.info("brief : %s indisponible (%s)", name, exc)
        return f"indisponible : {exc}"


@tool(
    "daily_brief",
    "Prépare le brief que Monsieur demande (« le brief », « quoi de neuf ? ») : météo, agenda du jour, "
    "mails non lus et marchés, avec des cartes. Ensuite, complétez avec web_search pour les actualités "
    "dans l'ordre des sujets rendus, puis faites un brief oral serré (90 secondes maximum).",
)
async def daily_brief(ctx: ToolContext):
    weather, agenda, outlook, gmail, markets = await asyncio.gather(
        _try(ctx, "get_weather", days=1),
        _try(ctx, "calendar_list", days=1),
        _try(ctx, "outlook_list", unread_only=True, count=6),
        _try(ctx, "gmail_list", count=6),
        _try(ctx, "get_markets"),
    )
    return {
        "meteo": weather, "agenda": agenda, "mails_outlook": outlook, "mails_gmail": gmail, "marches": markets,
        "sujets_actualite": ctx.cfg.get_path("brief.topics", []),
    }
