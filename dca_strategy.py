# pragma pylint: disable=missing-docstring, invalid-name, pointless-string-statement
# flake8: noqa: F401
# isort: skip_file
# --- Do not remove these libs ---
#from math import fabs
#import numpy as np
#import pandas as pd
#from pandas import DataFrame
from datetime import datetime, timedelta
from typing import Optional

# --------------------------------
# Add your lib to import here
from freqtrade.constants import Config
from freqtrade.persistence import Order, Trade

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

    STRATEGY_VERSION_DCA = "1.7.0"

    # Max number of safety orders (-1 means disabled)
    max_entry_position_adjustment = -1

    # Enable position adjustment
    position_adjustment_enable = False

    # Short or not
    can_short = False

    # Trading mode for this strategy (long / short / long_short)
    trading_direction = "long"

    # BaseOrder and SafetyOrder relation
    trade_bo_so_ratio = "1:1"

    # Safety Order configuration. 
    # The 'default' can be used when there is no specific entry for the pair and direction in the list
    safety_order_configuration = {}
    #safety_order_configuration["default"] = {}
    #safety_order_configuration["default"]["initial_so_amount"] = 10.0 # First Safety Order in stake amount
    #safety_order_configuration["default"]["price_deviation"] = 1.0
    #safety_order_configuration["default"]["volume_scale"] = 1.0
    #safety_order_configuration["default"]["step_scale"] = 1.0
    #safety_order_configuration["default"]["max_so"] = 1
    allow_multiple_safety_orders = True

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

        return self.STRATEGY_VERSION_DCA


    def __init__(self, config: Config) -> None:
        """
        Called upon construction of this class. Validate data and initialize
        all attributes,
        """

        # Call to super
        super().__init__(config)

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

        bo_so = 1.0
        if "bo:so" in config:
            if isinstance(config["bo:so"], str):
                self.trade_bo_so_ratio = config["bo:so"]
                bo_so = self.get_boso_factor()

        # Make sure the contents of the Safety Order configuration is correct
        for pairvalue in self.safety_order_configuration.values():
            for k, v in pairvalue.items():
                if k in ("max_so"):
                    pairvalue[k] = int(v)
                else:
                    pairvalue[k] = float(v)

                if k in ("initial_so_amount"):
                    # This could be 'unlimited' when the stake_amount from the config is used
                    if not isinstance(pairvalue[k], str):
                        old_value = pairvalue[k]
                        pairvalue[k] *= bo_so

                        self.log(
                            f"Updated initial so amount from {old_value} to {pairvalue[k]} "
                            f"based on bo amount {config['stake_amount']} and BO:SO {self.trade_bo_so_ratio}"
                        )

        # Make sure the contents of the Trailing Safety Order configuration is correct
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


    def bot_start(self, **kwargs) -> None:
        """
        Called only once after bot instantiation.
        :param **kwargs: Ensure to keep this here so updates to this won't break your strategy.
        """
    
        # Call to super first
        super().bot_start()
        self.log(f"Version - DCA Strategy: '{DCAStrategy.version(self)}'")

        self.log(f"Running with trading direction(s): '{self.trading_direction}'")
        self.log(f"Running with bo:so: '{self.trade_bo_so_ratio}'")

        # Display Safety Order configuration...
        for pairkey in self.safety_order_configuration:
            pair = pairkey
            direction = self.trading_direction

            if pairkey != "default":
                pair, direction = pairkey.split("_")

            self.log(f"Safety Order overview for '{pair}' in direction '{direction}':")

            self.log(
                f"BO | Deviation 0.0% | Order volume {self.stake_amount} ({self.stake_amount})"
            )
            so_count = 1
            max_so = self.safety_order_configuration[pairkey]["max_so"]
            while(so_count <= max_so):
                so_volume = self.calculate_dca_volume(so_count, pairkey, max_so)
                so_total_volume = self.calculate_dca_volume_total(so_count, pairkey, max_so)
                so_step_deviation = self.calculate_dca_step_deviation(so_count, pairkey, max_so)
                so_total_deviation = self.calculate_dca_deviation_total(so_count, pairkey, max_so)
                self.log(
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
            self.log(
                f"Trading direction '{side}' is currently disabled by bot configuration which has "
                f"'trading_direction' set to '{self.trading_direction}'. Not confirming this trade!",
                "WARNING"
            )
            return False  

        # When Safety Orders are enabled, check the configuration. The specific pair should be in the configuration, or
        # the default entry must be present. If this is not the case, don't open a new trade to avoid issues later on.
        pairkey = f"{pair}_{side}"
        if self.max_entry_position_adjustment > 0:
            if pairkey not in self.safety_order_configuration and "default" not in self.safety_order_configuration:
                self.log(
                    f"Safety Orders are enabled, but the specific '{pairkey}' or 'default' key is "
                    f"missing in the safety_order_configuration. Not confirming this trade!",
                    "WARNING"
                )
                return False

        # Check min stake amount required for the exchange, and keeping the bo:so into account
        pairdata = self.dp.market(pair)

        min_entry_amount = pairdata['limits']['amount']['min']
        min_entry_cost = pairdata['limits']['cost']['min']

        bo_so_factor = self.get_boso_factor()
        # TODO: calculate so_amount based on bo price reduced by the percentages the first SO will be bought on. This is 
        # actually lower than the bo price, and must be kept into account (price limit could be on the verge)
        so_amount = amount * bo_so_factor
        so_cost = (amount * rate) * bo_so_factor

        if so_amount < min_entry_amount or so_cost < min_entry_cost:
            self.log(
                f"{pair}: trading limit for a SO cannot be statisfied based on {self.trade_bo_so_ratio} ratio. "
                f"Safety Order amount {so_amount} (based on BO amount {amount}) is lower than {min_entry_amount} and/or "
                f"cost {so_cost} is lower than {min_entry_cost}. "
                f"Not starting this trade.",
                "WARNING"
            )
            self.lock_pair(pair, until=current_time + timedelta(minutes=1), reason="Min order limits could not be statisfied")
            return False

        self.initialize_custom_data(pairkey)

        return True


    def order_filled(self, pair: str, trade: Trade, order: Order, current_time: datetime, **kwargs) -> None:
        """
        Called right after an order fills. 
        Will be called for all order types (entry, exit, stoploss, position adjustment).
        :param pair: Pair for trade
        :param trade: trade object.
        :param order: Order object.
        :param current_time: datetime object, containing the current datetime
        :param **kwargs: Ensure to keep this here so updates to this won't break your strategy.
        """

        super().order_filled(pair, trade, order, current_time)

        if order.ft_order_side == trade.entry_side:
            custompairkey = self.get_custom_pairkey(trade)
            openorders = len(self.custom_info[custompairkey]["open_safety_orders"])
            if openorders > 0:
                # Check if the first order from the list has been bought. Remove the bought order and check if there are other
                # order(s) that should be bought. Keep in mind that an order can timeout on the exchange, in which case this function
                # is called again and the same volume must be returned (to place the order again)
                count_of_entries = trade.nr_of_successful_entries
                count_of_safety_orders = count_of_entries - 1 # Subtract Base Order
                if self.custom_info[custompairkey]["open_safety_orders"][0]["order"] == count_of_safety_orders:
                    self.custom_info[custompairkey]["open_safety_orders"].pop(0)

                    # Update number of open orders and send notification
                    openorders = len(self.custom_info[custompairkey]["open_safety_orders"])
                    self.log(
                        f"{trade.pair}: Safety Order {count_of_safety_orders} has been bought. "
                        f"There are {openorders} orders left.",
                        notify=True
                    )
        else:
            # Send notification about number of entries used to exit the trade
            filled_entries = trade.select_filled_orders(trade.entry_side)
            count_of_entries = len(filled_entries)

            self.log(
                f"{pair}: Exit after {count_of_entries} filled entry orders."
            )

        return None


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

        # Return when pair is locked
        if self.is_pair_locked(trade.pair):
            return None

        # Return when Trade is in profit
        if current_profit >= 0.0:
            return None

        # Return when no extra orders are allowed
        if self.max_entry_position_adjustment == -1:
            return None

        # Create pairkey, or use 'default' 
        custompairkey, configpairkey = self.get_pairkeys(trade)

        # Return when all Safety Orders are executed
        count_of_entries = trade.nr_of_successful_entries
        count_of_safety_orders = count_of_entries - 1 # Subtract Base Order
        if count_of_safety_orders >= self.safety_order_configuration[configpairkey]["max_so"]:
            self.log(
                f"{trade.pair}: reached max number ({self.safety_order_configuration[configpairkey]['max_so']}) of Safety Orders.",
                "DEBUG"
            )
            return None

        openorders = len(self.custom_info[custompairkey]["open_safety_orders"])
        if openorders > 0:
            pricedeviation = self.custom_info[custompairkey]["open_safety_orders"][0]["current_deviation"]
            totaldeviation = self.custom_info[custompairkey]["open_safety_orders"][0]["total_deviation"]
            volume = self.custom_info[custompairkey]["open_safety_orders"][0]["volume"]

            self.log(
                f"{trade.pair}: current profit {pricedeviation:.4f}% reached next SO {count_of_entries} at {totaldeviation:.4f}% "
                f"and calculated volume of {volume}.",
                notify=True
            )

            return volume, f"Safety Order {count_of_entries}"

        # Calculate the next Safety Order, if not calculated before. Store the calculated value to save some CPU cycles
        if self.custom_info[custompairkey]["next_safety_order_profit_percentage"] == 0.0:
            self.custom_info[custompairkey]["next_safety_order_profit_percentage"] = self.calculate_dca_deviation_total(count_of_entries, configpairkey, self.safety_order_configuration[configpairkey]["max_so"])
            self.log(
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

                    self.log(
                        f"{trade.pair}: current profit {current_entry_profit_percentage:.4f}% went above "
                        f"threshold {(next_safety_order_percentage - tso_start_percentage):.4f}%; reset trailing.",
                        notify=self.notify_trailing_reset
                    )
                # Else case: trailing did not start and we don't need to do anything
                return None

            # Increase trailing when profit has increased (in a negative way)
            if current_entry_profit_percentage < self.custom_info[custompairkey]["last_profit_percentage"]:
                new_threshold = next_safety_order_percentage + ((current_entry_profit_percentage - next_safety_order_percentage) * tso_factor)

                send_notification = ((self.custom_info[custompairkey]['last_profit_percentage'] == 0.0) & self.notify_trailing_start) | self.notify_trailing_update
                self.log(
                    f"{trade.pair}: profit from {self.custom_info[custompairkey]['last_profit_percentage']:.4f}% to {current_entry_profit_percentage:.4f}% "
                    f"(trailing from {next_safety_order_percentage:.4f}%). "
                    f"Safety Order threshold from {self.custom_info[custompairkey]['add_safety_order_on_profit_percentage']:.4f}% to {new_threshold:.4f}%.",
                    notify=send_notification
                )

                self.custom_info[custompairkey]["last_profit_percentage"] = current_entry_profit_percentage
                self.custom_info[custompairkey]["add_safety_order_on_profit_percentage"] = new_threshold

                return None
            # Return when profit has not increased, and is still below the thresold value to place a new Safety Order
            elif current_entry_profit_percentage < self.custom_info[custompairkey]["add_safety_order_on_profit_percentage"]:
                self.log(
                    f"{trade.pair}: profit {current_entry_profit_percentage:.4f}% still below threshold of {self.custom_info[custompairkey]['add_safety_order_on_profit_percentage']:.4f}%.",
                    "DEBUG"
                )
                return None
            # Else case: trailing passed the threshold and additional order can be placed

        # Oke, time to add a Safety Order!
        # Calculate order(s) to be filled. Can be more than one order when there's been a huge drop
        orderdata = self.determine_required_safety_orders(count_of_safety_orders, current_entry_profit_percentage, configpairkey, self.safety_order_configuration[configpairkey]["max_so"])

        volume = orderdata[0]["volume"]
        if tso_enabled:
            self.log(
                f"{trade.pair}: current profit {current_entry_profit_percentage:.4f}% reached next SO {count_of_entries} "
                f"at {self.custom_info[custompairkey]['add_safety_order_on_profit_percentage']:.4f}% (trailing from {next_safety_order_percentage:.4f}%) "
                f"and calculated volume of {volume} for order 1/{len(orderdata)}.",
                notify=True
            )
        else:
            self.log(
                f"{trade.pair}: current profit {current_entry_profit_percentage:.4f}% reached next SO {count_of_entries} "
                f"at {next_safety_order_percentage:.4f}% "
                f"and calculated volume of {volume} for order 1/{len(orderdata)}.",
                notify=True
            )

        # Reset data and trailing
        self.custom_info[custompairkey]["last_profit_percentage"] = 0.0
        self.custom_info[custompairkey]["next_safety_order_profit_percentage"] = 0.0
        self.custom_info[custompairkey]["add_safety_order_on_profit_percentage"] = 0.0

        # Store order data. Keep in mind orders can run into a timeout, and need to be placed again
        self.custom_info[custompairkey]["open_safety_orders"] = orderdata

        # Return volume for entry order
        return volume, f"Safety Order {count_of_entries}"


    def get_trailing_config(self, profit_percentage, safety_order_percentage, config_pair_key) -> tuple[bool, float, float]:
        """
        Get the trailing values for the current config based on the pair and profit

        :param profit_percentage: Current profit percentage.
        :param safety_order_percentage: Key to use for looking up data in the configuration.
        :param config_pair_key: Key to use for looking up data in the configuration.
        :return tuple[bool, float, float]: If trailing is enabled, the percentage trailing should start on 
                                            and the factor to increase the lacking threshold with
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
        :param config_pair_key: Key to use for looking up data in the configuration.
        :param max_safety_orders: Maximum number of Safety orders.
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
        :param config_pair_key: Key to use for looking up data in the configuration.
        :param max_safety_orders: Maximum number of Safety orders.
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
        :param config_pair_key: Key to use for looking up data in the configuration.
        :param max_safety_orders: Maximum number of Safety orders.
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
        :param config_pair_key: Key to use for looking up data in the configuration.
        :param max_safety_orders: Maximum number of Safety orders.
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

        :param current_safety_order: Current Safety order number.
        :param current_price_deviation: Current price deviation, calculated from entry.
        :param config_pair_key: Key to use for looking up data in the configuration.
        :param max_safety_orders: Maximum number of Safety orders.
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

                # Break when the Safety Order is not reached yet
                if current_price_deviation > total_deviation:
                    break

                order = {
                    "order": so_count,
                    "deviation": step_deviation,
                    "current_deviation": current_price_deviation,
                    "total_deviation": total_deviation,
                    "volume": self.calculate_dca_volume(so_count, config_pair_key, max_safety_orders)
                }
                requiredorders.append(order)

                # Break if Safety Orders may not be merged
                if not self.allow_multiple_safety_orders:
                    break;

                so_count += 1

        return requiredorders


    def initialize_custom_data(self, custom_pair_key):
        """
        Initialize the custom data with the required DCA fields.

        :param custom_pair_key: The key to create the data for.
        """

        super().create_custom_data(custom_pair_key)

        # Insert default data
        self.custom_info[custom_pair_key]["last_profit_percentage"] = float(0.0) # Keep track of profit percentage for every cycle/update
        self.custom_info[custom_pair_key]["next_safety_order_profit_percentage"] = float(0.0) # Percentage on which the next SO is configured
        self.custom_info[custom_pair_key]["add_safety_order_on_profit_percentage"] = float(0.0) # Percentage on which the next SO should be bought, based on trailing
        self.custom_info[custom_pair_key]["open_safety_orders"] = list() # List of open Safety Orders to buy


    def get_pairkeys(self, trade: 'Trade') -> tuple[str, str]:
        """
        Get the custom pairkey used for runtime storage of trade data.

        :param trade: Trade object of the trade for which the pairkeys should be fetched
        :return tuple[str, str]: key for custom data storage, and key for configuration data
        """

        custompairkey = super().get_custom_pairkey(trade)
        configpairkey = custompairkey
        if not configpairkey in self.safety_order_configuration:
            configpairkey = "default"

        return custompairkey, configpairkey


    def get_boso_factor(self) -> float:
        """
        Get the bo:so factor to take into account for orders
        :return float: The bo:so factor
        """

        bo, so = self.trade_bo_so_ratio.split(":")
        return float(so) / float(bo)