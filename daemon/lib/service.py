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
help: |
  And Welcome to this Discord Origin, how this Discord server interfaces with thie Unum.

  Everything here works via Commands. Commands that start with ? are questions abd ask me for information. Commands
  that start with ! are actions, asking me to change something.

  For help you can type `?help` or just `?` by itself. To get more info on a command type `?help __command__`. Read
  the command help fully. It'll explain the context of the command, what it does, and how to format arguments
  correctly. Such training is required before being allowed to use a command. You will get a friendly request to
  complete training, complete with the command to run.

  Everytime you join an App, you'll get new Awards to accomplish. To see you reaming Awards to accomplish, type
  `?award`. Using `?award` and `?help` this way should train you up on how to use all the awardures available to
  you here.

  Each channel has one or more Apps, each with its own set of Commands. If you message me privately, all commands
  are avaiable. To narrow down a Command to a particular App, add the App name to the command via a '.'. For example,
  to get just the help for the ledger, DM me `?help.ledger`. This also works in any channel.
channel: unifist-unum
commands:
- name: help
  description: Help for
  requires: none
  examples:
  - meme: '?'
    description: Lists all the commands for
  - meme: '?'
    args: help
    description: Shows the usages of help
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
  requires: none
  examples:
  - meme: '!'
    description: Record your concerns
  - meme: '?'
    description: List all unaissgned scats
  usages:
  - name: record
    meme: '!'
    description: Scat a problem, something wrong, for
    args:
    - name: thoughts
      format: remainder
  - name: list_unassigned
    meme: '?'
    description: List all scats currently unassigned
  - name: list_since
    meme: '?'
    description: List your scats from {since} ago to now
    args:
    - name: since
      description: How far back to list
      format: duration
  - name: list_from_to
    meme: '?'
    description: List your scats from {from} to {to}
    args:
    - name: from
      description: How far back to start listing
      format: duration
    - name: to
      description: How far back to stop listing
      format: duration
- name: award
  description: List your Awards in
  usages:
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
- name: task
  description: Manage your Tasks in
  usages:
  - name: assign
    meme: '!'
    description: Assign yourself tasks
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
  meme: '!'
  description: Join
  requires: none
- name: leave
  meme: '!'
  description: Leave
"""
NAME = f"{WHO}-daemon"

class Daemon: # pylint: disable=too-few-public-methods
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

        with open("/opt/service/secret/discord.json", "r") as creds_file:
            self.creds = json.load(creds_file)

        if not unum_ledger.Origin.one(who=WHO).retrieve(False):
            unum_ledger.Origin(who=WHO).create()

        self.origin = unum_ledger.Origin.one(who=WHO)
        self.origin.meta={**yaml.safe_load(META), **{"guild": self.creds["guild"]}}
        self.origin.update()

        self.redis = redis.Redis(host=f'redis.{self.unifist}', encoding="utf-8", decode_responses=True)

    def run(self):
        """
        Main loop with sleep
        """

        prometheus_client.start_http_server(80)

        unum_discord.run(self)
