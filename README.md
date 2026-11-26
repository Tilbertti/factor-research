# Factor Research

A small Python framework for backtesting systematic equity factor strategies on any market that EODHD covers.
The first factor is momentum, and the same code runs on the US market or on Nasdaq Helsinki by changing one line of config.

The project aims to be simple and to avoid common backtest biases:

- **No survivorship bias:** the ticker list includes delisted stocks, not just today's survivors.
- **No look-ahead bias:** the universe is decided point-in-time from information available the day before, and factor scores use only past prices.
- **Weights drift realistically:** between rebalances, weights drift with prices instead of being reset every day.

## Workflow

```text
config/settings.yaml
   │  strategy: market, universe rules, factor, portfolio settings
   ▼
1. Market data      data/<market>/        downloaded once, then loaded from disk
2. Universe         build_universe()      which stocks were tradable on each date
3. Factor scores    calculate_momentum()  computed in memory, only for eligible stocks
4. Backtest         run_backtest()        top-N portfolio, periodic rebalance
5. Results          results/<strategy>/   returns, config snapshot, QuantStats report
```

All of this runs with one command:

```bash
python run_pipeline.py momentum_fi
```

## Project structure

```text
FactorResearch/
├── run_pipeline.py          entry point: runs one strategy end to end
├── paths.py                 every file location in one place
├── config/settings.yaml     markets and strategies
├── data/
│   ├── loader.py            EODHD downloads + cache (ticker lists, prices, volume)
│   ├── universe.py          point-in-time universe rules
│   └── <market>/            cached data, e.g. data/HE/, data/US/ (not in git)
├── factors/
│   └── momentum.py          factor scores
├── portfolio/
│   ├── construction.py      weighting schemes and drifting-weight returns
│   ├── backtest.py          rebalancing loop
│   └── save_results.py      writes results/<strategy>/
└── results/<strategy>/      strategy_returns.parquet, config.json, report.html
```

## Setup

1. Create a virtual environment and install the dependencies (Windows):
   ```bash
   python -m venv .venv
   .venv\Scripts\python -m pip install -r requirements.txt
   ```
2. Put your EODHD API key in `~/.secrets/api_keys.env`, outside the project, so it can never be committed:
   ```text
   EODHD_API_TOKEN=your_key_here
   ```

## Running

```bash
python run_pipeline.py momentum_fi            # uses cached data if present, downloads it otherwise
python run_pipeline.py momentum_us --refresh  # re-downloads the market's data first
```

The first run for a market downloads the full price history of every stock ever listed there. For the US that is a large, slow download; Helsinki is quick.
Later runs read from `data/<market>/`. Use `--refresh` after changing a market's `exchanges` rule or when you want newer prices.

## Configuration

`config/settings.yaml` has two sections.

**`markets`** define *which instruments to download* for each EODHD exchange code. These are static filters only:

```yaml
markets:
  US:
    exchanges: ["NYSE", "NASDAQ", "NYSE MKT"]   # drops OTC stocks
  HE:
    exchanges: null                             # keep everything
```

All markets also keep only rows with `Type == "Common Stock"` and an ISIN.

**`strategies`** define *what to test*:

```yaml
strategies:
  momentum_fi:
    market: HE
    universe: {top_n: 50, min_traded_value: 1000000, min_price: 5, min_history: 252}
    factor: momentum
    n_positions: 10
    weighting: equal          # equal | rank
    rebalance_freq: ME        # pandas frequency, ME = month end
```

The universe rules are re-checked every day using the previous day's data:

| Rule | Meaning |
|---|---|
| `top_n` | keep the N most traded stocks that pass the other rules (`null` = no limit) |
| `min_traded_value` | median daily close × volume over ~3 months, in local currency |
| `min_price` | minimum raw close, in local currency |
| `min_history` | trading days of history required, so the factor can be computed |

To add a strategy, add a block under `strategies`. To add a market, add its EODHD exchange code under `markets`.

## Method

**Momentum score:** the return from 12 months ago to 1 month ago (the last month is skipped because short-term returns tend to reverse), divided by the stock's daily volatility over the past year. Scores are then standardised across the eligible stocks on each date.

**Portfolio:** on the last trading day of each period, buy the `n_positions` highest-scoring stocks at the close, weighted equally or by rank (where `rank` gives the best stock the largest weight). Hold them without rebalancing until the next rebalance date. A stock with no price on a day contributes a 0% return, so its position keeps its last value.

## Results

Each run writes `results/<strategy>/`:

- `strategy_returns.parquet`: daily strategy returns
- `config.json`: the exact strategy and market settings used
- `report.html`: QuantStats performance report

## Known limitations

- **No transaction costs or slippage.**
- **No data cleaning** beyond the universe filters. Extreme returns from bad ticks or split errors are not removed.
- **Delistings are treated as 0% returns** after the last price. A bankruptcy, which in reality is close to −100%, is therefore treated too kindly.
- **Reused tickers:** when an old and a new company share a ticker, EODHD has only one price series, and only one listing row is kept.
- **Downloads that fail are skipped** (listed in `data/<market>/failed_tickers.json`). If many delisted stocks fail, some survivorship bias remains.
- **No benchmark comparison** in the report yet.

## Ideas for later

- More factors (value, quality, low volatility) and multi-factor portfolios
- Benchmark comparison (an equal-weight universe portfolio, or a market index)
- Transaction cost model
- Portfolio size as a fraction of the universe, for fairer comparisons between markets
- A few `pytest` tests for the weighting and universe functions
