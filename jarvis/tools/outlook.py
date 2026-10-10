"""Outlook.com personnel via Microsoft Graph : lire, résumer, répondre, envoyer, contacts.

Connexion une fois avec `jarvis auth outlook` ; le jeton est chiffré par DPAPI dans
%LOCALAPPDATA%\\Jarvis. Envoi et réponse passent toujours par la confirmation orale.
Pas de suppression : aucun outil ne l'expose.
"""
from __future__ import annotations

import asyncio
import logging

import httpx

from jarvis import store
from jarvis.config import Config
from jarvis.tools import ToolContext, ToolError, tool

log = logging.getLogger("jarvis.outlook")

AUTHORITY = "https://login.microsoftonline.com/consumers"
SCOPES = ["User.Read", "Mail.Read", "Mail.Send", "Contacts.Read"]  # lecture seule + envoi : aucun droit de suppression
GRAPH = "https://graph.microsoft.com/v1.0"


def _app(cfg: Config):
    import msal

    client_id = cfg.get_path("outlook.client_id", "")
    if not client_id:
        raise ToolError("outlook.client_id manquant dans config.yaml (voir docs/SETUP.md).")
    cache = msal.SerializableTokenCache()
    blob = store.load("outlook")
    if blob:
        cache.deserialize(blob)
    return msal.PublicClientApplication(client_id, authority=AUTHORITY, token_cache=cache), cache


def _persist(cache) -> None:
    if cache.has_state_changed:
        store.save("outlook", cache.serialize())


def login(cfg: Config) -> str:
    """Ouvre le navigateur pour la connexion Microsoft (commande `jarvis auth outlook`)."""
    app, cache = _app(cfg)
    result = app.acquire_token_interactive(SCOPES, prompt="select_account")
    _persist(cache)
    if "access_token" not in result:
        raise RuntimeError(result.get("error_description") or str(result))
    return result.get("id_token_claims", {}).get("preferred_username", "compte connecté")


def token(cfg: Config) -> str:
    app, cache = _app(cfg)
    accounts = app.get_accounts()
    result = app.acquire_token_silent(SCOPES, account=accounts[0]) if accounts else None
    _persist(cache)
    if not result or "access_token" not in result:
        raise ToolError("Outlook n'est pas connecté : lancez `jarvis auth outlook`.")
    return result["access_token"]


async def graph(cfg: Config, method: str, path: str, **kw) -> dict:
    access = await asyncio.to_thread(token, cfg)  # MSAL peut rafraîchir le jeton via le réseau
    headers = {"Authorization": f"Bearer {access}", **kw.pop("headers", {})}
    async with httpx.AsyncClient(timeout=15) as http:
        r = await http.request(method, GRAPH + path, headers=headers, **kw)
    if r.status_code >= 400:
        raise ToolError(f"Outlook a répondu {r.status_code} : {r.text[:200]}")
    return r.json() if r.content else {}


def _enabled(cfg: Config) -> bool:
    return bool(cfg.get_path("outlook.enabled")) and bool(cfg.get_path("outlook.client_id"))


def _sender(m: dict) -> str:
    ea = (m.get("from") or {}).get("emailAddress") or {}
    return ea.get("name") or ea.get("address") or "inconnu"


@tool(
    "outlook_list",
    "Liste les mails Outlook (boîte de réception). Rend des références o1, o2… Affiche une carte.",
    {
        "unread_only": {"type": "boolean", "description": "défaut true"},
        "count": {"type": "integer", "description": "défaut 8, max 25"},
        "search": {"type": "string", "description": "mots-clés, expéditeur…"},
    },
    enabled=_enabled,
)
async def outlook_list(ctx: ToolContext, unread_only: bool = True, count: int = 8, search: str = ""):
    params = {"$top": max(1, min(count, 25)), "$select": "id,subject,from,receivedDateTime,isRead,bodyPreview,importance"}
    if search:  # $search ne se combine pas avec $orderby
        params["$search"] = f'"{search}"'
    else:
        params["$orderby"] = "receivedDateTime desc"
        if unread_only:
            params["$filter"] = "isRead eq false"
    data = await graph(ctx.cfg, "GET", "/me/mailFolders/inbox/messages", params=params)
    mails = data.get("value", [])
    if not mails:
        return "Aucun mail correspondant."
    refs = ctx.remember_refs("o", [{"id": m["id"], "from": _sender(m), "subject": m.get("subject", "")} for m in mails])
    rows = [{"ref": r, "de": _sender(m), "sujet": m.get("subject"), "recu": m.get("receivedDateTime", "")[:16],
             "lu": m.get("isRead"), "important": m.get("importance") == "high", "apercu": m.get("bodyPreview", "")[:160]}
            for r, m in zip(refs, mails)]
    ctx.card("mail", "Outlook", items=[{"from": r["de"], "subject": r["sujet"], "unread": not r["lu"]} for r in rows])
    return rows


@tool(
    "outlook_read",
    "Lit un mail Outlook en entier (référence o1…), pour le résumer ou y répondre.",
    {"ref": {"type": "string"}},
    required=["ref"],
    enabled=_enabled,
)
async def outlook_read(ctx: ToolContext, ref: str):
    mid = ctx.ref(ref)["id"]
    m = await graph(ctx.cfg, "GET", f"/me/messages/{mid}",
                    params={"$select": "subject,from,toRecipients,ccRecipients,receivedDateTime,body"},
                    headers={"Prefer": 'outlook.body-content-type="text"'})
    body = (m.get("body") or {}).get("content", "")
    return {"de": _sender(m), "sujet": m.get("subject"), "recu": m.get("receivedDateTime"), "texte": body[:12000]}


def _confirm_send(ctx: ToolContext, a: dict) -> str:
    to = ", ".join(a.get("to", []))
    return f"J'envoie à {to} un mail intitulé « {a.get('subject', '')} ». Il dit : {a.get('body', '')[:400]}"


@tool(
    "outlook_send",
    "Envoie un nouveau mail depuis Outlook. `to` = adresses e-mail (utilisez outlook_contacts pour un nom). "
    "Le système demandera lui-même confirmation à Monsieur : n'attendez pas son accord avant d'appeler l'outil.",
    {
        "to": {"type": "array", "items": {"type": "string"}},
        "subject": {"type": "string"},
        "body": {"type": "string", "description": "texte du mail, signé du prénom de Monsieur si connu"},
        "cc": {"type": "array", "items": {"type": "string"}},
    },
    required=["to", "subject", "body"],
    confirm=_confirm_send,
    enabled=_enabled,
)
async def outlook_send(ctx: ToolContext, to: list[str], subject: str, body: str, cc: list[str] | None = None):
    bad = [x for x in to + (cc or []) if "@" not in x]
    if bad:
        raise ToolError(f"Adresse invalide : {', '.join(bad)}. Cherchez d'abord le contact.")
    message = {
        "subject": subject,
        "body": {"contentType": "Text", "content": body},
        "toRecipients": [{"emailAddress": {"address": x}} for x in to],
        "ccRecipients": [{"emailAddress": {"address": x}} for x in (cc or [])],
    }
    await graph(ctx.cfg, "POST", "/me/sendMail", json={"message": message, "saveToSentItems": True})
    return "Mail envoyé."


def _confirm_reply(ctx: ToolContext, a: dict) -> str:
    m = ctx.refs.get(a.get("ref", ""), {})
    who = "tout le monde" if a.get("reply_all") else m.get("from", "l'expéditeur")
    return f"Je réponds à {who}, au sujet de « {m.get('subject', '')} ». Ma réponse : {a.get('body', '')[:400]}"


@tool(
    "outlook_reply",
    "Répond à un mail Outlook (référence o1…). Le système demandera confirmation à Monsieur.",
    {"ref": {"type": "string"}, "body": {"type": "string"}, "reply_all": {"type": "boolean"}},
    required=["ref", "body"],
    confirm=_confirm_reply,
    enabled=_enabled,
)
async def outlook_reply(ctx: ToolContext, ref: str, body: str, reply_all: bool = False):
    mid = ctx.ref(ref)["id"]
    await graph(ctx.cfg, "POST", f"/me/messages/{mid}/{'replyAll' if reply_all else 'reply'}", json={"comment": body})
    return "Réponse envoyée."


_contacts: list[dict] = []


@tool(
    "outlook_contacts",
    "Cherche un contact Outlook par nom et rend ses adresses e-mail.",
    {"name": {"type": "string"}},
    required=["name"],
    enabled=_enabled,
)
async def outlook_contacts(ctx: ToolContext, name: str):
    global _contacts
    if not _contacts:
        data = await graph(ctx.cfg, "GET", "/me/contacts", params={"$top": 500, "$select": "displayName,emailAddresses"})
        _contacts = data.get("value", [])
    from jarvis.speech import normalize

    key = normalize(name)
    hits = [
        {"nom": c.get("displayName"), "emails": [e.get("address") for e in c.get("emailAddresses", []) if e.get("address")]}
        for c in _contacts if key in normalize(c.get("displayName") or "")
    ]
    return hits[:8] or f"Aucun contact ne correspond à « {name} »."
