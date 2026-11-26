import pandas as pd

from portfolio.construction import portfolio_returns_drift, WEIGHT_FUNCTIONS


def run_backtest(returns: pd.DataFrame, scores: pd.DataFrame, params: dict) -> pd.Series:
    """
    Periodic top-N rebalancing backtest.

    returns: daily stock returns, dates x tickers
    scores:  factor scores in the same shape; NaN = not eligible on that date
    params:  strategy config (weighting, n_positions, rebalance_freq)

    On each rebalance date the portfolio is formed from that day's scores, bought at the close,
    and held (weights drifting) until the next rebalance date.
    Returns daily portfolio returns, starting from the first date with any eligible stocks.
    """
    start = params.get("start_date")

    returns = returns.sort_index().loc[start:]
    scores = scores.sort_index().loc[start:]
    weight_func = WEIGHT_FUNCTIONS[params["weighting"]]

    # The last actual trading day of each period (e.g. each month).
    rebalance_dates = returns.index.to_series().resample(params["rebalance_freq"]).last().dropna()

    period_returns = []
    warmup_skips = 0     # empty dates before the first portfolio: expected (factor needs history)
    gap_skips = []       # empty dates after the first portfolio: a data or universe problem
    for start, end in zip(rebalance_dates.iloc[:-1], rebalance_dates.iloc[1:]):
        # Latest scores available on the rebalance date.
        pos = scores.index.searchsorted(start, side="right") - 1
        latest = scores.iloc[pos].dropna() if pos >= 0 else pd.Series(dtype=float)
        if latest.empty:
            if period_returns:
                gap_skips.append(start.date())
            else:
                warmup_skips += 1
            continue

        weights = weight_func(latest, params["n_positions"])
        period, _ = portfolio_returns_drift(weights, returns, start, end)
        period_returns.append(period)

    if not period_returns:
        raise ValueError("No rebalance date had any eligible stocks. Check the universe rules.")

    if warmup_skips:
        print(f"Backtest: skipped {warmup_skips} rebalance dates before the first stock had a score (warm-up)")
    if gap_skips:
        print(f"WARNING: {len(gap_skips)} rebalance dates had no eligible stocks and are missing from the results:")
        print("  " + ", ".join(str(d) for d in gap_skips))

    return pd.concat(period_returns)
