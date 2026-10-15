import asyncio
import json
import os

import discord
from discord import app_commands
from dotenv import load_dotenv

load_dotenv(dotenv_path="config")

CTF_CATEGORY = "CTF"
ARCHIVE_CATEGORY = "archive"
FILE = "events.json"

# Rôles (en plus des administrateurs) autorisés à utiliser /close et /close_ctf.
# Mets les noms exacts de tes rôles, la casse n'a pas d'importance.
CLOSE_ROLES = ["Admin", "Bureau"]

# Tags prédéfinis du forum (20 caractères max chacun, 20 tags max)
FORUM_TAGS = ["Web", "Crypto", "Pwn", "Reverse", "Forensics", "OSINT", "Stégano", "Misc"]
DONE_TAG = "Résolu"  # ajouté automatiquement par /close

intents = discord.Intents.default()
intents.members = True  # à activer aussi dans le portail développeurs
client = discord.Client(intents=intents)
tree = app_commands.CommandTree(client)

# {eventId: {"role": roleId | None, "channel": forumId, "closed": bool}}
store = {}
if os.path.exists(FILE):
    with open(FILE, encoding="utf-8") as f:
        store = json.load(f)

lock = asyncio.Lock()  # évite de créer deux fois le même forum


def save():
    with open(FILE, "w", encoding="utf-8") as f:
        json.dump(store, f, indent=2)


def find_key(forum_id: int):
    """Retrouve l'ID d'événement à partir de l'ID du forum."""
    for key, entry in store.items():
        if entry["channel"] == forum_id:
            return key
    return None


def is_allowed(member: discord.Member) -> bool:
    allowed = {name.lower() for name in CLOSE_ROLES}
    return member.guild_permissions.administrator or any(
        role.name.lower() in allowed for role in member.roles
    )


async def get_or_create_category(guild: discord.Guild, name: str):
    for category in guild.categories:
        if category.name.lower() == name.lower():
            return category
    return await guild.create_category(name)


async def setup(event: discord.ScheduledEvent) -> dict:
    """Crée le rôle et le forum privé (dans CTF) d'un événement, une seule fois."""
    async with lock:
        key = str(event.id)
        if key in store:
            return store[key]

        guild = event.guild
        category = await get_or_create_category(guild, CTF_CATEGORY)

        role = await guild.create_role(
            name=event.name[:100],
            mentionable=True,
            reason=f"Événement {event.name}",
        )
        overwrites = {
            guild.default_role: discord.PermissionOverwrite(view_channel=False),
            role: discord.PermissionOverwrite(
                view_channel=True, send_messages=True, send_messages_in_threads=True
            ),
            guild.me: discord.PermissionOverwrite(
                view_channel=True,
                send_messages=True,
                send_messages_in_threads=True,
                manage_threads=True,
                manage_channels=True,
            ),
        }
        tags = [discord.ForumTag(name=name) for name in FORUM_TAGS + [DONE_TAG]]
        forum = await guild.create_forum(
            event.name[:100],
            category=category,
            overwrites=overwrites,
            topic="Un post par challenge. Choisis un tag pour la catégorie.",
            available_tags=tags,
            reason=f"Événement {event.name}",
        )

        store[key] = {"role": role.id, "channel": forum.id, "closed": False}
        save()
        return store[key]


async def give_role(event, user):
    entry = store.get(str(event.id))
    if entry is None:  # événement créé pendant que le bot était éteint
        entry = await setup(event)
    if entry["closed"]:
        return
    role = event.guild.get_role(entry["role"])
    if role is None:
        return
    try:
        member = await event.guild.fetch_member(user.id)
    except discord.NotFound:
        return  # la personne a quitté le serveur
    await member.add_roles(role)


async def take_role(event, user):
    entry = store.get(str(event.id))
    if entry is None or entry["closed"]:
        return
    role = event.guild.get_role(entry["role"])
    if role is None:
        return
    try:
        member = await event.guild.fetch_member(user.id)
    except discord.NotFound:
        return
    await member.remove_roles(role)


@client.event
async def on_scheduled_event_create(event):
    await setup(event)


@client.event
async def on_scheduled_event_user_add(event, user):
    await give_role(event, user)


@client.event
async def on_scheduled_event_user_remove(event, user):
    await take_role(event, user)


@tree.command(name="close", description="Ferme ce post (challenge terminé)")
@app_commands.guild_only()
async def close(interaction: discord.Interaction):
    await interaction.response.defer(ephemeral=True)

    if not is_allowed(interaction.user):
        return await interaction.followup.send(
            "Tu n'as pas la permission d'utiliser cette commande.", ephemeral=True
        )

    thread = interaction.channel
    if not isinstance(thread, discord.Thread) or find_key(thread.parent_id) is None:
        return await interaction.followup.send(
            "À utiliser dans un post d'un forum d'événement.", ephemeral=True
        )

    forum = thread.parent or interaction.guild.get_channel(thread.parent_id)
    tags = list(thread.applied_tags)
    done = discord.utils.get(forum.available_tags, name=DONE_TAG)
    if done and done not in tags:
        tags.append(done)

    # On répond avant d'archiver, car on est dans le post qu'on ferme
    await interaction.followup.send("Post fermé.", ephemeral=True)
    await thread.edit(applied_tags=tags[:5], locked=True, archived=True)


@tree.command(name="close_ctf", description="Archive tout le forum de ce CTF")
@app_commands.guild_only()
async def close_ctf(interaction: discord.Interaction):
    await interaction.response.defer(ephemeral=True)

    if not is_allowed(interaction.user):
        return await interaction.followup.send(
            "Tu n'as pas la permission d'utiliser cette commande.", ephemeral=True
        )

    guild = interaction.guild
    channel = interaction.channel
    # La commande se lance dans un post : on remonte au forum
    forum_id = channel.parent_id if isinstance(channel, discord.Thread) else channel.id

    key = find_key(forum_id)
    if key is None or store[key]["closed"]:
        return await interaction.followup.send(
            "Ce n'est pas un forum d'événement actif.", ephemeral=True
        )
    entry = store[key]
    forum = guild.get_channel(forum_id)

    archive = await get_or_create_category(guild, ARCHIVE_CATEGORY)

    # Lecture seule, visible par tout le monde (les anciens overwrites sont remplacés)
    overwrites = {
        guild.default_role: discord.PermissionOverwrite(
            view_channel=True,
            read_message_history=True,
            send_messages=False,  # créer des posts
            send_messages_in_threads=False,  # répondre dans les posts
            add_reactions=False,
        ),
        guild.me: discord.PermissionOverwrite(
            view_channel=True,
            send_messages=True,
            send_messages_in_threads=True,
            manage_threads=True,
            manage_channels=True,
        ),
    }
    await forum.edit(category=archive, overwrites=overwrites, reason="Forum archivé")

    role = guild.get_role(entry["role"])
    if role:
        await role.delete(reason="Forum archivé")

    entry["closed"] = True
    entry["role"] = None
    save()

    await interaction.followup.send("Forum archivé.", ephemeral=True)


_ready_done = False


@client.event
async def on_ready():
    global _ready_done
    print(f"Connecté en tant que {client.user}")
    if _ready_done:  # on_ready peut être rappelé après une reconnexion
        return
    _ready_done = True

    for guild in client.guilds:
        # Enregistre les commandes tout de suite sur ce serveur
        tree.copy_global_to(guild=guild)
        await tree.sync(guild=guild)

        # Rattrape les événements actifs et leurs inscrits
        for event in await guild.fetch_scheduled_events():
            if event.status in (
                discord.EventStatus.completed,
                discord.EventStatus.cancelled,
            ):
                continue
            entry = store.get(str(event.id)) or await setup(event)
            if entry["closed"]:
                continue
            role = guild.get_role(entry["role"])
            if role is None:
                continue
            async for user in event.users(limit=None):
                try:
                    member = await guild.fetch_member(user.id)
                except discord.NotFound:
                    continue
                if role not in member.roles:
                    await member.add_roles(role)

    print("Prêt.")


client.run(os.getenv("TOKEN"))
