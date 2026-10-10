"""Ce que Monsieur dit, et comment Jarvis le comprend."""
import pytest

from jarvis.app import goodbye_line, is_goodbye
from jarvis.audio.stt import clean_transcript
from jarvis.confirm import parse_answer


@pytest.mark.parametrize("text,expected", [
    ("Oui", True), ("Oui, envoie-le", True), ("Vas-y", True), ("D'accord.", True), ("je confirme", True),
    ("Non", False), ("Non, attends", False), ("Annule", False), ("Oui... non, attends", False),
    ("N'envoie pas", False), ("Surtout pas", False),
    ("Euh", None), ("", None), ("Quelle heure est-il ?", None),
])
def test_parse_answer(text, expected):
    assert parse_answer(text) is expected


@pytest.mark.parametrize("text", [
    "Merci Jarvis", "merci jarvis.", "Merci", "Non merci", "C'est tout, merci", "C’est tout",
    "Ce sera tout", "Bonne nuit Jarvis", "Au revoir", "À plus", "Parfait, merci beaucoup", "Tu peux disposer",
])
def test_goodbye(text):
    assert is_goodbye(text)


@pytest.mark.parametrize("text", [
    "Merci Jarvis, et la météo demain ?", "Merci, lis-moi mes mails", "Oui", "Non",
    "C'est tout ce que tu as trouvé ?", "Bonne nuit, éteins les lumières", "",
])
def test_not_goodbye(text):
    assert not is_goodbye(text)


def test_goodbye_line():
    assert goodbye_line("bonne nuit Jarvis") == "Bonne nuit, Monsieur."
    assert "Monsieur" in goodbye_line("merci")


@pytest.mark.parametrize("raw,clean", [
    ("Hey Jarvis, quelle heure est-il ?", "quelle heure est-il ?"),
    ("  ok   jarvis  ouvre Deezer", "ouvre Deezer"),
    ("Sous-titres réalisés par la communauté d'Amara.org", ""),
    ("...", ""),
    ("Mets la météo", "Mets la météo"),
])
def test_clean_transcript(raw, clean):
    assert clean_transcript(raw) == clean
