"""
Handles everything for the Discord Origin
"""

# pylint: disable=unsupported-membership-test,too-many-lines,no-self-use,undefined-loop-variable,unused-argument,too-many-locals,len-as-condition,too-many-branches,too-many-statements,unused-variable,assigning-non-slot,too-many-nested-blocks,invalid-overridden-method,too-many-return-statements,redefined-outer-name,too-many-public-methods,line-too-long,redefined-argument-from-local

import time
import copy
import json
import yaml

from emoji import EMOJI_DATA
import discord
import discord.abc
import discord.utils

import overscore

import service
import unum_base
import unum_ledger

FORMATS = [
    {
        "name": "word",
        "description": "a single word"
    },
    {
        "name": "remainder",
        "description": "words at the end of a command"
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

TASKS = {
    "inprogress": "👍",
    "wontdo": "👎",
    "done": "♥️",
    "blocked": "❓",
    "imperiled": "❗"
}

AWARDS = {
    "accepted": "👍",
    "rejected": "👎",
    "completed": "♥️",
    "requested": "❓",
    "excepted": "❗"
}

class OriginClient(discord.Client, unum_base.OriginSource):
    """
    Discord Client to handel the Discord origin
    """

    logger = None
    redis = None
    origin = None
    pool = None
    apps = None
    orgins = None
    witness_entity_ids = None
    witness_user_ids = None

    def __init__(self, *args, daemon, **kwargs):

        super(OriginClient, self).__init__(*args, **kwargs)

        self.logger = daemon.logger
        self.redis = daemon.redis
        self.group = daemon.group
        self.group_id = daemon.group_id
        self.guild = daemon.creds["guild"]

    async def journal_change(
            self,
            action,
            model,
            change=None
        ):
        """
        Makes a change and journals it
        """

        create = True
        who = f"{action}:{model.NAME}.{model.SOURCE}"
        what = {
            "action": action,
            "app": model.SOURCE,
            "block": model.NAME
        }

        if action == "create":

            model = model.create()
            what["after"] = model.export()

        who += f":{model.id}"
        what["id"] = model.id

        if action == "update":

            what["before"] = model.export()

            for key, value in change.items():

                path = overscore.parse(key)

                current = model

                for place in path[:-1]:
                    current = current[place]

                current[path[-1]] = value

            what["after"] = model.export()

            create = model.update()

        elif action == "delete":

            what["before"] = model.export()

            create = model.delete()

        if create:
            journal = unum_ledger.Journal(
                who=who,
                what=what,
                when=time.time()
            ).create()

            self.logger.info("journal", extra={"journal": {"id": journal.id}})
            await self.redis.xadd("ledger/journal", fields={"journal": json.dumps(journal.export())})

        if action == "create":
            return model

        return create

    def decode_text(self, text):
        """
        Take Discord text and makes it Unum friendly
        """

        cleaned = text

        for witness in unum_ledger.Witness.many(origin_id=self.origin.id):
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
        """
        Take Unum text and makes it Discord friendly
        """

        cleaned = text

        for witness in unum_ledger.Witness.many(origin_id=self.origin.id):
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
                    if current:
                        values[name] = current
                        current = ""
                        pieces = []
                    else:
                        errors[name] = "nothing remaining"
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

        # Sort remainders by number of args. The one that matches with
        # the most args is the best match since remainder can catch
        # anything.

        remainders = sorted([usage for usage in command["usages"] if
            usage not in invalid and
            usage.get("args") and
            usage["args"][-1].get("format") == "remainder"
        ], key=lambda usage: len(usage["args"]), reverse=True)

        valid = [usage for usage in command["usages"] if usage not in invalid and usage not in remainders]

        # If we can one valid, that's it

        if len(valid) == 1:
            what["usage"] = valid[0]["name"]
            what["values"] = valid[0]["values"]

        # if there's one remainder, or if there more than one remainder and
        # the top one has more args than the nex, that's it

        elif len(remainders) == 1 or (
            len(remainders) > 1 and len(remainders[0]["args"]) > len(remainders[1]["args"])
        ):
            what["usage"] = remainders[0]["name"]
            what["values"] = remainders[0]["values"]

        # Nope, too many good ones

        elif len(valid) > 1 or len(remainders):
            valids = " and ".join([usage["name"] for usage in valid + remainders])
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
                if key == "description" and what.get("kind") != "private":
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

        if not text or text[0] not in ["?", "*", "!"]:
            return

        # We know it's a command and it's meme

        what["base"] = "command"

        # If just a ?, then help

        if text == "?":
            text = "?help"
        elif text[:2] == "? ":
            text = f"?help {text[2:]}"
        elif text[:2] == "! ":
            text = f"!scat {text[2:]}"

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
                if origin.id != self.origin.id:
                    commands.extend([{**command, "source": origin.who} for command in origin.meta__commands])
                titles.append(origin.meta__title)
                descriptions.append(origin.meta__description)
                helps.append(origin.meta__help)

        # If we have an id, there's notjhing more to search for

        if "id" in what:
            return

        # If nothing to search

        if not commands:
            what["error"] = f"No Apps or Origin here - try `?help` in {{channel:{self.origin.meta__channel}}}"
            return

        # now that we narrowed things down, we can add the common commands to all

        title = " " + " and ".join(titles)

        # If we're public, add help, join, and leave. This means using these commands in
        # shared channel will simultaneously join/leave all at once.

        if kind == "public":

            commands = self.origin.meta__commands + commands

            self.encode_title(commands[0], title)
            self.encode_title(commands[1], title)
            self.encode_title(commands[2], title)
            self.encode_title(commands[3], title)
            self.encode_title(commands[4], title)
            self.encode_title(commands[5], title)

        # If we're private, just add help

        elif kind == "private":

            commands.insert(0, self.origin.meta__commands[0])
            commands.insert(1, self.origin.meta__commands[1])
            commands.insert(2, self.origin.meta__commands[2])
            commands.insert(3, self.origin.meta__commands[3])
            self.encode_title(commands[0], title)
            self.encode_title(commands[1], title)
            self.encode_title(commands[2], title)
            self.encode_title(commands[3], title)

        # Match by name alone for now

        found = [command for command in commands if name == command["name"]]

        # Not enough

        if not found:
            what["error"] = f"unknown command {name} - try `?help`"
            return

        # Too many

        if len(found) > 1:

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

        else:

            what["usage"] = "default"

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
                        "description":  command.get("description", command["name"])
                    } for command in commands
                ]

            # If they want the help for a specific command

            elif what["usage"] == "command":

                # Find the command you need the usage for

                usage = [command for command in commands if what["values"]["command"] == command["name"]][0]

                # Use the descrption of the command and the usages if there, if not, the command and meme

                if "source" in usage:
                    what["source"] = usage["source"]

                if "help" in usage:
                    what["help"] = usage["help"]

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

        if command['name'] in ["scat", "award", "task", "join", "leave"]:

            if "channel" not in what:

                what["error"] = f"channel required - try:\n- `?{command['name']}#channel`"

            else:

                award = f"command:help:{command['name']}#{what['channel']}"

                if not unum_ledger.Award.one(
                    entity_id=what.get("entity_id"),
                    who=award,
                    status="completed"
                ).retrieve(None):
                    what["error"] = f"training required - in {{channel:{channel}}} please ask:\n- `?help {command['name']}`"

        elif command['name'] != "help":

            award = f"command:help.{command['source']}:{command['name']}"

            if not unum_ledger.Award.one(
                entity_id=what.get("entity_id"),
                who=award,
                status="completed"
            ).retrieve(None):
                what["error"] = f"training required - please ask:\n- `?help.{command['source']} {command['name']}`"

    async def parse_ancestor(self, ancestor, what, meta):
        """
        Adds parent to the resource provider
        """

        while ancestor.reference:

            if ancestor.content and ancestor.content[0] in ['!', '?', '*']:
                break

            ancestor = await ancestor.channel.fetch_message(ancestor.reference.message_id)

        what["ancestor"], meta["ancestor"] = await self.parse_statement(ancestor)

    async def parse_statement(self, message):
        """
        Converts a message obj to a standard dict, optional including the reply
        """

        what = {"base": "statement"}
        meta = {"author": self.parse_user(message.author)}

        self.parse_kind(message, what, meta)

        what["text"] = self.decode_text(message.content)
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
        meta = {
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

        texts = text if isinstance(text, list) else [text]

        for text in texts:

            while text:

                if len(text) > 2000:
                    closest = text[:1950].rfind('\n')
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
            entity = await self.journal_change("create", unum_ledger.Entity(
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
            ))

            what["entity_id"] = entity.id

            await self.journal_change("create", unum_ledger.Witness(
                entity_id=what["entity_id"],
                origin_id=self.origin.id,
                who=message.author.id,
                status="inactive"
            ))

            await self.create_awards(what["entity_id"], self.origin.who)

        if "origin" in what:
            await self.create_awards(what["entity_id"], what["origin"])

        for app in what.get("apps", []):
            await self.create_awards(what["entity_id"], app)

        channel = message.channel

        if what["usage"] == "general":

            text = "♥️ *" + what["description"] + "*\n"

            if "help" in what:
                text += "\n" + what["help"]

            text += "\nCommands:"

            for command in what["commands"]:
                text += f"\n- **{command['name']}** - *{command['description']}*"

            text += "\n\nUse ?help __command__ for more info"

        elif what["usage"] == "command":

            text = f'♥️ *{what["description"]}*'

            if "help" in what:
                text += "\n" + what["help"]

            if "examples" in what:

                text += '\nexamples:'

                for example in what["examples"]:

                    sources = [None]
                    descriptions = {}

                    if example.get("kind") == "private":

                        sources = what.get("apps", [])

                        if "origin" in what and what["origin"] != self.origin.who:
                            sources.append(what["origin"])

                    for source in sources:

                        text += f"\n- `{example['meme']}{what['values']['command']}"

                        if "channel" in example:
                            text += f"#{example['channel']}"
                        elif source:
                            text += f".{source}"

                        if "args" in example:
                            text += f" {example['args']}"

                        text += '`'

                        if "description" in example:

                            description = example['description']

                            if "channel" in example:
                                description += f" while not in {{channel:{example['channel']}}}"

                            if source:

                                origin = unum_ledger.Origin.one(who=source).retrieve(False)

                                if origin:
                                    description += f" {origin.meta__title}"

                                app = unum_ledger.App.one(who=source).retrieve(False)

                                if app:
                                    description += f" {app.meta__title}"

                                description += f" while in direct message <@{self.user.id}> (or anywhere else)"

                            text += f"\n  - *{description}*"

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

                    await self.journal_change("update", herald, {"status": "active"})
                    backs.append(app.meta__title)

                else:

                    alreadys.append(app.meta__title)

            else:

                herald = await self.journal_change("create", unum_ledger.Herald(
                    entity_id=what["entity_id"],
                    app_id=app.id,
                    status="active"
                ))

                welcomes.append(app.meta__title)

            await self.create_awards(what["entity_id"], app.who)

        if what.get("origin") == self.origin.who:

            witness = unum_ledger.Witness.one(
                origin_id=self.origin.id,
                who=user_id
            ).retrieve()

            entity = unum_ledger.Entity.one(id=witness.entity_id)

            if entity.status == "inactive":

                await self.journal_change("update", entity, {"status": "active"})

            if witness.status == "inactive":

                await self.journal_change("update", witness, {"status": "active"})

                before = entity.export()
                witness.status = "active"
                witness.update()

            welcomes.append(self.origin.meta__title)

        elif what.get("origin") and what["origin"] != self.origin.who:

            await self.create_awards(what["entity_id"], what["origin"])

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

                    await self.journal_change("update", herald, {"status": "inactive"})
                    lefts.append(app.meta__title)

                else:

                    alreadys.append(app.meta__title)

            else:

                nevers.append(app.meta__title)

        if what.get("origin") == self.origin.who:

            witness = unum_ledger.Witness.one(
                origin_id=self.origin.id,
                who=user_id
            ).retrieve(False)

            if witness:

                entity = unum_ledger.Entity.one(id=witness.entity_id).retrieve()

                if entity.status == "active":

                    await self.journal_change("update", entity, {"status": "inactive"})

                if witness.status == "active":

                    await self.journal_change("update", witness, {"status": "inactive"})
                    lefts.append(self.origin.meta__title)

                else:

                    alreadys.append(self.origin.meta__title)

            else:

                nevers.append(self.origin.meta__title)

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

    async def command_scat(self, what, meta, message):
        """
        Records a scat or lists them
        """

        channel = message.channel

        entity_id = what["entity_id"]
        meme = what["meme"]
        usage = what["usage"]
        values = what.get("values", {})

        if meme == "!":

            scat = await self.journal_change("create", unum_ledger.Scat(
                entity_id=entity_id,
                who=f"discord.message:{message.id}",
                status="recorded",
                when=time.time(),
                what={
                    "description": values["thoughts"],
                    "on": what
                }
            ))

            if usage == "assign":

                await self.ensure_task(
                    entity_id=entity_id,
                    who=f"ledger.scat:{scat.id}",
                    what={
                        "source": "ledger",
                        "description": f"Looking into Scat: {scat.what__description}",
                        "scat": {
                            "id": scat.id
                        }
                    }
                )

                await self.journal_change("update", scat, {"status": "assigned"})

                text = f"scatted and assigned to you {values['thoughts']}"

            else:

                text = f"scatted {values['thoughts']}"

        elif meme == "?":

            if usage == "list_unassigned":

                text = ["♥️ unassigned scats are (👍 to assign, ♥️ to complete):"]

                for scat in unum_ledger.Scat.many(status="recorded"):
                    text.append(f"*scat:{scat.id} {scat.what__description} - {scat.status}")

            else:

                now = time.time()
                when_min = when_max = 0

                if usage == "list_since":

                    when_min = values["since"]
                    text = [f"♥️ your scats from {self.encode_time(when_min) or 'now'} are (👍 to assign, ♥️ to complete):"]

                elif usage == "list_from_to":

                    when_min = values["from"]
                    when_max = values["to"]
                    text = [f"♥️ your scats from {self.encode_time(when_min) or 'now'} to {self.encode_time(when_max) or 'now'} are (👍 to assign, ♥️ to complete):"]

                for scat in unum_ledger.Scat.many(
                    entity_id=entity_id,
                    when__gte=now - when_min,
                    when__lte=now - when_max
                ):
                    when = self.encode_time(now - scat.when) or "now"
                    text.append(f"*scat:{scat.id} {scat.what__description} - {scat.status} - {when}")

        await self.multi_send(channel, text, reference=message)

    async def reaction_scat(self, what, meta, reaction):
        """
        Reacts to a scat or lists them
        """

        channel = reaction.message.channel
        entity_id = what["entity_id"]
        meme = what["meme"]
        id = what["ancestor"]["id"]

        scat = unum_ledger.Scat.one(id)

        if meme == "+":

            await self.ensure_task(
                entity_id=entity_id,
                who=f"ledger.scat:{scat.id}",
                what={
                    "source": "ledger",
                    "description": f"Looking into Scat: {scat.what__description}",
                    "scat": {
                        "id": scat.id
                    }
                }
            )

            await self.journal_change("update", scat, {"status": "assigned"})

            text = f"assigned to you {scat.what__description}"

        elif meme == "*":

            await self.journal_change("update", scat, {"status": "received"})

            text = f"completed {scat.what__description}"

            task = unum_ledger.Task.one(what__scat__id=scat.id).retrieve(False)

            if task:

                await self.journal_change("update", task, {"status": "done"})

                text += " and its task"

        await self.multi_send(channel, text, reference=reaction.message)

    async def command_award(self, what, meta, message):
        """
        Joins the Unum, Ledger, and Discord Origin
        """

        channel = message.channel
        user_id = meta["author"]["id"]

        herald = unum_ledger.Witness.one(
            origin_id=self.origin.id,
            who=user_id
        ).retrieve(False)

        if not herald:
            what["error"] = "not yet aware of you - type `?help`"
            return

        entity_id = what["entity_id"]
        meme = what["meme"]
        usage = what["usage"]
        values = what.get("values", {})

        if usage == "list_incomplete":

            text = "♥️ your incomplete awards are:"

            if what.get("origin"):
                for award in unum_ledger.Award.many(entity_id=entity_id, status__not_eq="completed", what__source=what["origin"]):
                    text += f"\n- {award.what__description} - {award.status} {AWARDS[award.status]}"

            for app in what.get("apps", []):
                for award in unum_ledger.Award.many(entity_id=entity_id, status__not_eq="completed", what__source=app):
                    text += f"\n- {award.what__description} - {award.status} {AWARDS[award.status]}"

        else:

            text = "♥️ your awards are:"

            if what.get("origin"):
                for award in unum_ledger.Award.many(entity_id=entity_id, what__source=what["origin"]):
                    text += f"\n- {award.what__description} - {award.status} {AWARDS[award.status]}"

            for app in what.get("apps", []):
                for award in unum_ledger.Award.many(entity_id=entity_id, what__source=app):
                    text += f"\n- {award.what__description} - {award.status} {AWARDS[award.status]}"

        await self.multi_send(channel, text, reference=message)

    async def command_task(self, what, meta, message):
        """
        Joins the Unum, Ledger, and Discord Origin
        """

        channel = message.channel
        user_id = meta["author"]["id"]

        herald = unum_ledger.Witness.one(
            origin_id=self.origin.id,
            who=user_id
        ).retrieve(False)

        if not herald:
            what["error"] = "not yet aware of you - type `?help`"
            return

        entity_id = what["entity_id"]
        meme = what["meme"]
        usage = what["usage"]
        values = what.get("values", {})

        if meme == "!":

            updated = True
            work = values["work"]

            if work == "scat":

                updated = await self.create_scat_task(entity_id)

            else:

                whos = []

                if "origin" in what:
                    whos.append(what["origin"])

                for app in what.get("apps", []):
                    whos.append(app)

                if work == "learn":
                    for who in whos:
                        await self.create_learn_tasks(entity_id, who)
                elif work == "qa":
                    for who in whos:
                        await self.create_qa_tasks(entity_id, who)

            text = f"assigned {work} work" if updated else "no scats to assign"

        elif meme == "?":

            manuals = []

            if usage == "list_incomplete":

                text = "♥️ your incomplete tasks are:"

                if what.get("origin"):
                    for task in unum_ledger.Task.many(entity_id=entity_id, status__not_eq="done", what__source=what["origin"]):
                        if task.what__fact:
                            text += f"\n- {task.what__description} - {task.status} {TASKS[task.status]}"
                        else:
                            manuals.append(f"*task:{task.id} {task.what__description} - {task.status} {TASKS[task.status]}")

                for app in what.get("apps", []):
                    for task in unum_ledger.Task.many(entity_id=entity_id, status__not_eq="done", what__source=app):
                        if task.what__fact:
                            text += f"\n- {task.what__description} - {task.status} {TASKS[task.status]}"
                        else:
                            manuals.append(f"*task:{task.id} {task.what__description} - {task.status} {TASKS[task.status]}")

            else:

                text = ["♥️ your tasks are (♥️ to complete):"]

                if what.get("origin"):
                    for task in unum_ledger.Task.many(entity_id=entity_id, what__source=what["origin"]):
                        if task.what__fact:
                            text += f"\n- {task.what__description} - {task.status} {TASKS[task.status]}"
                        else:
                            manuals.append(f"*task:{task.id} {task.what__description} - {task.status} {TASKS[task.status]}")

                for app in what.get("apps", []):
                    for task in unum_ledger.Task.many(entity_id=entity_id, what__source=app):
                        if task.what__fact:
                            text += f"\n- {task.what__description} - {task.status} {TASKS[task.status]}"
                        else:
                            manuals.append(f"*task:{task.id} {task.what__description} - {task.status} {TASKS[task.status]}")

            if manuals:
                text += "\n(♥️ to complete):"
                text = [text] + manuals

        await self.multi_send(channel, text, reference=message)

    async def reaction_task(self, what, meta, reaction):
        """
        Reacts to a scat or lists them
        """

        channel = reaction.message.channel
        entity_id = what["entity_id"]
        meme = what["meme"]
        id = what["ancestor"]["id"]

        task = unum_ledger.Task.one(id)

        if meme == "*":

            await self.journal_change("update", task, {"status": "done"})

            text = f"completed {task.what__description}"

            scat = unum_ledger.Scat.one(task.what__scat__id).retrieve(False)

            if task:

                await self.journal_change("update", scat, {"status": "received"})

                text += " and its scat"

        await self.multi_send(channel, text, reference=reaction.message)

    async def do_command(self, what, meta, message):
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
        else:

            app = unum_ledger.App.one(who=what.get("source")).retrieve(False)

            if not self.is_active(what.get("entity_id")) or (app and not unum_ledger.Herald.one(
                entity_id=what.get("entity_id"),
                app_id=app.id,
                status="active"
            ).retrieve(False)):
                text = '❗ not active - need to join first'
                await self.multi_send(channel, text, reference=message)
            elif what["command"] == "scat":
                await self.command_scat(what, meta, message)
            elif what["command"] == "award":
                await self.command_award(what, meta, message)
            elif what["command"] == "task":
                await self.command_task(what, meta, message)


    async def do_reaction(self, what, meta, reaction):
        """
        Perform the who
        """

        name = what["ancestor"]["command"]

        if name == "scat":
            await self.reaction_scat(what, meta, reaction)
        elif name == "award":
            await self.reaction_award(what, meta, reaction)
        elif name == "task":
            await self.reaction_task(what, meta, reaction)

    # Reacting to Discord events

    async def on_message(self, message):
        """
        For every message this bot sees
        """

        what, meta = await self.parse_statement(message)

        if what.get("self"):
            return

        if what.get("command"):
            await self.do_command(what, meta, message)

        self.logger.info("statement", extra={"what": what, "meta": meta})

        if "entity_id" in what:
            await self.create_fact(
                message,
                origin_id=self.origin.id,
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

        if what.get("ancestor", {}).get("command"):
            await self.do_reaction(what, meta, reaction)

        self.logger.info("reaction", extra={"what": what, "meta": meta})

        if "entity_id" in what:
            await self.create_fact(
                reaction.message,
                origin_id=self.origin.id,
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

        self.logger.info(f"logged in as {self.user}", extra={"id": self.user.id})

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

            guild = await self.fetch_guild(self.origin.meta__guild__id)

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

    async def complete_awards(self, message, fact):
        """
        Complete awards if so
        """

        for award in unum_ledger.Award.many(
            entity_id=fact.entity_id,
            status__in=["requested", "accepted"]
        ):

            completed = []

            # Oh yes this is horribly inefficient but it's like no code

            if award.what__fact and unum_ledger.Fact.one(id=fact.id, **award.what__fact).retrieve(False):

                await self.journal_change("update", award, {"status": "completed"})
                completed.append(award.what__description)

            if completed:
                text = f"{MEMES['*'] } completed Awards:"

                for award in completed:
                    text += f"\n- {award}"

                await self.multi_send(message.channel, text, reference=message)

    async def complete_tasks(self, message, fact):
        """
        Complete tasks if so
        """

        for task in unum_ledger.Task.many(
            entity_id=fact.entity_id,
            status__in=["blocked", "inprogress"]
        ):

            completed = []

            # Oh yes this is horribly inefficient but it's like no code

            if task.what__fact and unum_ledger.Fact.one(id=fact.id, **task.what__fact).retrieve(False):

                await self.journal_change("update", task, {"status": "done"})
                completed.append(task.what__description)

            if completed:
                text = f"{MEMES['*'] } completed Tasks:"

                for task in completed:
                    text += f"\n- {task}"

                await self.multi_send(message.channel, text, reference=message)

    async def create_fact(self, message, **fact):
        """
        Creates a fact if needed
        """

        if fact["what"].get("command") not in ["help", "award", "join", "leave"] and not self.is_active(fact["entity_id"]):
            return

        fact = await self.journal_change("create", unum_ledger.Fact(**fact))

        self.logger.info("fact", extra={"fact": {"id": fact.id}})
        service.FACTS.observe(1)
        await self.redis.xadd("ledger/fact", fields={"fact": json.dumps(fact.export())})

        if not fact.what__error and not fact.what__errors:
            await self.complete_awards(message, fact)
            await self.complete_tasks(message, fact)

    async def ensure_award(self, entity_id, who, **award):
        """
        Ensure a award exists
        """

        if unum_ledger.Award.one(entity_id=entity_id, who=who).retrieve(False):
            return

        award = await self.journal_change("create", unum_ledger.Award(
            entity_id=entity_id,
            who=who,
            status="requested",
            when=time.time(),
            **award
        ))

    async def ensure_task(self, entity_id, who, status="inprogress", **task):
        """
        Ensure a task exists
        """

        if unum_ledger.Task.one(entity_id=entity_id, who=who).retrieve(False):
            return

        task = await self.journal_change("create", unum_ledger.Task(
            entity_id=entity_id,
            who=who,
            status=status,
            when=time.time(),
            **task
        ))

    async def create_awards(self, entity_id, who):
        """
        Creates awards if needed
        """

        if who == self.origin.who:

            await self.ensure_award(
                entity_id=entity_id,
                who=f"command:help#{self.origin.meta__channel}",
                what={
                    "source": self.origin.who,
                    "description": f"Run help publicly in {{channel:{self.origin.meta__channel}}}",
                    "fact": {
                        "what__origin": self.origin.who,
                        "what__base": "command",
                        "what__command": "help",
                        "what__channel": self.origin.meta__channel
                    }
                }
            )

            await self.ensure_award(
                entity_id=entity_id,
                who=f"command:help.{who}:private",
                what={
                    "source": self.origin.who,
                    "description": f"Run help privately for {who}",
                    "fact": {
                        "what__origin": self.origin.who,
                        "what__base": "command",
                        "what__kind": "private",
                        "what__command": "help"
                    }
                }
            )

            for command in self.origin.meta__commands[1:]:

                await self.ensure_award(
                    entity_id=entity_id,
                    who=f"command:help:{command['name']}#{self.origin.meta__channel}",
                    what={
                        "source": self.origin.who,
                        "description": f"Get help for {command['name']} in {{channel:{self.origin.meta__channel}}}",
                        "fact": {
                            "what__base": "command",
                            "what__command": "help",
                            "what__usage": "command",
                            "what__channel": self.origin.meta__channel,
                            "what__values__command": command['name']
                        }
                    }
                )

            return

        source = unum_ledger.App.one(who=who).retrieve(False) or unum_ledger.Origin.one(who=who).retrieve(False)

        if not source:
            return

        if source.who != "ledger":

            await self.ensure_award(
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

            for command in self.origin.meta__commands[1:]:

                await self.ensure_award(
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

            await self.ensure_award(
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

            await self.ensure_award(
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

    async def create_learn_tasks(self, entity_id, who):
        """
        Creates tasks from command awards if needed
        """

        await self.create_awards(entity_id, who)

        for award in unum_ledger.Award.many(entity_id=entity_id, status="requested", what__source=who):

            await self.ensure_task(
                entity_id=award.entity_id,
                who=award.who,
                what=award.what,
                status=("done" if award.status == "completed" else "inprogress")
            )

            await self.journal_change("update", award, {"status": "accepted"})

    async def create_qa_tasks(self, entity_id, who):
        """
        Creates awards if needed
        """

        # This makes sure all the help is run

        await self.create_awards(entity_id, who)

        source = unum_ledger.App.one(who=who).retrieve(False) or unum_ledger.Origin.one(who=who).retrieve(False)

        if not source:
            return

        # We run every usage of every command

        if source.who != "ledger":

            for command in self.origin.meta__commands[1:]:

                if command["name"] in ["join", "leave"]:
                    continue

                for usage in command.get("usages", [
                    {
                        "meme": command.get("meme", "*"),
                        "name": "default",
                        "description": command["description"]
                    }
                ]):

                    await self.ensure_task(
                        entity_id=entity_id,
                        who=f"command:{command['name']}.{usage['name']}#{source.meta__channel}",
                        what={
                            "source": source.who,
                            "description": f"Run {usage['name']} usage for {command['name']} in {{channel:{source.meta__channel}}}",
                            "fact": {
                                "what__base": "command",
                                "what__command": command['name'],
                                "what__usage": usage['name'],
                                "what__channel": source.meta__channel
                            }
                        }
                    )

        for command in source.meta__commands:

            if command["name"] in ["join", "leave"]:
                continue

            for usage in command.get("usages", [
                {
                    "meme": command.get("meme", "*"),
                    "name": "default",
                    "description": command.get("description", command["name"])
                }
            ]):

                await self.ensure_task(
                    entity_id=entity_id,
                    who=f"command:{command['name']}.{usage['name']}#{source.meta__channel}",
                    what={
                        "source": source.who,
                        "description": f"Run {usage['name']} usage for {command['name']} in {source.who}",
                        "fact": {
                            "what__base": "command",
                            "what__command": command['name'],
                            "what__usage": usage['name'],
                            "what__channel": source.meta__channel
                        }
                    }
                )

    async def create_scat_task(self, entity_id):
        """
        Creates awards if needed
        """

        for scat in unum_ledger.Scat.many(status="recorded"):

            await self.ensure_task(
                entity_id=entity_id,
                who=f"ledger.scat:{scat.id}",
                what={
                    "source": "ledger",
                    "description": f"Looking into Scat: {scat.what__description or scat.id}",
                    "scat": {
                        "id": scat.id
                    }
                }
            )

            return await self.journal_change("update", scat, {"status": "assigned"})

        return 0

    # Recieving Unum Events

    async def on_acts(self):
        """
        Listens for Acts
        """

        if (
            not await self.redis.exists("ledger/act") or
            self.group not in [group["name"]
            for group in await self.redis.xinfo_groups("ledger/act")]
        ):
            await self.redis.xgroup_create("ledger/act", self.group, mkstream=True)

        while True:

            message = await self.redis.xreadgroup(
                self.group, self.group_id, {"ledger/act": ">"}, count=1, block=500
            )

            if not message or "act" not in message[0][1][0][1]:
                continue

            instance = json.loads(message[0][1][0][1]["act"])
            self.logger.info("act", extra={"act": instance})
            service.ACTS.observe(1)

            if not self.is_active(instance["entity_id"]):
                return

            if instance["what"]["base"] == "statement":
                await self.act_statement(instance)
            elif instance["what"]["base"] == "reaction":
                await self.act_reaction(instance)

            await self.redis.xack("ledger/act", self.group, message[0][1][0][0])

    async def setup_hook(self):
        """
        Register our Fact and Act listeners
        """

        self.origin = unum_ledger.Origin.one(who=service.WHO).retrieve(False)

        if not self.origin:
            self.origin = await self.journal_change("create", unum_ledger.Origin(who=service.WHO))

        await self.journal_change("update", self.origin, {"meta": {**yaml.safe_load(service.META), **{"guild": self.guild}}})

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
