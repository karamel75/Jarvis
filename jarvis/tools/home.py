"""Domotique : lumières Philips Hue (pont local) et prises/ampoules TP-Link Kasa & Tapo.

Sans confirmation : allumer une lampe n'a rien d'irréversible.
"""
from __future__ import annotations

import logging

import httpx

from jarvis import keys
from jarvis.config import Config, save_value
from jarvis.speech import normalize
from jarvis.tools import ToolContext, ToolError, tool

log = logging.getLogger("jarvis.home")

# couleurs prononçables → état Hue (hue 0-65535, sat 0-254, ou température ct en mireds)
COLORS = {
    "rouge": {"hue": 0, "sat": 254}, "orange": {"hue": 6000, "sat": 254}, "jaune": {"hue": 12750, "sat": 254},
    "vert": {"hue": 25500, "sat": 254}, "cyan": {"hue": 35000, "sat": 254}, "bleu": {"hue": 46920, "sat": 254},
    "violet": {"hue": 50000, "sat": 254}, "rose": {"hue": 56100, "sat": 200}, "magenta": {"hue": 54000, "sat": 254},
    "blanc": {"ct": 300}, "blanc chaud": {"ct": 454}, "chaud": {"ct": 454}, "blanc froid": {"ct": 200},
    "froid": {"ct": 200}, "lecture": {"ct": 250}, "tamise": {"ct": 454},
}


def hue_state(on: bool | None, brightness: int | None, color: str) -> dict:
    state: dict = {}
    if on is not None:
        state["on"] = on
    if brightness is not None:
        state["bri"] = max(1, min(254, round(brightness * 2.54)))
        state.setdefault("on", brightness > 0)
    if color:
        c = COLORS.get(normalize(color))
        if c is None:
            raise ToolError(f"Couleur inconnue : {color}. Possibles : {', '.join(COLORS)}")
        state.update(c)
        state.setdefault("on", True)
    return state


# ── Hue ──────────────────────────────────────────────────────────────────

async def hue_bridge(cfg: Config) -> str:
    ip = cfg.get_path("home.hue.bridge_ip", "")
    if ip:
        return ip
    async with httpx.AsyncClient(timeout=6) as http:
        found = (await http.get("https://discovery.meethue.com")).json()
    if not found:
        raise ToolError("Aucun pont Hue trouvé sur le réseau.")
    ip = found[0]["internalipaddress"]
    save_value("home.hue.bridge_ip", ip)
    return ip


async def hue_link(cfg: Config) -> str:
    """À lancer après avoir appuyé sur le bouton du pont (commande `jarvis auth hue`)."""
    ip = await hue_bridge(cfg)
    async with httpx.AsyncClient(timeout=6, verify=False) as http:
        res = (await http.post(f"https://{ip}/api", json={"devicetype": "jarvis#pc"})).json()
    if "success" not in res[0]:
        raise RuntimeError(res[0].get("error", {}).get("description", str(res)))
    keys.set("hue_username", res[0]["success"]["username"])
    return ip


async def _hue(cfg: Config, method: str, path: str, body: dict | None = None):
    user = keys.get("hue_username")
    if not user:
        raise ToolError("Pont Hue non appairé : lancez `jarvis auth hue`.")
    ip = await hue_bridge(cfg)
    # le pont présente un certificat auto-signé ; trafic strictement local
    async with httpx.AsyncClient(timeout=6, verify=False) as http:
        r = await http.request(method, f"https://{ip}/api/{user}{path}", json=body)
    return r.json()


def pick(target: str, named: dict[str, str]) -> list[str]:
    """Ids dont le nom correspond à la cible prononcée (« salon », « lampe du bureau »)."""
    key = normalize(target)
    exact = [i for i, n in named.items() if normalize(n) == key]
    return exact or [i for i, n in named.items() if key in normalize(n) or normalize(n) in key]


@tool(
    "lights",
    "Allume, éteint, règle l'intensité ou la couleur des lumières Hue. `target` = pièce ou lampe "
    "(« salon », « chambre », « tout »).",
    {
        "target": {"type": "string"},
        "on": {"type": "boolean"},
        "brightness": {"type": "integer", "description": "0 à 100 %"},
        "color": {"type": "string", "description": "rouge, bleu, blanc chaud, lecture, tamisé…"},
    },
    required=["target"],
    enabled=lambda cfg: bool(cfg.get_path("home.hue.enabled")),
)
async def lights(ctx: ToolContext, target: str, on: bool | None = None, brightness: int | None = None, color: str = ""):
    state = hue_state(on, brightness, color)
    if not state:
        raise ToolError("Que dois-je faire de ces lumières ?")
    if normalize(target) in ("tout", "toutes", "partout", "maison", "toutes les lumieres"):
        await _hue(ctx.cfg, "PUT", "/groups/0/action", state)
        return "Toutes les lumières réglées."
    groups = await _hue(ctx.cfg, "GET", "/groups")
    ids = pick(target, {i: g["name"] for i, g in groups.items()})
    if ids:
        for i in ids:
            await _hue(ctx.cfg, "PUT", f"/groups/{i}/action", state)
        return f"Pièce réglée : {', '.join(groups[i]['name'] for i in ids)}."
    lamps = await _hue(ctx.cfg, "GET", "/lights")
    ids = pick(target, {i: l["name"] for i, l in lamps.items()})
    if not ids:
        names = [g["name"] for g in groups.values()] + [l["name"] for l in lamps.values()]
        raise ToolError(f"Je ne trouve pas « {target} ». Disponibles : {', '.join(names)}")
    for i in ids:
        await _hue(ctx.cfg, "PUT", f"/lights/{i}/state", state)
    return f"Lampe réglée : {', '.join(lamps[i]['name'] for i in ids)}."


# ── Kasa / Tapo ──────────────────────────────────────────────────────────

_devices: dict = {}


async def kasa_devices() -> dict:
    global _devices
    if _devices:
        return _devices
    from kasa import Discover

    found = await Discover.discover(username=keys.get("tapo_username"), password=keys.get("tapo_password"), timeout=5)
    for dev in found.values():
        try:
            await dev.update()
        except Exception:
            log.debug("appareil injoignable", exc_info=True)
    _devices = {dev.alias or ip: dev for ip, dev in found.items()}
    return _devices


@tool(
    "smart_plug",
    "Allume ou éteint une prise ou ampoule connectée TP-Link Kasa/Tapo (« allume la prise du radiateur »). "
    "`brightness` pour les ampoules.",
    {"target": {"type": "string"}, "on": {"type": "boolean"}, "brightness": {"type": "integer", "description": "0 à 100"}},
    required=["target"],
    enabled=lambda cfg: bool(cfg.get_path("home.kasa.enabled")),
)
async def smart_plug(ctx: ToolContext, target: str, on: bool | None = None, brightness: int | None = None):
    devices = await kasa_devices()
    names = pick(target, {n: n for n in devices})
    if not names:
        raise ToolError(f"Appareil introuvable. Disponibles : {', '.join(devices) or 'aucun'}")
    for n in names:
        dev = devices[n]
        if on is True:
            await dev.turn_on()
        elif on is False:
            await dev.turn_off()
        if brightness is not None:
            from kasa import Module

            light = dev.modules.get(Module.Light)
            if light is None:
                raise ToolError(f"{n} n'est pas une ampoule réglable.")
            await light.set_brightness(max(0, min(100, brightness)))
        await dev.update()
    return f"Fait : {', '.join(names)}."
