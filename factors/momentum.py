import numpy as np
import pandas as pd


def calculate_momentum(prices: pd.DataFrame, lookback: int = 252, skip: int = 21,
                       vol_window: int = 252) -> pd.DataFrame:
    """
    Volatility-scaled 12-1 momentum.

    The return from `lookback` days ago to `skip` days ago (the most recent month is skipped
    because it tends to reverse), divided by the stock's daily volatility over the past year.
    Every value uses only prices up to that date.

    prices: adjusted close, dates x tickers. Returns scores in the same shape.
    """
    returns = prices.pct_change()
    momentum = prices.shift(skip) / prices.shift(lookback) - 1
    # min_periods: a few missing days inside the window shouldn't wipe out a whole year of scores.
    volatility = returns.rolling(vol_window, min_periods=int(vol_window * 0.8)).std().shift(1)
    scores = momentum / volatility
    # Zero volatility (e.g. a halted stock with a flat price) gives +/- infinity: treat as no score.
    return scores.replace([np.inf, -np.inf], np.nan)


def cross_sectional_zscore(scores: pd.DataFrame) -> pd.DataFrame:
    """Standardise each date's scores across stocks: mean 0, std 1."""
    return scores.sub(scores.mean(axis=1), axis=0).div(scores.std(axis=1), axis=0)
