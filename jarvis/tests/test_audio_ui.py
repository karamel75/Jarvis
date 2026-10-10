"""Fin de phrase, spectre pour le globe, choix de l'écran."""
from types import SimpleNamespace

import numpy as np

from jarvis.audio.ears import Endpointer
from jarvis.audio.voice import BANDS, RATE, chime, spectrum
from jarvis.ui.window import pick_screen

F = b"\x00\x00" * 320


def run(ep, pattern):
    for i, voiced in enumerate(pattern):
        r = ep.push(F, voiced)
        if r:
            return r, i
    return None, len(pattern)


def test_endpointer_sentence():
    ep = Endpointer(end_silence_ms=400, no_speech_ms=2000)
    verdict, i = run(ep, [False] * 10 + [True] * 30 + [False] * 30)
    assert verdict == "done" and i == 10 + 30 + 20 - 1
    assert len(ep.audio()) > 0


def test_endpointer_silence_timeout():
    verdict, i = run(Endpointer(no_speech_ms=1000), [False] * 100)
    assert verdict == "timeout" and i == 49


def test_endpointer_ignores_a_click():
    ep = Endpointer(no_speech_ms=1000)
    verdict, _ = run(ep, [True, False, False, False, False, False] * 10)
    assert verdict == "timeout" and not ep.started


def test_spectrum_follows_pitch():
    t = np.arange(2048) / RATE
    low = spectrum((np.sin(2 * np.pi * 150 * t) * 8000).astype(np.int16))
    high = spectrum((np.sin(2 * np.pi * 4000 * t) * 8000).astype(np.int16))
    assert len(low) == BANDS and all(0 <= v <= 1 for v in low + high)
    assert int(np.argmax(low)) < int(np.argmax(high))
    assert spectrum(np.zeros(10, dtype=np.int16)) == [0.0] * BANDS


def test_chime_is_short_and_quiet():
    pcm = np.frombuffer(chime(), dtype=np.int16)
    assert abs(len(pcm) / RATE - 0.22) < 0.01
    assert np.abs(pcm).max() < 32767 * 0.25


def test_pick_screen():
    main, ext = SimpleNamespace(x=0, y=0), SimpleNamespace(x=1920, y=0)
    assert pick_screen([main, ext]) is ext
    assert pick_screen([main]) is main
    assert pick_screen([main, ext], 0) is main
    assert pick_screen([]) is None
