"""Ligne de commande : `jarvis run | setup | auth | doctor | devices | say | ask | preview`."""
from __future__ import annotations

import argparse
import asyncio
import getpass
import platform
import shutil
import sys
import webbrowser

from jarvis import config, keys

OK, KO, WARN = "  ✔", "  ✘", "  ·"


def _yes(question: str, default: bool = False) -> bool:
    hint = "O/n" if default else "o/N"
    answer = input(f"{question} [{hint}] ").strip().lower()
    return default if not answer else answer in ("o", "oui", "y", "yes")


def _secret(name: str, label: str) -> None:
    current = "déjà enregistrée — Entrée pour garder" if keys.has(name) else "Entrée pour passer"
    value = getpass.getpass(f"{label} ({current}) : ").strip()
    if value:
        keys.set(name, value)
        print(f"{OK} {label} enregistrée dans le Gestionnaire d'identification Windows")


# ── commandes ────────────────────────────────────────────────────────────

def cmd_run(args) -> None:
    from jarvis import app, log

    log.setup(args.verbose)
    app.run(config.load(), window=not args.no_window)


def cmd_setup(args) -> None:
    if not config.CONFIG.exists():
        shutil.copy(config.EXAMPLE, config.CONFIG)
        print(f"{OK} config.yaml créé à partir de config.example.yaml")
    cfg = config.load()
    print("\nLes clés vont dans le Gestionnaire d'identification Windows, jamais dans un fichier.\n")
    _secret("anthropic", "Clé API Anthropic (console.anthropic.com, compte perso)")
    _secret("elevenlabs", "Clé API ElevenLabs")
    voice_id = input(f"Voice ID ElevenLabs [{cfg.get_path('voice.voice_id') or 'vide'}] : ").strip()
    if voice_id:
        config.save_value("voice.voice_id", voice_id)
    vault = input(f"Coffre Obsidian (chemin) [{cfg.get_path('obsidian.vault') or 'aucun'}] : ").strip().strip('"')
    if vault:
        config.save_value("obsidian.vault", vault)
    if _yes("Configurer les prises/ampoules Tapo ou Kasa ?"):
        user = input("Adresse e-mail du compte Tapo : ").strip()
        if user:
            keys.set("tapo_username", user)
        _secret("tapo_password", "Mot de passe Tapo")
        config.save_value("home.kasa.enabled", True)
    print("\nÉtapes suivantes : `jarvis auth outlook`, `jarvis auth google`, `jarvis auth hue`, puis `jarvis doctor`.")


def cmd_auth(args) -> None:
    cfg = config.load()
    if args.service == "outlook":
        from jarvis.tools import outlook

        if not cfg.get_path("outlook.client_id"):
            cid = input("ID d'application (client) Entra — voir docs/SETUP.md §4 : ").strip()
            if not cid:
                raise SystemExit("ID d'application requis.")
            config.save_value("outlook.client_id", cid)
            cfg = config.load()
        who = outlook.login(cfg)
        config.save_value("outlook.enabled", True)
        print(f"{OK} Outlook connecté : {who}")
    elif args.service == "google":
        from jarvis.tools import google

        google.login(cfg)
        config.save_value("google.enabled", True)
        print(f"{OK} Google connecté (Gmail, Agenda, Drive)")
    elif args.service == "hue":
        from jarvis.tools import home

        input("Appuyez sur le gros bouton du pont Hue, puis Entrée dans les 30 secondes… ")
        ip = asyncio.run(home.hue_link(cfg))
        config.save_value("home.hue.enabled", True)
        print(f"{OK} Pont Hue {ip} appairé")


def cmd_doctor(args) -> None:
    """Vérifie tout ce qui peut l'être sans parler à Jarvis."""
    cfg = config.load()
    a = cfg.get_path
    bad = 0

    def check(label: str, fn, optional: bool = False):
        nonlocal bad
        try:
            detail = fn()
            print(f"{OK} {label}" + (f" — {detail}" if detail else ""))
        except Exception as e:  # noqa: BLE001 - on veut tout afficher
            print(f"{WARN if optional else KO} {label} — {e}")
            bad += 0 if optional else 1

    def python():
        if sys.version_info < (3, 11):
            raise RuntimeError(f"Python {platform.python_version()} : 3.11 minimum (3.12 conseillé)")
        return f"{platform.python_version()} sur {platform.system()} {platform.release()}"

    def anthropic_key():
        import anthropic

        key = keys.get("anthropic")
        if not key:
            raise RuntimeError("absente — `jarvis setup`")
        model = anthropic.Anthropic(api_key=key).models.retrieve(a("brain.model"))
        return f"modèle {model.id} accessible"

    def elevenlabs():
        import httpx

        key, vid = keys.get("elevenlabs"), a("voice.voice_id")
        if not key or not vid:
            raise RuntimeError("clé ou voice_id manquant — voix de secours Edge utilisée")
        r = httpx.get(f"https://api.elevenlabs.io/v1/voices/{vid}", headers={"xi-api-key": key}, timeout=10)
        r.raise_for_status()
        return f"voix « {r.json().get('name', vid)} »"

    def microphone():
        import sounddevice as sd

        dev = sd.query_devices(a("audio.input_device"), "input")
        out = sd.query_devices(a("audio.output_device"), "output")
        return f"entrée « {dev['name']} », sortie « {out['name']} »"

    def wake():
        from jarvis.audio.ears import WakeWord

        WakeWord(a("audio.wake_threshold", 0.5))
        return "modèle « hey_jarvis » chargé"

    def whisper():
        from jarvis.audio.stt import Transcriber

        Transcriber(cfg)
        return f"faster-whisper {a('stt.model')} ({a('stt.compute_type')}, CPU)"

    def webview():
        import webview as wv

        return f"pywebview {getattr(wv, '__version__', '')} — {len(wv.screens)} écran(s)"

    def obsidian():
        vault = a("obsidian.vault")
        if not vault:
            raise RuntimeError("non configuré (facultatif)")
        path = config.expand(vault)
        if not path.is_dir():
            raise RuntimeError(f"{path} introuvable")
        return f"{path} — écrit seulement dans {a('obsidian.folder')}/"

    def outlook():
        if not a("outlook.enabled"):
            raise RuntimeError("désactivé — `jarvis auth outlook`")
        from jarvis.tools import outlook as o

        o.token(cfg)
        return "jeton valide"

    def google():
        if not a("google.enabled"):
            raise RuntimeError("désactivé — `jarvis auth google`")
        from jarvis.tools import google as g

        g.service(cfg, "gmail", "v1").users().getProfile(userId="me").execute()
        return "Gmail répond"

    def hue():
        if not a("home.hue.enabled"):
            raise RuntimeError("désactivé — `jarvis auth hue`")
        from jarvis.tools import home

        return f"pont {asyncio.run(home.hue_bridge(cfg))}"

    def everything():
        es = config.expand(a("files.everything_cli", ""))
        if not es.exists():
            raise RuntimeError("Everything absent : recherche de fichiers plus lente (facultatif)")
        return str(es)

    def tool_list():
        from jarvis import tools

        return ", ".join(sorted(t.name for t in tools.available(cfg)))

    print("\nJARVIS — diagnostic\n")
    check("Python", python)
    check("Clé Anthropic", anthropic_key)
    check("ElevenLabs", elevenlabs, optional=True)
    check("Audio", microphone)
    check("Mot-clé", wake)
    check("Transcription", whisper)
    check("Fenêtre", webview)
    check("Obsidian", obsidian, optional=True)
    check("Outlook", outlook, optional=True)
    check("Google", google, optional=True)
    check("Hue", hue, optional=True)
    check("Everything", everything, optional=True)
    check("Outils actifs", tool_list)
    print("\n" + ("Tout est prêt, Monsieur." if not bad else f"{bad} point(s) bloquant(s) à corriger."))
    sys.exit(1 if bad else 0)


def cmd_devices(args) -> None:
    import sounddevice as sd

    print(sd.query_devices())


def cmd_say(args) -> None:
    from jarvis.audio.voice import Player, Voice

    async def go():
        player = Player(config.load().get_path("audio.output_device"))
        player.start()
        await Voice(config.load()).synth(args.text, player.feed)
        await player.drain()

    asyncio.run(go())


class _ConsoleUI:
    def card(self, card: dict) -> None:
        print(f"  [carte {card.get('kind')}] {card.get('title')}")


def cmd_ask(args) -> None:
    """Le cerveau et les outils, sans micro ni voix : utile pour tester."""
    from jarvis import log
    from jarvis.brain import Brain
    from jarvis.confirm import parse_answer
    from jarvis.tools import ToolContext

    log.setup(args.verbose)
    cfg = config.load()

    async def speak(text: str) -> None:
        print(f"JARVIS › {text}")

    async def confirm(phrase: str) -> bool:
        print(f"JARVIS › {phrase}")
        return bool(parse_answer(await asyncio.to_thread(input, "VOUS   › ")))

    async def go():
        brain = Brain(cfg, ToolContext(cfg, _ConsoleUI()), speak=speak, confirm=confirm)
        question = " ".join(args.question)
        while question:
            await brain.respond(question)
            if not args.chat:
                break
            question = (await asyncio.to_thread(input, "VOUS   › ")).strip()

    asyncio.run(go())


def cmd_preview(args) -> None:
    """Le globe et les cartes dans le navigateur, sans micro ni clé (touches 1-4, h, w m e a s i)."""
    from jarvis.ui.server import UIBridge

    async def go():
        ui = UIBridge(config.load().get_path("ui.port", 8765))
        await ui.start()
        webbrowser.open(ui.url + "?demo")
        print(f"Aperçu sur {ui.url}?demo — Ctrl+C pour quitter")
        await asyncio.Event().wait()

    try:
        asyncio.run(go())
    except KeyboardInterrupt:
        pass


def main(argv: list[str] | None = None) -> None:
    p = argparse.ArgumentParser(prog="jarvis", description="Assistant vocal Jarvis.")
    sub = p.add_subparsers(dest="cmd")

    r = sub.add_parser("run", help="lance Jarvis (défaut)")
    r.add_argument("--no-window", action="store_true", help="sans globe (voix seule)")
    r.add_argument("-v", "--verbose", action="store_true")
    r.set_defaults(fn=cmd_run)

    sub.add_parser("setup", help="clés API, voix, coffre Obsidian").set_defaults(fn=cmd_setup)

    au = sub.add_parser("auth", help="connecte un compte")
    au.add_argument("service", choices=["outlook", "google", "hue"])
    au.set_defaults(fn=cmd_auth)

    sub.add_parser("doctor", help="vérifie l'installation").set_defaults(fn=cmd_doctor)
    sub.add_parser("devices", help="liste micros et haut-parleurs").set_defaults(fn=cmd_devices)

    s = sub.add_parser("say", help="fait parler Jarvis")
    s.add_argument("text")
    s.set_defaults(fn=cmd_say)

    q = sub.add_parser("ask", help="pose une question au clavier")
    q.add_argument("question", nargs="+")
    q.add_argument("--chat", action="store_true", help="continue la conversation")
    q.add_argument("-v", "--verbose", action="store_true")
    q.set_defaults(fn=cmd_ask)

    sub.add_parser("preview", help="aperçu du globe dans le navigateur").set_defaults(fn=cmd_preview)

    args = p.parse_args(argv)
    if not getattr(args, "fn", None):
        args = p.parse_args(["run", *(argv or [])])
    if sys.platform == "win32":
        for stream in (sys.stdout, sys.stderr):
            try:
                stream.reconfigure(encoding="utf-8")  # type: ignore[attr-defined]
            except Exception:
                pass
    args.fn(args)
