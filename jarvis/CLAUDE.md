# CLAUDE.md — instructions pour Claude Code

Tu arrives sur le **PC Windows personnel** de l'utilisateur (« Monsieur »). Ton rôle : installer Jarvis, le tester, et l'ajuster jusqu'à ce qu'il marche vraiment. Le code a été écrit et testé sur un autre ordinateur, **sans Windows, sans micro, sans clé** : tout ce qui touche au matériel et aux comptes est à valider ici.

Réponds à l'utilisateur en français. Le code, les commentaires et les messages sont en français ; garde ce style.

## Règles à ne jamais casser

Elles sont la raison d'être du projet. Toute modification doit les préserver, et les tests doivent continuer à le prouver.

1. **Confirmation orale imposée par le code.** Un outil qui envoie quelque chose à quelqu'un ou qu'on ne peut pas défaire déclare `confirm=` dans `@tool(...)`. `Brain` appelle alors `App.confirm()` avant d'exécuter. Silence ou réponse floue = **non**. Outils concernés aujourd'hui : `gmail_send`, `gmail_reply`, `calendar_create`, `outlook_send`, `outlook_reply`, `power`. Ne retire jamais un `confirm=`. Ajoutes-en un à tout nouvel outil qui écrit chez un tiers.
2. **Zéro suppression.** Aucun outil ne supprime de mail, de fichier, de rendez-vous ni de note. N'en ajoute pas, même si on te le demande « pour tester ». Les scopes OAuth sont en lecture seule plus envoi (`Mail.Read` + `Mail.Send`, `gmail.readonly` + `gmail.send`, `drive.readonly`). Seul `calendar.events` permettrait techniquement une suppression : le code n'appelle aucun DELETE. N'élargis pas ces scopes.
3. **Zones interdites.** `files.forbidden` et `files.forbidden_names` (dans `config.yaml`), appliqués par `files.is_forbidden()`. Ne les affaiblis pas.
4. **Secrets.**
   - Les clés vont dans `keyring` (service `jarvis`, donc dans le Gestionnaire d'identification Windows), via `jarvis setup`.
   - Les jetons OAuth sont chiffrés DPAPI dans `%LOCALAPPDATA%\Jarvis`.
   - **N'écris jamais une clé dans un fichier, un commit, un log ou ta réponse.** Si l'utilisateur colle une clé dans le chat, dis-lui de lancer `jarvis setup` plutôt que de l'utiliser toi-même.
5. **Obsidian.** Jarvis lit tout le coffre mais n'écrit que dans `obsidian.folder` (`Jarvis/` par défaut).
6. **Capture d'écran** seulement quand Monsieur la demande (`look_at_screen`).
7. **Voix.** Pas de clonage de la voix d'un comédien réel. Voir `docs/VOICE.md`.

## Installation, dans cet ordre

```powershell
powershell -ExecutionPolicy Bypass -File scripts\install.ps1   # Python 3.12, .venv, dépendances, modèles, WebView2
.\.venv\Scripts\activate
pytest -q                     # 70 tests, doivent tous passer sous Windows aussi
jarvis preview                # le globe dans le navigateur : vérifier le rendu (touches 1-4, h, w m e a s i)
jarvis setup                  # l'UTILISATEUR tape ses clés (getpass) — ne le fais pas à sa place
jarvis doctor                 # chaque ✘ est à corriger avant d'aller plus loin
jarvis say "Bonsoir, Monsieur."           # voix ElevenLabs
jarvis ask "quel temps fait-il demain ?"  # cerveau + outils, sans micro
jarvis ask --chat "ouvre le bloc-notes"
jarvis run -v                 # le vrai : « Hey Jarvis »
```

Ensuite, un compte à la fois, en suivant `docs/SETUP.md` : `jarvis auth outlook`, `jarvis auth google`, `jarvis auth hue`, puis `jarvis doctor` à nouveau. Tapo/Kasa se configure dans `jarvis setup`.

Démarrage automatique quand tout marche : `scripts\autostart.ps1` (désinstallation : `-Remove`).

## Ce qui n'a pas pu être testé : à vérifier ici en priorité

| Zone | Ce qu'il faut vérifier | Où |
|---|---|---|
| Mot-clé | `openwakeword` télécharge bien `hey_jarvis` ; le nom de clé de la prédiction correspond ; `wake_threshold` adapté au micro | `audio/ears.py` (`WakeWord`), `scripts/install.ps1` |
| Fin de phrase | `end_silence_ms` (800) ni trop court (coupe Monsieur) ni trop long (latence) | `audio/ears.py` (`Endpointer`) |
| Carillon | Le carillon de réveil ne doit pas être pris pour le début d'une phrase par le VAD | `App.conversation`, `Ears.listen` |
| Barge-in | Avec enceintes, `barge_in: wake_word` ; avec casque, essayer `voice` | `audio/ears.py` |
| Transcription | Latence de `small` int8 sur ce CPU ; si plus de 1,5 s, essayer `base` | `audio/stt.py` |
| Volume | API `pycaw` (`AudioUtilities.GetSpeakers().EndpointVolume` selon la version) | `tools/system.py` (`set_volume`) |
| Deezer | Le lien `deezer://www.deezer.com/{kind}/{id}` ouvre l'appli ; la lecture démarre vraiment (`try_play_async`) ; sinon envoyer la touche média Play | `tools/media.py` |
| Fenêtre | pywebview sans bordure, plein écran sur l'écran externe ; géométrie correcte avec mise à l'échelle DPI 125/150 % ; `show`/`hide` sans flash blanc (WebView2) | `ui/window.py` |
| Python | `asyncio.Task.cancelling` exige Python ≥ 3.11 ; l'installeur prend 3.12 | `audio/voice.py` |
| Hue | Le pont répond en https avec un certificat auto-signé (`verify=False` voulu) | `tools/home.py` |
| Kasa/Tapo | Modules `python-kasa` (`Discover`, `Module.Light`…) selon la version installée | `tools/home.py` |
| Localisation | Windows Location (`winrt` Geolocator) si autorisée dans Paramètres › Confidentialité, sinon IP, sinon Paris | `tools/weather.py` (`locate`) |
| Raccourci | `Ctrl+Alt+J` via pynput, éventuellement en conflit avec une autre appli | `App._hotkey` |

Méthode : reproduire, corriger au plus petit endroit, ajouter un test dans `tests/` quand c'est testable sans matériel, relancer `pytest`.

## Architecture en une minute

```
jarvis/app.py      machine à états : veille → conversation → veille ; barge-in ; confirm()
jarvis/brain.py    boucle Claude en flux : phrases → Mouth au fil de l'eau ; outils ; confirmation
jarvis/persona.py  prompt système du majordome (vouvoiement, « Monsieur », flegme, oral court)
jarvis/speech.py   découpe en phrases, nettoyage pour la voix, normalize()
jarvis/confirm.py  parse_answer : oui / non / None
jarvis/audio/      ears (micro 16 kHz, mot-clé, VAD), stt (faster-whisper), voice (ElevenLabs / Edge → Player 24 kHz)
jarvis/tools/      un fichier par domaine ; @tool(name, description, schema, confirm=, hides_ui=)
jarvis/ui/         server.py (aiohttp + WebSocket sur 127.0.0.1), window.py (pywebview), web/ (Three.js)
jarvis/cli.py      run | setup | auth | doctor | devices | say | ask | preview
```

- **Fils d'exécution.** WebView2 exige le fil principal : `app.run()` y place la fenêtre et fait tourner asyncio dans un fil secondaire. Les callbacks audio arrivent par `loop.call_soon_threadsafe`.
- **Cerveau.**
  - `AsyncAnthropic`, `messages.stream`, `cache_control` sur le prompt système.
  - Thinking adaptatif, `output_config.effort`.
  - Outil serveur `web_search_20260209`.
  - `eager_input_streaming` sur les outils maison, avec validation du schéma faite par nous (`tools.validate`) avant toute exécution.
- **Interface.** Le globe a quatre états : `idle`, `listen`, `think`, `speak`. `show`/`hide` le font apparaître ou s'effacer. Les cartes (`show_hologram` ou cartes automatiques météo, marchés, mails) passent par `ui.card()`. Un outil `hides_ui=True` pose `ctx.hide_requested` et l'App efface le globe.

## Ajouter ou modifier un outil

```python
@tool("nom_outil", "Ce que l'outil fait, du point de vue du modèle.",
      {"param": {"type": "string", "description": "…"}}, required=["param"],
      confirm=lambda ctx, a: f"J'envoie « {a['param']} »",   # si l'action part chez un tiers
      hides_ui=True,                                         # s'il emmène Monsieur dans une appli
      enabled=lambda cfg: cfg.get_path("service.enabled"))  # s'il dépend d'un compte
async def nom_outil(ctx: ToolContext, param: str):
    ...
    return "résultat court, factuel, que Claude reformulera à l'oral"
```

`enabled=` retire l'outil de la liste envoyée à Claude tant que le compte n'est pas connecté (voir `tools.available`).

## Coûts

Budget de l'utilisateur : 5 à 15 € par mois. Ne passe pas `brain.model` sur Opus ni `effort` au-dessus de `low` sans le lui proposer. Ne lance pas de boucles de test qui appellent l'API en masse.

## GitHub (plus tard)

L'utilisateur publiera le dépôt lui-même. Avant tout `git add` :
- `git status --ignored` : `config.yaml`, `credentials.json`, `client_secret*.json`, `*.token`, `.env`, `.venv/` doivent être ignorés ;
- `git grep -nE "sk-ant-|xi-api-key\s*[:=]\s*['\"][A-Za-z0-9]"` ne doit rien trouver ;
- ne commite ni ne pousse sans qu'il le demande.
