#!/usr/bin/env python3
# vim:fileencoding=utf-8:ts=8:et:sw=4:sts=4:tw=79

"""
commander.py: XMPP bot for Planetary Annihilation

Copyright (c) 2015 Pyrus <pyrus at coffee dash break dot at>
See the file LICENSE for copying permission.
"""

from datetime import datetime
from os import environ
from pytz import timezone, utc
from sleekxmpp import ClientXMPP

import logging
LOG_FORMAT = "{levelname}({name}): {message}"
logging.basicConfig(level=logging.INFO, format=LOG_FORMAT, style="{")


class Commander(ClientXMPP):
    """
    The Commander XMPP bot.
    It registers necessary plugins, joins multi-user chat rooms and responds to
    certain commands.
    """
    logger = logging.getLogger("commander")

    def __init__(self, jid, password, nick, room):
        """Register event handlers and plugins."""
        ClientXMPP.__init__(self, jid, password)

        self.nick = nick
        self.room = room

        self.add_event_handler("session_start", self.handle_session_start)
        self.add_event_handler("groupchat_message", self.handle_muc_message)

        self.register_plugin("xep_0045")  # Multi-User Chat
        self.register_plugin("xep_0071")  # XHTML-IM
        self.register_plugin("xep_0199")  # XMPP Ping

        self.logger.info("Initialized XMPP Client instance.")

    def handle_session_start(self, event):
        """Join the configured multi-user chat room after connecting."""
        self.logger.info("XMPP client session started.")
        self.logger.info("Joining MUC room %s as %s", self.room, self.nick)

        # join the configured room
        muc_plugin = self.plugin["xep_0045"]
        muc_plugin.joinMUC(self.room, self.nick)

    def handle_muc_message(self, msg):
        """Parse and respond to incoming multi-user chat messages."""
        nick = msg["mucnick"]
        room = msg["mucroom"]
        message = msg["body"]

        # we ignore our own messages, obviously
        if nick == self.nick:
            return

        # ignore everything that's not a command
        if not message.startswith("!"):
            return

        # commands and arguments are separated by spaces
        command, *arguments = message.split(" ")

        # check if we can handle that command
        command_name = "handle_command_{0}".format(command[1:])
        handle_command = getattr(self, command_name, None)
        if handle_command and callable(handle_command):
            self.logger.info("Got command %s from %s.", command, nick)
            handle_command(room, arguments)

    def handle_command_now(self, room, args):
        """
        Handle !now command.
        Print current UTC (and US/Pacific) time and date.
        """
        now = datetime.utcnow().replace(microsecond=0, tzinfo=utc)
        now_str = now.isoformat(" ")
        ubernow = now.astimezone(timezone("US/Pacific"))
        ubernow_str = ubernow.isoformat(" ")

        body = "It is now {0} (UTC) / {1} (Ubertime)".format(now_str,
                                                             ubernow_str)
        html = ("It is now "
                "<strong>{0}</strong> (UTC) / "
                "<strong>{1}</strong> (Ubertime)".format(now_str,
                                                         ubernow_str))

        self.send_message(mto=room, mtype="groupchat", mbody=body, mhtml=html)

if __name__ == "__main__":
    # get configuration
    ubername = environ["UBERENT_UBERNAME"]
    password = environ["UBERENT_PASSWORD"]
    xmpp_url = environ["UBERENT_XMPP_URL"]
    xmpp_jid = "{0}@{1}".format(ubername, xmpp_url)
    nickname = environ["PA_CHAT_NICK"]
    chatroom = environ["PA_CHAT_ROOM"]
    muc_base = "conference.{0}".format(xmpp_url)
    muc_room = "{0}@{1}".format(chatroom, muc_base)

    # initialize, connect and start processing
    bot = Commander(xmpp_jid, password, nickname, muc_room)
    bot.connect()
    bot.process(block=True)
