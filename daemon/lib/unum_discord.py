"""
Handles everything for the Discord Origin
"""

# pylint: disable=unsupported-membership-test

import time
import copy
import json
import asyncio

import pprint

from emoji import EMOJI_DATA
import discord
import discord.abc
import discord.utils

import service
import unum_ledger

FORMATS = [
    {
        "name": "word",
        "description": "a single word"
    },
    {
        "name": "remainder",
        "description": "a - followed by words at the end of a command"
    },
    {
        "name": "emoji",
        "description": "a single emoji"
    },
    {
        "name": "duration",
        "description": "for time: 3d2h1m = 3 days 2 hour 1 min"
    },
    {
        "name": "user",
        "description": "an @'d person who's joined the relevant Unum/App/Origin"
    }
]

MEMES = {
    "+": "👍",
    "-": "👎",
    "*": "♥️",
    "?": "❓",
    "!": "❗"
}

FEATS = {
    "accepted": "👍",
    "rejected": "👎",
    "completed": "♥️",
    "requested": "❓",
    "excepted": "❗"
}

class OriginClient(discord.Client):
    """
    Discord Client to handel the Discord origin
    """

    daemon = None
    pool = None
    apps = None
    orgins = None
    witness_entity_ids = None
    witness_user_ids = None

    def __init__(self, *args, daemon=daemon, **kwargs):

        super(OriginClient, self).__init__(*args, **kwargs)

        self.daemon = daemon

    # Security

    def is_active(self, entity_id):
        """
        Checks to see if an enity is active
        """

        return (
            unum_ledger.Entity.one(
                id=entity_id,
                status="active"
            ).retrieve(False) is not None
            and
            unum_ledger.Witness.one(
                entity_id=entity_id,
                origin_id=self.daemon.origin.id,
                status="active"
            ).retrieve(False) is not None
        )

    # Parsing

    def decode_time(self, arg):
        """
        Decodes 3d2h3m format to seconds

        """

        seconds = 0
        current = ""

        for letter in arg:

            if '0' <= letter and letter <= '9':
                current += letter
            elif current and letter == 'd':
                seconds += int(current) * 24*60*60
                current = ""
            elif current and letter == 'h':
                seconds += int(current) * 60*60
                current = ""
            elif current and letter == 'm':
                seconds += int(current) * 60
                current = ""

        return seconds

    def decode_text(self, text):

        cleaned = text

        for witness in unum_ledger.Witness.many(origin_id=self.daemon.origin.id):
            encode_text = f"<@{witness.who}>"
            decode_text = f"{{entity:{witness.entity_id}}}"

            if encode_text in cleaned:
                cleaned = cleaned.replace(encode_text, decode_text)

        for channel in self.get_all_channels():
            encode_text = f"<#{channel.id}>"
            decode_text = f"{{channel:{channel.name}}}"

            if encode_text in cleaned:
                cleaned = cleaned.replace(encode_text, decode_text)

        return cleaned

    def encode_text(self, text):

        cleaned = text

        for witness in unum_ledger.Witness.many(origin_id=self.daemon.origin.id):
            encode_text = f"<@{witness.who}>"
            decode_text = f"{{entity:{witness.entity_id}}}"

            if decode_text in cleaned:
                cleaned = cleaned.replace(decode_text, encode_text)

        for channel in self.get_all_channels():
            encode_text = f"<#{channel.id}>"
            decode_text = f"{{channel:{channel.name}}}"

            if decode_text in cleaned:
                cleaned = cleaned.replace(decode_text, encode_text)

        return cleaned

    def parse_user(self, user):
        """
        Converts a user object to a standard dict
        """

        return {
            "id": str(user.id),
            "name": user.name,
            "discriminator": user.discriminator,
            "bot": user.bot
        }

    def parse_meme(self, emoji):
        """
        Determines the meme ?.+,*,-,!
        """

        if emoji[0] in MEMES.keys():
            return emoji[0]

        if emoji[0] in MEMES.values():
            return [key for key, value in MEMES.items() if emoji[0] == value][0]

        return "*"

    def parse_kind(self, message, what, meta):
        """
        Converts a channel info to a standard dict
        """

        witness = unum_ledger.Witness.one(who=message.author.id).retrieve(False)

        if witness:
            what["entity_id"] = witness.entity_id
        elif message.author.id == self.user.id:
            what["self"] = True

        meta["channel"] = {
            "id": str(message.channel.id)
        }

        if isinstance(message.channel, discord.DMChannel):
            what["kind"] = "private"
        else:
            what["kind"] = "public"
            what["channel"] = meta["channel"]["name"] = message.channel.name
            meta["channel"]["type"] = message.channel.type
            meta["channel"]["guild"] = {
                "id": str(message.guild.id),
                "name": message.guild.name,
            }

    def parse_usage(self, what, command, text):
        """
        Parse the args of the command
        """

        invalid = []

        for usage in command["usages"]:

            current = text
            args = usage.get("args", [])
            usage["values"] = values = {}
            usage["errors"] = errors = {}

            if what['meme'] != usage['meme']:
                usage["error"] = F"wrong usage - try {usage['meme']}{command['name']}"
                invalid.append(usage)
                continue

            if not args and current:
                usage["error"] = "less args than text"
                invalid.append(usage)
                continue

            for arg in args:

                name = arg["name"]

                if not current:
                    errors[name] = "missing value"
                    invalid.append(usage)
                    break

                format = arg.get("format", "word")
                pieces = current.split(maxsplit=1)
                piece = pieces.pop(0)

                if format == "word":
                    if not arg.get("valids"):
                        values[name] = piece
                    else:
                        if arg["valids"] and isinstance(arg["valids"][0], dict):
                            options = [list(valid.keys())[0] for valid in arg["valids"]]
                        else:
                            options = arg["valids"]

                        if piece in options:
                            values[name] = piece
                        else:
                            valids = ', '.join(options)
                            errors[name] = f"{piece} is not in {valids}"
                elif format == "remainder":
                    if piece == "-":
                        values[name] = pieces.pop(0)
                    else:
                        errors[name] = f"put a - before what you want to say"
                elif format == "emoji":
                    if piece in EMOJI_DATA:
                        values[name] = piece
                    else:
                        errors[name] = f"{pieces} is not a single emoji"
                elif format == "duration":
                    seconds = self.decode_time(piece)
                    if seconds:
                        values[name] = seconds
                    else:
                        errors[name] = f"{piece} is not in duration format, ie 3d2h1m = 3 days 2 hours 1 min"
                elif format == "user":
                    if piece.startswith("{entity:") and piece.endswith("}"):
                        values[name] = int(piece[1:-1].split(":")[-1])
                    elif piece.startswith("<@") and piece.endswith(">"):
                        errors[name] = f"{piece} hasn't joined"
                    else:
                        errors[name] = f"{piece} is not a user"

                current = pieces.pop(0) if pieces else ""

            if current:
                usage["error"] = "more text than args"
                invalid.append(usage)
            elif errors:
                invalid.append(usage)

        valid = [usage for usage in command["usages"] if usage not in invalid]

        if len(valid) == 1:
            what["usage"] = valid[0]["name"]
            what["values"] = valid[0]["values"]
        elif len(valid) > 1:
            valids = " and ".join([usage["name"] for usage in valid])
            what["error"] = f"too many valid usages: {valids}"
        elif len(invalid):
            closest = sorted(invalid, key=lambda close: len(close.get("errors", [])))[0]
            what["usage"] = closest["name"]
            if "args" in usage:
                what["args"] = usage["args"]
            if "error" in usage:
                what["error"] = usage["error"]
            if "errors" in usage:
                what["errors"] = usage["errors"]
        else:
            what["error"] = "no usage found"

        return "error" not in what

    def encode_title(self, what, title):
        """
        Adds title to all descriptions
        """

        if isinstance(what, dict):
            for key, value in what.items():
                if key == "description":
                    what[key] += title
                else:
                    self.encode_title(what[key], title)
        elif isinstance(what, list):
            for value in what:
                self.encode_title(value, title)

    def parse_command(self, what):
        """
        Add command info to the dicts
        """

        kind = what["kind"]
        text = what["text"]

        # Needs ot be either a question or an action

        if not text or text[0] not in ["?", "!"]:
            return

        # We know it's a command and it's meme

        what["base"] = "command"

        # If just a ?, then help

        if text == "?":
            text = "?help"

        # Get the name, text

        pieces = text.split(maxsplit=1)

        name = pieces.pop(0)[1:]
        text = pieces.pop(0) if pieces else ""

        # Building a list of all possible commands using search criteria

        search = {}

        # If there's a . in the name, that's the who of the origin or app
        # Note: this works anywhere in any channel

        if '.' in name:
            name, who = name.split(".")
            search["who"] = who

        # If we're in a public channel, use the channel name to match orgins and apps

        elif kind == "public":
            channel = what["channel"]
            search["meta__channel"] = channel

        # If we're in DM's, they can specify the channel with #

        elif kind == "private" and "#" in name:
            name, channel = name.split("#")
            search["meta__channel"] = what["channel"] = channel

        # If this was said by me the bot and a : then this is an id

        if what.get("self") and ':' in name:
            name, what["id"] = name.split(':')

        # Everything's been split out, only the true name remains

        what["command"] = name

        # Data structures multiple apps and a single origin

        commands = []
        what["apps"] = []
        titles = []
        descriptions = []
        helps = []

        # Find all Apps that could apply. This could be all of them
        # if we're in a proivate chat

        for app in unum_ledger.App.many(**search):
            what["apps"].append(app.who)
            commands.extend([{**command, "source": app.who} for command in app.meta__commands])
            titles .append(app.meta__title)
            descriptions.append(app.meta__description)
            helps.append(app.meta__help)

        # If there's search criteria, find a single Origin

        if search:
            origin = unum_ledger.Origin.one(**search).retrieve(False)

            if origin:
                what["origin"] = origin.who
                if origin.id != self.daemon.origin.id:
                    commands.extend([{**command, "source": origin.who} for command in origin.meta__commands])
                titles.append(origin.meta__title)
                descriptions.append(origin.meta__description)
                helps.append(origin.meta__help)

        # If we have an id, there's notjhing more to search for

        if "id" in what:
            return

        # If nothing to search

        if not commands:
            what["error"] = f"No Apps or Origin here - try `?help` in {{channel:{self.daemon.origin.meta__channel}}}"
            return

        # now that we narrowed things down, we can add the common commands to all

        title = " " + " and ".join(titles)

        # If we're public, add help, join, and leave. This means using these commands in
        # shared channel will simultaneously join/leave all at once.

        if kind == "public":

            commands = self.daemon.origin.meta__commands + commands

            self.encode_title(commands[0], title)
            self.encode_title(commands[1], title)
            self.encode_title(commands[2], title)
            self.encode_title(commands[3], title)

        # If we're private, just add help

        elif kind == "private":

            commands.insert(0, self.daemon.origin.meta__commands[0])
            commands.insert(1, self.daemon.origin.meta__commands[1])
            self.encode_title(commands[0], title)
            self.encode_title(commands[1], title)

        # Match by name alone for now

        found = [command for command in commands if name == command["name"]]

        # Not enough

        if not found:
            what["error"] = f"unknown command {name} - try `?help`"
            return

        # Too many

        elif len(found) > 1:

            if kind == "public":
                text = "too many matching commands found - ?help won't help"
            elif kind == "private":
                text = "too many matching commands found - Add .{who} for who or #{channel} to specify an App/Origin"

            what["error"] = text
            return

        # We're going to be mucking with data structures, make a copy to not fuck up original

        command = copy.deepcopy(found[0])

        # Grab the single single if there is one

        if "source" in command:
            what["source"] = command["source"]

        # If they've chosen help, add all the possible commands we just checked to valid usage

        if command["name"] == "help":
            command["usages"][1]["args"][0]["valids"] = [command["name"] for command in commands]

        # If this command has usages, check those

        if command.get("usages"):

            # If couldn't find one, bail

            if not self.parse_usage(what, command, text):
                return

        # If it doens't have usages, we must match it's meme

        elif command["meme"] != what["meme"]:
            what["error"] = f"no usage for {what['meme']}{name} - try `{command['meme']}{name}`"
            return

        # Rather do the same query twice, add what's needed here
        # no let's not optimize right now. Let's do things the right way

        if command["name"] == "help":

            # If it's general usage, we're just going to list all the commands

            if what["usage"] == "general":

                # Use the descrption of the command and the usages if there, if not, the command and meme

                what["description"] = " and ".join(descriptions)
                what["help"] = "\n".join(helps)
                what["commands"] = [
                    {
                        "name": command["name"],
                        "description":  command["description"]
                    } for command in commands
                ]

            # If they want the help for a specific command

            elif what["usage"] == "command":

                # Find the command you need the usage for

                usage = [command for command in commands if what["values"]["command"] == command["name"]][0]

                # Use the descrption of the command and the usages if there, if not, the command and meme

                if "source" in usage:
                    what["source"] = usage["source"]

                what["description"] = usage["description"]
                what["usages"] = usage.get("usages", [
                    {
                        "meme": usage.get("meme", "*"),
                        "description": usage["description"]
                    }
                ])
                what["examples"] = usage.get("examples", [
                    {
                        "meme": usage.get("meme", "*"),
                        "description": usage["description"]
                    }
                ])

        # Determine if there's permissions to use it

        if command['name'] in ["join", "leave", "feats"]:

            feat = f"command:help:{command['name']}#{what['channel']}"

            if not unum_ledger.Feat.one(who=feat, status="completed").retrieve(None):
                what["error"] = f"training required - in {{channel:{channel}}} please ask:\n- `?help {command['name']}`"

        elif command['name'] != "help":

            feat = f"command:help.{command['source']}:{command['name']}"

            if not unum_ledger.Feat.one(who=feat, status="completed").retrieve(None):
                what["error"] = f"training required - please ask:\n- `?help.{command['source']} {command['name']}`"

    async def parse_ancestor(self, ancestor, what, meta):
        """
        Adds parent to the resource provider
        """

        while ancestor.reference:
            ancestor = await ancestor.channel.fetch_message(ancestor.reference.message_id)

        what["ancestor"], meta["ancestor"]= await self.parse_statement(ancestor)

    async def parse_statement(self, message):
        """
        Converts a message obj to a standard dict, optional including the reply
        """

        what = {"base": "statement"}
        meta = {"author": self.parse_user(message.author)}

        self.parse_kind(message, what, meta)

        what["text"]  = self.decode_text(message.content)
        what["meme"] = self.parse_meme(what["text"])

        self.parse_command(what)

        if message.attachments:
            what["links"] = [attachment.url for attachment in message.attachments]

        meta.update({
            "id": str(message.id),
            "content": message.content,
            "created_at": str(message.created_at)
        })

        if message.reference:
            ancestor = await message.channel.fetch_message(message.reference.message_id)
            await self.parse_ancestor(ancestor, what, meta)

        if not what.get("error") and (
            what.get("ancestor", {}).get("error") or
            what.get("ancestor", {}).get("errors") or
            what.get("parent", {}).get("error") or
            what.get("parent", {}).get("errors")
        ):
            what["error"] = "There are errors"

        return what, meta

    async def parse_reaction(self, reaction, user):
        """
        Converts a reaction and user obj to a standard dict
        """

        kind = "private" if isinstance(reaction.message.channel, discord.DMChannel) else "public"

        what = {
            "base": "reaction",
            "kind": kind,
            "emoji": reaction.emoji,
            "meme":  self.parse_meme(reaction.emoji)
        }
        meta =  {
            "user": self.parse_user(user)
        }

        await self.parse_ancestor(reaction.message, what, meta)

        witness = unum_ledger.Witness.one(who=user.id).retrieve(False)

        if witness:
            what["entity_id"] = witness.entity_id

        return what, meta

    # Reacting to Discord commands

    async def multi_send(self, channel, text, reference=None):
        """
        Sends
        """

        while text:

            if len(text) > 2000:
                closest = text[:2000].rfind('\n')
                current = text[:closest]
                text = text[(closest+1):]
            else:
                current = text
                text = ""

            await channel.send(self.encode_text(current), reference=reference)

    async def command_help(self, what, meta, message):
        """
        Prints out help message for an App or Origin
        """

        # Ensure we can track this person

        if "entity_id" not in what:

            unum = unum_ledger.Unum.one(who='self')
            what["entity_id"] = unum_ledger.Entity(
                unum_id=unum.id,
                who=meta["author"]["name"],
                status="inactive",
                meta={
                    "talk": {
                        "after": self.decode_time("8h"),
                        "before": self.decode_time("20h"),
                        "kind": "public",
                        "noise": "loud"
                    }
                }
            ).create().id

            unum_ledger.Witness(
                entity_id=what["entity_id"],
                origin_id=self.daemon.origin.id,
                who=message.author.id,
                status="inactive"
            ).create()

            await self.create_feats(what["entity_id"], self.daemon.origin.who)

        channel = message.channel

        if what["usage"] == "general":

            text = "♥️ *" + what["description"] + "*\n"

            text += "\n" + what["help"]

            text += "\nCommands:"

            for command in what["commands"]:
                text += f"\n- **{command['name']}** - *{command['description']}*"

            text += "\n\nUse ?help __command__ for more info"

        elif what["usage"] == "command":

            text = f'♥️ *{what["description"]}*'

            if "examples" in what:

                text += '\nexamples:'

                for example in what["examples"]:

                    text += f"\n- `{example['meme']}{what['values']['command']}"

                    if "args" in example:
                        text += f" {example['args']}"

                    text += '`'

                    if "description" in example:
                        text += (f"\n  - *{example['description']}*")

            text += '\nusages:'

            formats = set()

            for usage in what["usages"]:

                text += f"\n- **{usage['meme']}{what['values']['command']}**"
                args = ""

                for arg in usage.get("args", []):

                    text += f" __{arg['name']}__"
                    args += f"\n  - __{arg['name']}__"

                    if arg.get("description"):
                        description = arg['description'].replace("{", "__").replace("}", "__")
                        args += (f" - *{description}*")

                    format = arg.get("format", "word")
                    formats.add(format)
                    args += f" - format: ***{format}***"

                    if arg.get("valids"):

                        if isinstance(arg["valids"][0], dict):

                            valids = ""

                            for valid in arg["valids"]:
                                for key, value in valid.items():
                                    valids += f"\n    - __{key}__ - *{value}*"

                        else:
                            valids = ', '.join(f"__{valid}__" for valid in arg["valids"])

                        args += f" - valid values: {valids}"

                if "description" in usage:
                    description = usage['description'].replace("{", "__").replace("}", "__")
                    text += f" - *{description}*"

                text += args

            if formats:
                text += "\nformats:"
                for format in FORMATS:
                    if format["name"] in formats:
                        text += f'\n- ***{format["name"]}*** - *{format["description"]}*'

        await self.multi_send(channel, text, reference=message)

    async def command_join(self, what, meta, message):
        """
        Joins the Unum, Ledger, and Discord Origin
        """

        channel = message.channel
        user_id = meta["author"]["id"]
        welcomes = []
        backs = []
        alreadys = []

        for app in unum_ledger.App.many(who__in=what.get("apps", [])):

            herald = unum_ledger.Herald.one(
                entity_id=what["entity_id"],
                app_id=app.id
            ).retrieve(False)

            if herald:

                if herald.status == "inactive":

                    herald.status = "active"
                    herald.update()
                    backs.append(app.meta__title)

                else:

                    alreadys.append(app.meta__title)

            else:

                unum_ledger.Herald(
                    entity_id=what["entity_id"],
                    app_id=app.id,
                    status="active"
                ).create()

                welcomes.append(app.meta__title)

            await self.create_feats(what["entity_id"], app.who)

        if what.get("origin") == self.daemon.origin.who:

            witness = unum_ledger.Witness.one(
                origin_id=self.daemon.origin.id,
                who=user_id
            ).retrieve()

            entity = unum_ledger.Entity.one(id=witness.entity_id)

            if entity.status == "inactive":

                entity.status = "active"
                entity.update()

            if witness.status == "inactive":

                witness.status = "active"
                witness.update()

            welcomes.append(self.daemon.origin.meta__title)

        elif what.get("origin") and what["origin"] != self.daemon.origin.who:

            await self.create_feats(what["entity_id"], what["origin"])

        comments = []

        if welcomes:
            welcome = ' and '.join(welcomes)
            comments.append(f"Welcome to {welcome}!")

        if backs:
            back = ' and '.join(backs)
            comments.append(f"Welcome back to {back}!")

        if not welcomes and not backs and alreadys:
            already = ' and '.join(alreadys)
            comments.append(f"You've already joined {already}!")

        if comments:
            comment = " ".join(comments)
            text = f"👍 {comment}"
            await self.multi_send(channel, text, reference=message)

    async def command_leave(self, what, meta, message):
        """
        Joins the Unum, Ledger, and Discord Origin
        """

        channel = message.channel
        user_id = meta["author"]["id"]

        text = None

        channel = message.channel
        user_id = meta["author"]["id"]
        lefts = []
        nevers = []
        alreadys = []

        for app in unum_ledger.App.many(who__in=what.get("apps", [])):

            herald = unum_ledger.Herald.one(
                entity_id=what["entity_id"],
                app_id=app.id
            ).retrieve(False)

            if herald:

                if herald.status == "active":

                    herald.status = "inactive"
                    herald.update()
                    lefts.append(app.meta__title)

                else:

                    alreadys.append(app.meta__title)

            else:

                nevers.append(app.meta__title)

        if what.get("origin") == self.daemon.origin.who:

            witness = unum_ledger.Witness.one(
                origin_id=self.daemon.origin.id,
                who=user_id
            ).retrieve(False)

            if witness:

                entity = unum_ledger.Entity.one(id=witness.entity_id).retrieve()

                if entity.status == "active":

                    entity.status = "inactive"
                    entity.update()

                if witness.status == "active":

                    witness.status = "inactive"
                    witness.update()
                    lefts.append(self.daemon.origin.meta__title)

                else:

                    alreadys.append(self.daemon.origin.meta__title)

            else:

                nevers.append(self.daemon.origin.meta__title)

        comments = []

        if lefts:
            left = ' and '.join(lefts)
            comments.append(f"You have left {left}. Good luck to you!")

        if nevers:
            never = ' and '.join(nevers)
            comments.append(f"You were never in {never}!")

        if not lefts and not nevers and alreadys:
            already = ' and '.join(alreadys)
            comments.append(f"You've already left {already}!")

        if comments:
            comment = " ".join(comments)
            text = f"👍 {comment}"
            await self.multi_send(channel, text, reference=message)

    async def command_feats(self, what, meta, message):
        """
        Joins the Unum, Ledger, and Discord Origin
        """

        channel = message.channel
        user_id = meta["author"]["id"]

        herald = unum_ledger.Witness.one(
            origin_id=self.daemon.origin.id,
            who=user_id
        ).retrieve(False)

        if not herald:
            what["error"] = "not yet aware of you - type `?help`"
            return

        text = "♥️ your feats are:"

        if what.get("origin"):
            for feat in unum_ledger.Feat.many(entity_id=herald.entity_id, what__source=what["origin"]):
                text += f"\n- {feat.what__description} - {feat.status} {FEATS[feat.status]}"

        for app in what.get("apps", []):
            for feat in unum_ledger.Feat.many(entity_id=herald.entity_id, what__source=app):
                text += f"\n- {feat.what__description} - {feat.status} {FEATS[feat.status]}"

        await self.multi_send(channel, text, reference=message)

    async def on_command(self, what, meta, message):
        """
        If there's a command that doesn't require creation
        """

        channel = message.channel

        if what.get("error"):
            text = f'❗ {what["error"]}'
            await self.multi_send(channel, text, reference=message)
        elif what.get("errors"):
            text = f'❗ issues with {what["command"]} usage:'
            args = what["args"]
            errors = what["errors"]
            for arg in args:
                if arg["name"] in errors:
                    text += f'\n- {arg["name"]} - {errors[arg["name"]]}'
            await self.multi_send(channel, text, reference=message)
        elif what["command"] == "help":
            await self.command_help(what, meta, message)
        elif what["command"] == "join":
            await self.command_join(what, meta, message)
        elif what["command"] == "leave":
            await self.command_leave(what, meta, message)
        elif what["command"] == "feats":
            await self.command_feats(what, meta, message)

    # Reacting to Discord events

    async def on_message(self, message):
        """
        For every message this bot sees
        """

        what, meta = await self.parse_statement(message)

        if what.get("self"):
            return

        if what.get("command"):
            await self.on_command(what, meta, message)

        self.daemon.logger.info("statement", extra={"what": what, "meta": meta})

        if "entity_id" in what:
            await self.create_fact(
                message,
                origin_id=self.daemon.origin.id,
                entity_id=what["entity_id"],
                who=f"message:{message.id}",
                when=time.mktime(message.created_at.timetuple()),
                what=what,
                meta=meta
            )

    async def on_reaction_add(self, reaction, user):
        """
        For every reactino this bot sees
        """

        what, meta = await self.parse_reaction(reaction, user)

        self.daemon.logger.info("reaction", extra={"what": what, "meta": meta})

        if "entity_id" in what:
            await self.create_fact(
                reaction.mesage,
                origin_id=self.daemon.origin.id,
                entity_id=what["entity_id"],
                who=f"reaction:{reaction.message.id}:{reaction.emoji}",
                when=time.mktime(reaction.message.created_at.timetuple()),
                what=what,
                meta=meta
            )

    async def on_ready(self):
        """
        Called when starting up
        """

        self.daemon.logger.info(f"logged in as {self.user}", extra={"id": self.user.id})

    # Executing Unum Acts

    async def act_statement(self, instance):
        """
        Sends a message where information is required
        """

        entity_id = instance["entity_id"]
        entity = unum_ledger.Entity.one(entity_id)

        meme = instance["what"].get("meme", "*")
        emoji = instance["what"].get("emoji", MEMES[meme])
        command = ""
        text = instance["what"].get("text", "")
        app = unum_ledger.App.one(instance["app_id"]).retrieve(False)

        if "command" in instance["what"]:

            command += meme
            command += instance["what"]["command"]

            if "id" in instance["what"]:
                command += f":{instance['what']['id']}"

        if "listing" in instance["what"]:

            text += instance["what"]["listing"]["description"]

            for item in instance["what"]["listing"]["items"]:
                text += f"\n- {item}"

        target = None
        reference = None

        if instance["meta"].get("ancestor", {}).get("id"):
            target = await self.fetch_channel(instance["meta"]["ancestor"]["channel"]["id"])
            reference = await target.fetch_message(instance["meta"]["ancestor"]["id"])

        if not target and entity.meta__talk__kind == "public":

            target = discord.utils.get(self.get_all_channels(), name=(
                instance["what"].get("channel") or
                app.meta__channel or
                "unifist-unum"
            ))

            if entity.meta__talk__noise == "loud":
                text = f"{{entity:{entity.id}}}, " + text
            else:
                text = f"{entity.who}, " + text

        elif not target:

            if command:
                command += f".{app.who}"

            guild = await self.fetch_guild(self.daemon.origin.meta__guild__id)

            target = await guild.fetch_member(unum_ledger.Witness.one(entity_id=entity_id).who)

        text = (command or emoji) + " " + text

        await self.multi_send(target, text, reference=reference)

    async def act_reaction(self, instance):
        """
        Responds to a message
        """

        entity_id = instance["entity_id"]
        entity = unum_ledger.Entity.one(entity_id)

        meme = instance["what"].get("meme", "*")
        text = instance["what"].get("text")
        emoji = instance["what"].get("emoji", MEMES[meme])

        channel = await self.fetch_channel(instance["meta"]["ancestor"]["channel"]["id"])
        reference = await channel.fetch_message(instance["meta"]["ancestor"]["id"])

        # If we have something to say and we're allowed to say it

        if text and entity.meta__talk__noise in ["loud", "calm"]:

            if not isinstance(channel, discord.DMChannel):

                if entity.meta__talk__noise == "loud":
                    text = f"{{entity:{entity.id}}} " + text
                else:
                    text = f"{entity.who}, " + text

            text = emoji + " " + text

            await self.multi_send(channel, text, reference=reference)

        # Else we only have a reaction

        else:

            await reference.add_reaction(emoji)

    # Create Unum Events

    async def complete_feats(self, message, fact):
        """
        Complete feats if so
        """

        for feat in unum_ledger.Feat.many(
            entity_id=fact.entity_id,
            status__in=["requested", "accepted"],
            what__source=self.daemon.origin.who
        ):

            completed = []

            # Oh yes this is horribly inefficient but it's like no code

            if feat.what__fact and unum_ledger.Fact.one(id=fact.id, **feat.what__fact).retrieve(False):
                feat.status = "completed"
                feat.update()
                completed.append(feat.what__description)

            if completed:
                text = f"{MEMES['*'] } completed Feats:"

                for feat in completed:
                    text += f"\n- {feat}"

                await self.multi_send(message.channel, text, reference=message)

    async def create_fact(self, message, **fact):
        """
        Creates a fact if needed
        """

        if fact["what"].get("command") not in ["help", "feat", "join", "leave"] and not self.is_active(fact["entity_id"]):
            return

        fact = unum_ledger.Fact(**fact).create()

        self.daemon.logger.info("fact", extra={"fact": {"id": fact.id}})
        service.FACTS.observe(1)
        await self.daemon.redis.xadd("ledger/fact", fields={"fact": json.dumps(fact.export())})

        if not fact.what__error and not fact.what__errors:
            await self.complete_feats(message, fact)

    def ensure_feat(self, entity_id, who, **feat):
        """
        Ensure a feat exists
        """

        unum_ledger.Feat.one(entity_id=entity_id, who=who).retrieve(False) or unum_ledger.Feat(
            entity_id=entity_id,
            who=who,
            status="requested",
            when=time.time(),
            **feat
        ).create()

    async def create_feats(self, entity_id, who):
        """
        Creates feats if needed
        """

        if who == self.daemon.origin.who:

            self.ensure_feat(
                entity_id=entity_id,
                who=f"command:help#{self.daemon.origin.meta__channel}",
                what={
                    "source": self.daemon.origin.who,
                    "description": f"Run help publicly in {{channel:{self.daemon.origin.meta__channel}}}",
                    "fact": {
                        "what__origin": self.daemon.origin.who,
                        "what__base": "command",
                        "what__command": "help",
                        "what__channel": self.daemon.origin.meta__channel
                    }
                }
            )

            self.ensure_feat(
                entity_id=entity_id,
                who=f"command:help.{who}:private",
                what={
                    "source": self.daemon.origin.who,
                    "description": f"Run help privately for {who}",
                    "fact": {
                        "what__origin": self.daemon.origin.who,
                        "what__base": "command",
                        "what__kind": "private",
                        "what__command": "help"
                    }
                }
            )

            for command in self.daemon.origin.meta__commands[1:]:

                self.ensure_feat(
                    entity_id=entity_id,
                    who=f"command:help:{command['name']}#{self.daemon.origin.meta__channel}",
                    what={
                        "source": self.daemon.origin.who,
                        "description": f"Get help for {command['name']} in {{channel:{self.daemon.origin.meta__channel}}}",
                        "fact": {
                            "what__base": "command",
                            "what__command": "help",
                            "what__usage": "command",
                            "what__channel": self.daemon.origin.meta__channel,
                            "what__values__command": command['name']
                        }
                    }
                )

            return

        source = unum_ledger.App.one(who=who).retrieve(False) or unum_ledger.Origin.one(who=who).retrieve(False)

        if not source:
            return

        if source.who != "ledger":

            self.ensure_feat(
                entity_id=entity_id,
                who=f"command:help#{source.meta__channel}",
                what={
                    "source": source.who,
                    "description": f"Run help for {source.who} in {{channel:{source.meta__channel}}}",
                    "fact": {
                        "what__base": "command",
                        "what__command": "help",
                        "what__usage": "general",
                        "what__channel": source.meta__channel
                    }
                }
            )

            for command in self.daemon.origin.meta__commands[1:]:

                self.ensure_feat(
                    entity_id=entity_id,
                    who=f"command:help:{command['name']}#{source.meta__channel}",
                    what={
                        "source": source.who,
                        "description": f"Get help for {command['name']} in {{channel:{source.meta__channel}}}",
                        "fact": {
                            "what__base": "command",
                            "what__command": "help",
                            "what__usage": "command",
                            "what__channel": source.meta__channel,
                            "what__values__command": command['name']
                        }
                    }
                )

        if isinstance(source, unum_ledger.App):
            self.ensure_feat(
                entity_id=entity_id,
                who=f"command:help.{source.who}:public",
                what={
                    "source": source.who,
                    "description": f"Run help publicly for {source.who} but not in {{channel:{source.meta__channel}}}",
                    "fact": {
                        "what__apps__has": [source.who],
                        "what__base": "command",
                        "what__kind": "public",
                        "what__command": "help",
                        "what__channel__not_eq": source.meta__channel
                    }
                }
            )

        for command in source.meta__commands:

            self.ensure_feat(
                entity_id=entity_id,
                who=f"command:help.{source.who}:{command['name']}",
                what={
                    "source": source.who,
                    "description": f"Get help for {command['name']} in {source.who}",
                    "fact": {
                        "what__source": source.who,
                        "what__base": "command",
                        "what__command": "help",
                        "what__usage": "command",
                        "what__values__command": command['name']
                    }
                }
            )

    # Recieving Unum Events

    async def on_acts(self):
        """
        Listens for Acts
        """

        if (
            not await self.daemon.redis.exists("ledger/act") or
            self.daemon.group not in [group["name"]
            for group in await self.daemon.redis.xinfo_groups("ledger/act")]
        ):
            await self.daemon.redis.xgroup_create("ledger/act", self.daemon.group, mkstream=True)

        while True:

            message = await self.daemon.redis.xreadgroup(
                self.daemon.group, self.daemon.group_id, {"ledger/act": ">"}, count=1, block=500
            )

            if not message or "act" not in message[0][1][0][1]:
                continue

            instance = json.loads(message[0][1][0][1]["act"])
            self.daemon.logger.info("act", extra={"act": instance})
            service.ACTS.observe(1)

            if not self.is_active(instance["entity_id"]):
                return

            if instance["what"]["base"] == "statement":
                await self.act_statement(instance)
            elif instance["what"]["base"] == "reaction":
                await self.act_reaction(instance)

            await self.daemon.redis.xack("ledger/act", self.daemon.group, message[0][1][0][0])

    async def setup_hook(self):
        """
        Register our Fact and Act listeners
        """

        self.loop.create_task(self.on_acts())


def run(daemon):
    """
    Handles everyting about this origin
    """

    intents = discord.Intents.default()
    intents.members = True
    intents.message_content = True # pylint: disable=assigning-non-slot

    client = OriginClient(daemon=daemon, intents=intents)
    client.run(daemon.creds["token"])
