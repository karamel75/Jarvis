"""Google : Gmail (lire, répondre, envoyer), Agenda (consulter, créer), Drive (chercher, ouvrir).

Connexion une fois avec `jarvis auth google` (client OAuth « Application de bureau »
téléchargé en credentials.json). Jeton chiffré DPAPI. Jamais de suppression.
"""
from __future__ import annotations

import base64
import json
import logging
import webbrowser
from datetime import datetime, timedelta
from email.mime.text import MIMEText
from email.utils import parseaddr

from jarvis import store
from jarvis.config import ROOT, Config, expand
from jarvis.tools import ToolContext, ToolError, tool

log = logging.getLogger("jarvis.google")

SCOPES = [
    "https://www.googleapis.com/auth/gmail.readonly",
    "https://www.googleapis.com/auth/gmail.send",
    "https://www.googleapis.com/auth/calendar.events",
    "https://www.googleapis.com/auth/drive.readonly",
]


def login(cfg: Config) -> None:
    from google_auth_oauthlib.flow import InstalledAppFlow

    path = expand(cfg.get_path("google.credentials_file", "credentials.json"))
    if not path.is_absolute():
        path = ROOT / path
    if not path.exists():
        raise RuntimeError(f"{path} introuvable (voir docs/SETUP.md §5).")
    flow = InstalledAppFlow.from_client_secrets_file(str(path), SCOPES)
    creds = flow.run_local_server(port=0, prompt="consent", access_type="offline")
    store.save("google", creds.to_json())


def _creds(cfg: Config):
    from google.auth.transport.requests import Request
    from google.oauth2.credentials import Credentials

    raw = store.load("google")
    if not raw:
        raise ToolError("Google n'est pas connecté : lancez `jarvis auth google`.")
    creds = Credentials.from_authorized_user_info(json.loads(raw), SCOPES)
    if not creds.valid:
        if creds.expired and creds.refresh_token:
            creds.refresh(Request())
            store.save("google", creds.to_json())
        else:
            raise ToolError("La session Google a expiré : relancez `jarvis auth google`.")
    return creds


_services: dict[str, object] = {}


def service(cfg: Config, name: str, version: str):
    from googleapiclient.discovery import build

    key = f"{name}/{version}"
    if key not in _services:
        _services[key] = build(name, version, credentials=_creds(cfg), cache_discovery=False)
    return _services[key]


def _enabled(cfg: Config) -> bool:
    return bool(cfg.get_path("google.enabled"))


def _headers(msg: dict) -> dict:
    return {h["name"].lower(): h["value"] for h in msg.get("payload", {}).get("headers", [])}


def _plain_text(payload: dict) -> str:
    if payload.get("mimeType") == "text/plain" and payload.get("body", {}).get("data"):
        return base64.urlsafe_b64decode(payload["body"]["data"]).decode("utf-8", "replace")
    for part in payload.get("parts", []) or []:
        text = _plain_text(part)
        if text:
            return text
    return ""


# ── Gmail ────────────────────────────────────────────────────────────────

@tool(
    "gmail_list",
    "Liste des mails Gmail. `query` suit la syntaxe Gmail (défaut « is:unread in:inbox » ; ex. « from:banque », "
    "« newer_than:2d »). Rend des références g1, g2… Affiche une carte.",
    {"query": {"type": "string"}, "count": {"type": "integer", "description": "défaut 8, max 20"}},
    enabled=_enabled,
)
def gmail_list(ctx: ToolContext, query: str = "is:unread in:inbox", count: int = 8):
    gm = service(ctx.cfg, "gmail", "v1")
    ids = gm.users().messages().list(userId="me", q=query, maxResults=max(1, min(count, 20))).execute().get("messages", [])
    if not ids:
        return "Aucun mail correspondant."
    metas = []
    for m in ids:
        full = gm.users().messages().get(userId="me", id=m["id"], format="metadata",
                                         metadataHeaders=["From", "Subject", "Date", "Message-ID"]).execute()
        h = _headers(full)
        metas.append({"id": m["id"], "threadId": full.get("threadId"), "from": parseaddr(h.get("from", ""))[0] or h.get("from", ""),
                      "address": parseaddr(h.get("from", ""))[1], "subject": h.get("subject", ""),
                      "message_id": h.get("message-id", ""), "unread": "UNREAD" in full.get("labelIds", []),
                      "snippet": full.get("snippet", "")})
    refs = ctx.remember_refs("g", metas)
    ctx.card("mail", "Gmail", items=[{"from": m["from"], "subject": m["subject"], "unread": m["unread"]} for m in metas])
    return [{"ref": r, "de": m["from"], "sujet": m["subject"], "apercu": m["snippet"][:160]} for r, m in zip(refs, metas)]


@tool("gmail_read", "Lit un mail Gmail en entier (référence g1…).", {"ref": {"type": "string"}}, required=["ref"], enabled=_enabled)
def gmail_read(ctx: ToolContext, ref: str):
    meta = ctx.ref(ref)
    full = service(ctx.cfg, "gmail", "v1").users().messages().get(userId="me", id=meta["id"], format="full").execute()
    return {"de": meta["from"], "sujet": meta["subject"], "texte": (_plain_text(full["payload"]) or full.get("snippet", ""))[:12000]}


def _raw(to: str, subject: str, body: str, extra: dict | None = None) -> str:
    msg = MIMEText(body, "plain", "utf-8")
    msg["To"], msg["Subject"] = to, subject
    for k, v in (extra or {}).items():
        msg[k] = v
    return base64.urlsafe_b64encode(msg.as_bytes()).decode()


@tool(
    "gmail_send",
    "Envoie un mail depuis Gmail. Le système demandera confirmation à Monsieur.",
    {"to": {"type": "array", "items": {"type": "string"}}, "subject": {"type": "string"}, "body": {"type": "string"}},
    required=["to", "subject", "body"],
    confirm=lambda ctx, a: f"J'envoie depuis Gmail à {', '.join(a.get('to', []))}, objet « {a.get('subject', '')} ». "
                           f"Il dit : {a.get('body', '')[:400]}",
    enabled=_enabled,
)
def gmail_send(ctx: ToolContext, to: list[str], subject: str, body: str):
    if any("@" not in x for x in to):
        raise ToolError("Il me faut des adresses e-mail complètes.")
    service(ctx.cfg, "gmail", "v1").users().messages().send(userId="me", body={"raw": _raw(", ".join(to), subject, body)}).execute()
    return "Mail envoyé."


@tool(
    "gmail_reply",
    "Répond à un mail Gmail (référence g1…). Le système demandera confirmation à Monsieur.",
    {"ref": {"type": "string"}, "body": {"type": "string"}},
    required=["ref", "body"],
    confirm=lambda ctx, a: f"Je réponds à {ctx.refs.get(a.get('ref', ''), {}).get('from', 'l’expéditeur')} : {a.get('body', '')[:400]}",
    enabled=_enabled,
)
def gmail_reply(ctx: ToolContext, ref: str, body: str):
    m = ctx.ref(ref)
    subject = m["subject"] if m["subject"].lower().startswith("re:") else f"Re: {m['subject']}"
    raw = _raw(m["address"], subject, body, {"In-Reply-To": m["message_id"], "References": m["message_id"]})
    service(ctx.cfg, "gmail", "v1").users().messages().send(userId="me", body={"raw": raw, "threadId": m["threadId"]}).execute()
    return "Réponse envoyée."


# ── Agenda ───────────────────────────────────────────────────────────────

@tool(
    "calendar_list",
    "Événements Google Agenda à venir (défaut : aujourd'hui et demain). Affiche une carte.",
    {"days": {"type": "integer", "description": "nombre de jours à couvrir, défaut 2"}},
    enabled=_enabled,
)
def calendar_list(ctx: ToolContext, days: int = 2):
    now = datetime.now().astimezone()
    start = now.replace(hour=0, minute=0, second=0, microsecond=0)
    events = service(ctx.cfg, "calendar", "v3").events().list(
        calendarId=ctx.cfg.get_path("google.calendar_id", "primary"), timeMin=start.isoformat(),
        timeMax=(start + timedelta(days=max(1, days))).isoformat(), singleEvents=True, orderBy="startTime", maxResults=25,
    ).execute().get("items", [])
    rows = []
    for e in events:
        s = e.get("start", {})
        when = s.get("dateTime", s.get("date", ""))
        rows.append({"quand": when[:16].replace("T", " "), "titre": e.get("summary", "(sans titre)"), "lieu": e.get("location", "")})
    ctx.card("agenda", "Agenda", items=[{"label": r["titre"], "value": r["quand"][5:]} for r in rows])
    return rows or "Rien de prévu."


@tool(
    "calendar_create",
    "Crée un événement dans Google Agenda. Dates au format AAAA-MM-JJTHH:MM (heure locale). "
    "Le système demandera confirmation à Monsieur.",
    {
        "title": {"type": "string"}, "start": {"type": "string"}, "end": {"type": "string", "description": "défaut : +1 h"},
        "location": {"type": "string"}, "description": {"type": "string"},
    },
    required=["title", "start"],
    confirm=lambda ctx, a: f"Je crée « {a.get('title', '')} » le {a.get('start', '').replace('T', ' à ')}.",
    enabled=_enabled,
)
def calendar_create(ctx: ToolContext, title: str, start: str, end: str = "", location: str = "", description: str = ""):
    try:
        t0 = datetime.fromisoformat(start)
        t1 = datetime.fromisoformat(end) if end else t0 + timedelta(hours=1)
    except ValueError as exc:
        raise ToolError(f"Date illisible : {exc}") from exc
    tz = ctx.cfg.get_path("user.timezone", "Europe/Paris")
    body = {"summary": title, "location": location, "description": description,
            "start": {"dateTime": t0.strftime("%Y-%m-%dT%H:%M:%S"), "timeZone": tz},
            "end": {"dateTime": t1.strftime("%Y-%m-%dT%H:%M:%S"), "timeZone": tz}}
    ev = service(ctx.cfg, "calendar", "v3").events().insert(calendarId=ctx.cfg.get_path("google.calendar_id", "primary"), body=body).execute()
    return {"cree": ev.get("summary"), "lien": ev.get("htmlLink")}


# ── Drive ────────────────────────────────────────────────────────────────

@tool(
    "drive_search",
    "Cherche des documents dans Google Drive par nom. Rend des références d1, d2…",
    {"query": {"type": "string"}},
    required=["query"],
    enabled=_enabled,
)
def drive_search(ctx: ToolContext, query: str):
    q = "name contains '{}' and trashed = false".format(query.replace("\\", "\\\\").replace("'", "\\'"))
    files = service(ctx.cfg, "drive", "v3").files().list(
        q=q, pageSize=8, orderBy="modifiedTime desc", fields="files(id,name,mimeType,modifiedTime,webViewLink)",
    ).execute().get("files", [])
    if not files:
        return "Aucun document trouvé."
    refs = ctx.remember_refs("d", files)
    ctx.card("list", f"Drive · {query}", items=[{"label": f["name"], "value": f["modifiedTime"][:10]} for f in files])
    return [{"ref": r, "nom": f["name"], "modifie": f["modifiedTime"][:10]} for r, f in zip(refs, files)]


@tool("drive_open", "Ouvre un document Drive (référence d1…) dans le navigateur.", {"ref": {"type": "string"}},
      required=["ref"], enabled=_enabled, hides_ui=True)
def drive_open(ctx: ToolContext, ref: str):
    webbrowser.open(ctx.ref(ref)["webViewLink"])
    ctx.hide_requested = True
    return "Document ouvert."
