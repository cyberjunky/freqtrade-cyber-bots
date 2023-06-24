#!/usr/bin/env python3
"""Cyberjunky's Freqtrade bot helpers."""
import argparse
import configparser
import json
import os
import sys
import time
from pathlib import Path
import requests
from urllib.parse import urlencode, urlparse, urlunparse
from freqtrade.configuration import Configuration
from freqtrade.resolvers import ExchangeResolver

from helpers.freqtrade import load_blacklist
from helpers.logging import Logger, NotificationHandler
from helpers.misc import (
    format_pair,
    get_botassist_data,
    wait_time_interval,
    populate_pair_lists,
)

def load_config():
    """Create default or load existing config file."""

    cfg = configparser.ConfigParser()
    if cfg.read(f"{datadir}/{program}.ini"):
        return cfg

    cfg["settings"] = {
        "timezone": "Europe/Amsterdam",
        "timeinterval": 3600,
        "debug": False,
        "logrotate": 7,
        "start-number": 1,
        "end-number": 200,
        "list": "binance_spot_usdt_highest_volatility_day",
        "ft-config": f"{os.path.expanduser('~')}/freqtrade/your-bot-config.json",
        "minvolume": 50.0,
        "notifications": False,
        "notify-urls": ["notify-url1"],
    }

    with open(f"{datadir}/{program}.ini", "w") as cfgfile:
        cfg.write(cfgfile)

    return None


def botassist_pairs(ftcfg):
    """Find new pairs and update the bot config."""

    # Load config from freqtrade file
    ftconfig = Configuration.from_files([ftcfg])

    # Gather some bot values
    base = ftconfig["stake_currency"]
    exchangename = ftconfig["exchange"]["name"]
    botname = ftconfig["bot_name"]

    logger.info("Bot: %s" % botname)
    logger.info("Bot base currency: %s" % base)
    logger.info("Bot exchange: %s" % exchangename)
    logger.info("Bot pairs minimal 24h USDT volume: %s" % minvolume)

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
    for pairdata in botassistdata:
        pair = format_pair(logger, pairdata["pair"])
        # Check if coin has minimum 24h volume as set in bot
        if pairdata["volume"] < minvolume:
            logger.debug(
                "Pair '%s' does not have enough 24h BTC volume (%s), skipping"
                % (pair, str(pairdata["volume"]))
            )
            continue

        # Populate lists
        populate_pair_lists(pair, blacklist, blackpairs, badpairs, newpairs, tickerlist)

    logger.debug("These pairs are blacklisted and were skipped: %s" % blackpairs)

    if not newpairs:
        logger.info(
            "None of the BotAssist pairs are present on the '%s' exchange!"
            % exchangename
        )
        return

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

    # Prepare API to be able to reload config
    url = ftconfig.get('api_server', {}).get('listen_ip_address', '127.0.0.1')
    port = ftconfig.get('api_server', {}).get('listen_port', '8080')
    username = ftconfig.get('api_server', {}).get('username')
    password = ftconfig.get('api_server', {}).get('password')

    server_url = f"http://{url}:{port}"
    client = FtRestClient(server_url, username, password)

    logger.info("Reloading config for Bot '%s'" % botname)
    client.reload_config()


class FtRestClient():

    def __init__(self, serverurl, username=None, password=None):

        self._serverurl = serverurl
        self._session = requests.Session()
        self._session.auth = (username, password)

    def _call(self, method, apipath, params: dict = None, data=None, files=None):

        if str(method).upper() not in ('GET', 'POST', 'PUT', 'DELETE'):
            raise ValueError(f'invalid method <{method}>')
        basepath = f"{self._serverurl}/api/v1/{apipath}"

        hd = {"Accept": "application/json",
              "Content-Type": "application/json"
              }

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

    def _post(self, apipath, params: dict = None, data: dict = None):
        return self._call("POST", apipath, params=params, data=data)

    def reload_config(self):
        """Reload configuration.
        :return: json object
        """
        return self._post("reload_config")

# Start application
program = Path(__file__).stem

# Parse and interpret options.
parser = argparse.ArgumentParser(description="Cyberjunky's Freqtrade bot helper.")
parser.add_argument(
    "-d", "--datadir", help="directory to use for config and logs files", type=str
)
parser.add_argument(
    "-b", "--blacklist", help="local blacklist to use instead of 3Commas's", type=str
)

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
    # Initialise temp logging
    logger = Logger(datadir, program, None, 7, False, False)
    logger.info(
        f"Created example config file '{datadir}/{program}.ini', edit it and restart the program"
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

    logger.info(f"Loaded configuration from '{datadir}/{program}.ini'")

# Inject botassist pairs into freqtrade's StaticPairList
while True:

    # Reload config files and data to catch changes
    config = load_config()
    logger.info(f"Reloaded configuration from '{datadir}/{program}.ini'")

    # Configuration settings
    startnumber = int(config.get("settings", "start-number"))
    endnumber = 1 + (int(config.get("settings", "end-number")) - startnumber)
    ftconf = config.get("settings", "ft-config")
    minvolume = float(config.get("settings", "minvolume"))
    botassistdata = get_botassist_data(
        logger, config.get("settings", "list"), startnumber, endnumber
    )
    timeint = int(config.get("settings", "timeinterval"))

    # Update the blacklist
    blacklist = load_blacklist(logger, blacklistfile)

    # Find the pairs
    botassist_pairs(ftconf)

    if not wait_time_interval(logger, notification, timeint):
        break
