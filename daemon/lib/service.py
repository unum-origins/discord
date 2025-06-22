"""
Module for the Daemon
"""

# pylint: disable=no-self-use,too-many-instance-attributes

import os
import micro_logger
import json
import yaml

import redis.asyncio as redis

import relations_rest

import prometheus_client

import unum_ledger
import unum_discord

FACTS = prometheus_client.Summary("facts_written", "Facts written")
ACTS = prometheus_client.Summary("acts_read", "Acts read")

WHO = "discord"
META = """
title: the Discord Origin
description: Discord interface with this Unum.
channel: unifist-unum
help: |
  And Welcome to this Discord Origin, how this Discord server interfaces with thie Unum. Everything here works via Commands. Commands that start with ? are questions abd ask me for information. Commands that start with ! are actions, asking me to change something.

  For help you can type `?help` or just `?` by itself. To get more info on a command type ?help and the name of the command. Read the help fully.

  Each channel has one or more Apps, each with its own set of Commands. If you message me privately, commands from multiple Apps are avaiable. To narrow down a Command to a particular App, add the App name to the command via a '.'. For example, to get just the help for the ledger, DM me `?help.ledger`. This also works in any channel.
commands:
- name: help
  description: Help for
  help: |
    Help shows you how things work. Alone it'll list all commands avaialble. With a command, it'll tell you everything about using that command.

    Each command has various usages. Each usage can take zero or more arguments. Each argument has a format. There are also example for each usage.

    Simply asking for help automatically assigns you Awards to complete. For each command you ask for help, you'll receieve an Award for learning about that command. This is useful, because such awards aqre required to run commands.
  examples:
  - meme: '?'
    description: Lists all the commands for
  - meme: '?'
    args: help
    description: Shows the usages of help for
  - meme: '?'
    channel: unifist-unum
    args: help
    description: Shows in a different channel the usages of help for
  - meme: '?'
    kind: private
    args: help
    description: Shows in a private message (and anywhere else) the usages of help for
  usages:
  - name: general
    meme: '?'
    description: List resources for
  - name: command
    meme: '?'
    description: List usages for the {command} resource for
    args:
    - name: command
      description: The command to list the usages of
      valids: []
- name: scat
  description: Comment riff or poop, on
  help: |
    Scat allows you to comment, riff, complain about anything. This process is eseential to an Unum. Everyone is an Onwer so everyone has a say about anything.

    Scats can be assigned as Tasks, meaning someone is responsible for reading the issue, deciding whether to work on it, and ultimately communciating back to the originator what happened.

    So if you have an issue, a question, a comment, Scat it, and it'll eventually get worked on.
  examples:
  - meme: '!'
    description: Record your concerns for
    args: I don't like it
  - meme: '!'
    description: Record and assign your concerns for
    args: task I don't like it and will do something about it
  - meme: '?'
    description: List all unaissgned scats for
  - meme: '?'
    channel: unifist-unum
    description: List in a different channel all unaissgned scats for
  - meme: '?'
    kind: private
    description: List in a private message (and anywhere else) all unaissgned scats for
  usages:
  - name: record
    meme: '!'
    description: Scat a problem, something wrong, for
    args:
    - name: thoughts
      format: remainder
  - name: assign
    meme: '!'
    description: Scat a problem, and assign to you as a task, for
    args:
    - name: task
      valids:
      - task
    - name: thoughts
      format: remainder
  - name: list_unassigned
    meme: '?'
    description: List all scats currently unassigned for
  - name: list_since
    meme: '?'
    description: List your scats from {since} ago to now for
    args:
    - name: since
      description: How far back to list
      format: duration
  - name: list_from_to
    meme: '?'
    description: List your scats from {from} to {to} for
    args:
    - name: from
      description: How far back to start listing
      format: duration
    - name: to
      description: How far back to stop listing
      format: duration
- name: award
  description: List your Awards in
  help: |
    Awards track achievements, accomplishments that typically open up functionality to you. For example, each command you ask for help, you'll receieve an Award for learning about that command. This is useful, because such awards are required to run commands.

    Awards are completed automatically when you perform them and you can assign Awards as Tasks, like Scats. This moves them from merely being something you can do to something you should do (by your command). The Task feature allows you to do this.
  examples:
  - meme: '?'
    description: List not completed awards for
  - meme: '?'
    channel: unifist-unum
    description: List in a different channel not completed awards for
  - meme: '?'
    kind: private
    description: List in a private message (and anywhere else) all not completed awards for
  - meme: '?'
    description: List all awards for
    args: all
  usages:
  - name: list_incomplete
    meme: '?'
    description: List not completed in
  - name: list_all
    meme: '?'
    description: List all
    args:
    - name: all
      valids:
      - all
- name: task
  description: Manage your Tasks in
  help: |
    Tasks track todos, actions you've decided to do. You can take on an Apps Awards as Tasks. You can grab a random Scat as a Task. You can even QA an entire App or Origin, taking on running every command every which way for that App or Origin.

    Tasks from awards are completed automatically when you perform them. These tasks are listed as bullet points since you can't interact with them.

    Other Tasks, like those created from Scats or just created manually, have to be completed manually. They are listed as individual messages so you can react to them.
  examples:
  - meme: '?'
    description: List not completed tasks for
  - meme: '?'
    channel: unifist-unum
    description: List in a different channel not completed tasks for
  - meme: '?'
    kind: private
    description: List in a private message (and anywhere else) all not completed tasks for
  - meme: '?'
    description: List all tasks for
    args: all
  usages:
  - name: assign
    meme: '!'
    description: Assign yourself tasks in
    args:
    - name: work
      valids:
      - learn: Learn the commands available here
      - qa: Run every command here
      - scat: Assign yourself the most recent Scat
  - name: list_incomplete
    meme: '?'
    description: List not completed
  - name: list_all
    meme: '?'
    description: List all
    args:
    - name: all
      valids:
      - all
- name: join
  help: |
    Joining allows you to interact with an App or Origin. Unums don't just automatically subscribe or bombard people with notifications. You have to agree to participate.

    Joining is that agreement.
  meme: '!'
  description: Join
  requires: none
- name: leave
  help: |
    Leaving severs the connection with an App or Origin. I won't actually delete any records, just inactivate your status.

    You can always join again and not lose anything.
  meme: '!'
"""
NAME = f"{WHO}-daemon"

class Daemon(): # pylint: disable=too-few-public-methods
    """
    Daemon class
    """

    def __init__(self):

        self.name = self.group = NAME
        self.unifist = unum_ledger.Base.SOURCE
        self.group_id = os.environ["K8S_POD"]

        self.sleep = int(os.environ.get("SLEEP", 5))

        self.logger = micro_logger.getLogger(self.name)

        self.source = relations_rest.Source(self.unifist, url=f"http://api.{self.unifist}")

        self.redis = redis.Redis(host=f'redis.{self.unifist}', encoding="utf-8", decode_responses=True)

        with open("/opt/service/secret/discord.json", "r") as creds_file:
            self.creds = json.load(creds_file)

    def run(self):
        """
        Main loop with sleep
        """

        prometheus_client.start_http_server(80)

        unum_discord.run(self)
