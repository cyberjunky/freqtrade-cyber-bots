"""Cyberjunky's Freqtrade bot helpers."""
import time
import requests
from bs4 import BeautifulSoup

def wait_time_interval(logger, notification, time_interval, notify=True):
    """Wait for time interval."""

    if time_interval > 0:
        localtime = time.time()
        nexttime = localtime + int(time_interval)
        timeresult = time.strftime("%H:%M:%S", time.localtime(nexttime))
        logger.info(
            "Next update in %s Seconds at %s" % (time_interval, timeresult), notify
        )
        notification.send_notification()
        time.sleep(time_interval)
        return True

    notification.send_notification()
    time.sleep(2)

    return False


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


def format_pair(logger, pair):
    """Create crypto pair."""

    base = pair.split("_")[0]
    coin = pair.split("_")[1]
    # Construct pair based on stake_currency
    pair = f"{coin}/{base}"

    logger.debug("New pair constructed: %s" % pair)

    return pair


def get_botassist_data(logger, botassistlist, start_number, limit):
    """Get the top pairs from 3c-tools bot-assist explorer."""

    url = "https://www.3c-tools.com/markets/bot-assist-explorer"
    parms = {"list": botassistlist}

    pairs = list()
    try:
        result = requests.get(url, params=parms)
        result.raise_for_status()
        soup = BeautifulSoup(result.text, features="html.parser")
        data = soup.find("table", class_="table table-striped table-sm")
        tablerows = data.find_all("tr")

        for row in tablerows:
            rowcolums = row.find_all("td")
            if len(rowcolums) > 0:
                rank = int(rowcolums[0].text)
                if rank < start_number:
                    continue

                pairdata = {}
                pairdata["pair"] = rowcolums[1].text
                pairdata["volume"] = float(rowcolums[len(rowcolums) - 1].text.replace(" BTC", "").replace(",", ""))

                logger.debug(f"Rank {rank}: {pairdata}")
                pairs.append(pairdata)

                if rank == limit:
                    break

    except requests.exceptions.HTTPError as err:
        logger.error("Fetching 3c-tools bot-assist data failed with error: %s" % err)
        if result.status_code == 500:
            logger.error(f"Check if the list setting '{botassistlist}' is correct")

        return pairs

    logger.info("Fetched 3c-tools bot-assist data OK (%s pairs)" % (len(pairs)))

    return pairs
