# pragma pylint: disable=missing-docstring, invalid-name, pointless-string-statement
# flake8: noqa: F401
# isort: skip_file
# --- Do not remove these libs ---
from pandas import DataFrame
from datetime import datetime
from typing import Optional

# --------------------------------
# Add your lib to import here
from freqtrade.constants import Config
from freqtrade.persistence import Order, Trade

from dca_strategy import DCAStrategy
class ExampleStrat(DCAStrategy):
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

    STRATEGY_VERSION = "0.1.0"

    # Optimal timeframe for the strategy.
    timeframe = '1h'

    # Minimal ROI designed for the strategy.
    # This attribute will be overridden if the config file contains "minimal_roi".
    minimal_roi = {
        "0":  0.0150    # Exit if there is 1.5% profit
    }

    ignore_roi_if_entry_signal = False

    # Number of candles the strategy requires before producing valid signals
    startup_candle_count = 1

    @property
    def plot_config(self):
        return {
            # Main plot indicators (Moving averages, ...)
            'main_plot': {
            },
            'subplots': {
                # Subplots - each dict defines one additional plot
            }
        }


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

        # Leverage configuration for this strategy
        self.leverage_configuration["default"] = 1.0

        # No stoploss configuration for this strategy (use default of 99%)

        # Setup Safety Order configuration for this strategy. For BTC and ETH there are
        # specific settings configured, for all other pairs the 'default' will be used
        self.safety_order_configuration["default"] = {}
        self.safety_order_configuration["default"]["initial_so_amount"] = config["stake_amount"]
        self.safety_order_configuration["default"]["price_deviation"] = 2.50
        self.safety_order_configuration["default"]["volume_scale"] = 1.05
        self.safety_order_configuration["default"]["step_scale"] = 0.95
        self.safety_order_configuration["default"]["max_so"] = 4

        self.safety_order_configuration["BTC/USDC_long"] = {}
        self.safety_order_configuration["BTC/USDC_long"]["initial_so_amount"] = config["stake_amount"]
        self.safety_order_configuration["BTC/USDC_long"]["price_deviation"] = 1.75
        self.safety_order_configuration["BTC/USDC_long"]["volume_scale"] = 1.10
        self.safety_order_configuration["BTC/USDC_long"]["step_scale"] = 0.95
        self.safety_order_configuration["BTC/USDC_long"]["max_so"] = 6

        self.safety_order_configuration["ETH/USDC_long"] = {}
        self.safety_order_configuration["ETH/USDC_long"]["initial_so_amount"] = config["stake_amount"]
        self.safety_order_configuration["ETH/USDC_long"]["price_deviation"] = 1.85
        self.safety_order_configuration["ETH/USDC_long"]["volume_scale"] = 1.15
        self.safety_order_configuration["ETH/USDC_long"]["step_scale"] = 1.00
        self.safety_order_configuration["ETH/USDC_long"]["max_so"] = 8

        # Use trailing safety orders
        self.trailing_safety_order_configuration.clear()
        self.trailing_safety_order_configuration['default'] = {}
        self.trailing_safety_order_configuration['default'][0] = {}
        self.trailing_safety_order_configuration['default'][0]['start_percentage'] = 0.50
        self.trailing_safety_order_configuration['default'][0]['factor'] = 0.50
        self.trailing_safety_order_configuration['default'][1] = {}
        self.trailing_safety_order_configuration['default'][1]['start_percentage'] = 1.00
        self.trailing_safety_order_configuration['default'][1]['factor'] = 0.55
        self.trailing_safety_order_configuration['default'][2] = {}
        self.trailing_safety_order_configuration['default'][2]['start_percentage'] = 2.00
        self.trailing_safety_order_configuration['default'][2]['factor'] = 0.60
        self.trailing_safety_order_configuration['default'][3] = {}
        self.trailing_safety_order_configuration['default'][3]['start_percentage'] = 3.00
        self.trailing_safety_order_configuration['default'][3]['factor'] = 0.75

        # Call to super
        super().__init__(config)


    def bot_start(self, **kwargs) -> None:
        """
        Called only once after bot instantiation.
        :param **kwargs: Ensure to keep this here so updates to this won't break your strategy.
        """
    
        # Call to super first
        super().bot_start()

        # Log the version of the strategy
        self.log(f"Version - Example Strategy: '{self.version()}'")


    def populate_entry_trend(self, dataframe: DataFrame, metadata: dict) -> DataFrame:
        """
        Based on TA indicators, populates the entry signal for the given dataframe
        :param dataframe: DataFrame
        :param metadata: Additional information, like the currently traded pair
        :return: DataFrame with entry columns populated
        """

        dataframe = super().populate_entry_trend(dataframe, metadata)

        # Always open trade, behaves like ASAP on other platforms
        # Alternatively implement own logic and indicators
        dataframe.loc[:,'enter_long'] = 1

        return dataframe


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

        # Schedule the removal of the 'Auto Lock' from Freqtrade which prevents trades
        # to start in the same candle as the sell of a previous trade. This prevents
        # the ASAP behaviour of this strategy
        #if order.ft_order_side == trade.exit_side and not trade.is_open:
        #    self.schedule_remove_autolock(trade.pair)

        return None