"""La machine à états de bout en bout, avec micro, voix et cerveau simulés."""
import asyncio
import threading

from jarvis.app import App
from jarvis.config import Config
from jarvis.tools import ToolContext


class FakeUI:
    def __init__(self):
        self.events = []

    def set_state(self, s):
        if not self.events or self.events[-1] != s:
            self.events.append(s)

    def show(self):
        self.events.append("SHOW")

    def hide(self, delay=0.75):
        self.events.append("HIDE")


class FakePlayer:
    def __init__(self):
        self.idle = threading.Event()
        self.idle.set()

    async def drain(self):
        pass


class FakeMouth:
    def __init__(self):
        self.said, self.cuts, self.pending = [], 0, 0

    async def say(self, text):
        self.said.append(text)

    async def wait_done(self):
        pass

    async def play(self, pcm):
        pass

    def cut(self):
        self.cuts += 1


class FakeEars:
    """Rend les phrases prévues, une par écoute ; None = silence."""

    def __init__(self, lines):
        self.lines, self.speaking = list(lines), False

    async def listen(self, wait_s):
        await asyncio.sleep(0.01)
        line = self.lines.pop(0) if self.lines else None
        return None if line is None else line.encode()

    def cancel_listen(self):
        pass


class FakeSTT:
    def transcribe(self, pcm):
        return pcm.decode()


class FakeBrain:
    def __init__(self, app, script):
        self.app, self.script, self.heard, self.results = app, script, [], []

    def refresh_profile(self):
        pass

    async def respond(self, text):
        self.heard.append(text)
        return await self.script(self, text)


def converse(lines, script, before=None):
    """Construit l'appli DANS la boucle (Python 3.9 lie Event/Queue à la boucle courante) et converse."""
    async def go():
        app = make_app(lines, script)
        if before:
            before(app)
        await asyncio.wait_for(app.conversation(), 5)
        return app

    return asyncio.run(go())


def make_app(lines, script):
    app = App(Config({"audio": {"chime": False}}))
    app.ui, app.player, app.mouth = FakeUI(), FakePlayer(), FakeMouth()
    app.ears, app.stt = FakeEars(lines), FakeSTT()
    app.ctx = ToolContext(app.cfg, app.ui)
    app.brain = FakeBrain(app, script)
    return app


async def answer_simply(brain, text):
    await brain.app.mouth.say(f"Réponse à « {text} »")
    return "ok"


def test_conversation_then_goodbye():
    app = converse(["quelle heure est-il", "et la météo", "merci Jarvis"], answer_simply)
    assert app.brain.heard == ["quelle heure est-il", "et la météo"]
    assert app.mouth.said[-1].endswith("Monsieur.")
    assert app.ui.events[0] == "SHOW" and app.ui.events[-1] == "HIDE"
    assert not app.in_conversation


def test_silence_goes_back_to_sleep():
    app = converse([None], answer_simply)
    assert app.brain.heard == [] and app.ui.events[-1] == "HIDE"


def test_oral_confirmation():
    async def send_mail(brain, text):
        ok = await brain.app.confirm("J'envoie le mail à Léa, Monsieur ?")
        brain.results.append(ok)
        return "envoyé" if ok else "annulé"

    for answer, expected in (["oui", True], ["non", False], ["euh", None]):
        lines = ["écris à Léa", answer] + (["toujours pas clair"] if expected is None else []) + [None]
        app = converse(lines, send_mail)
        assert app.brain.results == [bool(expected)]
        if expected is None:
            assert "Oui ou non, Monsieur ?" in app.mouth.said   # relance, puis refus par défaut


def test_barge_in_cuts_the_turn():
    async def long_speech(brain, text):
        brain.app.player.idle.clear()            # Jarvis parle…
        asyncio.get_running_loop().call_later(0.15, brain.app._on_wake)  # « Hey Jarvis ! »
        await asyncio.sleep(5)
        return "jamais atteint"

    app = converse(["raconte-moi une histoire", None], long_speech)
    assert app.mouth.cuts == 1 and app.turn.cancelled()


def test_opening_an_app_hides_the_globe():
    async def open_deezer(brain, text):
        brain.app.ctx.hide_requested = True
        await asyncio.sleep(0.12)
        await brain.app.mouth.say("Deezer est ouvert, Monsieur.")
        return "ok"

    app = converse(["ouvre Deezer", None], open_deezer)
    assert app.ui.events.count("HIDE") == 2      # pendant le tour, puis à la mise en veille
    assert app.ui.events.index("HIDE") < len(app.ui.events) - 1


def test_typed_text_wakes_and_is_answered():
    def type_hello(app):
        app._typed("bonjour")
        assert app.wake.is_set()

    app = converse([None], answer_simply, before=type_hello)
    assert app.brain.heard == ["bonjour"]
