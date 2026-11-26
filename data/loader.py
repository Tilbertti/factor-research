"""Download and cache EODHD market data: ticker lists, prices and volume.

Main entry point: get_market_data(market) -> loads data/<market>/ from disk,
or downloads it first if it isn't there yet.
"""

import asyncio
import json
import os

import aiohttp
import pandas as pd
import requests
from dotenv import load_dotenv
from tqdm.asyncio import tqdm_asyncio

from paths import market_dir, TICKERS_FILE, PRICES_FILE, CLOSES_FILE, VOLUME_FILE, FAILED_FILE

load_dotenv(os.path.expanduser("~/.secrets/api_keys.env"))
API_KEY = os.getenv("EODHD_API_TOKEN")

# Which EODHD column is saved to which file.
EOD_FIELDS = {
    "adjusted_close": PRICES_FILE,   # for returns and factors
    "close": CLOSES_FILE,            # raw close, for traded value and price filters
    "volume": VOLUME_FILE,
}


def _require_api_key():
    if not API_KEY:
        raise RuntimeError("EODHD_API_TOKEN not found. Add it to ~/.secrets/api_keys.env")


# ---------------------------------------------------------------------------
# Ticker lists
# ---------------------------------------------------------------------------

def _get_symbol_list(market: str, delisted: bool) -> pd.DataFrame:
    """Download EODHD's symbol list for one exchange (active or delisted)."""
    params = {"api_token": API_KEY, "fmt": "json"}
    if delisted:
        params["delisted"] = 1

    resp = requests.get(f"https://eodhd.com/api/exchange-symbol-list/{market}", params=params, timeout=60)
    # Don't use raise_for_status(): its message contains the full URL, including the API key.
    if resp.status_code != 200:
        raise RuntimeError(f"Symbol list for {market} (delisted={delisted}) failed: HTTP {resp.status_code}")

    data = resp.json()
    if not isinstance(data, list):
        raise RuntimeError(f"Unexpected response for {market} (delisted={delisted}): {str(data)[:200]}")

    df = pd.DataFrame(data)
    df["Delisted"] = delisted
    return df


def fetch_tickers(market: str, exchanges: list | None = None) -> pd.DataFrame:
    """
    All common stocks ever listed on `market` (active + delisted), one row per ticker.

    Filters only on static facts about the instrument (type, ISIN, exchange).
    Price and volume filters belong in build_universe, point-in-time.

    market:    EODHD exchange code, e.g. "US" or "HE"
    exchanges: optional list of allowed values in the "Exchange" column,
               e.g. ["NYSE", "NASDAQ", "NYSE MKT"] to drop US OTC stocks.
               None = keep everything.
    """
    _require_api_key()
    df = pd.concat(
        [_get_symbol_list(market, delisted=False), _get_symbol_list(market, delisted=True)],
        ignore_index=True,
    )
    print(f"{market}: {len(df)} instruments in symbol lists")

    # Static filters: common stocks with an ISIN.
    has_isin = df["Isin"].fillna("").str.strip() != ""
    df = df[(df["Type"] == "Common Stock") & has_isin]

    if exchanges:
        df = df[df["Exchange"].isin(exchanges)]

    if df.empty:
        raise ValueError(f"No tickers left for {market}. Check the exchange names in config.")

    # Full ticker for the API, e.g. "AAPL.US" or "NOKIA.HE".
    df["Ticker"] = df["Code"] + f".{market}"

    # The same code can appear in both lists (a ticker reused by a new company).
    # EODHD returns one price series per code, so keep one row (the active one comes first).
    n_dupes = df["Ticker"].duplicated().sum()
    if n_dupes:
        print(f"{market}: {n_dupes} tickers appear in both active and delisted lists, keeping the active row")
    df = df.drop_duplicates("Ticker", keep="first")

    print(f"{market}: {len(df)} common stocks after filtering")
    columns = ["Ticker", "Code", "Name", "Exchange", "Isin", "Currency", "Delisted"]
    return df[columns].reset_index(drop=True)


# ---------------------------------------------------------------------------
# Prices and volume
# ---------------------------------------------------------------------------

async def _fetch_eod(session: aiohttp.ClientSession, sem: asyncio.Semaphore, ticker: str):
    """Download daily EOD data for one full ticker (e.g. "NOKIA.HE"). Returns (ticker, DataFrame or None)."""
    url = f"https://eodhd.com/api/eod/{ticker}"
    params = {"api_token": API_KEY, "fmt": "json", "period": "d"}
    async with sem:
        try:
            async with session.get(url, params=params, timeout=aiohttp.ClientTimeout(total=60)) as resp:
                resp.raise_for_status()
                data = await resp.json(content_type=None)

            # EODHD returns a list of rows on success; anything else (error dict, empty list) is a failure.
            if not isinstance(data, list) or not data:
                raise ValueError("no data returned")

            df = pd.DataFrame(data)
            df["date"] = pd.to_datetime(df["date"])
            df = df.set_index("date")[list(EOD_FIELDS)]
            return ticker, df[~df.index.duplicated(keep="last")]
        except Exception as e:
            # Print only the error type: some exception messages contain the URL, which includes the API key.
            print(f"  [FAILED] {ticker}: {type(e).__name__}")
            return ticker, None


async def _download_eod(tickers: list, concurrency: int):
    sem = asyncio.Semaphore(concurrency)
    async with aiohttp.ClientSession() as session:
        tasks = [_fetch_eod(session, sem, t) for t in tickers]
        results = await tqdm_asyncio.gather(*tasks, desc="Fetching prices")

    downloaded = {t: df for t, df in results if df is not None}
    failed = [t for t, df in results if df is None]
    return downloaded, failed


def save_prices(tickers: list, market: str, concurrency: int = 10) -> dict:
    """
    Download adjusted close, raw close and volume for full tickers and save them to data/<market>/.
    Returns {"adjusted_close": df, "close": df, "volume": df}, each with dates as rows and tickers as columns.
    """
    _require_api_key()
    folder = market_dir(market)
    folder.mkdir(parents=True, exist_ok=True)

    downloaded, failed = asyncio.run(_download_eod(tickers, concurrency))
    if not downloaded:
        raise RuntimeError(f"{market}: every download failed. Check the API key and plan limits.")

    frames = {}
    for field, filename in EOD_FIELDS.items():
        wide = pd.DataFrame({t: df[field] for t, df in downloaded.items()}).sort_index()
        wide = wide.astype("float32")   # half the memory of float64, plenty precise for prices
        wide.to_parquet(folder / filename)
        frames[field] = wide
        print(f"Saved {field}: {wide.shape[1]} tickers, {wide.shape[0]} dates -> {market}/{filename}")

    # Always overwrite, so an old failure list never lingers after a successful run.
    (folder / FAILED_FILE).write_text(json.dumps(failed, indent=2))
    if failed:
        print(f"{len(failed)} of {len(tickers)} tickers failed — saved to {market}/{FAILED_FILE}")

    return frames


# ---------------------------------------------------------------------------
# Cache: load from disk, download only when needed
# ---------------------------------------------------------------------------

def _cached_files(market: str) -> list:
    folder = market_dir(market)
    return [folder / TICKERS_FILE] + [folder / f for f in EOD_FIELDS.values()]


def load_market_data(market: str) -> dict:
    """Read saved data for a market. Same format as save_prices returns."""
    folder = market_dir(market)
    return {field: pd.read_parquet(folder / filename) for field, filename in EOD_FIELDS.items()}


def get_market_data(market: str, exchanges: list | None = None, refresh: bool = False,
                    max_fill_days: int = 5) -> dict:
    """
    Return price and volume data for a market.
    Uses the files in data/<market>/ if they exist; otherwise (or with refresh=True) downloads them first.

    Prices are forward-filled over gaps of up to `max_fill_days` (a missing day becomes a 0% return).
    This also covers stray dates, such as a single ticker with a price on an exchange holiday,
    which would otherwise leave every other stock with a missing day.
    The files on disk stay raw; filling happens only in memory.
    """
    if not refresh and all(path.exists() for path in _cached_files(market)):
        print(f"{market}: using cached data in {market_dir(market)}")
        data = load_market_data(market)
    else:
        print(f"{market}: downloading ticker list and full price history")
        tickers = fetch_tickers(market, exchanges)
        market_dir(market).mkdir(parents=True, exist_ok=True)
        tickers.to_parquet(market_dir(market) / TICKERS_FILE, index=False)
        data = save_prices(tickers["Ticker"].tolist(), market)

    # Fill prices only. A missing volume stays missing: the traded-value median skips it.
    for field in ("adjusted_close", "close"):
        data[field] = data[field].ffill(limit=max_fill_days)
    return data


def fetch_benchmark(ticker):
    url = f"https://eodhd.com/api/eod/{ticker}"
    params = {"api_token": API_KEY, "fmt": "json", "period": "d"}
    resp = requests.get(url, params=params, timeout=60)
    if resp.status_code != 200:
        raise RuntimeError (f'Benchmark {ticker} failed. Status code: {resp.status_code}')

    data = resp.json()
    if not isinstance(data, list) or not data:
        raise RuntimeError (f'No data for benchmark {ticker}. Check the ticker on EODHD.')
    prices = pd.DataFrame(data)
    prices['date'] = pd.to_datetime(prices['date'])
    prices = prices.set_index("date")['adjusted_close']
    return prices.pct_change().dropna().rename(ticker)