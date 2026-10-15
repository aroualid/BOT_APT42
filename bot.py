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

# Rôles (en plus des administrateurs) autorisés à utiliser /close.
# Mets les noms exacts de tes rôles, la casse n'a pas d'importance.
CLOSE_ROLES = ["Ad;in", "Bureau"]

intents = discord.Intents.default()
intents.members = True  # à activer aussi dans le portail développeurs
client = discord.Client(intents=intents)
tree = app_commands.CommandTree(client)

# {eventId: {"role": roleId | None, "channel": channelId, "closed": bool}}
store = {}
if os.path.exists(FILE):
    with open(FILE, encoding="utf-8") as f:
        store = json.load(f)

lock = asyncio.Lock()  # évite de créer deux fois le même salon


def save():
    with open(FILE, "w", encoding="utf-8") as f:
        json.dump(store, f, indent=2)


async def get_or_create_category(guild: discord.Guild, name: str):
    for category in guild.categories:
        if category.name.lower() == name.lower():
            return category
    return await guild.create_category(name)


async def setup(event: discord.ScheduledEvent) -> dict:
    """Crée le rôle et le salon privé (dans CTF) d'un événement, une seule fois."""
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
            role: discord.PermissionOverwrite(view_channel=True, send_messages=True),
            guild.me: discord.PermissionOverwrite(
                view_channel=True, send_messages=True, manage_channels=True
            ),
        }
        channel = await guild.create_text_channel(
            event.name[:100],
            category=category,
            overwrites=overwrites,
            reason=f"Événement {event.name}",
        )

        store[key] = {"role": role.id, "channel": channel.id, "closed": False}
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


@tree.command(name="close", description="Archive le salon de cet événement")
@app_commands.guild_only()
async def close(interaction: discord.Interaction):
    await interaction.response.defer(ephemeral=True)

    # Réservé aux administrateurs et aux rôles de CLOSE_ROLES
    allowed = {name.lower() for name in CLOSE_ROLES}
    user = interaction.user
    is_allowed = user.guild_permissions.administrator or any(
        role.name.lower() in allowed for role in user.roles
    )
    if not is_allowed:
        return await interaction.followup.send(
            "Tu n'as pas la permission d'utiliser cette commande.", ephemeral=True
        )

    guild = interaction.guild
    channel = interaction.channel

    # Retrouve l'événement à partir du salon où la commande est lancée
    key = next(
        (k for k, v in store.items() if v["channel"] == channel.id and not v["closed"]),
        None,
    )
    if key is None:
        return await interaction.followup.send(
            "Ce salon n'est pas un salon d'événement actif.", ephemeral=True
        )
    entry = store[key]

    archive = await get_or_create_category(guild, ARCHIVE_CATEGORY)

    # Lecture seule, visible par tout le monde (les anciens overwrites sont remplacés)
    overwrites = {
        guild.default_role: discord.PermissionOverwrite(
            view_channel=True,
            read_message_history=True,
            send_messages=False,
            add_reactions=False,
            create_public_threads=False,
            create_private_threads=False,
            send_messages_in_threads=False,
        ),
        guild.me: discord.PermissionOverwrite(
            view_channel=True, send_messages=True, manage_channels=True
        ),
    }
    await channel.edit(category=archive, overwrites=overwrites, reason="Salon archivé")

    role = guild.get_role(entry["role"])
    if role:
        await role.delete(reason="Salon archivé")

    entry["closed"] = True
    entry["role"] = None
    save()

    await interaction.followup.send("Salon archivé.", ephemeral=True)


_ready_done = False


@client.event
async def on_ready():
    global _ready_done
    print(f"Connecté en tant que {client.user}")
    if _ready_done:  # on_ready peut être rappelé après une reconnexion
        return
    _ready_done = True

    for guild in client.guilds:
        # Enregistre /close tout de suite sur ce serveur
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
