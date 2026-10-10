# La voix de Jarvis

Jarvis parle avec **une seule voix ElevenLabs**, choisie par vous. Sa référence est `voice.voice_id` dans `config.yaml`.

> **Règle :** pas de clone de la voix d'un comédien réel, par exemple les doubleurs français ou anglais du film. C'est interdit par les conditions d'ElevenLabs sans l'accord de la personne, et ce n'est pas nécessaire : une voix conçue sur mesure donne le même effet.

## Trouver la voix

Deux façons de faire ; comptez une vingtaine de minutes d'écoute.

### A. Bibliothèque de voix (le plus rapide)

1. Sur elevenlabs.io, ouvrez **Voices → Library**.
2. Filtrez : langue **français** (ou anglais britannique, voir plus bas), genre **masculin**, âge **moyen / âgé**, usage **narration** ou **conversationnel**.
3. Cherchez :
   - **timbre** grave, posé, légèrement feutré ;
   - **diction** nette, sans accent appuyé ;
   - **débit** calme ;
   - **ton** chaleureux mais distant, comme un majordome qui sourit en coin.
4. **Add to my voices**, puis copiez le **Voice ID** (icône ⋯ → *Copy voice ID*).

### B. Voice Design (sur mesure)

**Voices → Create → Voice Design**, avec une description de ce genre :

```
Homme d'une cinquantaine d'années, voix grave et veloutée, diction parfaite,
élocution calme et mesurée. Majordome britannique distingué qui parle un
français impeccable avec une très légère pointe d'accent anglais. Ton poli,
flegmatique, une ironie discrète. Enregistrement studio, proche du micro,
sans réverbération.
```

Générez plusieurs propositions et gardez la meilleure. Pour la tester, utilisez une phrase typique :

> « Bonsoir, Monsieur. Dix-neuf degrés à Paris, le CAC termine en hausse, et vous avez trois mails, dont un de votre banquier, qui semble pressé. »

### Accent britannique ou français ?

Deux pistes valent d'être écoutées :
- une voix **anglaise britannique** qui lit le français avec `eleven_multilingual_v2` : on obtient un léger accent, très « Jarvis » ;
- une voix **française** native : plus naturelle au quotidien.

## Réglages (`config.yaml → voice`)

| Clé | Défaut | Effet |
|---|---|---|
| `model_id` | `eleven_flash_v2_5` | le plus rapide (environ 75 ms) : la réponse démarre presque instantanément |
| | `eleven_multilingual_v2` | plus expressif, mais plus lent et plus cher |
| `stability` | `0.45` | plus haut, la voix est égale ; plus bas, elle est plus vivante (mais varie d'une phrase à l'autre) |
| `similarity_boost` | `0.8` | fidélité au timbre choisi |
| `style` | `0.15` | exagération du style ; au-delà de 0.3, il en fait trop |
| `speed` | `1.0` | 0.9 donne un phrasé plus majestueux |

Testez chaque réglage avec `jarvis say "…"` avant de lancer Jarvis.

## Voix de secours

Si la clé ElevenLabs manque, si le quota est épuisé ou si le service ne répond pas, Jarvis passe sur **Microsoft Edge TTS** (`fr-FR-HenriNeural`), qui est gratuite. Elle est moins incarnée, mais Jarvis ne reste jamais muet. Pour l'utiliser en permanence : `voice.provider: edge`.
