#!/usr/bin/env python3
"""Cyberjunky's 3Commas bot helpers."""
import argparse
import configparser
#import json
import os
import sys
import time
#from datetime import datetime, timedelta
from pathlib import Path

from helpers.logging import Logger, NotificationHandler
from helpers.misc import (
    wait_time_interval
)

from freqtradeclient.ft_rest_client import FtRestClient


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
        "notifications": False,
        "notify-urls": ["notify-url1"],
        "botlist": [],
    }

    with open(f"{datadir}/{program}.ini", "w") as cfgfile:
        cfg.write(cfgfile)

    return None


def upgrade_config(cfg):
    """Upgrade config file if needed."""

    return cfg


# Start application
program = Path(__file__).stem

# Parse and interpret options.
parser = argparse.ArgumentParser(description="Cyberjunky's Freqtrade bot helper.")
parser.add_argument(
    "-d", "--datadir", help="directory to use for config and logs files", type=str
)

args = parser.parse_args()
if args.datadir:
    datadir = args.datadir
else:
    datadir = os.getcwd()

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

    # Upgrade config file if needed
    config = upgrade_config(config)

    logger.info(f"Loaded configuration from '{datadir}/{program}.ini'")

# Create profit report
while True:
    # Reload config files and data to catch changes
    config = load_config()
    logger.info(f"Reloaded configuration from '{datadir}/{program}.ini'")

    # Configuration settings
    timeint = int(config.get("settings", "timeinterval"))
    debug = config.getboolean("settings", "debug")

    serverlist = []
    serverlist.append('192.168.1.144:8081')
    serverlist.append('192.168.1.144:8082')
    serverlist.append('192.168.1.144:8083')
    serverlist.append('192.168.1.144:8084')

    # Prepare API to be able to reload config
    #url = '192.168.1.144'
    #port = 8075
    username = 'freqtrader'
    password = 'freqtrader'

    datalist={}

    for server in serverlist:
        server_url = f"http://{server}"
        client = FtRestClient(server_url, username, password)

        configdata = client.show_config()
        botname = configdata['bot_name']

        dailydata = client.daily(days=5)
        for day in dailydata['data']:
            #logger.info(f"Day: {day}")
            daydate = day['date']

            profitdata = {
                "profit": day['abs_profit'],
                "percentage": day['rel_profit'] * 100.0,
                "balance": day['starting_balance'],
                "trade-count": day['trade_count']
            }
        
            if daydate not in datalist:
                datalist[daydate] = {}

            datalist[daydate][botname] = profitdata

    #logger.info(f"Datalist: {datalist}")

    for key, day in datalist.items():
        totalprofit = 0.0
        totaltrades = 0
        totalbalance = 0.0

        #logger.info(day)

        for bot in day.values():
            #logger.info(bot)
            totalprofit += bot['profit']
            totaltrades += bot['trade-count']
            totalbalance += bot['balance']
        
        totalpercentage = (totalprofit / totalbalance) * 100.0

        message = f"Profit of {key}: {totalprofit:.2f} ({totaltrades}) - {totalpercentage:.2f}"
        for botname, botdata in day.items():
            message += f"\n- {botname}: {botdata['profit']:.2f} ({botdata['trade-count']}) - {botdata['percentage']:.2f}"

        logger.info(message, notify=True)

        # Send notification for each day, so the user can see it as seperate messages
        notification.send_notification()

    if not wait_time_interval(logger, notification, timeint, False):
        break
