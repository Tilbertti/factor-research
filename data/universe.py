import pandas as pd


def build_universe(close: pd.DataFrame, volume: pd.DataFrame, top_n: int | None = None,
                   min_traded_value: float = 0, min_price: float = 0,
                   min_history: int = 252, window: int = 63) -> pd.DataFrame:
    """
    Point-in-time universe: True where a stock was eligible on that date.

    A stock is eligible when, using only data up to the previous day:
      - its median daily traded value (raw close x volume) over `window` days > min_traded_value
      - its raw close > min_price
      - it has at least `min_history` days of price history
      - (if top_n is set) it is among the top_n most traded of the stocks passing the rules above

    close, volume: dates x tickers, raw (unadjusted) close and volume.
    Values are in the market's own currency, so thresholds differ by market.
    """
    traded_value = (close * volume).rolling(window, min_periods=window // 2).median()

    eligible = (
        (traded_value > min_traded_value)
        & (close > min_price)
        & (close.notna().cumsum() >= min_history)   # enough data for 12-month momentum
    )

    if top_n:
        # Rank only the stocks that already pass the floor rules, 1 = most traded.
        rank = traded_value.where(eligible).rank(axis=1, ascending=False)
        eligible = eligible & (rank <= top_n)

    # Shift one day: today's decision may only use what was known yesterday.
    return eligible.shift(1, fill_value=False)
