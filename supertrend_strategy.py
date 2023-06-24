import sys
from pathlib import Path
sys.path.append(str(Path(__file__).parent))

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
from functools import reduce

from indicators.supertrend import supertrend

from base_strategy import BaseStrategy
class Supertrend_Strategy(BaseStrategy):
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

    # Optimal timeframe for the strategy.
    timeframe = '30m'

    # Minimal ROI designed for the strategy.
    # This attribute will be overridden if the config file contains "minimal_roi".
    minimal_roi = {
        "0": 0.03
    }
    
    # Number of candles the strategy requires before producing valid signals
    startup_candle_count = 15

    # Run "populate_indicators()" only for new candle.
    process_only_new_candles = True

    use_exit_signal = False
    ignore_roi_if_entry_signal = True

    # Stoploss
    stoploss = -0.02
    trailing_stop = True
    trailing_stop_positive = 0.001
    trailing_stop_positive_offset = 0.0025
    trailing_only_offset_is_reached = True
    use_custom_stoploss = False

    # Supertrend configuration
    st_length: int = 5
    st_multiplier: float = 1.0
    st_source: str = 'open'

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
                #"MFI & RSI": {
                    #'mfi14': {'color': 'purple'},
                    #'rsi14': {'color': 'black'},
                #}
            }
        }

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
        
        # Supertrend
        column_postfix = f"_{self.st_length}_{self.st_multiplier}"
        sti = supertrend(dataframe['open'], dataframe['high'], dataframe['low'], dataframe['close'], self.st_length, self.st_multiplier, self.st_source)
        dataframe['trend'] = sti[f'SUPERT{column_postfix}']
        dataframe['direction'] = sti[f'SUPERTd{column_postfix}']
        dataframe['long'] = sti[f'SUPERTl{column_postfix}']
        dataframe['short'] = sti[f'SUPERTs{column_postfix}']

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
                pd.notnull(dataframe['long']) &
                (dataframe['direction'] > 0) &
                (dataframe['direction'].shift(1) < 0) &
                (dataframe['volume'] > 0)  # Make sure Volume is not 0
            ),
            'enter_long'] = 1

        return dataframe

    def populate_exit_trend(self, dataframe: DataFrame, metadata: dict) -> DataFrame:
        """
        Based on TA indicators, populates the exit signal for the given dataframe
        :param dataframe: DataFrame
        :param metadata: Additional information, like the currently traded pair
        :return: DataFrame with exit columns populated
        """

        dataframe = super().populate_exit_trend(dataframe, metadata)

        dataframe.loc[
            (
                pd.notnull(dataframe['short'])
            ),
            'exit_long'] = 1

        return dataframe