#!/usr/bin/env python3
"""Cyberjunky's 3Commas bot helpers."""
import argparse
import configparser
import json
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

    cfgbotconfig = list()
    cfgbotconfig.append({
        "ip": "127.0.0.1",
        "port": "8080",
        "username": "user",
        "password": "pass",
    })
    cfgbotconfig.append({
        "ip": "127.0.0.1",
        "port": "8081",
        "username": "user",
        "password": "pass",
    })

    cfg["settings"] = {
        "timezone": "Europe/Amsterdam",
        "timeinterval": 3600,
        "debug": False,
        "logrotate": 7,
        "notifications": False,
        "notify-urls": ["notify-url1"],
        "bot-list": json.dumps(cfgbotconfig),
    }

    with open(f"{datadir}/{program}.ini", "w") as cfgfile:
        cfg.write(cfgfile)

    return None


def upgrade_config(cfg):
    """Upgrade config file if needed."""

    return cfg


def process_data(bot_name, data, storage_list):
    """
    """

    for timeperiod in data['data']:
        timeperioddate = timeperiod['date']

        profitdata = {
            "profit": timeperiod['abs_profit'],
            "percentage": timeperiod['rel_profit'] * 100.0,
            "balance": timeperiod['starting_balance'],
            "trade-count": timeperiod['trade_count']
        }

        if timeperioddate not in storage_list:
            storage_list[timeperioddate] = {}

        storage_list[timeperioddate][bot_name] = profitdata


def summarize_and_log(periodtype, storage_list):
    """
    """

    for key, timeperiod in storage_list.items():
        totalprofit = 0.0
        totaltrades = 0
        totalbalance = 0.0

        for bot in timeperiod.values():
            totalprofit += bot['profit']
            totaltrades += bot['trade-count']
            totalbalance += bot['balance']
        
        totalpercentage = (totalprofit / totalbalance) * 100.0

        message = f"{periodtype} profit of {key}: {totalprofit:.2f} (# {totaltrades}) - {totalpercentage:.2f}%"
        for botname, botdata in timeperiod.items():
            message += f"\n- {botname}: {botdata['profit']:.2f} (# {botdata['trade-count']}) - {botdata['percentage']:.2f}%"

        logger.info(message, notify=True)

        # Send notification for each period, so the user can see it as seperate messages
        notification.send_notification()


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

    botlist = json.loads(config.get("settings", "bot-list"))

    dailydatalist={}
    weeklydatalist={}
    monthlydatalist={}

    for bot in botlist:
        server_url = f"http://{bot['ip']}:{bot['port']}"
        client = FtRestClient(server_url, bot['username'], bot['password'])

        configdata = client.show_config()
        if configdata is None:
            logger.warning(f"No data could be fetched from {server_url}...")
            continue

        botname = configdata['bot_name']

        dailydata = client.daily(days=2)
        process_data(botname, dailydata, dailydatalist)

        weeklydata = client.weekly(weeks=2)
        process_data(botname, weeklydata, weeklydatalist)

        monthlydata = client.monthly(months=2)
        process_data(botname, monthlydata, monthlydatalist)

    summarize_and_log('Daily', dailydatalist)
    summarize_and_log('Weekly', weeklydatalist)
    summarize_and_log('Monthly', monthlydatalist)

    if not wait_time_interval(logger, notification, timeint, False):
        break
