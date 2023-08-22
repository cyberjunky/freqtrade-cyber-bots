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

from indicators.supertrend import supertrend

from dca_strategy import DCAStrategy
class BaseSupertrendStrategy(DCAStrategy):
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

    minimal_roi = {
        "0": 0.0015
    }
  
    # Number of candles the strategy requires before producing valid signals
    startup_candle_count = 50

    # Supertrend configuration.
    supertrend_length = 0
    supertrend_multiplier = 0
    supertrend_source = ""
    supertrend_change_atr = False

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
        column_postfix = f"_{self.supertrend_length}_{self.supertrend_multiplier}"
        sti = supertrend(dataframe['open'], dataframe['high'], dataframe['low'], dataframe['close'], self.supertrend_length, self.supertrend_multiplier, self.supertrend_source, self.supertrend_change_atr)
        dataframe['trend'] = sti[f'SUPERT{column_postfix}']
        dataframe['direction'] = sti[f'SUPERTd{column_postfix}']
        dataframe['long'] = sti[f'SUPERTl{column_postfix}']
        dataframe['short'] = sti[f'SUPERTs{column_postfix}']

        # Inspect the last 5 rows
        #if self.logger:
        #    self.logger.debug(
        #        f"populate_indicators:\n{dataframe.tail()}"
        #    )

        return dataframe