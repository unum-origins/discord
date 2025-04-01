"""
Module for the Daemon
"""

# pylint: disable=no-self-use,too-many-instance-attributes

import os
import micro_logger
import json
import redis

import relations_rest

import prometheus_client

import unum_ledger
import unum_discord

FACTS = prometheus_client.Summary("facts_created", "Facts created")

class Daemon: # pylint: disable=too-few-public-methods
    """
    Daemon class
    """

    def __init__(self):

        self.name = "discord-daemon"
        self.unifist = unum_ledger.Base.SOURCE
        self.group = "daemon-discord"
        self.group_id = os.environ["K8S_POD"]

        self.sleep = int(os.environ.get("SLEEP", 5))

        self.logger = micro_logger.getLogger(self.name)

        self.source = relations_rest.Source(self.unifist, url=f"http://api.{self.unifist}")

        self.redis = redis.Redis(host=f'redis.{self.unifist}', encoding="utf-8", decode_responses=True)

    def fact(self, **fact):
        """
        Creates a fact if needed
        """

        fact = unum_ledger.Fact(**fact).create()

        self.logger.info("fact", extra={"fact": {"id": fact.id}})
        FACTS.observe(1)
        self.redis.xadd("ledger/fact", fields={"fact": json.dumps(fact.export())})

        return fact

    def run(self):
        """
        Main loop with sleep
        """

        prometheus_client.start_http_server(80)

        unum_discord.run(self)
