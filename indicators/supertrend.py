from numpy import nan as npNaN
from pandas import DataFrame
from pandas_ta.overlap import hl2, sma
from pandas_ta.volatility import atr, true_range
from pandas_ta.utils import get_offset, verify_series

### This supertrend indicator is a copy of pandas-ta. The functionality is the same, 
##  however the pandas version is not offering the option to pass the series on
##  which the upper- and lowerband are calculated. It defaults to HL2 which is most
##  of the time what you want. Only not always.
##  Changes made:
##  - open argument added
##  - source argument added (defaults to hl2)
##  - renamed `hl2_` to `middleband_value`
##  - add match case (switch case in Python, supported from 3.10)

def supertrend(open, high, low, close, length=None, multiplier=None, source='hl2', change_atr_calculation=False, offset=None, **kwargs):
    """Supertrend (supertrend)

Supertrend is an overlap indicator. It is used to help identify trend
direction, setting stop loss, identify support and resistance, and/or
generate buy & sell signals.

Sources:
    http://www.freebsensetips.com/blog/detail/7/What-is-supertrend-indicator-its-calculation

Calculation:
    Default Inputs:
        length=7, multiplier=3.0
    Default Direction:
	Set to +1 or bullish trend at start

    MID = multiplier * ATR
    LOWERBAND = HL2 - MID
    UPPERBAND = HL2 + MID

    if UPPERBAND[i] < FINAL_UPPERBAND[i-1] and close[i-1] > FINAL_UPPERBAND[i-1]:
        FINAL_UPPERBAND[i] = UPPERBAND[i]
    else:
        FINAL_UPPERBAND[i] = FINAL_UPPERBAND[i-1])

    if LOWERBAND[i] > FINAL_LOWERBAND[i-1] and close[i-1] < FINAL_LOWERBAND[i-1]:
        FINAL_LOWERBAND[i] = LOWERBAND[i]
    else:
        FINAL_LOWERBAND[i] = FINAL_LOWERBAND[i-1])

    if close[i] <= FINAL_UPPERBAND[i]:
        SUPERTREND[i] = FINAL_UPPERBAND[i]
    else:
        SUPERTREND[i] = FINAL_LOWERBAND[i]

Args:
    open (pd.Series): Series of 'open's
    high (pd.Series): Series of 'high's
    low (pd.Series): Series of 'low's
    close (pd.Series): Series of 'close's
    length (int) : length for ATR calculation. Default: 7
    multiplier (float): Coefficient for upper and lower band distance to
        midrange. Default: 3.0
    source (string): source to use for calculation of lower- and 
        upperband. Default: hl2        
    offset (int): How many periods to offset the result. Default: 0

Kwargs:
    fillna (value, optional): pd.DataFrame.fillna(value)
    fill_method (value, optional): Type of fill method

Returns:
    pd.DataFrame: SUPERT (trend), SUPERTd (direction), SUPERTl (long), SUPERTs (short) columns.
"""

    # Validate Arguments
    length = int(length) if length and length > 0 else 7
    multiplier = float(multiplier) if multiplier and multiplier > 0 else 3.0
    open = verify_series(open, length)
    high = verify_series(high, length)
    low = verify_series(low, length)
    close = verify_series(close, length)
    offset = get_offset(offset)

    if open is None or high is None or low is None or close is None: return

    # Calculate Results
    m = close.size
    dir_, trend = [1] * m, [0] * m
    long, short = [npNaN] * m, [npNaN] * m

    middleband_value = 0.0

    if source == "open":
        middleband_value = open
    elif source == "high":
        middleband_value = high
    elif source == "low":
        middleband_value = low
    elif source == "close":
        middleband_value = close
    else:
        middleband_value = hl2(high, low)

    matr = multiplier
    if change_atr_calculation:
        matr *= atr(high, low, close, length)
    else:
        matr *= sma(true_range(high, low, close), length)

    upperband = middleband_value + matr
    lowerband = middleband_value - matr

    for i in range(1, m):
        if close.iloc[i] > upperband.iloc[i - 1]:
            dir_[i] = 1
        elif close.iloc[i] < lowerband.iloc[i - 1]:
            dir_[i] = -1
        else:
            dir_[i] = dir_[i - 1]

        if dir_[i] > 0 and lowerband.iloc[i] < lowerband.iloc[i - 1]:
            lowerband.iloc[i] = lowerband.iloc[i - 1]
        if dir_[i] < 0 and upperband.iloc[i] > upperband.iloc[i - 1]:
            upperband.iloc[i] = upperband.iloc[i - 1]

        if dir_[i] > 0:
            trend[i] = long[i] = lowerband.iloc[i]
        else:
            trend[i] = short[i] = upperband.iloc[i]

    # Prepare DataFrame to return
    _props = f"_{length}_{multiplier}"
    df = DataFrame({
            f"SUPERT{_props}": trend,
            f"SUPERTd{_props}": dir_,
            f"SUPERTl{_props}": long,
            f"SUPERTs{_props}": short,
        }, index=close.index)

    df.name = f"SUPERT{_props}"
    df.category = "overlap"

    # Apply offset if needed
    if offset != 0:
        df = df.shift(offset)

    # Handle fills
    if "fillna" in kwargs:
        df.fillna(kwargs["fillna"], inplace=True)

    if "fill_method" in kwargs:
        df.fillna(method=kwargs["fill_method"], inplace=True)

    return df
