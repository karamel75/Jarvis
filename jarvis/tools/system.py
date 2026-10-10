"""Contrôle du PC : applications, sites, volume, alimentation, état, vision d'écran, fenêtres."""
from __future__ import annotations

import base64
import difflib
import io
import json
import logging
import os
import subprocess
import sys
import time
import webbrowser
from urllib.parse import quote_plus

from jarvis.speech import normalize
from jarvis.tools import ToolContext, ToolError, tool

log = logging.getLogger("jarvis.system")
WIN = sys.platform == "win32"
NO_WINDOW = 0x08000000 if WIN else 0

# raccourcis vocaux → commande ou URI Windows
ALIASES = {
    "explorateur": "explorer.exe",
    "explorateur de fichiers": "explorer.exe",
    "parametres": "ms-settings:",
    "reglages": "ms-settings:",
    "calculatrice": "calc.exe",
    "bloc notes": "notepad.exe",
    "terminal": "wt.exe",
    "gestionnaire des taches": "taskmgr.exe",
    "paint": "mspaint.exe",
    "capture d'ecran": "ms-screenclip:",
    "outil capture": "ms-screenclip:",
    "horloge": "ms-clock:",
    "meteo windows": "msnweather:",
    "microsoft store": "ms-windows-store:",
}

_apps_cache: dict[str, str] = {}
_apps_time = 0.0


def _ps(command: str, timeout: int = 15) -> str:
    out = subprocess.run(
        ["powershell", "-NoProfile", "-NonInteractive", "-Command", command],
        capture_output=True, text=True, timeout=timeout, creationflags=NO_WINDOW, encoding="utf-8", errors="replace",
    )
    return out.stdout


def _start_apps() -> dict[str, str]:
    """Toutes les applis du menu Démarrer (classiques et Store) : nom normalisé → AppID."""
    global _apps_cache, _apps_time
    if _apps_cache and time.time() - _apps_time < 3600:
        return _apps_cache
    raw = _ps("[Console]::OutputEncoding=[Text.Encoding]::UTF8; Get-StartApps | ConvertTo-Json -Compress")
    apps = json.loads(raw) if raw.strip() else []
    if isinstance(apps, dict):
        apps = [apps]
    _apps_cache = {normalize(a["Name"]): a["AppID"] for a in apps if a.get("Name") and a.get("AppID")}
    _apps_time = time.time()
    return _apps_cache


def match_app(name: str, apps: dict[str, str]) -> tuple[str, str] | None:
    """Trouve l'appli la plus proche d'un nom prononcé (« ouvre Deezer », « lance Word »)."""
    key = normalize(name)
    if key in apps:
        return key, apps[key]
    starts = [k for k in apps if k.startswith(key) or f" {key}" in f" {k}"]
    if starts:
        best = min(starts, key=len)
        return best, apps[best]
    close = difflib.get_close_matches(key, list(apps), n=1, cutoff=0.6)
    if close:
        return close[0], apps[close[0]]
    return None


@tool(
    "open_app",
    "Ouvre une application Windows (Deezer, Outlook, Word, Chrome, Obsidian, Paramètres…) et y emmène Monsieur. "
    "À utiliser quand il dit « ouvre », « lance », « mets-moi ».",
    {"name": {"type": "string", "description": "Nom de l'application tel que prononcé"}},
    required=["name"],
    hides_ui=True,
)
def open_app(ctx: ToolContext, name: str):
    if not WIN:
        raise ToolError("Disponible sous Windows uniquement.")
    key = normalize(name)
    if key in ALIASES:
        os.startfile(ALIASES[key])
        ctx.hide_requested = True
        return f"{name} ouvert."
    found = match_app(name, _start_apps())
    if not found:
        raise ToolError(f"Aucune application ne ressemble à « {name} ».")
    label, app_id = found
    subprocess.Popen(["explorer.exe", f"shell:AppsFolder\\{app_id}"], creationflags=NO_WINDOW)
    ctx.hide_requested = True
    return f"Application ouverte : {label}."


@tool(
    "open_website",
    "Ouvre une page web dans le navigateur et y emmène Monsieur. Donnez une URL complète si vous la connaissez "
    "(https://www.youtube.com, https://mail.google.com…) ; sinon `search` lance une recherche Google affichée.",
    {
        "url": {"type": "string", "description": "URL complète https://…"},
        "search": {"type": "string", "description": "Requête à afficher dans Google si aucune URL"},
    },
    hides_ui=True,
)
def open_website(ctx: ToolContext, url: str = "", search: str = ""):
    if url:
        if not url.startswith(("http://", "https://")):
            url = "https://" + url
        target = url
    elif search:
        target = "https://www.google.com/search?q=" + quote_plus(search)
    else:
        raise ToolError("Il faut une URL ou une recherche.")
    webbrowser.open(target)
    ctx.hide_requested = True
    return f"Page ouverte : {target}"


def _endpoint():
    from ctypes import POINTER, cast

    from comtypes import CLSCTX_ALL, CoInitialize
    from pycaw.pycaw import AudioUtilities, IAudioEndpointVolume

    CoInitialize()
    speakers = AudioUtilities.GetSpeakers()
    if hasattr(speakers, "EndpointVolume"):  # pycaw récent
        return speakers.EndpointVolume
    iface = speakers.Activate(IAudioEndpointVolume._iid_, CLSCTX_ALL, None)
    return cast(iface, POINTER(IAudioEndpointVolume))


@tool(
    "set_volume",
    "Règle le volume général du PC. `level` absolu 0-100, ou `delta` relatif (+10, -20), ou `mute`.",
    {
        "level": {"type": "integer", "description": "0 à 100"},
        "delta": {"type": "integer", "description": "variation, ex. 10 ou -10"},
        "mute": {"type": "boolean"},
    },
)
def set_volume(ctx: ToolContext, level: int | None = None, delta: int | None = None, mute: bool | None = None):
    if not WIN:
        raise ToolError("Disponible sous Windows uniquement.")
    ep = _endpoint()
    if mute is not None:
        ep.SetMute(1 if mute else 0, None)
    current = round(ep.GetMasterVolumeLevelScalar() * 100)
    if level is not None or delta is not None:
        target = level if level is not None else current + (delta or 0)
        target = max(0, min(100, int(target)))
        ep.SetMute(0, None)
        ep.SetMasterVolumeLevelScalar(target / 100, None)
        current = target
    return {"volume": current, "muet": bool(ep.GetMute())}


_POWER = {
    "lock": ["rundll32.exe", "user32.dll,LockWorkStation"],
    "sleep": ["rundll32.exe", "powrprof.dll,SetSuspendState", "0,1,0"],
    "shutdown": ["shutdown", "/s", "/t", "30"],
    "restart": ["shutdown", "/r", "/t", "30"],
    "cancel": ["shutdown", "/a"],
}
_POWER_FR = {"sleep": "mettre le PC en veille", "shutdown": "éteindre le PC dans 30 secondes",
             "restart": "redémarrer le PC dans 30 secondes"}


@tool(
    "power",
    "Verrouille, met en veille, éteint ou redémarre le PC (cancel annule un arrêt programmé).",
    {"action": {"type": "string", "enum": list(_POWER)}},
    required=["action"],
    confirm=lambda ctx, a: f"Je vais {_POWER_FR[a['action']]}." if a.get("action") in _POWER_FR else "",
)
def power(ctx: ToolContext, action: str):
    if not WIN:
        raise ToolError("Disponible sous Windows uniquement.")
    subprocess.Popen(_POWER[action], creationflags=NO_WINDOW)
    return f"Action {action} lancée."


@tool("system_status", "État du PC : batterie, processeur, mémoire, disque, temps depuis le démarrage.")
def system_status(ctx: ToolContext):
    import psutil

    bat = psutil.sensors_battery()
    disk = psutil.disk_usage(os.path.expanduser("~"))
    return {
        "processeur_pct": psutil.cpu_percent(interval=0.4),
        "memoire_pct": psutil.virtual_memory().percent,
        "disque_libre_go": round(disk.free / 1e9, 1),
        "batterie_pct": round(bat.percent) if bat else None,
        "sur_secteur": bat.power_plugged if bat else None,
        "allume_depuis_h": round((time.time() - psutil.boot_time()) / 3600, 1),
    }


@tool(
    "look_at_screen",
    "Fait une capture de l'écran et vous la montre. UNIQUEMENT si Monsieur le demande explicitement "
    "(« regarde mon écran », « tu vois ça ? »). Jamais de votre propre initiative.",
    {"screen": {"type": "integer", "description": "1 = principal, 2 = second écran ; 0 = tous"}},
)
def look_at_screen(ctx: ToolContext, screen: int = 1):
    import mss
    from PIL import Image

    with mss.mss() as sct:
        monitors = sct.monitors  # [0] = tous les écrans réunis
        idx = screen if 0 <= screen < len(monitors) else 1
        shot = sct.grab(monitors[idx])
    img = Image.frombytes("RGB", shot.size, shot.rgb)
    img.thumbnail((1568, 1568))
    buf = io.BytesIO()
    img.save(buf, format="JPEG", quality=80)
    data = base64.b64encode(buf.getvalue()).decode()
    return [
        {"type": "image", "source": {"type": "base64", "media_type": "image/jpeg", "data": data}},
        {"type": "text", "text": "Capture de l'écran demandée par Monsieur. Ne la conservez pas en mémoire."},
    ]


@tool(
    "move_window",
    "Déplace et agrandit la fenêtre d'une application sur un écran (« mets Outlook sur l'écran externe »).",
    {
        "app": {"type": "string", "description": "Mot du titre de la fenêtre (Outlook, Chrome, Deezer…)"},
        "screen": {"type": "integer", "description": "1 = principal, 2 = second écran"},
    },
    required=["app", "screen"],
)
def move_window(ctx: ToolContext, app: str, screen: int):
    if not WIN:
        raise ToolError("Disponible sous Windows uniquement.")
    import win32api
    import win32con
    import win32gui

    wanted = normalize(app)
    hits = []

    def _enum(hwnd, _):
        if win32gui.IsWindowVisible(hwnd):
            title = win32gui.GetWindowText(hwnd)
            if title and wanted in normalize(title):
                hits.append(hwnd)

    win32gui.EnumWindows(_enum, None)
    if not hits:
        raise ToolError(f"Aucune fenêtre ouverte ne contient « {app} ».")
    monitors = win32api.EnumDisplayMonitors()
    primary_first = sorted(monitors, key=lambda m: win32api.GetMonitorInfo(m[0])["Flags"] != 1)
    if not 1 <= screen <= len(primary_first):
        raise ToolError(f"Il n'y a que {len(primary_first)} écran(s).")
    left, top, right, bottom = win32api.GetMonitorInfo(primary_first[screen - 1][0])["Work"]
    hwnd = hits[0]
    win32gui.ShowWindow(hwnd, win32con.SW_RESTORE)
    win32gui.MoveWindow(hwnd, left, top, right - left, bottom - top, True)
    win32gui.ShowWindow(hwnd, win32con.SW_MAXIMIZE)
    try:
        win32gui.SetForegroundWindow(hwnd)
    except Exception:
        pass
    ctx.hide_requested = True
    return f"Fenêtre « {win32gui.GetWindowText(hwnd)} » placée sur l'écran {screen}."
