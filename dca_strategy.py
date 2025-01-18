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
from freqtrade.exchange.exchange_utils_timeframe import timeframe_to_minutes
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

    STRATEGY_VERSION_DCA = '1.11.0'

    # Max number of safety orders (-1 means disabled)
    max_entry_position_adjustment = -1

    # Enable position adjustment
    position_adjustment_enable = False

    # Short or not
    can_short = False

    # Trading mode for this strategy (long / short / long_short)
    trading_direction = 'long'

    # BaseOrder and SafetyOrder relation
    trade_bo_so_ratio = '1:1'

    # Safety Order configuration. 
    # The 'default' can be used when there is no specific entry for the pair and direction in the list
    safety_order_configuration = {}
    #safety_order_configuration['default'] = {}
    #safety_order_configuration['default']['initial_so_amount'] = 10.0 # First Safety Order in stake amount
    #safety_order_configuration['default']['price_deviation'] = 1.0
    #safety_order_configuration['default']['volume_scale'] = 1.0
    #safety_order_configuration['default']['step_scale'] = 1.0
    #safety_order_configuration['default']['max_so'] = 1
    safety_order_mode = 'shift' #Allowed options: 'shift', 'merge'

    # Trailing Safety Order configuration. 
    # First try to use the configuration for the pair and direction, then try 'default'. If none of them are 
    # available, no trailing will be used for placing Safety Order(s).
    trailing_safety_order_configuration = {}
    #trailing_safety_order_configuration['default'] = {}
    #trailing_safety_order_configuration['default'][0] = {}
    #trailing_safety_order_configuration['default'][0]['start_percentage'] = 0.25
    #trailing_safety_order_configuration['default'][0]['factor'] = 0.50

    # Settings controlling when to send notification about the trailing safety orders
    notify_trailing_start = True
    notify_trailing_update = True
    notify_trailing_reset = True

    # Profit configuration. 
    # First try to use the configuration for the pair and direction, then try 'default'. If none of them are 
    # available, strategy defaults for stoploss and roi will be used
    profit_configuration = {}
    #profit_configuration['default'] = {}
    #profit_configuration['default'][0] = {}
    #profit_configuration['default'][0]['activation-percentage'] = 2.25
    #self.profit_configuration['default'][0]['min-order-threshold-sell'] = 1
    #self.profit_configuration['default'][0]['min-order-threshold-stoploss'] = 1
    #self.profit_configuration['default'][0]['min-order-threshold-profit'] = 1
    #profit_configuration['default'][0]['sell-percentage'] = 50.00
    #profit_configuration['default'][0]['stoploss-initial'] = 0.50
    #profit_configuration['default'][0]['stoploss-increment-factor'] = 0.25
    #profit_configuration['default'][0]['profit-increment-factor'] = 0.50

    patch_dca_table = False


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
        if 'trading_direction' in config:
            if config['trading_direction'] in ('long', 'short', 'long_short'):
                self.trading_direction = config['trading_direction']

        # Try to get the trailing notify options from the config and validate when present
        if 'notify_trailing_start' in config:
            if isinstance(config['notify_trailing_start'], bool):
                self.notify_trailing_start = config['notify_trailing_start']
        if 'notify_trailing_update' in config:
            if isinstance(config['notify_trailing_update'], bool):
                self.notify_trailing_update = config['notify_trailing_update']
        if 'notify_trailing_reset' in config:
            if isinstance(config['notify_trailing_reset'], bool):
                self.notify_trailing_reset = config['notify_trailing_reset']

        if 'safety_order_mode' in config:
            if config['safety_order_mode'] in ('shift', 'merge'):
                self.safety_order_mode = config['safety_order_mode']

        if 'safety_configuration' in config:
            if isinstance(config['safety_configuration'], dict):
                self.load_safety_config(config['safety_configuration'])

        if 'trailing_configuration' in config:
            if isinstance(config['trailing_configuration'], dict):
                self.load_trailing_config(config['trailing_configuration'])

        if 'profit_configuration' in config:
            if isinstance(config['profit_configuration'], dict):
                self.load_profit_config(config['profit_configuration'])

        if 'patch_dca_table' in config:
            if isinstance(config['patch_dca_table'], bool):
                self.patch_dca_table = config['patch_dca_table']

        bo_so = 1.0
        if 'bo:so' in config:
            if isinstance(config['bo:so'], str):
                self.trade_bo_so_ratio = config['bo:so']
                bo_so = self.get_boso_factor()

        # Make sure the contents of the Safety Order configuration is correct
        for pairvalue in self.safety_order_configuration.values():
            if 'initial_so_amount' not in pairvalue.keys():
                pairvalue['initial_so_amount'] = config['stake_amount']

            for k, v in pairvalue.items():
                if k in ('dca_table'):
                    continue

                if k in ('max_so'):
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

        # Make sure the contents of the Profit configuration is correct
        for pairvalue in self.profit_configuration.values():
            for l in pairvalue.values():
                for k, v in l.items():
                    if k in ('min-order-threshold-sell', 'min-order-threshold-stoploss', 'min-order-threshold-profit'):
                        l[k] = int(v)
                    else:
                        l[k] = float(v)

        # Process Safety Order configuration...
        for pairkey in self.safety_order_configuration:
            if pairkey != 'default':
                # Determine the trading direction, and skip it when the trading direction for this bot does not allow it
                _, direction = pairkey.split("_")
                if direction not in self.trading_direction:
                    continue

            max_so = self.safety_order_configuration[pairkey]['max_so']
            
            # Make sure the max of entry adjustments is set to the highest number of max Safety Orders
            if self.max_entry_position_adjustment < max_so:
                self.max_entry_position_adjustment = max_so

                self.log(f"Adjusted number of position adjustments to {self.max_entry_position_adjustment}!")

        # Disabled by default, so enable when there are additional Safety Orders configured
        if self.max_entry_position_adjustment > 0:
            self.position_adjustment_enable = True

        # Process Profit configuration...
        for pairkey in self.profit_configuration:
            for l in pairvalue.keys():
                # Check if there is any stoploss configured. If so, make sure we can process it by enabling the functioncall
                stoploss = self.profit_configuration[pairkey][l]['stoploss-initial']
                if stoploss > 0.0:
                    self.use_custom_stoploss = True
                    break


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
        self.log(f"Running with custom stoploss: '{self.use_custom_stoploss}'")

        # Display Safety Order configuration...
        for pairkey in self.safety_order_configuration:
            pair = pairkey
            direction = self.trading_direction

            if pairkey != 'default':
                pair, direction = pairkey.split('_')

            self.log(f"Safety Order overview for '{pair}' in direction '{direction}':")
            self.log(
                f"BO | Deviation 0.0% | Order volume {self.stake_amount} ({self.stake_amount})"
            )

            dca_tbl = self.get_initial_dca_table(pair, direction)
            if len(dca_tbl) > 0:
                so_count = 1
                max_so = self.safety_order_configuration[pairkey]['max_so']
                while(so_count <= max_so):
                    so_volume = dca_tbl[so_count - 1]['volume']
                    so_total_volume = dca_tbl[so_count - 1]['total_volume']
                    so_step_deviation = dca_tbl[so_count - 1]['deviation_current']
                    so_total_deviation = dca_tbl[so_count - 1]['total_deviation_current']
                    
                    self.log(
                        f"SO {so_count} | Deviation {so_step_deviation}% ({so_total_deviation}%) | Order volume {so_volume} ({so_total_volume})"
                    )

                    so_count += 1

        # Create custom data required for DCA
        opentrades = Trade.get_trades_proxy(is_open=True)
        for opentrade in opentrades:
            # Check pressence of dca table
            trade_dca_tbl = opentrade.get_custom_data(key='dca_table')
            if trade_dca_tbl is None:
                trade_dca_tbl = self.get_initial_dca_table(opentrade.pair, opentrade.trade_direction)
                opentrade.set_custom_data(key='dca_table', value=trade_dca_tbl)
                self.log(f"{opentrade.pair}: added initial dca table")
            elif self.patch_dca_table:
                dca_tbl = self.get_initial_dca_table(opentrade.pair, opentrade.trade_direction)

                configuredcount = len(dca_tbl)
                currentcount = len(trade_dca_tbl)

                if configuredcount > currentcount:
                    shift_percentage = trade_dca_tbl[-1]['total_deviation_current'] - trade_dca_tbl[-1]['total_deviation_initial']

                    trade_dca_tbl += dca_tbl[currentcount:]

                    self.shift_dca_table(trade_dca_tbl, currentcount + 1, shift_percentage, True)

                    opentrade.set_custom_data(key='dca_table', value=trade_dca_tbl)

                    self.log(
                        f"{opentrade.pair}: patched dca_tbl by copying orders from {currentcount} to {configuredcount}. "
                        f"Shifted from {currentcount + 1} by {shift_percentage:.2f}%."
                    )
                elif configuredcount < currentcount:
                    count_of_entries = opentrade.nr_of_successful_entries
                    if (count_of_entries - 1) <= configuredcount:
                        if count_of_entries == 1:
                            trade_dca_tbl = trade_dca_tbl[0:0]
                            trade_dca_tbl += dca_tbl[0:]

                            opentrade.set_custom_data(key='dca_table', value=trade_dca_tbl)

                            self.log(f"{opentrade.pair}: patched dca_tbl by replacing all Safety Orders as only base order was filled.")
                        else:
                            trade_dca_tbl = trade_dca_tbl[0:configuredcount]

                            opentrade.set_custom_data(key='dca_table', value=trade_dca_tbl)

                            self.log(f"{opentrade.pair}: patched dca_tbl by removing orders after order {configuredcount}.")
                    else:
                        trade_dca_tbl = trade_dca_tbl[0:(count_of_entries - 1)]

                        opentrade.set_custom_data(key='dca_table', value=trade_dca_tbl)

                        self.log(
                            f"{opentrade.pair}: patched dca_tbl by removing only not filled orders after {(count_of_entries - 1)}. "
                            f"Configured number of orders {configuredcount} is less, but already {(count_of_entries - 1)} orders are filled!",
                            level="WARNING"
                        )

            self.log(f"{opentrade.pair}: dca table = '{trade_dca_tbl}'")

            custompairkey = self.get_custom_pairkey(opentrade.pair, opentrade.trade_direction)
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
        pairkey = self.get_custom_pairkey(pair, side)
        if self.max_entry_position_adjustment > 0:
            if pairkey not in self.safety_order_configuration and 'default' not in self.safety_order_configuration:
                self.log(
                    f"Safety Orders are enabled, but the specific '{pairkey}' or 'default' key is "
                    f"missing in the safety_order_configuration. Not confirming this trade!",
                    "WARNING"
                )
                return False

        # Check min stake amount required for the exchange, and keeping the bo:so into account
        # Fetch market data uncluding trading limits
        pairdata = self.dp.market(pair)

        min_entry_amount = pairdata['limits']['amount']['min']
        min_entry_cost = pairdata['limits']['cost']['min']

        # Get our BO:SO factor
        bo_so_factor = self.get_boso_factor()

        # Get percentage of first SO
        dca_tbl = self.get_initial_dca_table(pair, side)
        if len(dca_tbl) > 0:
            so_deviation = dca_tbl[0]['deviation_current']

            #TODO: keep volume of first SO from dca_tbl into account, which should have been updated by the bo:so factor already
            # Calculate how much will be bought for the first SO
            so_cost = (amount * rate) * bo_so_factor
            so_amount = so_cost / (rate * (1.0 - (so_deviation / 100.0)))

            if so_amount < min_entry_amount or so_cost < min_entry_cost:
                self.log(
                    f"{pair}: trading limit for first SO (on {so_deviation:.2f}%) cannot be statisfied based on {self.trade_bo_so_ratio} ratio. "
                    f"Safety Order amount {so_amount} (based on BO amount {amount}) is lower than {min_entry_amount} and/or "
                    f"cost {so_cost} is lower than {min_entry_cost}. "
                    f"Not starting this trade.",
                    "WARNING"
                )
                self.lock_pair(pair, until=current_time + timedelta(minutes=timeframe_to_minutes(self.timeframe)), reason="Min order limits could not be statisfied")
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

        # TODO: handle profit based on profit configuration. Deny exit when profit is still trailing up

        return confirmed


    def custom_stoploss(self, pair: str, trade: Trade, current_time: datetime,
                        current_rate: float, current_profit: float, after_fill: bool, 
                        **kwargs) -> Optional[float]:
        """
        Custom stoploss logic, returning the new distance relative to current_rate (as ratio).
        e.g. returning -0.05 would create a stoploss 5% below current_rate.
        The custom stoploss can never be below self.stoploss, which serves as a hard maximum loss.

        For full documentation please go to https://www.freqtrade.io/en/latest/strategy-advanced/

        When not implemented by a strategy, returns the initial stoploss value.
        Only called when use_custom_stoploss is set to True.

        :param pair: Pair that's currently analyzed
        :param trade: trade object.
        :param current_time: datetime object, containing the current datetime
        :param current_rate: Rate, calculated based on pricing settings in exit_pricing.
        :param current_profit: Current profit (as ratio), calculated based on current_rate.
        :param after_fill: True if the stoploss is called after the order was filled.
        :param **kwargs: Ensure to keep this here so updates to this won't break your strategy.
        :return float: New stoploss value, relative to the current_rate
        """

        # Create pairkey, or use 'default' 
        custompairkey, configpairkey = self.get_pairkeys(trade.pair, trade.trade_direction, 'Profit')

        # Get SL values from config
        current_profit_percentage = current_profit * 100.0
        sl_enabled, activation_percentage, sl_percentage, sl_factor = self.get_stoploss_config(current_profit_percentage, configpairkey)

        # Call base
        new_stoploss = super().custom_stoploss(pair, trade, current_time, current_rate, current_profit, after_fill)

        # Calculate new stoploss, when enabled and profit has increased
        if sl_enabled:
            if current_profit_percentage > self.custom_info[custompairkey]['last_profit_percentage']:
                # Calculate stoploss percentage based on the config and current profit
                stoploss_percentage = sl_percentage + ((current_profit_percentage - activation_percentage) * sl_factor)

                # Determine new stoploss value based on current rate/profit
                new_stoploss = current_profit_percentage - stoploss_percentage

                self.log(
                    f"{trade.pair}: profit increased from {self.custom_info[custompairkey]['last_profit_percentage']:.2f}% "
                    f"to {current_profit_percentage:.2f}%. Updating stoploss to {stoploss_percentage:.2f}% ({new_stoploss:.2f}%) based on "
                    f"initial SL {sl_percentage:.2f}% and factor {sl_factor:.2f}%",
                    notify=False
                )

                self.custom_info[custompairkey]['last_profit_percentage'] = current_profit_percentage

                # Convert to ratio instead of percentage for framework
                new_stoploss /= 100.0
            else:
                self.log(
                    f"{trade.pair}: profit {current_profit_percentage:.2f} below {self.custom_info[custompairkey]['last_profit_percentage']:.2f}% "
                    f"not changing the stoploss percentage."
                )
        #elif self.custom_info[custompairkey]['last_profit_percentage'] != 0.0:
        #    self.custom_info[custompairkey]['last_profit_percentage'] = float(0.0)

        return new_stoploss


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
            custompairkey = self.get_custom_pairkey(trade.pair, trade.trade_direction)

            # Get number of entry orders
            count_of_entries = trade.nr_of_successful_entries
            if count_of_entries == 1:
                # Base order filled, add DCA table
                dca_tbl = self.get_initial_dca_table(trade.pair, trade.trade_direction)
                trade.set_custom_data(key='dca_table', value=dca_tbl)

                self.log(f"Initial DCA table added to trade: {dca_tbl}")

            openorders = len(self.custom_info[custompairkey]['open_safety_orders'])
            if openorders > 0:
                # Check if the first order from the list has been bought. Remove the bought order and check if there are other
                # order(s) that should be bought. Keep in mind that an order can timeout on the exchange, in which case this function
                # is called again and the same volume must be returned (to place the order again)
                count_of_entries = trade.nr_of_successful_entries
                count_of_safety_orders = count_of_entries - 1 # Subtract Base Order
                if self.custom_info[custompairkey]['open_safety_orders'][0]['order'] == count_of_safety_orders:
                    if self.safety_order_mode == 'shift':
                        # Calculate shift percentage, based on configured SO deviation and actual profit percentage bought on
                        profit_percentage = self.custom_info[custompairkey]['open_safety_orders'][0]['current_deviation']
                        safety_order_percentage = self.custom_info[custompairkey]['open_safety_orders'][0]['total_deviation']
                        shift_percentage = profit_percentage - safety_order_percentage

                        self.log(
                            f"{trade.pair}: calculated shift percentage {shift_percentage:.4f}% based on "
                            f"profit {profit_percentage:.4f}% and SO {safety_order_percentage:.4f}%"
                        )

                        # Shift the DCA tabel by this percentage and store it with the trade
                        dca_table = trade.get_custom_data(key='dca_table')
                        self.shift_dca_table(dca_table, count_of_safety_orders, shift_percentage)
                        trade.set_custom_data(key='dca_table', value=dca_table)

                        self.log(
                            f"{trade.pair}: shifted dca table by {shift_percentage:.4f}% from order {count_of_safety_orders}. "
                            f"Max deviation shifted from {dca_table[-1]['total_deviation_initial']:.4f}% to {dca_table[-1]['total_deviation_current']:.4f}%.",
                            notify=True
                        )
                        self.log(
                            f"DCA table: '{dca_table}'."
                        )

                    self.custom_info[custompairkey]['open_safety_orders'].pop(0)

                    # Update number of open orders and send notification
                    openorders = len(self.custom_info[custompairkey]['open_safety_orders'])
                    self.log(
                        f"{trade.pair}: Safety Order {count_of_safety_orders} has been bought. "
                        f"There are {openorders} orders left.",
                        notify=True
                    )
        elif not trade.is_open:
            # Trade completely exited; send notification about number of entries used to exit
            filled_entries = trade.select_filled_orders(trade.entry_side)
            count_of_entries = len(filled_entries)

            deviationmsg = ""
            if self.safety_order_mode == 'shift':
                dca_table = trade.get_custom_data(key='dca_table')
                if len(dca_table) > 0:
                    deviationmsg = f"Max deviation was shifted from {dca_table[-1]['total_deviation_initial']:.4f}% to {dca_table[-1]['total_deviation_current']:.4f}%."

            self.log(
                f"{pair}: Exited after {count_of_entries} filled entry orders. {deviationmsg}",
                notify=True
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
        custompairkey, configpairkey = self.get_pairkeys(trade.pair, trade.trade_direction, 'Safety')

        # Return when all Safety Orders are executed
        count_of_entries = trade.nr_of_successful_entries
        count_of_safety_orders = count_of_entries - 1 # Subtract Base Order

        dca_table = trade.get_custom_data(key='dca_table')
        max_orders = len(dca_table)
        if count_of_safety_orders >= max_orders:
            self.log(
                f"{trade.pair}: reached max number ({max_orders}) of Safety Orders.",
                "DEBUG"
            )
            return None

        rounddigits = self.get_round_digits(trade.pair)

        openorders = len(self.custom_info[custompairkey]['open_safety_orders'])
        if openorders > 0:
            pricedeviation = self.custom_info[custompairkey]['open_safety_orders'][0]['current_deviation']
            totaldeviation = self.custom_info[custompairkey]['open_safety_orders'][0]['total_deviation']
            volume = self.custom_info[custompairkey]['open_safety_orders'][0]['volume']

            self.log(
                f"{trade.pair}: current profit {pricedeviation:.4f}% reached next SO {count_of_entries}/{max_orders} at {totaldeviation:.4f}% "
                f"and calculated volume of {volume:.{rounddigits}f}.",
                notify=True
            )

            return volume, f"Safety Order {count_of_entries}"

        # Calculate the next Safety Order, if not calculated before. Store the calculated value to save some CPU cycles
        if self.custom_info[custompairkey]['next_safety_order_profit_percentage'] == 0.0:
            dca_table = trade.get_custom_data(key='dca_table')
            dca_table_deviation = dca_table[count_of_safety_orders]['total_deviation_current']

            self.custom_info[custompairkey]['next_safety_order_profit_percentage'] = dca_table_deviation
            self.log(
                f"{trade.pair}: calculated next safety order on {self.custom_info[custompairkey]['next_safety_order_profit_percentage']:.4f}%."
            )

        # Return when the current (negative) profit hasn't reached the next Safety Order. 
        current_entry_profit_percentage = (current_entry_profit / trade.leverage) * 100.0
        next_safety_order_percentage = self.custom_info[custompairkey]['next_safety_order_profit_percentage']
        if current_entry_profit_percentage > next_safety_order_percentage:
            return None

        tso_enabled, tso_start_percentage, tso_factor = self.get_safety_trailing_config(current_entry_profit_percentage, next_safety_order_percentage, configpairkey)
        if tso_enabled:
            # Return when profit is above Safety Order percentage keeping start_percentage into account (and reset data when required)
            if current_entry_profit_percentage > (next_safety_order_percentage - tso_start_percentage):
                if self.custom_info[custompairkey]['last_profit_percentage'] != 0.0:
                    self.custom_info[custompairkey]['last_profit_percentage'] = float(0.0)
                    self.custom_info[custompairkey]['add_safety_order_on_profit_percentage'] = float(0.0)
                    self.custom_info[custompairkey]['trailing_start_datetime'] = datetime.min

                    self.log(
                        f"{trade.pair}: current profit {current_entry_profit_percentage:.4f}% went above "
                        f"threshold {(next_safety_order_percentage - tso_start_percentage):.4f}%; reset trailing.",
                        notify=self.notify_trailing_reset
                    )
                # Else case: trailing did not start and we don't need to do anything
                return None

            # Increase trailing when profit has increased (in a negative way)
            if current_entry_profit_percentage < self.custom_info[custompairkey]['last_profit_percentage']:
                new_threshold = next_safety_order_percentage + ((current_entry_profit_percentage - next_safety_order_percentage) * tso_factor)

                send_notification = ((self.custom_info[custompairkey]['last_profit_percentage'] == 0.0) and self.notify_trailing_start) or self.notify_trailing_update
                self.log(
                    f"{trade.pair}: profit from {self.custom_info[custompairkey]['last_profit_percentage']:.4f}% to {current_entry_profit_percentage:.4f}% "
                    f"(trailing from {next_safety_order_percentage:.4f}%). "
                    f"Safety Order threshold from {self.custom_info[custompairkey]['add_safety_order_on_profit_percentage']:.4f}% to {new_threshold:.4f}%.",
                    notify=send_notification
                )

                # Set start time only when trailing starts
                if (self.custom_info[custompairkey]['last_profit_percentage'] == 0.0):
                    self.custom_info[custompairkey]['trailing_start_datetime'] = datetime.now()

                # Update trailing position
                self.custom_info[custompairkey]['last_profit_percentage'] = current_entry_profit_percentage
                self.custom_info[custompairkey]['add_safety_order_on_profit_percentage'] = new_threshold

                return None
            # Return when profit has not increased, and is still below the thresold value to place a new Safety Order
            elif current_entry_profit_percentage < self.custom_info[custompairkey]['add_safety_order_on_profit_percentage']:
                self.log(
                    f"{trade.pair}: profit {current_entry_profit_percentage:.4f}% still below threshold of {self.custom_info[custompairkey]['add_safety_order_on_profit_percentage']:.4f}%.",
                    "DEBUG"
                )
                return None
            # Else case: trailing passed the threshold and additional order can be placed

        # Oke, time to add a Safety Order!
        # Calculate order(s) to be filled. Can be more than one order when there's been a huge drop
        dca_table = trade.get_custom_data(key='dca_table')
        orderdata = self.determine_required_safety_orders(dca_table, count_of_safety_orders, current_entry_profit_percentage)

        volume = orderdata[0]['volume']
        if tso_enabled:
            trailingstart = self.custom_info[custompairkey]['trailing_start_datetime']
            self.log(
                f"{trade.pair}: bounced from {self.custom_info[custompairkey]['last_profit_percentage']:.4f}% and "
                f"current profit {current_entry_profit_percentage:.4f}% reached SO {count_of_entries}/{max_orders} "
                f"at {self.custom_info[custompairkey]['add_safety_order_on_profit_percentage']:.4f}% "
                f"(trailing from {next_safety_order_percentage:.4f}% at {trailingstart.strftime('%Y-%m-%d %H:%M:%S')}). "
                f"Calculated volume of {volume:.{rounddigits}f} for order 1/{len(orderdata)}.",
                notify=True
            )
        else:
            self.log(
                f"{trade.pair}: current profit {current_entry_profit_percentage:.4f}% reached SO {count_of_entries}/{max_orders} "
                f"at {next_safety_order_percentage:.4f}% "
                f"and calculated volume of {volume:.{rounddigits}f} for order 1/{len(orderdata)}.",
                notify=True
            )

        # Reset data and trailing
        self.custom_info[custompairkey]['last_profit_percentage'] = 0.0
        self.custom_info[custompairkey]['next_safety_order_profit_percentage'] = 0.0
        self.custom_info[custompairkey]['add_safety_order_on_profit_percentage'] = 0.0
        self.custom_info[custompairkey]['trailing_start_datetime'] = datetime.min

        # Store order data. Keep in mind orders can run into a timeout, and need to be placed again
        self.custom_info[custompairkey]['open_safety_orders'] = orderdata

        # Return volume for entry order
        return volume, f"Safety Order {count_of_entries}"


    def handle_trade_safety(self):
        """
        """


    def handle_trade_profit(self, trade: 'Trade', current_profit: float):
        """
        """


    def load_safety_config(self, safety_config: dict) -> None:
        """
        Load safety order configuration based on supplied dict of configuration elements
        """

        # We don't clear the safety order configuration to allow changing a single value

        for pk, pv in safety_config.items():
            if not ('_long' in pk or '_short' in pk) and pk != 'default':
                self.log(f"Invalid safety order configuration key '{pk}'!", 'WARNING', False)
                continue

            if pk not in self.safety_order_configuration:
                self.safety_order_configuration[pk] = {}

            for k, v in pv.items():
                if k in ('initial_so_amount', 'price_deviation', 'volume_scale', 'step_scale', 'max_so'):
                    self.safety_order_configuration[pk][k] = v
                    self.log(f"Set safety order configuration key '{k}' for pair '{pk}' to value '{v}'")
                else:
                    self.log(f"Unknown safety order configuration key '{k}' for pair '{pk}'!", 'WARNING', False)


    def load_trailing_config(self, trailing_config: dict) -> None:
        """
        Load trailing configuration based on supplied dict of configuration elements
        """

        for pk, pv in trailing_config.items():
            if not ('_long' in pk or '_short' in pk) and pk != 'default':
                self.log(f"Invalid trailing configuration key '{pk}'!", 'WARNING', False)
                continue

            # Create pair section, or clear the existing one to load the new configuration
            if pk not in self.trailing_safety_order_configuration:
                self.trailing_safety_order_configuration[pk] = {}
            else:
                self.trailing_safety_order_configuration[pk].clear()

            for index, entry in enumerate(pv):
                self.trailing_safety_order_configuration[pk][index] = {}
                for k, v in entry.items():
                    if k in ('start_percentage', 'factor'):
                        self.trailing_safety_order_configuration[pk][index][k] = v
                        self.log(f"Set trailing order configuration key '{k}' for pair '{pk}' on index '{index}' to value '{v}'")
                    else:
                        self.log(f"Unknown trailing order configuration key '{k}' for pair '{pk}' on index '{index}'!", 'WARNING', False)


    def load_profit_config(self, profit_config: dict) -> None:
        """
        Load profit configuration based on supplied dict of configuration elements
        """

        for pk, pv in profit_config.items():
            if not ('_long' in pk or '_short' in pk) and pk != 'default':
                self.log(f"Invalid profit configuration key '{pk}'!", 'WARNING', False)
                continue

            # Create pair section, or clear the existing one to load the new configuration
            if pk not in self.profit_configuration:
                self.profit_configuration[pk] = {}
            else:
                self.profit_configuration[pk].clear()

            for index, entry in enumerate(pv):
                self.profit_configuration[pk][index] = {}
                for k, v in entry.items():
                    if k in ('activation-percentage',
                             'min-order-threshold-sell',
                             'min-order-threshold-stoploss',
                             'min-order-threshold-profit',
                             'sell-percentage',
                             'stoploss-initial',
                             'stoploss-increment-factor',
                             'profit-increment-factor'
                             ):
                        self.profit_configuration[pk][index][k] = v
                        self.log(f"Set profit configuration key '{k}' for pair '{pk}' on index '{index}' to value '{v}'")
                    else:
                        self.log(f"Unknown profit configuration key '{k}' for pair '{pk}' on index '{index}'!", 'WARNING', False)


    def get_safety_trailing_config(self, profit_percentage, safety_order_percentage, config_pair_key) -> tuple[bool, float, float]:
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
        elif 'default' in self.trailing_safety_order_configuration:
            key = 'default'
        
        if not key:
            return use_trailing, start_percentage, factor
        else:
            use_trailing = True

        # Find percentage and factor to use based on current (negative) profit. Always look one level
        # further to make sure the previous one is the right one to use
        start_percentage = self.trailing_safety_order_configuration[key][0]['start_percentage']
        factor = self.trailing_safety_order_configuration[key][0]['factor']

        for l in self.trailing_safety_order_configuration[key].values():
            if profit_percentage > (safety_order_percentage - l['start_percentage']):
                break

            start_percentage = l['start_percentage']
            factor = l['factor']

        return use_trailing, start_percentage, factor


    def get_stoploss_config(self, current_profit_percentage, config_pair_key) -> tuple[bool, float, float, float]:
        """
        Get the stoploss values for the current config based on the pair and profit

        :param current_profit_percentage: The current profit percentage.
        :param config_pair_key: Key to use for looking up data in the configuration.
        :return tuple[bool, float, float, float]: If stoploss is enabled, the activation percentage, the initial stoploss 
                                            percentage and the factor to increase the stoploss with based on the current profit
        """

        activation_percentage = 0.0
        initial_stoploss = 0.0
        factor = 0.0

        # Check which key to use; pair or default. If neither is present, assume the user doesn't
        # want to use Trailing Safety Order
        key = ""
        if config_pair_key in self.profit_configuration:
            key = config_pair_key
        elif 'default' in self.profit_configuration:
            key = 'default'
        
        if not key:
            return False, activation_percentage, initial_stoploss, factor

        # Find percentage and factor to use based on current (positive) profit. Always look one level
        # further to make sure the previous one is the right one to use
        for l in self.profit_configuration[key].values():
            if l['activation-percentage'] > current_profit_percentage:
                break

            activation_percentage = l['activation-percentage']
            initial_stoploss = l['stoploss-initial']
            factor = l['stoploss-increment-factor']

        return (initial_stoploss > 0.0), activation_percentage, initial_stoploss, factor


    def get_profit_config(self, profit_percentage, current_profit_percentage, config_pair_key) -> tuple[bool, float, float]:
        """
        Get the profit values for the current config based on the pair and profit

        :param profit_percentage: Current profit percentage.
        :param current_profit_percentage: Key to use for looking up data in the configuration.
        :param config_pair_key: Key to use for looking up data in the configuration.
        :return tuple[bool, float, float]: If trailing is enabled, the percentage trailing should start on 
                                            and the factor to increase the lacking threshold with
        """

        use_trailing = False
        factor = 0.0

        # Check which key to use; pair or default. If neither is present, assume the user doesn't
        # want to use Trailing Safety Order
        key = ""
        if config_pair_key in self.profit_configuration:
            key = config_pair_key
        elif 'default' in self.profit_configuration:
            key = 'default'
        
        if not key:
            return use_trailing, profit_percentage, factor
        else:
            use_trailing = True

        # Find percentage and factor to use based on current (positive) profit. Always look one level
        # further to make sure the previous one is the right one to use
        activation_percentage = self.profit_configuration[key][0]['activation_percentage']
        factor = self.profit_configuration[key][0]['factor']

        for l in self.profit_configuration[key].values():
            if l['activation_percentage'] > current_profit_percentage:
                break

            activation_percentage = l['activation_percentage']
            factor = l['factor']

        return use_trailing, activation_percentage, factor


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
                volume = self.safety_order_configuration[config_pair_key]['initial_so_amount'] * (pow(self.safety_order_configuration[config_pair_key]['volume_scale'], (safety_order - 1)))
            elif 'default' in self.safety_order_configuration:
                volume = self.safety_order_configuration['default']['initial_so_amount'] * (pow(self.safety_order_configuration['default']['volume_scale'], (safety_order - 1)))

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
                deviation = -(self.safety_order_configuration[config_pair_key]['price_deviation'] * (pow(self.safety_order_configuration[config_pair_key]['step_scale'], (safety_order - 1))))
            elif 'default' in self.safety_order_configuration:
                deviation = -(self.safety_order_configuration['default']['price_deviation'] * (pow(self.safety_order_configuration['default']['step_scale'], (safety_order - 1))))

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


    def determine_required_safety_orders(self, dca_table: list, current_safety_order: int, current_price_deviation: float) -> list:
        """
        DCA implementation; calculate the total price deviation from the entry price including the
        specified Safety Order.

        This function checks if the provided safety order number is below the max number of 
        allowed trades as specifed with the `max_entry_position_adjustment`.

        :param dca_table: Configuration of safety orders
        :param current_safety_order: Current Safety order number.
        :param current_price_deviation: Current price deviation, calculated from entry.
        :param config_pair_key: Key to use for looking up data in the configuration.
        :param max_safety_orders: Maximum number of Safety orders.
        :return float: Percentage,
                       Return 0.0 for safety order above the `max_entry_position_adjustment`.
        """

        requiredorders = list()

        max_safety_orders = len(dca_table)
        if 0 <= current_safety_order <= max_safety_orders:

            self.log(
                f"Determing order list starting from {current_safety_order} till max {max_safety_orders}..."
            )

            so_count = current_safety_order + 1
            while (so_count <= max_safety_orders):
                # Break when the Safety Order is not reached yet
                idx = so_count - 1
                if current_price_deviation > dca_table[idx]['total_deviation_current']:
                    self.log(
                        f"Current_price_deviation {current_price_deviation} > {dca_table[idx]['total_deviation_current']}. Stop adding orders."
                    )
                    break

                order = {
                    'order': so_count,
                    'deviation': dca_table[idx]['deviation_current'],
                    'current_deviation': current_price_deviation,
                    'total_deviation': dca_table[idx]['total_deviation_current'],
                    'volume': dca_table[idx]['volume'] #self.calculate_dca_volume(so_count, config_pair_key, max_safety_orders)
                }
                requiredorders.append(order)

                self.log(
                    f"Added order {order} to list of Safety Orders to buy."
                )

                # Break if Safety Orders may not be merged
                if self.safety_order_mode != 'merge':
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
        self.custom_info[custom_pair_key]['last_profit_percentage'] = float(0.0) # Keep track of profit percentage for every cycle/update
        self.custom_info[custom_pair_key]['next_safety_order_profit_percentage'] = float(0.0) # Percentage on which the next SO is configured
        self.custom_info[custom_pair_key]['add_safety_order_on_profit_percentage'] = float(0.0) # Percentage on which the next SO should be bought, based on trailing
        self.custom_info[custom_pair_key]['trailing_start_datetime'] = datetime.min # Datetime trailing started
        self.custom_info[custom_pair_key]['open_safety_orders'] = list() # List of open Safety Orders to buy


    def get_pairkeys(self, pair: str, side: str, config_type: str) -> tuple[str, str]:
        """
        Get the custom pairkey used for runtime storage of trade data.

        :param pair: Trading pair
        :param side: Direction of the trade (long/short)
        :param config_type: 'Safety' or 'Profit'
        :return tuple[str, str]: key for custom data storage, and key for configuration data
        """

        custompairkey = super().get_custom_pairkey(pair, side)
        configpairkey = custompairkey
        if config_type == 'Safety' and not configpairkey in self.safety_order_configuration:
            configpairkey = 'default'
        elif config_type == 'Profit' and not configpairkey in self.profit_configuration:
            configpairkey = 'default'

        return custompairkey, configpairkey


    def get_boso_factor(self) -> float:
        """
        Get the bo:so factor to take into account for orders
        :return float: The bo:so factor
        """

        bo, so = self.trade_bo_so_ratio.split(':')
        return float(so) / float(bo)


    def get_initial_dca_table(self, pair: str, side: str) -> list:
        """
        Get the DCA table applicable for this trade, based on the configuration

        :param pair: Trading pair
        :param side: Direction of the trade (long/short)
        :return list: list of Safety Orders
        """

        table = list()

        _, configpairkey = self.get_pairkeys(pair, self.trading_direction, 'Safety')

        # If there is a preconfigured dca_table, use that one.
        if "dca_table" in self.safety_order_configuration[configpairkey]:
            return self.safety_order_configuration[configpairkey]["dca_table"].copy()

        # There is no preconfigured dca_table, so build one based on the configured settings
        so_count = 1
        max_so = self.safety_order_configuration[configpairkey]['max_so']
        total_volume = self.stake_amount
        while(so_count <= max_so):
            deviation = self.calculate_dca_step_deviation(so_count, configpairkey, max_so)
            total_deviation = self.calculate_dca_deviation_total(so_count, configpairkey, max_so)

            volume = self.calculate_dca_volume(so_count, configpairkey, max_so)
            total_volume += volume

            order = {
                'order': so_count,
                'deviation_current': deviation,
                'deviation_initial': deviation,
                'total_deviation_current': total_deviation,
                'total_deviation_initial': total_deviation,
                'volume': volume,
                'total_volume': total_volume
            }
            table.append(order)

            so_count += 1

        return table


    def shift_dca_table(self, dca_table: list, start_from_order: int, shift_percentage: float, only_total = False):
        """
        Shift the values in the DCA table by the given percentage from a certain order
        Will shift the deviation for the current order number to account for the shift, and 
        the total deviation for all the orders after that one.

        :param dca_table: DCA table to shift
        :param start_from_order: Order number to start shifting from
        :param shift_percentage: Percentage to shift
        """

        for safetyorder in dca_table:
            # Skip previous orders
            if safetyorder['order'] < start_from_order:
                continue

            # Update deviation for current order
            if (not only_total) and (safetyorder['order'] == start_from_order):
                safetyorder['deviation_current'] += shift_percentage

            # Record shift for current order and shift future orders
            safetyorder['total_deviation_current'] += shift_percentage
