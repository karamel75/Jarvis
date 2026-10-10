"""Découpage en phrases pour la voix : on parle dès la première phrase prête."""
from jarvis.speech import SentenceSplitter, clean, normalize


def speak_all(chunks, **kw):
    s = SentenceSplitter(**kw)
    out = []
    for c in chunks:
        out += s.feed(c)
    return out + s.flush()


def test_streaming_split():
    text = "Bien sûr, Monsieur. Il fait 17 degrés à Paris. Le ciel est partiellement nuageux !"
    chunks = [text[i:i + 7] for i in range(0, len(text), 7)]
    out = speak_all(chunks)
    assert out[0].startswith("Bien sûr, Monsieur.")
    assert "".join(out).replace(" ", "") == text.replace(" ", "")


def test_no_cut_in_numbers_or_titles():
    out = speak_all(["Le CAC 40 gagne 0.84 % ce matin, M. Dupont a appelé à 9 h. Voilà."])
    assert not any(o.endswith("0.") or o.endswith("M.") for o in out)


def test_clean_strips_markdown_links_and_urls():
    t = clean("**Voici** [le lien](https://exemple.fr) et https://x.y/z 🚀\n- point")
    assert "*" not in t and "http" not in t and "🚀" not in t
    assert "le lien" in t


def test_normalize():
    assert normalize("  Ça VA, Été !") == "ca va ete"
