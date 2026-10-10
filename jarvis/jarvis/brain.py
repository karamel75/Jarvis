"""Le cerveau : boucle Claude en flux, outils, confirmation imposée par le code.

Le texte arrive token par token, il est découpé en phrases et envoyé à la voix au fil
de l'eau : Jarvis commence à parler avant que Claude ait fini d'écrire.
"""
from __future__ import annotations

import asyncio
import json
import logging
import time
from typing import Awaitable, Callable

import anthropic

from jarvis import keys, persona, tools
from jarvis.config import Config
from jarvis.speech import SentenceSplitter
from jarvis.tools import ToolContext, ToolError
from jarvis.tools import memory as obsidian

log = logging.getLogger("jarvis.brain")

Speak = Callable[[str], Awaitable[None]]       # met une phrase en file pour la voix
Confirm = Callable[[str], Awaitable[bool]]     # lit la phrase, écoute oui/non
MAX_STEPS = 12                                 # appels d'outils enchaînés au maximum par demande


class Brain:
    def __init__(self, cfg: Config, ctx: ToolContext, speak: Speak, confirm: Confirm,
                 on_state: Callable[[str], None] = lambda s: None):
        key = keys.get("anthropic")
        if not key:
            raise RuntimeError("Clé Anthropic absente : lancez `jarvis setup`.")
        self.client = anthropic.AsyncAnthropic(api_key=key, max_retries=3)
        self.cfg, self.ctx = cfg, ctx
        self.speak, self.confirm, self.on_state = speak, confirm, on_state
        self.messages: list[dict] = []
        self.last_turn = 0.0
        self.city = cfg.get_path("user.default_city", "Paris")
        self._system = ""

    # ── préparation ──────────────────────────────────────────────────────

    def _tools(self) -> tuple[list[dict], dict[str, tools.Tool]]:
        avail = {t.name: t for t in tools.available(self.cfg)}
        defs = [t.definition() for t in avail.values()]
        if self.cfg.get_path("brain.web_search", True):
            defs.append({"type": "web_search_20260209", "name": "web_search", "max_uses": 5})
        return defs, avail

    def _system_blocks(self) -> list[dict]:
        if not self._system:
            self._system = persona.system_prompt(self.cfg, obsidian.profile(self.cfg))
        # tools + system forment un préfixe stable : mis en cache (≈ -90 % sur l'entrée répétée)
        return [{"type": "text", "text": self._system, "cache_control": {"type": "ephemeral"}}]

    def refresh_profile(self) -> None:
        self._system = ""

    def _trim(self) -> None:
        idle = time.time() - self.last_turn
        if self.last_turn and idle > 60 * self.cfg.get_path("brain.reset_after_minutes", 30):
            self.messages.clear()
            self.refresh_profile()
        keep = self.cfg.get_path("brain.history_turns", 24)
        while len(self.messages) > keep:
            # on coupe par le début, en recommençant toujours sur un vrai message de Monsieur
            self.messages.pop(0)
            while self.messages and not _is_user_text(self.messages[0]):
                self.messages.pop(0)

    # ── tour de parole ───────────────────────────────────────────────────

    async def respond(self, text: str) -> str:
        """Traite une demande ; parle au fil de l'eau ; rend le texte complet prononcé."""
        self._trim()
        snapshot = len(self.messages)
        self.messages.append({"role": "user", "content": f"{persona.context_line(self.city)} {text}"})
        spoken: list[str] = []
        try:
            await self._loop(spoken)
        except asyncio.CancelledError:
            # coupé par Monsieur : on garde une trace cohérente (jamais de tool_use orphelin)
            del self.messages[snapshot + 1:]
            partial = " ".join(spoken).strip()
            self.messages.append({"role": "assistant", "content": (partial + " …" if partial else "…") + " [interrompu]"})
            raise
        except anthropic.AuthenticationError:
            del self.messages[snapshot:]
            await self.speak("Ma clé d'accès au cerveau est refusée, Monsieur. Il faudra relancer la configuration.")
        except anthropic.APIConnectionError:
            del self.messages[snapshot:]
            await self.speak("Je n'arrive pas à joindre mes serveurs, Monsieur. La connexion semble capricieuse.")
        except anthropic.APIStatusError as exc:
            del self.messages[snapshot:]
            log.error("API %s : %s", exc.status_code, exc)
            await self.speak("Mes serveurs font des difficultés. Je vous propose de réessayer dans un instant.")
        finally:
            self.last_turn = time.time()
        return " ".join(spoken)

    async def _loop(self, spoken: list[str]) -> None:
        defs, avail = self._tools()
        json_retries = 0
        for _ in range(MAX_STEPS):
            splitter = SentenceSplitter()
            self.on_state("think")
            kwargs = dict(
                model=self.cfg.get_path("brain.model", "claude-sonnet-5"),
                max_tokens=self.cfg.get_path("brain.max_tokens", 4096),
                system=self._system_blocks(),
                tools=defs,
                messages=self.messages,
                output_config={"effort": self.cfg.get_path("brain.effort", "low")},
            )
            try:
                async with self.client.messages.stream(**kwargs) as stream:
                    async for event in stream:
                        if event.type == "text":
                            for sentence in splitter.feed(event.text):
                                spoken.append(sentence)
                                await self.speak(sentence)
                    response = await stream.get_final_message()
                json_retries = 0
            except ValueError:
                # entrée d'outil JSON illisible (flux « eager ») : on relance ce tour, 2 fois max
                json_retries += 1
                if json_retries > 2:
                    raise
                continue
            for sentence in splitter.flush():
                spoken.append(sentence)
                await self.speak(sentence)

            self.messages.append({"role": "assistant", "content": response.content})
            if response.stop_reason == "pause_turn":  # recherche web longue : on reprend
                continue
            uses = [b for b in response.content if b.type == "tool_use"]
            if response.stop_reason == "refusal" or not uses:
                return
            if response.stop_reason == "max_tokens":
                # entrée d'outil tronquée : on ne l'exécute pas
                self.messages.append({"role": "user", "content": [
                    {"type": "tool_result", "tool_use_id": b.id, "is_error": True,
                     "content": "Entrée tronquée (max_tokens). Recommencez plus court."} for b in uses]})
                continue
            results = [await self._run_tool(b, avail) for b in uses]
            self.messages.append({"role": "user", "content": results})
        await self.speak("Je m'arrête là, Monsieur : cette demande tourne en rond.")

    async def _run_tool(self, block, avail: dict[str, tools.Tool]) -> dict:
        def result(content, error: bool = False) -> dict:
            out = {"type": "tool_result", "tool_use_id": block.id, "content": content}
            if error:
                out["is_error"] = True
            return out

        t = avail.get(block.name)
        if t is None:
            return result(f"Outil inconnu : {block.name}", True)
        args = block.input if isinstance(block.input, dict) else {}
        problem = tools.validate(t.schema, block.input)
        if problem:
            return result(json.dumps({"INVALID_JSON": json.dumps(block.input, ensure_ascii=False), "erreur": problem},
                                     ensure_ascii=False), True)

        if t.confirm is not None:
            phrase = t.confirm(self.ctx, args)
            if phrase:
                title = self.cfg.get_path("user.title", "Monsieur")
                if not await self.confirm(f"{phrase} Je confirme, {title} ?"):
                    log.info("action refusée : %s", block.name)
                    return result("Monsieur a refusé ou n'a pas confirmé. Ne rien faire ; en prendre acte en une phrase.")

        self.on_state("think")
        log.info("outil %s %s", block.name, json.dumps(args, ensure_ascii=False)[:300])
        try:
            return result(tools.to_content(await tools.run(t, self.ctx, args)))
        except ToolError as exc:
            return result(str(exc), True)
        except Exception as exc:
            log.exception("outil %s en échec", block.name)
            return result(f"Erreur technique : {type(exc).__name__}: {exc}", True)


def _is_user_text(msg: dict) -> bool:
    return msg["role"] == "user" and isinstance(msg["content"], str)
