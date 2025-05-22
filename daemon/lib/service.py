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
  This does a lot of cool shit with Discord
channel: unifist-unum
commands:
- name: help
  description: Help for
  requires: none
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
