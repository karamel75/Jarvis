"""Interprétation d'une réponse orale à « Je confirme, Monsieur ? »."""
from __future__ import annotations

from jarvis.speech import normalize

_YES = {
    "oui", "ouais", "ouai", "yes", "ok", "okay", "d'accord", "daccord", "vas y", "vas-y", "allez y",
    "go", "confirme", "je confirme", "confirmé", "confirmer", "exactement", "parfait", "c'est ca",
    "c'est bon", "absolument", "bien sur", "evidemment", "affirmatif", "envoie", "envoie le", "fais le",
    "valide", "je valide", "carrement", "tout a fait",
}
_NO = {
    "non", "nan", "no", "annule", "annuler", "stop", "arrete", "attends", "attend", "surtout pas",
    "pas maintenant", "laisse tomber", "negatif", "jamais", "pas du tout", "non merci", "oublie",
    "je ne confirme pas", "ne fais pas", "n'envoie pas", "change", "modifie",
}


def parse_answer(text: str) -> bool | None:
    """True = oui, False = non, None = pas compris. Le « non » l'emporte en cas de doute."""
    t = normalize(text)
    if not t:
        return None
    padded = f" {t} "
    for phrase in sorted(_NO, key=len, reverse=True):
        if f" {normalize(phrase)} " in padded:
            return False
    for phrase in sorted(_YES, key=len, reverse=True):
        if f" {normalize(phrase)} " in padded:
            return True
    return None
