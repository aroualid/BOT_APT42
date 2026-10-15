# CTF Discord Bot

Bot Discord permettant de gérer simplement les événements CTF et leurs challenges directement depuis Discord.

## Configuration

1. Créer une application sur le [Discord Developer Portal](https://discord.com/developers/applications).
2. Activer l'intent **Server Members Intent** dans les paramètres du bot.
3. Inviter le bot sur le serveur avec les scopes `bot` et `applications.commands`, ainsi que les permissions suivantes :
   - **View Channels**
   - **Manage Channels**
   - **Manage Roles**
   - **Send Messages**
   - **Send Messages in Threads**
   - **Manage Threads**
   - **Read Message History**
4. Configurer le token dans le fichier `config` :
   ```dotenv
   TOKEN=your_discord_bot_token
   ```

## Utilisation

### 1. Créer un événement CTF

Créer un événement planifié directement sur le serveur Discord.

Le bot configure automatiquement :
- Une catégorie `CTF` si nécessaire.
- Un rôle dédié à l'événement.
- Un forum privé réservé aux participants inscrits.

### 2. Gérer les participants

Les membres s'inscrivent à l'événement via Discord.

- **Inscription :** attribution automatique du rôle et accès au forum.
- **Désinscription :** retrait automatique du rôle.

### 3. Organiser les challenges

Chaque challenge dispose de son propre post dans le forum. Les tags permettent de classer les challenges : `Web`, `Crypto`, `Pwn`, `Reverse`, `Forensics`, `OSINT`, `Stégano` et `Misc`.

### 4. Fermer un challenge

`/close`

À utiliser dans le post du challenge terminé. Le bot ajoute le tag `Résolu`, puis verrouille et archive le post.

### 5. Archiver le CTF

`/close_ctf`

À utiliser dans le forum du CTF ou l'un de ses posts, une fois l'événement terminé. Le bot déplace le forum dans `archive`, le rend consultable en lecture seule et supprime le rôle dédié.

**Permissions des commandes :** réservées aux administrateurs et aux membres possédant le rôle `Admin` ou `Bureau`.

## Lancement

```bash
python -m pip install discord.py python-dotenv
python main.py
```

Les événements et leurs informations sont conservés dans `events.json`. Au redémarrage, le bot resynchronise les commandes et restaure les rôles des participants aux événements actifs.
