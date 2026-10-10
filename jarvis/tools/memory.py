"""Mémoire Obsidian : lit tout le coffre, n'écrit que dans le dossier Jarvis/.

Jarvis/Profil.md         ce que Jarvis sait de Monsieur (injecté dans le prompt)
Jarvis/Souvenirs/*.md    faits mémorisés, par thème
Jarvis/Journal/AAAA-MM-JJ.md   trace des échanges du jour
"""
from __future__ import annotations

import re
from datetime import datetime
from pathlib import Path

from jarvis.config import Config, expand
from jarvis.speech import normalize
from jarvis.tools import ToolContext, ToolError, tool


def vault(cfg: Config) -> Path | None:
    v = cfg.get_path("obsidian.vault", "")
    p = expand(v) if v else None
    return p if p and p.is_dir() else None


def jarvis_dir(cfg: Config) -> Path | None:
    v = vault(cfg)
    if v is None:
        return None
    d = v / cfg.get_path("obsidian.folder", "Jarvis")
    (d / "Souvenirs").mkdir(parents=True, exist_ok=True)
    (d / "Journal").mkdir(parents=True, exist_ok=True)
    return d


def profile(cfg: Config) -> str:
    d = jarvis_dir(cfg)
    if d is None:
        return ""
    p = d / "Profil.md"
    if not p.exists():
        p.write_text("# Profil de Monsieur\n\n_Jarvis complète ce fichier au fil des conversations._\n", encoding="utf-8")
    return p.read_text(encoding="utf-8")[:6000]


def journal(cfg: Config, who: str, text: str) -> None:
    d = jarvis_dir(cfg)
    if d is None or not text.strip():
        return
    now = datetime.now()
    f = d / "Journal" / f"{now:%Y-%m-%d}.md"
    if not f.exists():
        f.write_text(f"# Journal du {now:%d/%m/%Y}\n\n", encoding="utf-8")
    with f.open("a", encoding="utf-8") as fh:
        fh.write(f"- **{now:%H:%M}** {who} : {text.strip()}\n")


def _safe_name(s: str) -> str:
    s = re.sub(r"[^\w\- ]+", "", s, flags=re.UNICODE).strip()
    return s[:60] or "Divers"


def _enabled(cfg: Config) -> bool:
    return vault(cfg) is not None


@tool(
    "remember",
    "Mémorise durablement un fait utile sur Monsieur ou ses préférences (dans Obsidian). "
    "Utilisez-le quand il dit « retiens que… » ou quand une préférence claire apparaît.",
    {
        "fact": {"type": "string"},
        "topic": {"type": "string", "description": "thème : Préférences, Personnes, Travail, Santé, Maison…"},
        "profile": {"type": "boolean", "description": "true si c'est un trait durable à ajouter au Profil"},
    },
    required=["fact"],
    enabled=_enabled,
)
def remember(ctx: ToolContext, fact: str, topic: str = "Divers", profile: bool = False):
    d = jarvis_dir(ctx.cfg)
    stamp = datetime.now().strftime("%d/%m/%Y")
    target = d / "Profil.md" if profile else d / "Souvenirs" / f"{_safe_name(topic)}.md"
    if not target.exists():
        target.write_text(f"# {_safe_name(topic)}\n\n", encoding="utf-8")
    with target.open("a", encoding="utf-8") as fh:
        fh.write(f"- {fact.strip()} _(noté le {stamp})_\n")
    return f"Noté dans {target.relative_to(vault(ctx.cfg))}."


def search_vault(root: Path, query: str, limit: int = 6) -> list[dict]:
    words = [w for w in normalize(query).split() if len(w) > 2]
    if not words:
        return []
    scored = []
    for p in root.rglob("*.md"):
        if any(part.startswith(".") for part in p.relative_to(root).parts):
            continue
        try:
            text = p.read_text(encoding="utf-8", errors="ignore")
        except OSError:
            continue
        norm = normalize(text)
        name = normalize(p.stem)
        score = sum(norm.count(w) for w in words) + 5 * sum(w in name for w in words)
        if score:
            idx = min((norm.find(w) for w in words if w in norm), default=0)
            snippet = text[max(0, idx - 200): idx + 500].strip()
            scored.append((score, {"note": str(p.relative_to(root)), "extrait": snippet}))
    scored.sort(key=lambda x: -x[0])
    return [s for _, s in scored[:limit]]


@tool(
    "recall",
    "Cherche dans tout le coffre Obsidian de Monsieur (notes, souvenirs, journal) et rend des extraits.",
    {"query": {"type": "string"}},
    required=["query"],
    enabled=_enabled,
)
def recall(ctx: ToolContext, query: str):
    hits = search_vault(vault(ctx.cfg), query)
    return hits or "Rien trouvé dans les notes."


@tool(
    "read_note",
    "Lit une note Obsidian entière (chemin relatif au coffre, tel que rendu par recall).",
    {"note": {"type": "string"}},
    required=["note"],
    enabled=_enabled,
)
def read_note(ctx: ToolContext, note: str):
    root = vault(ctx.cfg).resolve()
    p = (root / note).resolve()
    if not p.is_relative_to(root) or not p.is_file():
        raise ToolError("Note introuvable dans le coffre.")
    return p.read_text(encoding="utf-8", errors="replace")[:20000]
