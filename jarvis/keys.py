"""Secrets dans le Gestionnaire d'identification Windows (keyring). Jamais dans un fichier."""
from __future__ import annotations

import os

SERVICE = "jarvis"

# nom logique → variable d'environnement de secours (pratique pour les tests)
KNOWN = {
    "anthropic": "ANTHROPIC_API_KEY",
    "elevenlabs": "ELEVENLABS_API_KEY",
    "hue_username": "JARVIS_HUE_USERNAME",
    "tapo_username": "JARVIS_TAPO_USERNAME",
    "tapo_password": "JARVIS_TAPO_PASSWORD",
}


def get(name: str) -> str | None:
    try:
        import keyring

        value = keyring.get_password(SERVICE, name)
        if value:
            return value
    except Exception:
        pass
    env = KNOWN.get(name)
    return os.environ.get(env) if env else None


def set(name: str, value: str) -> None:  # noqa: A001 - API volontairement courte
    import keyring

    keyring.set_password(SERVICE, name, value)


def has(name: str) -> bool:
    return bool(get(name))
