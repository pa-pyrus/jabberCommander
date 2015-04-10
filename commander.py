#!/usr/bin/env python3
# vim:fileencoding=utf-8:ts=8:et:sw=4:sts=4:tw=79

"""
commander.py: XMPP bot for Planetary Annihilation

Copyright (c) 2015 Pyrus <pyrus at coffee dash break dot at>
See the file LICENSE for copying permission.
"""

from concurrent.futures import ThreadPoolExecutor, wait
from datetime import datetime
from io import StringIO
from json import loads
from os import environ
from pytz import timezone, utc
from sleekxmpp import ClientXMPP
from time import sleep
from urllib.request import urlopen

import logging
LOG_FORMAT = "{levelname}({name}): {message}"
logging.basicConfig(level=logging.INFO, format=LOG_FORMAT, style="{")

HITBOX_URL = ("https://www.hitbox.tv/"
              "api/media/live/list"
              "?game=828&liveOnly=true&showHidden=false")
TWITCH_URL = ("https://api.twitch.tv/"
              "kraken/streams"
              "?game=Planetary+Annihilation")


def load_url(url, timeout):
    """Utility method to load URLs using the concurrent module."""
    return urlopen(url, timeout=timeout).read()


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

    def handle_command_live(self, room, args):
        """
        Handle !live command.
        Print current streams on Twitch and Hitbox.
        """
        self.logger.info("Loading Twitch and Hitbox streams.")
        with ThreadPoolExecutor(max_workers=2) as executor:
            futures = {"twitch": executor.submit(load_url, TWITCH_URL, 10),
                       "hitbox": executor.submit(load_url, HITBOX_URL, 10)}

        # we don't care for the return values here
        wait(futures.values())
        self.logger.info("Loaded Twitch and Hitbox streams.")

        # start with twitch
        twitch_streams = list()
        if not futures["twitch"].exception():
            raw = str(futures["twitch"].result(), "utf-8")
            data = loads(raw)

            streams = list()
            for stream in data.get("streams", tuple()):
                channel = stream.get("channel", None)
                if not channel:
                    continue
                name = channel.get("display_name", "N/A")
                desc = channel.get("status", "N/A")
                url = channel.get("url", "N/A")
                viewers = stream.get("viewers", 0)
                streams.append({"name": name, "desc": desc,
                                "url": url, "viewers": viewers})

            twitch_streams = sorted(streams,
                                    key=lambda x: x["viewers"],
                                    reverse=True)
            self.logger.info("Got %d Twitch streams.", len(twitch_streams))

        # continue with hitbox
        hitbox_streams = list()
        if not futures["hitbox"].exception():
            raw = str(futures["hitbox"].result(), "utf-8")
            data = loads(raw)

            streams = list()
            for stream in data.get("livestream", tuple()):
                channel = stream.get("channel", None)
                if not channel:
                    continue
                name = stream.get("media_display_name", "N/A")
                desc = stream.get("media_status", "N/A")
                url = channel.get("channel_link", "N/A")
                viewers = stream.get("media_views", 0)
                streams.append({"name": name, "desc": desc,
                                "url": url, "viewers": viewers})
            hitbox_streams = sorted(streams,
                                    key=lambda x: x["viewers"],
                                    reverse=True)
            self.logger.info("Got %d Hitbox streams.", len(hitbox_streams))

        twitch_nofs = len(twitch_streams)
        twitch_body = StringIO()
        twitch_html = StringIO()
        if not twitch_nofs:
            twitch_body.write(
                "There are no Planetary Annihilation streams on Twitch.tv "
                "at the moment.")
            twitch_html.write(
                "There are no Planetary Annihilation streams on "
                "<a href=\"{0}\">Twitch.tv</a> at the moment.".format(
                    "http://www.twitch.tv/"
                    "directory/game/Planetary%20Annihilation"))
        elif twitch_nofs > 5:
            twitch_body.write(
                "There currently are {0} PA streams on Twitch.tv. For a "
                "full list visit {1}. Five most viewed streams:\n".format(
                    twitch_nofs,
                    "http://www.twitch.tv/"
                    "directory/game/Planetary%20Annihilation"))
            twitch_html.write(
                "There currently are <strong>{0}</strong> PA streams on "
                "<a href=\"{1}\">Twitch.tv</a>. "
                "Five most viewed streams:<br/>".format(
                    twitch_nofs,
                    "http://www.twitch.tv/"
                    "directory/game/Planetary%20Annihilation"))
            twitch_nofs = 5
        elif twitch_nofs > 1:
            twitch_body.write(
                "There currently are {0} PA streams on Twitch.tv:\n".format(
                    twitch_nofs))
            twitch_html.write(
                "There currently are <strong>{0}</strong> PA streams on "
                "Twitch.tv:<br/>".format(twitch_nofs))
        else:
            twitch_body.write(
                "There currently is one PA stream on Twitch.tv:\n")
            twitch_html.write(
                "There currently is <strong>one</strong> PA stream on "
                "Twitch.tv:<br/>")

        if twitch_nofs:
            twitch_html.write("<ol>")

        for x in range(twitch_nofs):
            body = "#{0}: {1} by {2} ({3})".format(
                        x+1,
                        twitch_streams[x]["desc"].replace("\n", ""),
                        twitch_streams[x]["name"],
                        twitch_streams[x]["url"])
            twitch_body.write(body)
            if x < twitch_nofs - 1:
                twitch_body.write("\n")

            html = ("<li>"
                    "<a href=\"{2}\">{0} by <strong>{1}</strong></a>"
                    "</li>".format(
                        twitch_streams[x]["desc"].replace("\n", ""),
                        twitch_streams[x]["name"],
                        twitch_streams[x]["url"]))
            twitch_html.write(html)

        if twitch_nofs:
            twitch_html.write("</ol>")

        self.send_message(mto=room, mtype="groupchat",
                          mbody=twitch_body.getvalue(),
                          mhtml=twitch_html.getvalue())
        twitch_body.close()
        twitch_html.close()
        sleep(1.0)

        hitbox_nofs = len(hitbox_streams)
        hitbox_body = StringIO()
        hitbox_html = StringIO()
        if not hitbox_nofs:
            hitbox_body.write(
                "There are no Planetary Annihilation streams on Hitbox.tv "
                "at the moment.")
            hitbox_html.write(
                "There are no Planetary Annihilation streams on "
                "<a href=\"{0}\">Hitbox.tv</a> at the moment.".format(
                    "http://www.hitbox.tv/browse/planetary-annihilation"))
        elif hitbox_nofs > 5:
            hitbox_body.write(
                "There currently are {0} PA streams on Hitbox.tv. For a "
                "full list visit {1}. Five most viewed streams:\n".format(
                    hitbox_nofs,
                    "http://www.hitbox.tv/browse/planetary-annihilation"))
            hitbox_html.write(
                "There currently are <strong>{0}</strong> PA streams on "
                "<a href=\"{1}\">Hitbox.tv</a>. "
                "Five most viewed streams:<br/>".format(
                    hitbox_nofs,
                    "http://www.hitbox.tv/browse/planetary-annihilation"))
            hitbox_nofs = 5
        elif hitbox_nofs > 1:
            hitbox_body.write(
                "There currently are {0} PA streams on Hitbox.tv:\n".format(
                    hitbox_nofs))
            hitbox_html.write(
                "There currently are <strong>{0}</strong> PA streams on "
                "Hitbox.tv:<br/>".format(hitbox_nofs))
        else:
            hitbox_body.write(
                "There currently is one PA stream on Hitbox.tv:\n")
            hitbox_html.write(
                "There currently is <strong>one</strong> PA stream on "
                "Hitbox.tv:<br/>")

        if hitbox_nofs:
            hitbox_html.write("<ol>")

        for x in range(hitbox_nofs):
            body = "#{0}: {1} by {2} ({3})".format(
                        x+1,
                        hitbox_streams[x]["desc"].replace("\n", ""),
                        hitbox_streams[x]["name"],
                        hitbox_streams[x]["url"])
            hitbox_body.write(body)
            if x < hitbox_nofs - 1:
                hitbox_body.write("\n")

            html = ("<li>"
                    "<a href=\"{2}\">{0} by <strong>{1}</strong></a>"
                    "</li>".format(
                        hitbox_streams[x]["desc"].replace("\n", ""),
                        hitbox_streams[x]["name"],
                        hitbox_streams[x]["url"]))
            hitbox_html.write(html)

        if hitbox_nofs:
            hitbox_html.write("</ol>")

        self.send_message(mto=room, mtype="groupchat",
                          mbody=hitbox_body.getvalue(),
                          mhtml=hitbox_html.getvalue())
        hitbox_body.close()
        hitbox_html.close()

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
