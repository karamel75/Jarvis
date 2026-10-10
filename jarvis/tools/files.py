"""Fichiers : recherche (Everything si installé), ouverture, lecture. Jamais de suppression."""
from __future__ import annotations

import fnmatch
import os
import subprocess
import sys
import time
from datetime import datetime
from pathlib import Path

from jarvis.config import Config, expand
from jarvis.speech import normalize
from jarvis.tools import ToolContext, ToolError, tool

WIN = sys.platform == "win32"
NO_WINDOW = 0x08000000 if WIN else 0

KINDS = {
    "pdf": {".pdf"},
    "word": {".doc", ".docx", ".odt", ".rtf"},
    "excel": {".xls", ".xlsx", ".xlsm", ".csv", ".ods"},
    "powerpoint": {".ppt", ".pptx", ".odp"},
    "image": {".jpg", ".jpeg", ".png", ".gif", ".webp", ".heic", ".bmp"},
    "video": {".mp4", ".mov", ".mkv", ".avi", ".webm"},
    "audio": {".mp3", ".wav", ".flac", ".m4a", ".ogg"},
    "texte": {".txt", ".md", ".json", ".yaml", ".yml", ".log", ".py", ".js", ".html", ".css"},
}
TEXT_EXT = KINDS["texte"] | {".csv"}
SKIP_DIRS = {"node_modules", ".git", "__pycache__", ".venv", "venv", "appdata", "$recycle.bin", "windows"}
KNOWN_FOLDERS = {
    "bureau": "~/Desktop", "desktop": "~/Desktop", "documents": "~/Documents",
    "telechargements": "~/Downloads", "downloads": "~/Downloads", "images": "~/Pictures",
    "photos": "~/Pictures", "musique": "~/Music", "videos": "~/Videos", "home": "~",
}


def is_forbidden(path: Path, cfg: Config) -> bool:
    """Dossiers système, profils de navigateur, coffres de mots de passe, clés : intouchables."""
    p = str(path.expanduser()).replace("/", "\\").lower()
    for root in cfg.get_path("files.forbidden", []):
        r = str(expand(root)).replace("/", "\\").lower().rstrip("\\")
        if p == r or p.startswith(r + "\\"):
            return True
    name = path.name.lower()
    return any(fnmatch.fnmatch(name, pat.lower()) for pat in cfg.get_path("files.forbidden_names", []))


def _everything(cfg: Config, query: str, limit: int) -> list[Path] | None:
    es = expand(cfg.get_path("files.everything_cli", ""))
    if not WIN or not es.exists():
        return None
    out = subprocess.run(
        [str(es), "-n", str(limit * 3), "-sort", "date-modified-descending", query],
        capture_output=True, text=True, timeout=8, creationflags=NO_WINDOW, encoding="utf-8", errors="replace",
    )
    return [Path(line) for line in out.stdout.splitlines() if line.strip()]


def _walk(cfg: Config, words: list[str], exts: set[str] | None, limit: int, budget_s: float = 5.0) -> list[Path]:
    found: list[Path] = []
    stop = time.time() + budget_s
    for root in cfg.get_path("files.roots", ["~"]):
        for dirpath, dirnames, filenames in os.walk(expand(root)):
            if time.time() > stop:
                return found
            dirnames[:] = [d for d in dirnames if d.lower() not in SKIP_DIRS and not d.startswith(".")]
            for f in filenames:
                n = normalize(f)
                if all(w in n for w in words) and (not exts or Path(f).suffix.lower() in exts):
                    found.append(Path(dirpath) / f)
                    if len(found) >= limit * 3:
                        return found
    return found


@tool(
    "find_files",
    "Cherche des fichiers sur le PC par mots du nom. Rend des références f1, f2… à passer à open_file / read_file.",
    {
        "query": {"type": "string", "description": "mots du nom de fichier"},
        "kind": {"type": "string", "enum": list(KINDS), "description": "type de fichier (facultatif)"},
        "limit": {"type": "integer", "description": "nombre max de résultats (défaut 8)"},
    },
    required=["query"],
)
def find_files(ctx: ToolContext, query: str, kind: str = "", limit: int = 8):
    exts = KINDS.get(kind)
    hits = _everything(ctx.cfg, query, limit)
    if hits is None:
        hits = _walk(ctx.cfg, normalize(query).split(), exts, limit)
        hits.sort(key=lambda p: p.stat().st_mtime if p.exists() else 0, reverse=True)
    hits = [p for p in hits if p.is_file() and not is_forbidden(p, ctx.cfg) and (not exts or p.suffix.lower() in exts)]
    hits = hits[:limit]
    if not hits:
        return "Aucun fichier trouvé."
    refs = ctx.remember_refs("f", [str(p) for p in hits])
    rows = []
    for ref, p in zip(refs, hits):
        st = p.stat()
        rows.append({"ref": ref, "nom": p.name, "dossier": str(p.parent),
                     "modifie": datetime.fromtimestamp(st.st_mtime).strftime("%d/%m/%Y %H:%M"),
                     "taille_ko": round(st.st_size / 1024)})
    ctx.card("list", f"Fichiers · {query}", items=[{"label": r["nom"], "value": r["modifie"]} for r in rows])
    return rows


def _resolve(ctx: ToolContext, ref_or_path: str) -> Path:
    raw = ctx.ref(ref_or_path) if ref_or_path in ctx.refs else ref_or_path
    path = expand(raw)
    if not path.exists():
        raise ToolError(f"Introuvable : {path}")
    if is_forbidden(path, ctx.cfg):
        raise ToolError("Ce fichier est dans une zone protégée, je n'y touche pas.")
    return path


@tool(
    "open_file",
    "Ouvre un fichier ou un dossier avec son application par défaut et y emmène Monsieur. "
    "`target` = référence (f1…), chemin, ou dossier connu (bureau, documents, téléchargements, images).",
    {"target": {"type": "string"}},
    required=["target"],
    hides_ui=True,
)
def open_file(ctx: ToolContext, target: str):
    known = KNOWN_FOLDERS.get(normalize(target))
    path = expand(known) if known else _resolve(ctx, target)
    if WIN:
        os.startfile(str(path))
    else:
        subprocess.Popen(["open", str(path)])
    ctx.hide_requested = True
    return f"Ouvert : {path.name or path}"


@tool(
    "read_file",
    "Lit le contenu d'un fichier texte (txt, md, csv, json, code) pour le résumer ou répondre à une question.",
    {"target": {"type": "string", "description": "référence f1… ou chemin"}},
    required=["target"],
)
def read_file(ctx: ToolContext, target: str):
    path = _resolve(ctx, target)
    if path.suffix.lower() not in TEXT_EXT:
        raise ToolError("Je ne lis directement que les fichiers texte ; ouvrez-le avec open_file.")
    text = path.read_text(encoding="utf-8", errors="replace")
    return text[:30000] + ("\n[…tronqué]" if len(text) > 30000 else "")
