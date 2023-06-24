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

from base_strategy import BaseStrategy
class DCAStrategy(BaseStrategy):
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

    # Max number of safety orders (-1 means disabled)
    max_entry_position_adjustment = -1

    # Enable position adjustment
    position_adjustment_enable = True

    # Corresponds with the parameters as used on 3Commas
    initial_so_amount = 10.0 # First Safety Order in stake amount
    price_deviation = 1.0
    volume_scale = 1.0
    step_scale = 1.0

    direction: str = "long"

    can_short = False

    def bot_start(self, **kwargs) -> None:
        """
        Called only once after bot instantiation.
        :param **kwargs: Ensure to keep this here so updates to this won't break your strategy.
        """

        # Call to BaseStrategy first
        super().bot_start()

        if self.config['runmode'].value in ('live', 'dry_run'):
            self.logger.info("Safety Order overview for this strategy:")

            self.logger.info(
                f"BO | Deviation 0.0% | Order volume {self.stake_amount} ({self.stake_amount})"
            )
            so_count = 1
            while(so_count <= self.max_entry_position_adjustment):
                so_volume = self.calculate_dca_volume(so_count)
                so_total_volume = self.calculate_dca_volume_total(so_count)
                so_step_deviation = self.calculate_dca_step_deviation(so_count)
                so_total_deviation = self.calculate_dca_deviation_total(so_count)
                self.logger.info(
                    f"SO {so_count} | Deviation {so_step_deviation}% ({so_total_deviation}%) | Order volume {so_volume} ({so_total_volume})"
                )

                so_count += 1

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
        
        return super().populate_indicators(dataframe, metadata)

    def populate_entry_trend(self, dataframe: DataFrame, metadata: dict) -> DataFrame:
        """
        Based on TA indicators, populates the entry signal for the given dataframe
        :param dataframe: DataFrame
        :param metadata: Additional information, like the currently traded pair
        :return: DataFrame with entry columns populated
        """

        return super().populate_entry_trend(dataframe, metadata)

    def populate_exit_trend(self, dataframe: DataFrame, metadata: dict) -> DataFrame:
        """
        Based on TA indicators, populates the exit signal for the given dataframe
        :param dataframe: DataFrame
        :param metadata: Additional information, like the currently traded pair
        :return: DataFrame with exit columns populated
        """

        return super().populate_exit_trend(dataframe, metadata)

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

        # Return when no extra orders are allowed
        if self.max_entry_position_adjustment == -1:
            return None

        # Return when all Safety Orders are executed
        count_of_entries = trade.nr_of_successful_entries
        count_of_safety_orders = count_of_entries - 1 # Subtract Base Order
        if count_of_safety_orders >= self.max_entry_position_adjustment:
            self.logger.debug(
                f"{trade.pair}: reached max number ({self.max_entry_position_adjustment}) of Safety Orders."
            )
            return None

        # Return when the current profit hasn't reached the next Safety Order
        next_prive_deviation = self.calculate_dca_deviation_total(count_of_entries)
        if (self.direction == "long" and (current_entry_profit * 100.0) > next_prive_deviation) or (self.direction == "short" and (current_entry_profit * 100.0) < next_prive_deviation):
            return None      

        try:
            volume = self.calculate_dca_volume(count_of_entries)

            self.dp.send_msg(
                f"{trade.pair}: current profit {current_entry_profit * 100.0}% reached next SO {count_of_entries} at {next_prive_deviation} "
                f"and calculated volume of {volume} for order."
            )

            return volume if self.direction == "long" else -volume
        except Exception as exception:
            return None

        return None


    def calculate_dca_volume(self, safety_order) -> float:
        """
        DCA implementation; calculate the required volume (in stake currency) to buy for the Safety Order.

        This function checks if the provided safety order number is below or equal to the max number of 
        allowed trades as specifed with the `max_entry_position_adjustment`.

        :param safety_order: Safety order number.
        :return float: Volume in stake currency,
                       Return 0.0 for safety order above the `max_entry_position_adjustment`.
        """

        if 0 < safety_order <= self.max_entry_position_adjustment:
            return self.initial_so_amount * (pow(self.volume_scale, (safety_order - 1)))
        else:
            return 0.0

    def calculate_dca_volume_total(self, safety_order) -> float:
        """
        DCA implementation; calculate the total volume (in stake currency) that has been bought
         including the specified Safety Order.

        This function checks if the provided safety order number is below the max number of 
        allowed trades as specifed with the `max_entry_position_adjustment`.

        :param safety_order: Safety order number.
        :return float: Totale volume in stake curreny,
                       Return 0.0 for safety order above the `max_entry_position_adjustment`.
        """

        total_volume = self.stake_amount if self.direction == "long" else 0.0

        if 0 < safety_order <= self.max_entry_position_adjustment:
            so_count = 1
            while (so_count <= safety_order):
                total_volume += self.calculate_dca_volume(so_count)

                so_count += 1

        return total_volume

    def calculate_dca_step_deviation(self, safety_order) -> float:
        """
        DCA implementation; calculate the price deviation for a certain Safety Order, from the
        previous Safety Order.

        This function checks if the provided safety order number is below the max number of 
        allowed trades as specifed with the `max_entry_position_adjustment`.

        :param safety_order: Safety order number.
        :return float: Percentage,
                       Return 0.0 for safety order above the `max_entry_position_adjustment`.
        """

        if 0 < safety_order <= self.max_entry_position_adjustment:
            deviation = (self.price_deviation * (pow(self.step_scale, (safety_order - 1))))
            return -deviation if self.direction == "long" else deviation
        else:
            return 0.0

    def calculate_dca_deviation_total(self, safety_order) -> float:
        """
        DCA implementation; calculate the total price deviation from the entry price including the
        specified Safety Order.

        This function checks if the provided safety order number is below the max number of 
        allowed trades as specifed with the `max_entry_position_adjustment`.

        :param safety_order: Safety order number.
        :return float: Percentage,
                       Return 0.0 for safety order above the `max_entry_position_adjustment`.
        """

        total_deviation = 0.0

        if 0 < safety_order <= self.max_entry_position_adjustment:
            so_count = 1
            while (so_count <= safety_order):
                total_deviation += self.calculate_dca_step_deviation(so_count)

                so_count += 1

        return total_deviation
