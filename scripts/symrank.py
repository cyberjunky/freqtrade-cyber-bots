#!/usr/bin/env python3
"""Cyberjunky's Freqtrade bot helpers."""
import argparse
import configparser
import json
import os
import re
import sys
import time
from pathlib import Path
from urllib.parse import urlencode, urlparse, urlunparse

import requests
from freqtrade.configuration import Configuration
from freqtrade.resolvers import ExchangeResolver
from telethon import TelegramClient, events

from helpers.logging import Logger, NotificationHandler


def load_config():
    """Create default or load existing config file."""

    cfg = configparser.ConfigParser()
    if cfg.read(f"{datadir}/{program}.ini"):
        return cfg

    cfg["settings"] = {
        "timezone": "Europe/Amsterdam",
        "debug": False,
        "logrotate": 7,
        "symrank-signals": ["top30"],
        "symrank-pairs": False,
        "tgram-phone-number": "Your Telegram Phone number",
        "tgram-channel": "Telegram Channel to watch",
        "tgram-api-id": "Your Telegram API ID",
        "tgram-api-hash": "Your Telegram API Hash",
        "ft-config": f"{os.path.expanduser('~')}/freqtrade/your-bot-config.json",
        "notifications": False,
        "notify-urls": ["notify-url1"],
    }

    with open(f"{datadir}/{program}.ini", "w") as cfgfile:
        cfg.write(cfgfile)

    return None


# Start application
program = Path(__file__).stem

# Parse and interpret options.
parser = argparse.ArgumentParser(description="Cyberjunky's 3Commas bot helper.")
parser.add_argument(
    "-d", "--datadir", help="directory to use for config and logs files", type=str
)
parser.add_argument("-b", "--blacklist", help="blacklist to use", type=str)

args = parser.parse_args()
if args.datadir:
    datadir = args.datadir
else:
    datadir = os.getcwd()

# pylint: disable-msg=C0103
if args.blacklist:
    blacklistfile = f"{datadir}/{args.blacklist}"
else:
    blacklistfile = None

# Create or load configuration file
config = load_config()
if not config:
    logger = Logger(datadir, program, None, 7, False, False)
    logger.info(
        f"Created example config file '{program}.ini', edit it and restart the program"
    )
    sys.exit(0)
else:
    # Handle timezone
    if hasattr(time, "tzset"):
        os.environ["TZ"] = config.get(
            "settings", "timezone", fallback="Europe/Amsterdam"
        )
        time.tzset()

    # Init notification handler
    notification = NotificationHandler(
        program,
        config.getboolean("settings", "notifications"),
        config.get("settings", "notify-urls"),
    )

    # Initialise logging
    logger = Logger(
        datadir,
        program,
        notification,
        int(config.get("settings", "logrotate", fallback=7)),
        config.getboolean("settings", "debug"),
        config.getboolean("settings", "notifications"),
    )


class FtRestClient:
    """Freqtrade API client."""

    def __init__(self, ftconfig):

        username = ftconfig.get("api_server", {}).get("username")
        password = ftconfig.get("api_server", {}).get("password")
        url = ftconfig.get("api_server", {}).get("listen_ip_address", "127.0.0.1")
        port = ftconfig.get("api_server", {}).get("listen_port", "8080")
        self._session = requests.Session()
        self._session.auth = (username, password)
        self._serverurl = f"http://{url}:{port}"

    def _call(self, method, apipath, params: dict = None, data=None):

        if str(method).upper() not in ("GET", "POST", "PUT", "DELETE"):
            raise ValueError(f"invalid method <{method}>")
        basepath = f"{self._serverurl}/api/v1/{apipath}"

        hd = {"Accept": "application/json", "Content-Type": "application/json"}

        # Split url
        schema, netloc, path, par, query, fragment = urlparse(basepath)
        # URLEncode query string
        query = urlencode(params) if params else ""
        # recombine url
        url = urlunparse((schema, netloc, path, par, query, fragment))

        try:
            resp = self._session.request(method, url, headers=hd, data=json.dumps(data))
            # return resp.text
            return resp.json()
        except ConnectionError:
            logger.warning("Connection error")
            return None

    def _post(self, apipath, params: dict = None, data: dict = None):
        return self._call("POST", apipath, params=params, data=data)

    def _get(self, apipath, params: dict = None):
        return self._call("GET", apipath, params=params)

    def reload_config(self):
        """Reload configuration.
        :return: json object
        """
        return self._post("reload_config")

    def forcebuy(self, pair, price=None):
        """Buy an asset.

        :param pair: Pair to buy (ETH/BTC)
        :param price: Optional - price to buy
        :return: json object of the trade
        """
        data = {"pair": pair, "price": price}
        return self._post("forcebuy", data=data)

    def count(self):
        """Return the amount of open trades.
        :return: json object
        """
        return self._get("count")

    def performance(self):
        """Return the performance of the different coins.
        :return: json object
        """
        return self._get("performance")


def parse_tg(raw_text):
    """Return telegram textlines."""
    return raw_text.split("\n")


def tg_data(text_lines, base):
    """Parse telegram message."""
    # Make sure the message is a signal
    # 6 Lines old Telegram signal - will be removed after @Mantis update
    # 7 Lines new Telegram signal
    if len(text_lines) == 7:
        data = {}
        signal = text_lines[1]
        token = text_lines[2].replace("#", "")
        action = text_lines[3].replace("BOT_", "")
        volatility_score = text_lines[4].replace("Volatility Score ", "")

        if volatility_score == "N/A":
            volatility_score = 9999999

        priceaction_score = text_lines[5].replace("Price Action Score ", "")

        if priceaction_score == "N/A":
            priceaction_score = 9999999

        symrank = text_lines[6].replace("SymRank #", "")

        if symrank == "N/A":
            symrank = 9999999

        if signal == "SymRank Top 30":
            signal = "top30"
        elif signal == "SymRank Top 100 Triple Tracker":
            signal = "triple100"
        else:
            signal = "xvol"

        data = {
            "signal": signal,
            "pair": token + "/" + base,
            "action": action,
            "volatility": float(volatility_score),
            "price_action": float(priceaction_score),
            "symrank": int(symrank),
        }
    # Symrank list
    elif len(text_lines) == 17:
        pairs = {}
        data = []

        if "Volatile" not in text_lines[0]:
            for row in text_lines:
                if ". " in row:
                    # Sort the pair list from Telegram
                    line = re.split(" +", row)
                    pairs.update(
                        {
                            int(line[0][:-1]): line[1] + "/" + base,
                            int(line[2][:-1]): line[3] + "/" + base,
                        }
                    )

            allpairs = dict(sorted(pairs.items()))
            data = {"signal": "pairs", "pairs": list(allpairs.values())}
    else:
        data = False

    return data


def populate_pair_lists(pair, blacklist, blackpairs, badpairs, newpairs, tickerlist):
    """Create pair lists."""

    # Check if pair is in tickerlist and on 3Commas blacklist
    if pair in tickerlist:
        if pair in blacklist:
            blackpairs.append(pair)
        else:
            newpairs.append(pair)
    else:
        badpairs.append(pair)


def load_blacklist(logger, blacklistfile):
    """Return blacklist data to be used."""

    # Return file based blacklist
    if blacklistfile:
        newblacklist = []
        try:
            with open(blacklistfile, "r") as file:
                newblacklist = file.read().splitlines()
            if newblacklist:
                logger.info(
                    "Reading local blacklist file '%s' OK (%s pairs)"
                    % (blacklistfile, len(newblacklist))
                )
        except FileNotFoundError:
            logger.error(
                "Reading local blacklist file '%s' failed with error: File not found"
                % blacklistfile
            )

        return newblacklist

    return []


def forcebuy(ftcfg, pair):
    """Trigger the bot to forcebuy pair."""

    # Load config from freqtrade file
    ftconfig = Configuration.from_files([ftcfg])

    # Gather some bot values
    exchangename = ftconfig["exchange"]["name"]
    botname = ftconfig["bot_name"]

    # Init exchange for this config
    exchange = ExchangeResolver.load_exchange(
        ftconfig["exchange"]["name"], ftconfig, validate=False
    )

    # Load tickerlist for this exchange
    tickerlist = exchange.get_tickers()

    # Parse bot-assist data
    if pair not in tickerlist:
        logger.info(
            "Pair '%s' not present on the '%s' exchange!" % (pair, exchangename)
        )
        return

    # Client API
    client = FtRestClient(ftconfig)

    trades = client.count()
    if trades:
        current = trades["current"]
        max = trades["max"]
        if current == max:
            logger.info("Already running max. trades: %s/%s, skipping" % (current, max))
            return
        logger.info("Running trades: %s/%s" % (current, max))

    perf = client.performance()
    profit_pct = 0.0
    for pairperf in perf:
        if pairperf["pair"] == pair:
            profit_pct = float(pairperf["profit_pct"])
            logger.info("This pair had bad performance: %s, skipping" % profit_pct)
            return

        logger.info("Pair performance: %s" % profit_pct)

    logger.info("Trigger Forcebuy of '%s' for Bot '%s'" % (pair, botname))
    client.forcebuy(pair)


def symrank_pairs(ftcfg, symrank_list):
    """Find new pairs and update the bot."""

    # Load config from freqtrade file
    ftconfig = Configuration.from_files([ftcfg])

    # Gather some bot values
    base = ftconfig["stake_currency"]
    exchangename = ftconfig["exchange"]["name"]
    botname = ftconfig["bot_name"]

    logger.info("Bot: %s" % botname)
    logger.info("Bot base currency: %s" % base)
    logger.info("Bot exchange: %s" % exchangename)

    # Start from scratch
    newpairs = list()
    badpairs = list()
    blackpairs = list()

    # Init exchange for this config
    exchange = ExchangeResolver.load_exchange(
        ftconfig["exchange"]["name"], ftconfig, validate=False
    )

    # Load tickerlist for this exchange
    tickerlist = exchange.get_tickers()

    # Parse bot-assist data
    for pair in symrank_list:
        # Populate lists
        populate_pair_lists(pair, blacklist, blackpairs, badpairs, newpairs, tickerlist)

    if not newpairs:
        logger.info(
            "None of the Symrank pairs are present on the '%s' exchange!" % exchangename
        )
        return

    logger.info("Filtered %s" % newpairs)

    # Insert new pairs into config file
    with open(ftcfg) as infile:
        data = json.load(infile)

    data["exchange"]["pair_whitelist"] = newpairs

    with open(ftcfg, "w") as outfile:
        json.dump(data, outfile, indent=4)

    logger.info(
        "Bot '%s' updated with %d pairs (%s ... %s)"
        % (botname, len(newpairs), newpairs[0], newpairs[-1]),
        True,
    )

    # Client API
    client = FtRestClient(ftconfig)

    logger.info("Reloading config for Bot '%s'" % botname)
    client.reload_config()


# Prefetch blacklists
blacklist = load_blacklist(logger, blacklistfile)

ftconf = config.get("settings", "ft-config")
srsignals = config.get("settings", "symrank-signals")
srpairs = config.getboolean("settings", "symrank-pairs")

# Watchlist telegram trigger
client = TelegramClient(
    f"{datadir}/{program}",
    config.get("settings", "tgram-api-id"),
    config.get("settings", "tgram-api-hash"),
).start(config.get("settings", "tgram-phone-number"))


@client.on(events.NewMessage(chats=config.get("settings", "tgram-channel")))
async def callback(event):
    """Parse Telegram message."""
    logger.info(
        "Received telegram message: '%s'" % event.message.text.replace("\n", " - "),
        True,
    )
    # Load config from freqtrade file
    ftconfig = Configuration.from_files([ftconf])

    # Gather some bot values
    base = ftconfig["stake_currency"]

    data = tg_data(parse_tg(event.raw_text), base)
    print(data)
    if data["signal"] in srsignals and data["action"] == "START":
        pair = data["pair"]
        forcebuy(ftconf, pair)
    elif "pairs" in data["signal"] and srpairs:
        symrank_pairs(ftconf, data["pairs"])

    notification.send_notification()


async def symrankpairs(chatid):
    """Request symrank pairs."""
    logger.info("Calling Symrank to get new pairs")
    await client.send_message(chatid, "/symrank")


async def main():
    """Main loop."""
    async for dialog in client.iter_dialogs():
        if dialog.name == "3C Quick Stats":
            chatid = dialog.id

    await symrankpairs(chatid)


with client:
    client.loop.run_until_complete(main())

client.start()
client.run_until_disconnected()
