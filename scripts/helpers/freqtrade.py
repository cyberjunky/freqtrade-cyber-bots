"""Cyberjunky's Freqtrade bot helpers."""

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
