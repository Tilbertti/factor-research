import numpy as np
import pandas as pd


def portfolio_returns_drift(weights: pd.Series, returns: pd.DataFrame, start, end):
    """
    Buy at the close of `start` with `weights` and hold without rebalancing until the close of `end`.
    Weights drift with each stock's performance.

    Returns (daily portfolio returns, daily drifted weights) for the days after `start` up to `end`.
    """
    # The day after `start` up to and including `end`: `start`'s own return belongs to the previous period.
    data = returns.loc[start:end, weights.index].iloc[1:].astype("float64")

    # Missing return (non-trading day, or the stock stopped trading) = 0:
    # the position keeps its last value, as if the proceeds were held in cash.
    data = data.fillna(0.0)

    value = (1 + data).cumprod().mul(weights, axis=1)   # value of each position, start value = weight
    total = value.sum(axis=1)                           # portfolio value, start value = 1

    portfolio_returns = total.pct_change()
    if not portfolio_returns.empty:
        # The first day's return is measured against the starting value of 1.
        portfolio_returns.iloc[0] = total.iloc[0] - 1.0

    drift_weights = value.div(total, axis=0)
    return portfolio_returns, drift_weights


def weight_by_rank(scores: pd.Series, n: int) -> pd.Series:
    """Top n stocks, weighted by the square root of their rank: the best stock gets the largest weight."""
    portfolio = scores.nlargest(n)
    rank = portfolio.rank(ascending=True)   # 1 = weakest of the n, n = strongest
    rank_weight = np.sqrt(rank)
    return rank_weight / rank_weight.sum()


def equal_weight(scores: pd.Series, n: int) -> pd.Series:
    """Top n stocks, equal weights."""
    portfolio = scores.nlargest(n)
    return pd.Series(1.0 / len(portfolio), index=portfolio.index)


WEIGHT_FUNCTIONS = {
    "rank": weight_by_rank,
    "equal": equal_weight,
}
