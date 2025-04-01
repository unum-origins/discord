"""
Handles everything for the Discord Origin
"""

# pylint: disable=unsupported-membership-test

import time
import json

import discord

import unum_ledger

WHO = "discord"

class OriginClient(discord.Client):
    """
    Discord Client to handel the Discord origin
    """

    daemon = None
    user_ids = []
    witness_ids = {}

    def __init__(self, *args, daemon=daemon, **kwargs):

        super(OriginClient, self).__init__(*args, **kwargs)

        self.daemon = daemon

        for witness in unum_ledger.Witness.many(origin__who=WHO):

            user_id = int(witness.who)
            self.user_ids.append(user_id)
            self.witness_ids[user_id] = witness.id

    @staticmethod
    def user_to_dict(user):
        """
        Converts a user object to a standard dict
        """

        return {
            "id": str(user.id),
            "name": user.name,
            "discriminator": user.discriminator,
            "bot": user.bot
        }

    @classmethod
    def channel_to_dict(cls, message):
        """
        Converts a channel info to a standard dict
        """

        value = {
            "id": str(message.channel.id)
        }

        if message.author.dm_channel and message.channel.id == message.author.dm_channel.id:
            value["type"] = "direct"
            value["recipient"] = cls.user_to_dict(message.channel.recipient)
        elif not message.guild:
            value["type"] = "group"
        else:
            value["type"] = "guild"
            value["name"] = message.channel.name
            value["guild"] = {
                "id": str(message.guild.id),
                "name": message.guild.name,
            }

        return value

    @classmethod
    def message_to_dict(cls, message, reference=False):
        """
        Converts a message obj to a standard dict, optional including the reply
        """

        value = {
            "id": str(message.id),
            "content": message.content,
            "author": cls.user_to_dict(message.author),
            "channel": cls.channel_to_dict(message),
            "attachments": [attachment.url for attachment in message.attachments],
            "created_at": str(message.created_at)
        }

        if message.reference:
            value["reference"] = cls.message_to_dict(message.reference) if reference else {"id": str(message.reference.id)}

        return value

    @classmethod
    def reaction_to_dict(cls, reaction, user):
        """
        Converts a reaction and user obj to a standard dict
        """

        return {
            "user": cls.user_to_dict(user),
            "emoji": reaction.emoji,
            "message": cls.message_to_dict(reaction.message)
        }

    def message_user_ids(self, message):
        """
        Gets all the user_ids associated with a message within our list
        """

        if message.author.id in self.user_ids:
            yield message.author.id
        elif message.channel.id == message.author.dm_channel.id:
            yield message.channel.recipient.id
        else:
            for user in message.mentions:
                if user.id in self.user_ids:
                    yield user.id

    def reaction_user_ids(self, reaction, user):
        """
        Gets all the user_ids associated with a reaction within our list
        """

        if user.id in self.user_ids:
            yield user.id

        for user_id in self.message_user_ids(reaction.message):
            if user_id != user.id:
                yield user_id

    async def on_ready(self):
        """
        Called when starting up
        """

        self.daemon.logger.info(f"logged in as {self.user}", extra={"id": self.user.id})

    async def on_message(self, message):
        """
        For every message this bot sees
        """

        for user_id in self.message_user_ids(message):
            self.daemon.fact(
                witness_id=self.witness_ids[user_id],
                who=f"message:{message.id}",
                when=time.mktime(message.created_at.timetuple()),
                what=self.message_to_dict(message, reference=True)
            )

    async def on_reaction_add(self, reaction, user):
        """
        For every reactino this bot sees
        """

        for user_id in self.reaction_user_ids(reaction, user):
            self.daemon.fact(
                witness_id=self.witness_ids[user_id],
                who=f"reaction:{reaction.message.id}:{reaction.emoji}",
                when=time.mktime(reaction.message.created_at.timetuple()),
                what=self.reaction_to_dict(reaction, user)
            )

def run(daemon):
    """
    Handles everyting about this origin
    """

    with open("/opt/service/secret/discord.json", "r") as creds_file:
        token = json.load(creds_file)["token"]

    intents = discord.Intents.default()
    intents.message_content = True # pylint: disable=assigning-non-slot

    client = OriginClient(daemon=daemon, intents=intents)
    client.run(token)
