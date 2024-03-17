# pragma pylint: disable=missing-docstring, invalid-name, pointless-string-statement
# flake8: noqa: F401
# isort: skip_file
# --- Do not remove these libs ---
from math import fabs
import numpy as np
import pandas as pd
from pandas import DataFrame
from datetime import datetime
from typing import Optional, Union

# --------------------------------
# Add your lib to import here
from freqtrade.constants import Config
from freqtrade.persistence import Trade

from .base_strategy import BaseStrategy
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

    STRATEGY_VERSION = "1.4.0"

    # Max number of safety orders (-1 means disabled)
    max_entry_position_adjustment = -1

    # Enable position adjustment
    position_adjustment_enable = False

    # Short or not
    can_short = False

    # Trading mode for this strategy (long / short / long_short)
    trading_direction = "long"

    # Safety Order configuration. 
    # The 'default' can be used when there is no specific entry for the pair and direction in the list
    safety_order_configuration = {}
    #safety_order_configuration["default"] = {}
    #safety_order_configuration["default"]["initial_so_amount"] = 10.0 # First Safety Order in stake amount
    #safety_order_configuration["default"]["price_deviation"] = 1.0
    #safety_order_configuration["default"]["volume_scale"] = 1.0
    #safety_order_configuration["default"]["step_scale"] = 1.0
    #safety_order_configuration["default"]["max_so"] = 1

    # Trailing Safety Order configuration. 
    # First try to use the configuration for the pair and direction, then try 'default'. If none of them are 
    # available, no trailing will be used for placing Safety Order(s).
    trailing_safety_order_configuration = {}
    trailing_safety_order_configuration["default"] = {}
    trailing_safety_order_configuration["default"][0] = {}
    trailing_safety_order_configuration["default"][0]["start_percentage"] = 0.25
    trailing_safety_order_configuration["default"][0]["factor"] = 0.50

    # Settings controlling when to send notification about the trailing safety orders
    notify_trailing_start = True
    notify_trailing_update = True
    notify_trailing_reset = True


    def version(self) -> Optional[str]:
        """
        Returns version of the strategy.
        """

        return self.STRATEGY_VERSION


    def __init__(self, config: Config) -> None:
        """
        Called upon construction of this class. Validate data and initialize
        all attributes,
        """

        # Try to get the trading direction from the config and validate when present
        if "trading_direction" in config:
            if config["trading_direction"] in ("long", "short", "long_short"):
                self.trading_direction = config["trading_direction"]

        # Try to get the trailing notify options from the config and validate when present
        if "notify_trailing_start" in config:
            if isinstance(config["notify_trailing_start"], bool):
                self.notify_trailing_start = config["notify_trailing_start"]
        if "notify_trailing_update" in config:
            if isinstance(config["notify_trailing_update"], bool):
                self.notify_trailing_update = config["notify_trailing_update"]
        if "notify_trailing_reset" in config:
            if isinstance(config["notify_trailing_reset"], bool):
                self.notify_trailing_reset = config["notify_trailing_reset"]

        # First make sure the contents of the (Trailing) Safety Order configuration is correct
        for pairvalue in self.safety_order_configuration.values():
            for k, v in pairvalue.items():
                if k in ("max_so"):
                    pairvalue[k] = int(v)
                else:
                    pairvalue[k] = float(v)

        for pairvalue in self.trailing_safety_order_configuration.values():
            for l in pairvalue.values():
                for k, v in l.items():
                    l[k] = float(v)

        # Process Safety Order configuration...
        for pairkey in self.safety_order_configuration:
            if pairkey != "default":
                # Determine the trading direction, and skip it when the trading direction for this bot does not allow it
                _, direction = pairkey.split("_")
                if direction not in self.trading_direction:
                    continue

            max_so = self.safety_order_configuration[pairkey]["max_so"]
            
            # Make sure the max of entry adjustments is set to the highest number of max Safety Orders
            if self.max_entry_position_adjustment < max_so:
                self.max_entry_position_adjustment = max_so

            # Disabled by default, so enable when there are additional Safety Orders configured
            if self.max_entry_position_adjustment > 0:
                self.position_adjustment_enable = True

        # Call to super
        super().__init__(config)


    def bot_start(self, **kwargs) -> None:
        """
        Called only once after bot instantiation.
        :param **kwargs: Ensure to keep this here so updates to this won't break your strategy.
        """
    
        # Call to super first
        super().bot_start()

        self.logger.info(f"Running with trading direction(s): '{self.trading_direction}'")

        # Display Safety Order configuration...
        for pairkey in self.safety_order_configuration:
            pair = pairkey
            direction = self.trading_direction

            if pairkey != "default":
                pair, direction = pairkey.split("_")

            self.logger.info(f"Safety Order overview for '{pair}' in direction '{direction}':")

            self.logger.info(
                f"BO | Deviation 0.0% | Order volume {self.stake_amount} ({self.stake_amount})"
            )
            so_count = 1
            max_so = self.safety_order_configuration[pairkey]["max_so"]
            while(so_count <= max_so):
                so_volume = self.calculate_dca_volume(so_count, pairkey, max_so)
                so_total_volume = self.calculate_dca_volume_total(so_count, pairkey, max_so)
                so_step_deviation = self.calculate_dca_step_deviation(so_count, pairkey, max_so)
                so_total_deviation = self.calculate_dca_deviation_total(so_count, pairkey, max_so)
                self.logger.info(
                    f"SO {so_count} | Deviation {so_step_deviation}% ({so_total_deviation}%) | Order volume {so_volume} ({so_total_volume})"
                )

                so_count += 1

        # Create custom data required for DCA
        opentrades = Trade.get_trades_proxy(is_open=True)
        for opentrade in opentrades:
            custompairkey = self.get_custom_pairkey(opentrade)
            self.initialize_custom_data(custompairkey)


    def confirm_trade_entry(self, pair: str, order_type: str, amount: float, rate: float,
                            time_in_force: str, current_time: datetime, entry_tag: Optional[str],
                            side: str, **kwargs) -> bool:
        """
        Called right before placing a entry order.
        Timing for this function is critical, so avoid doing heavy computations or
        network requests in this method.

        For full documentation please go to https://www.freqtrade.io/en/latest/strategy-advanced/

        When not implemented by a strategy, returns True (always confirming).

        :param pair: Pair that's about to be bought/shorted.
        :param order_type: Order type (as configured in order_types). usually limit or market.
        :param amount: Amount in target (base) currency that's going to be traded.
        :param rate: Rate that's going to be used when using limit orders 
                     or current rate for market orders.
        :param time_in_force: Time in force. Defaults to GTC (Good-til-cancelled).
        :param current_time: datetime object, containing the current datetime
        :param entry_tag: Optional entry_tag (buy_tag) if provided with the buy signal.
        :param side: 'long' or 'short' - indicating the direction of the proposed trade
        :param **kwargs: Ensure to keep this here so updates to this won't break your strategy.
        :return bool: When True is returned, then the buy-order is placed on the exchange.
            False aborts the process
        """

        if side not in self.trading_direction:
            self.dp.send_msg(
                f"Trading direction '{side}' is currently disabled by bot configuration which has "
                f"'trading_direction' set to '{self.trading_direction}'. Not confirming this trade!"
            )
            return False  

        # When Safety Orders are enabled, check the configuration. The specific pair should be in the configuration, or
        # the default entry must be present. If this is not the case, don't open a new trade to avoid issues later on.
        pairkey = f"{pair}_{side}"
        if self.max_entry_position_adjustment > 0:
            if pairkey not in self.safety_order_configuration and "default" not in self.safety_order_configuration:
                self.dp.send_msg(
                    f"Safety Orders are enabled, but the specific '{pairkey}' or 'default' key is "
                    f"missing in the safety_order_configuration. Not confirming this trade!"
                )
                return False

        self.initialize_custom_data(pairkey)

        return True


    def confirm_trade_exit(self, pair: str, trade: 'Trade', order_type: str, amount: float,
                           rate: float, time_in_force: str, exit_reason: str,
                           current_time: datetime, **kwargs) -> bool:
        """
        Called right before placing a regular exit order.
        Timing for this function is critical, so avoid doing heavy computations or
        network requests in this method.

        For full documentation please go to https://www.freqtrade.io/en/latest/strategy-advanced/

        When not implemented by a strategy, returns True (always confirming).

        :param pair: Pair for trade that's about to be exited.
        :param trade: trade object.
        :param order_type: Order type (as configured in order_types). usually limit or market.
        :param amount: Amount in base currency.
        :param rate: Rate that's going to be used when using limit orders
                     or current rate for market orders.
        :param time_in_force: Time in force. Defaults to GTC (Good-til-cancelled).
        :param exit_reason: Exit reason.
            Can be any of ['roi', 'stop_loss', 'stoploss_on_exchange', 'trailing_stop_loss',
                           'exit_signal', 'force_exit', 'emergency_exit']
        :param current_time: datetime object, containing the current datetime
        :param **kwargs: Ensure to keep this here so updates to this won't break your strategy.
        :return bool: When True, then the exit-order is placed on the exchange.
            False aborts the process
        """

        confirmed = super().confirm_trade_exit(pair, trade, order_type, amount,
                                             rate, time_in_force, exit_reason,
                                             current_time)

        # Send notification about number of entries used to exit the trade
        filled_entries = trade.select_filled_orders(trade.entry_side)
        count_of_entries = len(filled_entries)

        self.dp.send_msg(
            f"{pair}: Exit after {count_of_entries} filled entry orders."
        )

        return confirmed


    def adjust_trade_position(self, trade: 'Trade', current_time: datetime,
                              current_rate: float, current_profit: float,
                              min_stake: Optional[float], max_stake: float,
                              current_entry_rate: float, current_exit_rate: float,
                              current_entry_profit: float, current_exit_profit: float,
                              **kwargs) -> Optional[float]:
        """
        Custom trade adjustment logic, returning the stake amount that a trade should be
        increased or decreased.
        This means extra entry or exit orders with additional fees.
        Only called when `position_adjustment_enable` is set to True.

        For full documentation please go to https://www.freqtrade.io/en/latest/strategy-advanced/

        When not implemented by a strategy, returns None

        :param trade: trade object.
        :param current_time: datetime object, containing the current datetime
        :param current_rate: Current entry rate (same as current_entry_profit)
        :param current_profit: Current profit (as ratio), calculated based on current_rate
                               (same as current_entry_profit).
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

        # Pair is locked, so return
        if self.is_pair_locked(trade.pair):
            return None

        # Trade is in profit, so return
        if current_profit >= 0.0:
            return None

        # Return when no extra orders are allowed
        if self.max_entry_position_adjustment == -1:
            return None

        # Create pairkey, or use 'default' 
        custompairkey = self.get_custom_pairkey(trade)
        configpairkey = custompairkey
        if not configpairkey in self.safety_order_configuration:
            configpairkey = "default"

        # Return when all Safety Orders are executed
        count_of_entries = trade.nr_of_successful_entries
        count_of_safety_orders = count_of_entries - 1 # Subtract Base Order
        if count_of_safety_orders >= self.safety_order_configuration[configpairkey]["max_so"]:
            if self.logger:
                self.logger.debug(
                    f"{trade.pair}: reached max number ({self.safety_order_configuration[pairkey]['max_so']}) of Safety Orders."
                )
            return None

        if len(self.custom_info[custompairkey]["open_safety_orders"]) > 0:
            pricedeviation = self.custom_info[custompairkey]["open_safety_orders"][0]["current_deviation"]
            totaldeviation = self.custom_info[custompairkey]["open_safety_orders"][0]["total_deviation"]
            volume = self.custom_info[custompairkey]["open_safety_orders"][0]["volume"]

            self.custom_info[custompairkey]["open_safety_orders"].pop(0)
            ordersleft = len(self.custom_info[custompairkey]["open_safety_orders"])

            self.dp.send_msg(
                f"{trade.pair}: current profit {pricedeviation:.4f}% reached next SO {count_of_entries} "
                f"at {totaldeviation:.4f}% "
                f"and calculated volume of {volume} ({ordersleft} orders left)."
            )

            if self.logger:
                self.logger.info(
                    f"{trade.pair}: about to fill next Safety Order and {ordersleft} orders left."
                )

            return volume #, f"Safety Order {count_of_entries}"

        # Calculate the next Safety Order, if not calculated before. Store the calculated value to save some CPU cycles
        if self.custom_info[custompairkey]["next_safety_order_profit_percentage"] == 0.0:
            self.custom_info[custompairkey]["next_safety_order_profit_percentage"] = self.calculate_dca_deviation_total(count_of_entries, configpairkey, self.safety_order_configuration[configpairkey]["max_so"])
            if self.logger:
                self.logger.info(
                    f"{trade.pair}: calculated next safety order on {self.custom_info[custompairkey]['next_safety_order_profit_percentage']:.4f}%."
                )

        # Return when the current (negative) profit hasn't reached the next Safety Order. 
        current_entry_profit_percentage = (current_entry_profit / trade.leverage) * 100.0
        next_safety_order_percentage = self.custom_info[custompairkey]["next_safety_order_profit_percentage"]
        if current_entry_profit_percentage > next_safety_order_percentage:
            return None

        tso_enabled, tso_start_percentage, tso_factor = self.get_trailing_config(current_entry_profit_percentage, next_safety_order_percentage, configpairkey)

        if tso_enabled:
            # Return when profit is above Safety Order percentage keeping start_percentage into account (and reset data when required)
            if current_entry_profit_percentage > (next_safety_order_percentage - tso_start_percentage):
                if self.custom_info[custompairkey]["last_profit_percentage"] != 0.0:
                    self.custom_info[custompairkey]["last_profit_percentage"] = float(0.0)
                    self.custom_info[custompairkey]["add_safety_order_on_profit_percentage"] = float(0.0)

                    if self.notify_trailing_reset:
                        self.dp.send_msg(
                            f"{trade.pair}: current profit {current_entry_profit_percentage:.4f}% went above "
                            f"{(next_safety_order_percentage - tso_start_percentage):.4f}%; reset trailing."
                        )

                return None

            # Increase trailing when profit has increased (in a negative way)
            if current_entry_profit_percentage < self.custom_info[custompairkey]["last_profit_percentage"]:
                new_threshold = next_safety_order_percentage + ((current_entry_profit_percentage - next_safety_order_percentage) * tso_factor)

                if ((self.custom_info[custompairkey]['last_profit_percentage'] == 0.0) & self.notify_trailing_start) | self.notify_trailing_update:
                    self.dp.send_msg(
                        f"{trade.pair}: profit from {self.custom_info[custompairkey]['last_profit_percentage']:.4f}% to {current_entry_profit_percentage:.4f}% ({tso_start_percentage}%). "
                        f"Safety Order threshold from {self.custom_info[custompairkey]['add_safety_order_on_profit_percentage']:.4f}% to {new_threshold:.4f}% ({tso_factor})."
                    )

                self.custom_info[custompairkey]["last_profit_percentage"] = current_entry_profit_percentage
                self.custom_info[custompairkey]["add_safety_order_on_profit_percentage"] = new_threshold

                return None
            # Return when profit has not increased, and is still below the thresold value to place a new Safety Order
            elif current_entry_profit_percentage < self.custom_info[custompairkey]["add_safety_order_on_profit_percentage"]:
                if self.logger:
                    self.logger.debug(
                        f"{trade.pair}: profit {current_entry_profit_percentage:.4f}% still below threshold of {self.custom_info[custompairkey]['add_safety_order_on_profit_percentage']:.4f}%."
                    )
                return None

        # Oke, time to add a Safety Order!
        try:
            # Calculate order(s) to be filled. Can be more than one order when the profit dropped big
            orderdata = self.determine_required_safety_orders(count_of_safety_orders, current_entry_profit_percentage, configpairkey, self.safety_order_configuration[configpairkey]["max_so"])

            if len(orderdata) >= 1:
                volume = orderdata[0]["volume"]
                if tso_enabled:
                    self.dp.send_msg(
                        f"{trade.pair}: current profit {current_entry_profit_percentage:.4f}% reached next SO {count_of_entries} "
                        f"at {self.custom_info[custompairkey]['add_safety_order_on_profit_percentage']:.4f}% (trailing from {next_safety_order_percentage:.4f}%) "
                        f"and calculated volume of {volume} for order 1/{len(orderdata)}."
                    )
                else:
                    self.dp.send_msg(
                        f"{trade.pair}: current profit {current_entry_profit_percentage:.4f}% reached next SO {count_of_entries} "
                        f"at {next_safety_order_percentage:.4f}% "
                        f"and calculated volume of {volume} for order 1/{len(orderdata)}."
                    )

                # Reset data and trailing
                self.custom_info[custompairkey]["last_profit_percentage"] = 0.0
                self.custom_info[custompairkey]["next_safety_order_profit_percentage"] = 0.0
                self.custom_info[custompairkey]["add_safety_order_on_profit_percentage"] = 0.0

                # Store order data for subsequent next orders to be bought after the first one has been bought
                if len(orderdata) > 1:
                    orderdata.pop(0) # Remove first order, as that one is already returned from this function
                    self.custom_info[custompairkey]["open_safety_orders"] = orderdata

                # Return volume for entry order
                return volume #, f"Safety Order {count_of_entries}"
            else:
                if self.logger:
                    self.logger.error(
                        f"{trade.pair}: calculated invalid orderdata based on {count_of_entries} of filled Safety Orders and current profit {current_entry_profit_percentage:.4f}%!"
                    )
        except Exception as exception:
            return None

        return None


    def get_trailing_config(self, profit_percentage, safety_order_percentage, config_pair_key) -> dict:
        """
        Get the trailing values for the current config based on the pair and profit
        """

        use_trailing = False
        start_percentage = 0.0
        factor = 0.0

        # Check which key to use; pair or default. If neither is present, assume the user doesn't
        # want to use Trailing Safety Order
        key = ""
        if config_pair_key in self.trailing_safety_order_configuration:
            key = config_pair_key
        elif "default" in self.trailing_safety_order_configuration:
            key = "default"
        
        if not key:
            return use_trailing, start_percentage, factor
        else:
            use_trailing = True

        # Find percentage and factor to use based on current (negative) profit. Always look one level
        # further to make sure the previous one is the right one to use
        start_percentage = self.trailing_safety_order_configuration[key][0]["start_percentage"]
        factor = self.trailing_safety_order_configuration[key][0]["factor"]

        for l in self.trailing_safety_order_configuration[key].values():
            if profit_percentage > (safety_order_percentage - l["start_percentage"]):
                break

            start_percentage = l["start_percentage"]
            factor = l["factor"]

        return use_trailing, start_percentage, factor


    def calculate_dca_volume(self, safety_order, config_pair_key, max_safety_orders) -> float:
        """
        DCA implementation; calculate the required volume (in stake currency) to buy for the Safety Order.

        This function checks if the provided safety order number is below or equal to the max number of 
        allowed trades as specifed with the `max_entry_position_adjustment`.

        :param safety_order: Safety order number.
        :return float: Volume in stake currency,
                       Return 0.0 for safety order above the `max_entry_position_adjustment`.
        """

        volume = 0.0

        if 0 < safety_order <= max_safety_orders:
            if config_pair_key in self.safety_order_configuration:
                volume = self.safety_order_configuration[config_pair_key]["initial_so_amount"] * (pow(self.safety_order_configuration[config_pair_key]["volume_scale"], (safety_order - 1)))
            elif "default" in self.safety_order_configuration:
                volume = self.safety_order_configuration["default"]["initial_so_amount"] * (pow(self.safety_order_configuration["default"]["volume_scale"], (safety_order - 1)))

        return volume


    def calculate_dca_volume_total(self, safety_order, config_pair_key, max_safety_orders) -> float:
        """
        DCA implementation; calculate the total volume (in stake currency) that has been bought
         including the specified Safety Order.

        This function checks if the provided safety order number is below the max number of 
        allowed trades as specifed with the `max_entry_position_adjustment`.

        :param safety_order: Safety order number.
        :return float: Totale volume in stake curreny,
                       Return 0.0 for safety order above the `max_entry_position_adjustment`.
        """

        total_volume = self.stake_amount

        if 0 < safety_order <= max_safety_orders:
            so_count = 1
            while (so_count <= safety_order):
                total_volume += self.calculate_dca_volume(so_count, config_pair_key, max_safety_orders)

                so_count += 1

        return total_volume


    def calculate_dca_step_deviation(self, safety_order, config_pair_key, max_safety_orders) -> float:
        """
        DCA implementation; calculate the price deviation for a certain Safety Order, from the
        previous Safety Order.

        This function checks if the provided safety order number is below the max number of 
        allowed trades as specifed with the `max_entry_position_adjustment`.

        :param safety_order: Safety order number.
        :return float: Percentage,
                       Return 0.0 for safety order above the `max_entry_position_adjustment`.
        """

        deviation = 0.0

        if 0 < safety_order <= max_safety_orders:
            if config_pair_key in self.safety_order_configuration:
                deviation = -(self.safety_order_configuration[config_pair_key]["price_deviation"] * (pow(self.safety_order_configuration[config_pair_key]["step_scale"], (safety_order - 1))))
            elif "default" in self.safety_order_configuration:
                deviation = -(self.safety_order_configuration["default"]["price_deviation"] * (pow(self.safety_order_configuration["default"]["step_scale"], (safety_order - 1))))

        return deviation


    def calculate_dca_deviation_total(self, safety_order, config_pair_key, max_safety_orders) -> float:
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

        if 0 < safety_order <= max_safety_orders:
            so_count = 1
            while (so_count <= safety_order):
                total_deviation += self.calculate_dca_step_deviation(so_count, config_pair_key, max_safety_orders)
                so_count += 1

        return total_deviation


    def determine_required_safety_orders(self, current_safety_order, current_price_deviation, config_pair_key, max_safety_orders) -> float:
        """
        DCA implementation; calculate the total price deviation from the entry price including the
        specified Safety Order.

        This function checks if the provided safety order number is below the max number of 
        allowed trades as specifed with the `max_entry_position_adjustment`.

        :param safety_order: Safety order number.
        :return float: Percentage,
                       Return 0.0 for safety order above the `max_entry_position_adjustment`.
        """

        requiredorders = list()

        if 0 <= current_safety_order <= (max_safety_orders - 1):
            so_count = 1
            step_deviation = 0.0
            total_deviation = 0.0
            while (so_count <= current_safety_order):
                step_deviation = self.calculate_dca_step_deviation(so_count, config_pair_key, max_safety_orders)
                total_deviation += step_deviation
                so_count += 1

            while (so_count <= max_safety_orders):
                step_deviation = self.calculate_dca_step_deviation(so_count, config_pair_key, max_safety_orders)
                total_deviation += step_deviation

                if current_price_deviation > total_deviation:
                    break

                volume = self.calculate_dca_volume(so_count, config_pair_key, max_safety_orders)

                order = {
                    "order": so_count,
                    "deviation": step_deviation,
                    "current_deviation": current_price_deviation,
                    "total_deviation": total_deviation,
                    "volume": volume
                }
                requiredorders.append(order)

                so_count += 1

        return requiredorders


    def initialize_custom_data(self, custom_pair_key):
        """
        """

        super().create_custom_data(custom_pair_key)

        # Insert default data
        self.custom_info[custom_pair_key]["last_profit_percentage"] = float(0.0) # Keep track of profit percentage for every cycle/update
        self.custom_info[custom_pair_key]["next_safety_order_profit_percentage"] = float(0.0) # Percentage on which the next SO is configured
        self.custom_info[custom_pair_key]["add_safety_order_on_profit_percentage"] = float(0.0) # Percentage on which the next SO should be bought, based on trailing
        self.custom_info[custom_pair_key]["open_safety_orders"] = list() # List of open Safety Orders to buy


    def get_custom_pairkey(self, trade: 'Trade'):
        """
        Get the custom pairkey used for runtime storage of trade data
        """

        return f"{trade.pair}_{trade.trade_direction}"