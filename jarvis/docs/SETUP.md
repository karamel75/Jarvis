# Connecter les comptes

Chaque section est indépendante. Commencez par **1** et **2** : c'est tout ce qu'il faut pour que Jarvis parle et réfléchisse. Le reste s'ajoute quand vous voulez, puis `jarvis doctor` pour vérifier.

Toutes les clés se saisissent avec `jarvis setup` et vont dans le **Gestionnaire d'identification Windows**. Elles ne sont jamais copiées dans un fichier.

| § | Service | Sert à | Coût |
|---|---|---|---|
| 1 | Anthropic | le cerveau | à l'usage, quelques €/mois |
| 2 | ElevenLabs | la voix | abonnement d'entrée |
| 3 | Obsidian | la mémoire | gratuit |
| 4 | Outlook.com | mails, contacts | gratuit |
| 5 | Google | Gmail, Agenda, Drive | gratuit |
| 6 | Philips Hue | lumières | — |
| 7 | Tapo / Kasa | prises, ampoules | — |
| 8 | Deezer | musique | votre abonnement |
| 9 | Everything | recherche de fichiers instantanée | gratuit |
| 10 | Windows | micro, écran, localisation | — |

---

## 1. Anthropic : le cerveau

> L'abonnement claude.ai et l'API sont **deux comptes de facturation distincts**. Il faut des crédits API, même si vous payez déjà Claude Pro ou Max.

1. Connectez-vous à la console Anthropic (**platform.claude.com**, anciennement console.anthropic.com) avec votre **adresse perso**, pas celle du travail.
2. **Billing**
   - Achetez des crédits (10 $ suffisent pour démarrer).
   - Laissez le rechargement automatique désactivé au début.
3. **Limits** : fixez une limite mensuelle, par exemple **15 $**. Jarvis ne pourra jamais la dépasser.
4. **API Keys → Create Key**
   - Nommez-la `jarvis-pc-perso`.
   - Copiez-la et collez-la dans `jarvis setup`.
5. `jarvis doctor` doit afficher `✔ Clé Anthropic — modèle claude-sonnet-5 accessible`.

Réglages dans `config.yaml → brain` :
- `model: claude-sonnet-5` et `effort: low` donnent des réponses rapides et bon marché.
- `claude-opus-5` réfléchit plus profondément, mais coûte plus cher et répond plus lentement.

## 2. ElevenLabs : la voix

1. Créez un compte sur **elevenlabs.io**. L'abonnement d'entrée suffit pour un usage quotidien avec `eleven_flash_v2_5`.
2. **Profil → API Keys → Create**
   - Si l'interface propose des permissions, cochez **Text to Speech** et **Voices (lecture)**, rien d'autre.
   - Collez la clé dans `jarvis setup`.
3. Choisissez ou créez la voix (voir [VOICE.md](VOICE.md)), puis copiez son **Voice ID** dans `jarvis setup`.
4. Testez avec `jarvis say "Bonsoir, Monsieur. Tous les systèmes sont opérationnels."`

Si le quota est épuisé ou qu'ElevenLabs ne répond pas, Jarvis bascule seul sur la voix Edge gratuite (`fr-FR-HenriNeural`).

## 3. Obsidian : la mémoire

1. Lancez `jarvis setup`, puis collez le chemin du coffre, par exemple `C:\Users\Vous\Documents\Obsidian\Perso`.
2. Ce que Jarvis fait dans le coffre :
   - **lire** : n'importe quelle note (« qu'est-ce que j'avais noté sur… ») ;
   - **écrire** : seulement dans `Jarvis/` :
     - `Jarvis/Profil.md`, ce qu'il sait de vous (relu à chaque conversation) ;
     - `Jarvis/Souvenirs/<thème>.md`, ce que vous lui demandez de retenir ;
     - `Jarvis/Journal/AAAA-MM-JJ.md`, le fil des conversations du jour.

   Vous pouvez éditer `Profil.md` à la main : prénom, goûts, habitudes, proches.

Pour changer le dossier d'écriture, modifiez `obsidian.folder` dans `config.yaml`.

## 4. Outlook.com : mails et contacts

Microsoft demande une petite « inscription d'application » pour lire votre boîte. C'est gratuit et fait une fois pour toutes, en dix minutes environ.

1. Allez sur **entra.microsoft.com** et connectez-vous avec votre compte **Outlook.com perso**.
   - Si Microsoft dit que votre compte n'a pas d'annuaire, créez un **compte Azure gratuit** (azure.microsoft.com/free) avec la même adresse.
   - Cela crée un annuaire par défaut. Aucun service payant n'est activé.
2. **Applications → Inscriptions d'applications → Nouvelle inscription**
   - Nom : `Jarvis`.
   - Types de comptes : **Comptes Microsoft personnels uniquement**.
   - URI de redirection : plateforme **Client public / natif (mobile et bureau)**, valeur `http://localhost`.
   - Cliquez sur **Inscrire**.
3. Sur la page de l'application, copiez **ID d'application (client)**.
4. **Authentification**
   - Mettez **Autoriser les flux clients publics** sur **Oui**.
   - Cliquez sur Enregistrer.
5. **Autorisations d'API → Ajouter → Microsoft Graph → Autorisations déléguées** :
   - `User.Read`
   - `Mail.Read` : lire et résumer. C'est de la lecture seule : aucun droit de modifier ou de supprimer.
   - `Mail.Send`
   - `Contacts.Read`

   Aucun « consentement administrateur » n'est nécessaire pour un compte perso.
6. Sur le PC, lancez `jarvis auth outlook`.
   - Collez l'ID d'application.
   - Une page Microsoft s'ouvre : connectez-vous et acceptez.
   - Le jeton est chiffré dans `%LOCALAPPDATA%\Jarvis`.

Il n'y a pas de client secret : c'est une application « publique » qui tourne sur votre PC, et rien n'est à cacher dans le code.

## 5. Google : Gmail, Agenda, Drive

1. Ouvrez **console.cloud.google.com** avec votre compte Google perso.
2. Créez un projet nommé `Jarvis`.
3. Dans **API et services → Bibliothèque**, activez :
   - **Gmail API**
   - **Google Calendar API**
   - **Google Drive API**
4. Dans **Google Auth Platform** (ou « Écran de consentement OAuth ») :
   - Type : **Externe**.
   - Nom : `Jarvis`.
   - E-mail d'assistance et de contact : le vôtre.
   - **Audience** : ajoutez votre adresse comme utilisateur test, puis cliquez sur **Publier l'application** pour la passer **en production**.

   > En mode « Test », Google expire les jetons au bout de **7 jours** et Jarvis vous redemanderait de vous connecter chaque semaine.

   En production sans validation, Google affiche « Google n'a pas validé cette application ». C'est normal pour une application perso : cliquez sur **Paramètres avancés → Accéder à Jarvis**.
5. **Clients → Créer un client**
   - Type : **Application de bureau**.
   - Nom : `Jarvis PC`.
   - **Téléchargez le JSON**, renommez-le `credentials.json` et placez-le à la racine du dossier `jarvis`. Il est déjà dans `.gitignore`.
6. Lancez `jarvis auth google`. Le navigateur s'ouvre : acceptez les accès.

Accès demandés et pourquoi :

| Scope | Usage |
|---|---|
| `gmail.readonly` | lire et résumer |
| `gmail.send` | envoyer et répondre, après confirmation orale |
| `calendar.events` | consulter et créer des rendez-vous, après confirmation. Jarvis ne supprime jamais. |
| `drive.readonly` | chercher et ouvrir un document |

## 6. Philips Hue

1. Le pont Hue et le PC doivent être sur le même réseau.
2. Lancez `jarvis auth hue`, appuyez sur le **gros bouton du pont**, puis tapez Entrée dans les 30 secondes.
3. Utilisez les noms de pièces de l'appli Hue : « allume le salon », « tamise la chambre à 30 % », « lumière bleue dans le bureau ».

Si la découverte automatique échoue, mettez l'adresse IP du pont dans `home.hue.bridge_ip`. Elle figure dans l'appli Hue, rubrique Paramètres › Ponts.

## 7. Tapo / Kasa

1. Dans `jarvis setup`, répondez **o** à « Configurer les prises/ampoules Tapo ou Kasa ? ».
2. Saisissez l'e-mail et le mot de passe du compte **Tapo**. Les appareils Tapo récents en ont besoin pour se piloter en local.
3. Gardez les noms de l'appli Tapo : « éteins la prise du radiateur ».

Conseil : dans votre box, fixez une IP par appareil (bail DHCP statique). La découverte sera plus rapide et plus fiable.

## 8. Deezer

1. Installez **Deezer pour Windows** (deezer.com ou Microsoft Store) et connectez-vous. Un abonnement Premium est conseillé pour choisir un titre précis.
2. Rien d'autre à configurer. Jarvis trouve le titre avec l'API publique de Deezer, ouvre l'appli au bon endroit et lance la lecture.
3. Exemples :
   - « mets Daft Punk » ;
   - « l'album Discovery » ;
   - « lance une playlist chill » (recherche dans les playlists publiques) ;
   - « pause », « suivant » ;
   - « c'est quoi ce morceau ? ».

## 9. Everything (facultatif, conseillé)

Avec Everything, « trouve le PDF du bail » répond en un instant au lieu de plusieurs secondes.

1. Installez **Everything** (voidtools.com).
2. Téléchargez aussi **ES**, l'outil en ligne de commande d'Everything, et placez `es.exe` dans `C:\Program Files\Everything\`. Si vous le mettez ailleurs, modifiez `files.everything_cli`.
3. Everything doit tourner en arrière-plan. C'est le cas par défaut.

## 10. Windows : micro, écran, localisation

- **Micro et haut-parleurs**
  - `jarvis devices` liste les périphériques. Reportez le nom ou l'index dans `audio.input_device` et `audio.output_device`. Avec `null`, Windows choisit le périphérique par défaut.
  - **Avec enceintes**, gardez `barge_in: wake_word` : seul « Hey Jarvis » le coupe, sinon il s'interromprait en s'entendant lui-même.
  - **Avec casque**, `barge_in: voice` permet de le couper simplement en parlant.
- **Sensibilité du mot-clé** (`audio.wake_threshold`) :
  - s'il ne vous entend pas, descendez vers `0.35` ;
  - s'il se réveille seul, montez vers `0.65`.
- **Écran** : avec `ui.screen: -1`, il choisit l'écran externe s'il y en a un. Sinon, indiquez `0`, `1`… Le globe s'y affiche en plein écran.
- **Localisation** :
  - activez **Paramètres → Confidentialité et sécurité → Localisation**, avec l'autorisation pour les **applications de bureau** ;
  - sinon, Jarvis se repère avec l'adresse IP, puis à défaut `user.default_city` (Paris).
- **Démarrage avec Windows** : `scripts\autostart.ps1`.
