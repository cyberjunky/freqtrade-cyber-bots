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

from freqtrade.constants import Config

from base_supertrend_strategy import BaseSupertrendStrategy
class SupertrendETH(BaseSupertrendStrategy):
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

    # Strategy interface version - allow new iterations of the strategy interface.
    # Check the documentation or the Sample strategy to get the latest version.
    INTERFACE_VERSION = 3

    STRATEGY_VERSION = "1.0.0"

    # Optimal timeframe for the strategy.
    timeframe = '3m'

    minimal_roi = {
        "0": 0.0012
    }
  
    # Number of candles the strategy requires before producing valid signals
    startup_candle_count = 50


    @property
    def plot_config(self):
        return {
            # Main plot indicators (Moving averages, ...)
            'main_plot': {
                'direction': {'color': 'black'},
                'trend': {'color': 'white'},
                'long': {'color': 'green'},
                'short': {'color': 'brown'}
            },
            'subplots': {
                # Subplots - each dict defines one additional plot
            }
        }


    def __init__(self, config: Config) -> None:
        """
        Called upon construction of this class. Validate data and initialize
        all attributes,
        """

        # Leverage configuration for this strategy
        self.leverage_configuration["ETH/USDT:USDT_long"] = 10.0
        self.leverage_configuration["ETH/USDT:USDT_short"] = 10.0

        # Stoploss configuration for this strategy
        self.stoploss_configuration["ETH/USDT:USDT_long"] = 4.0
        self.stoploss_configuration["ETH/USDT:USDT_short"] = 4.0

        # Setup Safety Order configuration for this strategy
        self.safety_order_configuration["ETH/USDT:USDT_long"] = {}
        self.safety_order_configuration["ETH/USDT:USDT_long"]["initial_so_amount"] = config["stake_amount"]
        self.safety_order_configuration["ETH/USDT:USDT_long"]["price_deviation"] = 1.0
        self.safety_order_configuration["ETH/USDT:USDT_long"]["volume_scale"] = 2.0
        self.safety_order_configuration["ETH/USDT:USDT_long"]["step_scale"] = 1.0
        self.safety_order_configuration["ETH/USDT:USDT_long"]["max_so"] = 5

        self.safety_order_configuration["ETH/USDT:USDT_short"] = {}
        self.safety_order_configuration["ETH/USDT:USDT_short"]["initial_so_amount"] = config["stake_amount"]
        self.safety_order_configuration["ETH/USDT:USDT_short"]["price_deviation"] = 1.0
        self.safety_order_configuration["ETH/USDT:USDT_short"]["volume_scale"] = 2.0
        self.safety_order_configuration["ETH/USDT:USDT_short"]["step_scale"] = 1.0
        self.safety_order_configuration["ETH/USDT:USDT_short"]["max_so"] = 5

        # Trailing Safety Order configuration for this strategy
        self.trailing_safety_order_configuration["default"][0]["start_percentage"] = 0.15
        self.trailing_safety_order_configuration["default"][0]["factor"] = 0.60
        self.trailing_safety_order_configuration["default"][1] = {}
        self.trailing_safety_order_configuration["default"][1]["start_percentage"] = 0.35
        self.trailing_safety_order_configuration["default"][1]["factor"] = 0.75
        self.trailing_safety_order_configuration["default"][2] = {}
        self.trailing_safety_order_configuration["default"][2]["start_percentage"] = 0.50
        self.trailing_safety_order_configuration["default"][2]["factor"] = 0.85

        # Supertrend configuration
        self.supertrend_length = 24
        self.supertrend_multiplier = 1.5
        self.supertrend_source = "open"
        self.supertrend_change_atr = True

        # Call to super
        super().__init__(config)


    def populate_entry_trend(self, dataframe: DataFrame, metadata: dict) -> DataFrame:
        """
        Based on TA indicators, populates the entry signal for the given dataframe
        :param dataframe: DataFrame
        :param metadata: Additional information, like the currently traded pair
        :return: DataFrame with entry columns populated
        """

        dataframe = super().populate_entry_trend(dataframe, metadata)

        if "long" in self.trading_direction:
            dataframe.loc[
                (
                    pd.notnull(dataframe['long']) &
                    (dataframe['direction'] > 0) &
                    (dataframe['direction'].shift(1) < 0) &
                    (dataframe['volume'] > 0)  # Make sure Volume is not 0
                ),
                'enter_long'] = 1
        else:
            dataframe.loc[:, "enter_long"] = 0

        if "short" in self.trading_direction:
            dataframe.loc[
                (
                    pd.notnull(dataframe['short']) &
                    (dataframe['direction'] < 0) &
                    (dataframe['direction'].shift(1) > 0) &
                    (dataframe['volume'] > 0)  # Make sure Volume is not 0
                ),
                'enter_short'] = 1
        else:
            dataframe.loc[:, "enter_short"] = 0

        # Inspect the last 5 rows
        #if self.logger:
        #    self.logger.debug(
        #        f"populate_entry_trend:\n{dataframe.tail()}"
        #    )

        return dataframe