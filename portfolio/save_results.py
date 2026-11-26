import json

import pandas as pd
import quantstats as qs

from paths import RESULTS


def save_results(returns: pd.Series, strategy_name: str, config: dict):
    """
    Save a strategy's results to results/<strategy_name>/:
      strategy_returns.parquet  daily strategy returns
      config.json               the settings that produced them
      report.html               QuantStats performance report
    """
    returns = returns.rename(strategy_name)

    path = RESULTS / strategy_name
    path.mkdir(parents=True, exist_ok=True)

    returns.to_frame().to_parquet(path / "strategy_returns.parquet")

    with open(path / "config.json", "w") as f:
        json.dump(config, f, indent=4)

    qs.reports.html(returns, output=str(path / "report.html"), title=strategy_name)
    print(f"Results saved to {path}")
