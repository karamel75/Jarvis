"""Météo (Open-Meteo, gratuit, sans clé) et localisation : Windows Location → IP → ville par défaut."""
from __future__ import annotations

import asyncio
import logging
import sys
import time
from datetime import date

import httpx

from jarvis.tools import ToolContext, ToolError, tool

log = logging.getLogger("jarvis.weather")

# codes météo OMM → (libellé, icône de carte)
WMO = {
    0: ("ciel dégagé", "sun"), 1: ("plutôt dégagé", "sun"), 2: ("partiellement nuageux", "cloud-sun"),
    3: ("couvert", "cloud"), 45: ("brouillard", "fog"), 48: ("brouillard givrant", "fog"),
    51: ("bruine légère", "drizzle"), 53: ("bruine", "drizzle"), 55: ("bruine dense", "drizzle"),
    56: ("bruine verglaçante", "drizzle"), 57: ("bruine verglaçante", "drizzle"),
    61: ("pluie faible", "rain"), 63: ("pluie", "rain"), 65: ("forte pluie", "rain"),
    66: ("pluie verglaçante", "rain"), 67: ("pluie verglaçante", "rain"),
    71: ("neige faible", "snow"), 73: ("neige", "snow"), 75: ("forte neige", "snow"), 77: ("grains de neige", "snow"),
    80: ("averses", "rain"), 81: ("averses", "rain"), 82: ("violentes averses", "rain"),
    85: ("averses de neige", "snow"), 86: ("averses de neige", "snow"),
    95: ("orage", "storm"), 96: ("orage avec grêle", "storm"), 99: ("orage avec grêle", "storm"),
}
DAYS_FR = ["lun", "mar", "mer", "jeu", "ven", "sam", "dim"]


def describe(code: int) -> tuple[str, str]:
    return WMO.get(int(code), ("conditions inconnues", "cloud"))


_loc_cache: tuple[float, dict] | None = None


async def _windows_location() -> tuple[float, float] | None:
    if sys.platform != "win32":
        return None
    try:
        from winrt.windows.devices.geolocation import Geolocator

        pos = await asyncio.wait_for(Geolocator().get_geoposition_async(), timeout=6)
        p = pos.coordinate.point.position
        return p.latitude, p.longitude
    except Exception:
        log.debug("Windows Location indisponible", exc_info=True)
        return None


async def locate(cfg) -> dict:
    """{city, lat, lon, source} — mis en cache une heure."""
    global _loc_cache
    if _loc_cache and time.time() - _loc_cache[0] < 3600:
        return _loc_cache[1]
    fallback = cfg.get_path("user.default_city", "Paris")
    loc = None
    if cfg.get_path("user.locate", True):
        async with httpx.AsyncClient(timeout=6) as http:
            coords = await _windows_location()
            if coords:
                try:
                    r = await http.get("https://api.bigdatacloud.net/data/reverse-geocode-client",
                                       params={"latitude": coords[0], "longitude": coords[1], "localityLanguage": "fr"})
                    city = r.json().get("city") or r.json().get("locality") or fallback
                    loc = {"city": city, "lat": coords[0], "lon": coords[1], "source": "windows"}
                except Exception:
                    loc = {"city": fallback, "lat": coords[0], "lon": coords[1], "source": "windows"}
            if loc is None:
                try:
                    j = (await http.get("https://ipapi.co/json/")).json()
                    if j.get("latitude"):
                        loc = {"city": j.get("city") or fallback, "lat": j["latitude"], "lon": j["longitude"], "source": "ip"}
                except Exception:
                    log.debug("géolocalisation IP impossible", exc_info=True)
    if loc is None:
        loc = await geocode(fallback)
        loc["source"] = "défaut"
    _loc_cache = (time.time(), loc)
    return loc


async def geocode(city: str) -> dict:
    async with httpx.AsyncClient(timeout=6) as http:
        r = await http.get("https://geocoding-api.open-meteo.com/v1/search",
                           params={"name": city, "count": 1, "language": "fr"})
        res = (r.json().get("results") or [None])[0]
    if not res:
        if city.lower() == "paris":
            return {"city": "Paris", "lat": 48.8566, "lon": 2.3522}
        raise ToolError(f"Ville inconnue : {city}")
    return {"city": res["name"], "lat": res["latitude"], "lon": res["longitude"]}


async def forecast(lat: float, lon: float, days: int = 4) -> dict:
    params = {
        "latitude": lat, "longitude": lon, "timezone": "auto", "forecast_days": max(1, min(days, 7)),
        "current": "temperature_2m,apparent_temperature,relative_humidity_2m,weather_code,wind_speed_10m,precipitation",
        "daily": "weather_code,temperature_2m_max,temperature_2m_min,precipitation_probability_max,sunrise,sunset",
    }
    async with httpx.AsyncClient(timeout=8) as http:
        r = await http.get("https://api.open-meteo.com/v1/forecast", params=params)
        r.raise_for_status()
        return r.json()


def summarize(city: str, data: dict) -> dict:
    cur, daily = data["current"], data["daily"]
    label, icon = describe(cur["weather_code"])
    days = []
    for i, d in enumerate(daily["time"]):
        dl, di = describe(daily["weather_code"][i])
        days.append({
            "jour": "auj." if i == 0 else DAYS_FR[date.fromisoformat(d).weekday()],
            "min": round(daily["temperature_2m_min"][i]), "max": round(daily["temperature_2m_max"][i]),
            "pluie_pct": daily["precipitation_probability_max"][i], "ciel": dl, "icon": di,
        })
    return {
        "ville": city,
        "maintenant": {"temp": round(cur["temperature_2m"]), "ressenti": round(cur["apparent_temperature"]),
                       "humidite": cur["relative_humidity_2m"], "vent_kmh": round(cur["wind_speed_10m"]),
                       "ciel": label, "icon": icon},
        "lever": daily["sunrise"][0][-5:], "coucher": daily["sunset"][0][-5:],
        "jours": days,
    }


@tool(
    "get_weather",
    "Météo actuelle et prévisions. Affiche automatiquement une carte holographique. "
    "Sans `city`, utilise la position actuelle de Monsieur.",
    {"city": {"type": "string"}, "days": {"type": "integer", "description": "1 à 7, défaut 4"}},
)
async def get_weather(ctx: ToolContext, city: str = "", days: int = 4):
    loc = await geocode(city) if city else await locate(ctx.cfg)
    info = summarize(loc["city"], await forecast(loc["lat"], loc["lon"], days))
    ctx.card("weather", info["ville"], **info)
    return info
