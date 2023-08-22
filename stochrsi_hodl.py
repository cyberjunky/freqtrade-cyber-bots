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

from freqtrade.constants import Config

from base_strategy import BaseStrategy
class StochRSI_Hodl(BaseStrategy):
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
    timeframe = '1d'

    minimal_roi = {
        "0": 10.00
    }

    # Max number of safety orders (-1 means disabled)
    max_entry_position_adjustment = 4

    # Enable position adjustment
    position_adjustment_enable = True

    @property
    def plot_config(self):
        return {
            # Main plot indicators (Moving averages, ...)
            'main_plot': {
                'direction': {'color': 'black'},
                'trend': {'color': 'white'},
                'long': {'color': 'green'},
                'short': {'color': 'red'}
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

        # Call to super
        super().__init__(config)


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

        dataframe = super().populate_indicators(dataframe, metadata)
        
        # STOCH
        length = 14
        rsi_length = 14
        k = 3
        d = 3

        stoch = pta.stochrsi(dataframe['close'], length, rsi_length, k, d)
        dataframe['stochrsi_k'] = stoch[f"STOCHRSIk_{length}_{rsi_length}_{k}_{d}"]
        dataframe['stochrsi_d'] = stoch[f"STOCHRSId_{length}_{rsi_length}_{k}_{d}"]

        # Inspect the last 5 rows
        #if self.logger:
        #    self.logger.debug(
        #        f"populate_indicators:\n{dataframe.tail()}"
        #    )

        return dataframe


    def populate_entry_trend(self, dataframe: DataFrame, metadata: dict) -> DataFrame:
        """
        Based on TA indicators, populates the entry signal for the given dataframe
        :param dataframe: DataFrame
        :param metadata: Additional information, like the currently traded pair
        :return: DataFrame with entry columns populated
        """

        dataframe = super().populate_entry_trend(dataframe, metadata)

        dataframe.loc[
            (
                (qtpylib.crossed_above(dataframe['stochrsi_k'], 20)) &
                (dataframe['volume'] > 0)  # Make sure Volume is not 0
            ),
            'enter_long'] = 1

        # Inspect the last 5 rows
        #if self.logger:
        #    self.logger.debug(
        #        f"populate_entry_trend:\n{dataframe.tail()}"
        #    )

        return dataframe


    def custom_exit(self, pair: str, trade: 'Trade', current_time: 'datetime', current_rate: float,
                    current_profit: float, **kwargs):
        """
        """

        dataframe, _ = self.dp.get_analyzed_dataframe(pair, self.timeframe)

        # Do not exit when the trade is in loss
        if current_profit <= 0.0:
            return False
        
        # Do not exit when the trade didn't cross
        if not qtpylib.crossed_above(dataframe['stochrsi_k'], 80):
            return False

        # Trade is in profit and crossed the value, so exit
        return True


def adjust_trade_position(self, trade: 'Trade', current_time: datetime,
                              current_rate: float, current_profit: float,
                              min_stake: Optional[float], max_stake: float,
                              current_entry_rate: float, current_exit_rate: float,
                              current_entry_profit: float, current_exit_profit: float,
                              **kwargs) -> Optional[float]:
        """
        Custom trade adjustment logic, returning the stake amount that a trade should be
        increased or decreased.
        This means extra buy or sell orders with additional fees.
        Only called when `position_adjustment_enable` is set to True.

        For full documentation please go to https://www.freqtrade.io/en/latest/strategy-advanced/

        When not implemented by a strategy, returns None

        :param trade: trade object.
        :param current_time: datetime object, containing the current datetime
        :param current_rate: Current buy rate.
        :param current_profit: Current profit (as ratio), calculated based on current_rate.
        :param min_stake: Minimal stake size allowed by exchange (for both entries and exits)
        :param max_stake: Maximum stake allowed (either through balance, or by exchange limits).
        :param current_entry_rate: Current rate using entry pricing.
        :param current_exit_rate: Current rate using exit pricing.
        :param current_entry_profit: Current profit using entry pricing.
        :param current_exit_profit: Current profit using exit pricing.
        :param **kwargs: Ensure to keep this here so updates to this won't break your strategy.
        :return float: Stake amount to adjust your trade,
                       Positive values to increase position, Negative values to decrease position.
                       Return None for no action.
        """

        # Obtain pair dataframe (just to show how to access it)
        dataframe, _ = self.dp.get_analyzed_dataframe(trade.pair, self.timeframe)

        # Only buy extra when we are below 20. Freqtrade should limit the amount of buys to 1 per candle
        # avoiding an extra buy in the same candle as where the buy is placed
        if dataframe['stochrsi_k'] >= 20:
            return None

        filled_entries = trade.select_filled_orders(trade.entry_side)

        try:
            # This returns first order stake size, which we want to increase our position with
            stake_amount = filled_entries[0].stake_amount

            return stake_amount
        except Exception as exception:
            return None

        return None