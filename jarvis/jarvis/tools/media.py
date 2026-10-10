"""Deezer à la voix : lecture, pause, suivant, « c'est quoi ce son ? ».

Pilotage via les contrôles média de Windows (SMTC) — fonctionne avec l'appli Deezer
de bureau sans clé API. La recherche de titres passe par l'API publique api.deezer.com.
"""
from __future__ import annotations

import asyncio
import logging
import os
import sys

import httpx

from jarvis.tools import ToolContext, ToolError, tool

log = logging.getLogger("jarvis.media")
WIN = sys.platform == "win32"


async def _session(prefer: str = "deezer"):
    if not WIN:
        raise ToolError("Disponible sous Windows uniquement.")
    from winrt.windows.media.control import GlobalSystemMediaTransportControlsSessionManager as Manager

    manager = await Manager.request_async()
    sessions = list(manager.get_sessions())
    for s in sessions:
        if prefer in (s.source_app_user_model_id or "").lower():
            return s
    return manager.get_current_session() or (sessions[0] if sessions else None)


@tool(
    "music_control",
    "Contrôle la musique en cours (Deezer en priorité) : play, pause, toggle, next, previous.",
    {"action": {"type": "string", "enum": ["play", "pause", "toggle", "next", "previous"]}},
    required=["action"],
)
async def music_control(ctx: ToolContext, action: str):
    s = await _session()
    if s is None:
        raise ToolError("Aucun lecteur actif. Dites par exemple « mets du Daft Punk ».")
    call = {
        "play": s.try_play_async, "pause": s.try_pause_async, "toggle": s.try_toggle_play_pause_async,
        "next": s.try_skip_next_async, "previous": s.try_skip_previous_async,
    }[action]
    ok = await call()
    return "Fait." if ok else "Le lecteur a refusé la commande."


@tool("now_playing", "Indique le titre et l'artiste en cours de lecture (« c'est quoi ce son ? »).")
async def now_playing(ctx: ToolContext):
    s = await _session()
    if s is None:
        return "Rien ne joue en ce moment."
    props = await s.try_get_media_properties_async()
    info = {"titre": props.title, "artiste": props.artist, "album": props.album_title,
            "source": s.source_app_user_model_id}
    ctx.card("info", "En lecture", lines=[props.title or "—", props.artist or "", props.album_title or ""])
    return info


@tool(
    "play_music",
    "Lance une musique sur Deezer : titre, artiste, album ou playlist (« mets Get Lucky », « mets du Jul », "
    "« lance ma playlist chill »).",
    {
        "query": {"type": "string"},
        "kind": {"type": "string", "enum": ["track", "artist", "album", "playlist"], "description": "défaut track"},
    },
    required=["query"],
)
async def play_music(ctx: ToolContext, query: str, kind: str = "track"):
    if not WIN:
        raise ToolError("Disponible sous Windows uniquement.")
    endpoint = {"track": "search", "artist": "search/artist", "album": "search/album", "playlist": "search/playlist"}[kind]
    async with httpx.AsyncClient(timeout=8) as http:
        r = await http.get(f"https://api.deezer.com/{endpoint}", params={"q": query, "limit": 1})
        r.raise_for_status()
        items = r.json().get("data") or []
        if not items:
            raise ToolError(f"Rien trouvé sur Deezer pour « {query} ».")
        item = items[0]
        if kind == "artist":  # un artiste : on démarre par son titre phare, Deezer enchaîne
            top = (await http.get(f"https://api.deezer.com/artist/{item['id']}/top", params={"limit": 1})).json()
            item, kind = (top.get("data") or [item])[0], "track"
    uri = f"deezer://www.deezer.com/{kind}/{item['id']}"
    os.startfile(uri)
    await asyncio.sleep(3.0)
    try:  # l'appli ouvre parfois la page sans démarrer la lecture
        s = await _session()
        if s is not None:
            await s.try_play_async()
    except Exception:
        log.debug("relance lecture impossible", exc_info=True)
    label = item.get("title") or item.get("name")
    artist = (item.get("artist") or {}).get("name", "")
    ctx.card("info", "Deezer", lines=[label, artist])
    return {"lance": label, "artiste": artist, "type": kind}
