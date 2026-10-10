"""Outils : validation des entrées, garde-fous fichiers, météo, domotique, applis."""
from datetime import datetime
from pathlib import Path

import pytest

from jarvis import persona
from jarvis.config import Config
from jarvis.tools import ToolError, validate
from jarvis.tools.files import is_forbidden
from jarvis.tools.home import hue_state, pick
from jarvis.tools.system import match_app
from jarvis.tools.weather import describe, summarize

SCHEMA = {"properties": {"to": {"type": "array", "items": {"type": "string"}}, "n": {"type": "integer"},
                         "mode": {"type": "string", "enum": ["a", "b"]}}, "required": ["to"]}


@pytest.mark.parametrize("args,ok", [
    ({"to": ["x@y.fr"]}, True), ({"to": ["x"], "n": 3, "mode": "a"}, True),
    ({}, False), ({"to": "x@y.fr"}, False), ({"to": [1]}, False), ({"to": [], "n": True}, False),
    ({"to": [], "mode": "c"}, False), ({"to": [], "pirate": 1}, False), ("pas un objet", False),
])
def test_validate(args, ok):
    assert (validate(SCHEMA, args) is None) is ok


def test_forbidden():
    cfg = Config({"files": {"forbidden": ["C:\\Windows"], "forbidden_names": [".env", "*.kdbx", "*password*"]}})
    assert is_forbidden(Path("C:/Windows/System32/drivers/etc/hosts"), cfg)
    assert is_forbidden(Path("projets/app/.env"), cfg)
    assert is_forbidden(Path("Coffre.kdbx"), cfg)
    assert is_forbidden(Path("Mes passwords.txt"), cfg)
    assert not is_forbidden(Path("C:/WindowsApps2/x"), cfg)
    assert not is_forbidden(Path("Documents/budget.xlsx"), cfg)


def test_weather_codes_and_summary():
    assert describe(0) == ("ciel dégagé", "sun")
    assert describe(1234)[1] == "cloud"
    data = {
        "current": {"weather_code": 2, "temperature_2m": 16.6, "apparent_temperature": 15.2,
                    "relative_humidity_2m": 61, "wind_speed_10m": 13.7},
        "daily": {"time": ["2026-10-10", "2026-10-11"], "weather_code": [2, 61],
                  "temperature_2m_min": [10.6, 9.4], "temperature_2m_max": [18.2, 14.5],
                  "precipitation_probability_max": [10, 80],
                  "sunrise": ["2026-10-10T08:04"], "sunset": ["2026-10-10T19:12"]},
    }
    s = summarize("Paris", data)
    assert s["maintenant"]["temp"] == 17 and s["maintenant"]["icon"] == "cloud-sun"
    assert s["lever"] == "08:04" and s["coucher"] == "19:12"
    assert [d["jour"] for d in s["jours"]] == ["auj.", "dim"]
    assert s["jours"][1]["icon"] == "rain"


def test_hue_state():
    assert hue_state(False, None, "") == {"on": False}
    assert hue_state(None, 50, "") == {"bri": 127, "on": True}
    assert hue_state(None, 0, "")["on"] is False
    assert hue_state(None, None, "lecture")["on"] is True
    with pytest.raises(ToolError):
        hue_state(None, None, "octarine")


def test_pick_lights():
    named = {"1": "Salon", "2": "Lampe du salon", "3": "Chambre"}
    assert pick("salon", named) == ["1"]
    assert pick("chambre", named) == ["3"]
    assert sorted(pick("lampe du salon", named)) == ["1", "2"] or pick("lampe du salon", named) == ["2"]


def test_match_app():
    apps = {"deezer": "a", "microsoft word": "b", "google chrome": "c", "obsidian": "d"}
    assert match_app("Deezer", apps)[0] == "deezer"
    assert match_app("word", apps)[0] == "microsoft word"
    assert match_app("chrome", apps)[0] == "google chrome"
    assert match_app("obsidien", apps)[0] == "obsidian"
    assert match_app("photoshop", apps) is None


def test_persona():
    cfg = Config({"user": {"title": "Monsieur"}, "brief": {"topics": ["intelligence artificielle", "marchés mondiaux"]}})
    prompt = persona.system_prompt(cfg, "Aime le jazz.")
    assert "Monsieur" in prompt and "Aime le jazz." in prompt and "intelligence artificielle" in prompt
    assert persona.context_line("Lyon", datetime(2026, 10, 10, 9, 5)) == "[samedi 10 octobre 2026, 09:05 — Lyon]"
