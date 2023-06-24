#!/usr/bin/env python3
"""Cyberjunky's Freqtrade bot helpers."""
import argparse
import configparser
import json
import os
import ssl
import sys
import time
import uuid
from pathlib import Path
from urllib.parse import urlencode, urlparse, urlunparse

import requests
from aiohttp import web
from freqtrade.configuration import Configuration
from freqtrade.resolvers import ExchangeResolver

from helpers.freqtrade import load_blacklist
from helpers.logging import Logger, NotificationHandler


def load_config():
    """Create default or load existing config file."""

    cfg = configparser.ConfigParser(allow_no_value=True)
    if cfg.read(f"{datadir}/{program}.ini"):
        return cfg

    cfg["settings"] = {
        "timezone": "Europe/Amsterdam",
        "debug": False,
        "logrotate": 7,
        "notifications": False,
        "notify-urls": ["notify-url1"],
    }

    cfg["webserver"] = {
        "baseurl": uuid.uuid4(),
        "port": 8090,
        "; Use ssl certificates when connected to the internet!": None,
        "ssl": False,
        "certfile": "Full path to your fullchain.pem",
        "privkey": "Full path to your privkey.pem",
    }

    cfg[f"webhook_{uuid.uuid4()}"] = {
        "ft-config": f"{os.path.expanduser('~')}/freqtrade/your-bot-config.json",
        "comment": "Just a description of this section",
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
    blacklistfile = args.blacklist
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


def webhook_action(ftcfg, pair, trade):
    """Check pair and trigger the bot."""

    # Load config from freqtrade file
    ftconfig = Configuration.from_files([ftcfg])

    # Gather some bot values
    base = ftconfig["stake_currency"]
    exchangename = ftconfig["exchange"]["name"]
    botname = ftconfig["bot_name"]

    # Init exchange for this config
    exchange = ExchangeResolver.load_exchange(
        ftconfig["exchange"]["name"], ftconfig, validate=False
    )

    # Load tickerlist for this exchange
    tickerlist = exchange.get_tickers()

    # Base curreny check
    if not pair.endswith(base):
        logger.info("Pair '%s' not using stakecurrency '%s'!" % (pair, base))
        return

    # Pair exchange check
    if pair not in tickerlist:
        logger.info(
            "Pair '%s' not present on the '%s' exchange!" % (pair, exchangename)
        )
        return

    # Prepare client API
    client = FtRestClient(ftconfig)

    if trade == "buy":
        logger.info("Triggering '%s' to buy '%s'" % (botname, pair))
        result = client.forcebuy(pair)
        logger.debug(result)
    else:
        logger.info("Triggering '%s' to sell '%s'" % (botname, pair))
        trades = client.status()
        for activetrade in trades:
            if activetrade["pair"] == pair:
                tradeid = activetrade["trade_id"]
                break

        if tradeid:
            result = client.forcesell(tradeid)
            logger.debug(result)
        else:
            logger.info(
                "Could not find active trade with '%s' and '%s'" % (botname, pair)
            )


# Initialize
blacklist = load_blacklist(logger, blacklistfile)

# Webserver app
app = web.Application(logger=logger)

# Webserver settings
baseurl = config.get("webserver", "baseurl")
httpport = config.get("webserver", "port")
# SSL
sslenabled = config.getboolean("webserver", "ssl")
certfile = config.get("webserver", "certfile")
privkey = config.get("webserver", "privkey")

# Fetch configured hooks
tokens = list()
for section in config.sections():
    if section.startswith("webhook_"):
        # Add token to list
        tokens.append(section.replace("webhook_", ""))

# Process webhook calls
async def handle(request):
    """Handle web requests."""

    data = await request.json()
    logger.debug("Webhook alert received: %s" % data)

    token = data.get("token")
    if token in tokens:
        logger.debug("Webhook alert token acknowledged")

        # Get and verify actions
        actiontype = data.get("action").lower()
        ftconf = config.get(f"webhook_{token}", "ft-config")

        # Deal actions
        if actiontype in ["buy", "sell"]:
            logger.debug(f"Webhook deal command received: {actiontype}")

            pair = data.get("pair")

            logger.debug("Trade type: %s" % actiontype)
            logger.debug("Pair: %s" % pair)

            webhook_action(ftconf, pair, actiontype)
        else:
            logger.error(
                f"Webhook alert received ignored, unsupported type '{actiontype}'"
            )

        return web.Response()

    logger.error("Webhook alert received denied, token '%s' invalid" % token)
    return web.Response(status=403)


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

    def _get(self, apipath, params: dict = None):
        return self._call("GET", apipath, params=params)

    def _post(self, apipath, params: dict = None, data: dict = None):
        return self._call("POST", apipath, params=params, data=data)

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

    def forcesell(self, tradeid):
        """Sell an asset.

        :param tradeid: id of trade to sell
        :return: json object of the trade
        """
        data = {"tradeid": tradeid}
        return self._post("forcesell", data=data)

    def status(self):
        """Get status
        :return: json object
        """
        return self._get("status")


# Prepare webhook webserver
app.router.add_post(f"/{baseurl}", handle)
logger.info(f"Starting webserver listening to '/{baseurl}'")

# https
if sslenabled:
    # Build ssl context
    context = ssl.SSLContext(ssl.PROTOCOL_TLSv1_2)
    context.load_cert_chain(certfile, privkey)

    web.run_app(
        app, host="0.0.0.0", port=httpport, ssl_context=context, access_log=None
    )

# http
web.run_app(app, host="0.0.0.0", port=httpport, access_log=None)
