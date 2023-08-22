# pragma pylint: disable=missing-docstring, invalid-name, pointless-string-statement
# flake8: noqa: F401
# isort: skip_file
# --- Do not remove these libs ---
import numpy as np
import pandas as pd
from pandas import DataFrame
from datetime import datetime
from typing import Optional, Union

from freqtrade.strategy import (BooleanParameter, CategoricalParameter, DecimalParameter,
                                IntParameter, IStrategy, merge_informative_pair)

# --------------------------------
# Add your lib to import here
import talib.abstract as ta
import pandas_ta as pta
from technical import qtpylib

# Strategy lib imports
import os

# Strategy local search path for own modules
import sys
from pathlib import Path
sys.path.append(str(Path(__file__).parent))

# Strategy modules
import logging
from freqtrade.constants import Config

class BaseStrategy(IStrategy):
    """
    This is a strategy template to get you started.
    More information in https://www.freqtrade.io/en/latest/strategy-customization/

    You can:
        :return: a Dataframe with all mandatory indicators for the strategies
    - Rename the class name (Do not forget to update class_name)
    - Add any methods you want to build your strategy
    - Add any lib you need to build your strategy

    You must keep:
    - the lib in the section "Do not remove these libs"
    - the methods: populate_indicators, populate_entry_trend, populate_exit_trend
    You should keep:
    - timeframe, minimal_roi, stoploss, trailing_*
    """

    # Logger used for specific logging for this strategy
    logger = None

    # Strategy interface version - allow new iterations of the strategy interface.
    # Check the documentation or the Sample strategy to get the latest version.
    INTERFACE_VERSION = 3

    STRATEGY_VERSION = "1.0.1"

    # Optimal timeframe for the strategy.
    timeframe = '1h'

    # Can this strategy go short?
    can_short = False

    # Minimal ROI designed for the strategy.
    # This attribute will be overridden if the config file contains "minimal_roi".
    # Exit trade at profit of 1%
    minimal_roi = {
        "0": 0.01
    }

    # Optimal stoploss designed for the strategy.
    # This attribute will be overridden if the config file contains "stoploss".
    # Set to -99% to actually disable the stoploss
    stoploss = -0.99

    # Stoploss configuration
    use_custom_stoploss = True
    stoploss_configuration = {}

    # Trailing stoploss
    trailing_stop = False

    # Run "populate_indicators()" only for new candle.
    process_only_new_candles = True

    # These values can be overridden in the config.
    use_exit_signal = False
    exit_profit_only = False
    ignore_roi_if_entry_signal = False

    # Number of candles the strategy requires before producing valid signals
    startup_candle_count = 1

    # Leverage configuration
    leverage_configuration = {}


    def __init__(self, config: Config) -> None:
        """
        Called upon construction of this class. Validate data and initialize
        all attributes,
        """

        # Initialize logger
        self.logger = logging.getLogger("freqtrade.strategy")

        # Make sure the contents of the Leverage configuration is correct
        for k, v in self.leverage_configuration.items():
            self.leverage_configuration[k] = float(v)

        # Make sure the contents of the Stoploss configuration is correct
        for k, v in self.stoploss_configuration.items():
            self.stoploss_configuration[k] = float(v)
        
        # Update minimum ROI table keeping leverage into account
        # TODO: improve later on with custom exit with profit and leverage calculation for each pair
        leverage = min(self.leverage_configuration.values()) if len(self.leverage_configuration) > 0 else 1.0

        self.logger.info(
            f"Update minimal ROI keeping leverage of {leverage} into account."
        )

        for k, v in self.minimal_roi.items():
            self.minimal_roi[k] = round(v * leverage, 4)

        # Call to super
        super().__init__(config)


    def bot_start(self, **kwargs) -> None:
        """
        Called only once after bot instantiation.
        :param **kwargs: Ensure to keep this here so updates to this won't break your strategy.
        """
    
        # Call to super first
        super().bot_start()

        self.logger.info(f"Running with stoploss configuration: '{self.stoploss_configuration}'")
        self.logger.info(f"Running with leverage configuration: '{self.leverage_configuration}'")


    def populate_indicators(self, dataframe: DataFrame, metadata: dict) -> DataFrame:
        """
        Adds several different TA indicators to the given DataFrame

        Performance Note: For the best performance be frugal on the number of indicators
        you are using. Let uncomment only the indicator you are using in your strategies
        or your hyperopt configuration, otherwise you will waste your memory and CPU usage.
        :param dataframe: Dataframe with data from the exchange
        :param metadata: Additional information, like the currently traded pair
        :return: a Dataframe with all mandatory indicators for the strategies
        """

        return dataframe


    def populate_entry_trend(self, dataframe: DataFrame, metadata: dict) -> DataFrame:
        """
        Based on TA indicators, populates the entry signal for the given dataframe
        :param dataframe: DataFrame
        :param metadata: Additional information, like the currently traded pair
        :return: DataFrame with entry columns populated
        """

        return dataframe


    def populate_exit_trend(self, dataframe: DataFrame, metadata: dict) -> DataFrame:
        """
        Based on TA indicators, populates the exit signal for the given dataframe
        :param dataframe: DataFrame
        :param metadata: Additional information, like the currently traded pair
        :return: DataFrame with exit columns populated
        """

        return dataframe


    def leverage(self, pair: str, current_time: datetime, current_rate: float,
                 proposed_leverage: float, max_leverage: float, entry_tag: Optional[str], side: str,
                 **kwargs) -> float:
        """
        Customize leverage for each new trade. This method is only called in futures mode.

        :param pair: Pair that's currently analyzed
        :param current_time: datetime object, containing the current datetime
        :param current_rate: Rate, calculated based on pricing settings in exit_pricing.
        :param proposed_leverage: A leverage proposed by the bot.
        :param max_leverage: Max leverage allowed on this pair
        :param entry_tag: Optional entry_tag (buy_tag) if provided with the buy signal.
        :param side: 'long' or 'short' - indicating the direction of the proposed trade
        :return: A leverage amount, which is between 1.0 and max_leverage.
        """

        pairkey = f"{pair}_{side}"
        if pairkey in self.leverage_configuration:
            return self.leverage_configuration[pairkey]
        else:
            return 1.0


    def custom_stoploss(self, pair: str, trade: 'Trade', current_time: datetime,
                        current_rate: float, current_profit: float, **kwargs) -> float:
        """
        Custom stoploss logic, returning the new distance relative to current_rate (as ratio).
        e.g. returning -0.05 would create a stoploss 5% below current_rate.
        The custom stoploss can never be below self.stoploss, which serves as a hard maximum loss.

        For full documentation please go to https://www.freqtrade.io/en/latest/strategy-advanced/

        When not implemented by a strategy, returns the initial stoploss value
        Only called when use_custom_stoploss is set to True.

        :param pair: Pair that's currently analyzed
        :param trade: trade object.
        :param current_time: datetime object, containing the current datetime
        :param current_rate: Rate, calculated based on pricing settings in exit_pricing.
        :param current_profit: Current profit (as ratio), calculated based on current_rate.
        :param **kwargs: Ensure to keep this here so updates to this won't break your strategy.
        :return float: New stoploss value, relative to the current rate
        """

        sl = self.stoploss

        pairkey = f"{pair}_{trade.trade_direction}"
        if pairkey in self.stoploss_configuration:
            sl = self.stoploss_configuration[pairkey] * self.leverage_configuration[pairkey]

        return sl
