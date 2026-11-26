"""
Run one strategy end to end:

    config -> market data (cached) -> universe -> factor scores -> backtest -> results

Usage:
    python run_pipeline.py momentum_fi
    python run_pipeline.py momentum_us --refresh     # re-download the market's data first
"""

import argparse

import yaml

from data.loader import get_market_data, fetch_benchmark
from data.universe import build_universe
from factors.momentum import calculate_momentum, cross_sectional_zscore
from paths import SETTINGS
from portfolio.backtest import run_backtest
from portfolio.construction import WEIGHT_FUNCTIONS
from portfolio.save_results import save_results

# Factor name in config -> function that turns adjusted prices into scores.
FACTOR_FUNCTIONS = {
    "momentum": calculate_momentum,
}


def load_config() -> dict:
    with open(SETTINGS) as f:
        return yaml.safe_load(f)


def check_strategy(config: dict, name: str) -> dict:
    """Return the strategy's settings, or stop with a clear message if something is missing."""
    strategies = config.get("strategies", {})
    if name not in strategies:
        raise SystemExit(f"Unknown strategy {name!r}. Options: {', '.join(strategies)}")

    params = strategies[name]
    checks = [
        (params.get("market") in config.get("markets", {}), f"market {params.get('market')!r} is not under 'markets'"),
        (params.get("factor") in FACTOR_FUNCTIONS, f"factor must be one of {list(FACTOR_FUNCTIONS)}"),
        (params.get("weighting") in WEIGHT_FUNCTIONS, f"weighting must be one of {list(WEIGHT_FUNCTIONS)}"),
        (isinstance(params.get("n_positions"), int), "n_positions must be a whole number"),
        (isinstance(params.get("universe"), dict), "universe rules are missing"),
    ]
    errors = [message for ok, message in checks if not ok]
    if errors:
        raise SystemExit(f"Problems in strategy {name!r}:\n  - " + "\n  - ".join(errors))
    return params


def run(strategy_name: str, refresh: bool = False):
    config = load_config()
    params = check_strategy(config, strategy_name)
    market = params["market"]
    market_config = config["markets"][market]

    # 1. Data: loaded from data/<market>/, downloaded first if missing.
    data = get_market_data(market, market_config.get("exchanges"), refresh=refresh)
    prices = data["adjusted_close"]

    # 2. Universe: which stocks were tradable on each date.
    universe = build_universe(data["close"], data["volume"], **params["universe"])
    size = universe.sum(axis=1)
    print(f"Universe: {int(size.max())} stocks at most, {size[size > 0].mean():.0f} on average (on days with any)")

    # 3. Factor scores, only for eligible stocks.
    factor = FACTOR_FUNCTIONS[params["factor"]]
    scores = cross_sectional_zscore(factor(prices).where(universe))

    # 4. Backtest.
    returns = prices.pct_change()
    strategy_returns = run_backtest(returns, scores, params)
    total = (1 + strategy_returns).prod() - 1
    print(f"Backtest: {strategy_returns.index[0].date()} to {strategy_returns.index[-1].date()}, "
          f"total return {total:.1%}")

    # 5. Add benchmark to results if configured
    benchmark = None
    if params.get("benchmark"):
        benchmark = fetch_benchmark(params["benchmark"])
        benchmark = benchmark.reindex(strategy_returns.index).fillna(0.0)

    # 6. Results, with the full settings that produced them.
    save_results(strategy_returns, strategy_name, {"strategy": params, "market": {market: market_config}}, benchmark)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Run a factor strategy backtest.")
    parser.add_argument("strategy", help="strategy name from config/settings.yaml, e.g. momentum_fi")
    parser.add_argument("--refresh", action="store_true", help="re-download the market's data")
    args = parser.parse_args()
    run(args.strategy, refresh=args.refresh)
