"""All file locations in one place. Paths are built from this file's folder,
so they work no matter where the program is started from."""

from pathlib import Path

ROOT = Path(__file__).resolve().parent

CONFIG = ROOT / "config"
DATA = ROOT / "data"
RESULTS = ROOT / "results"

SETTINGS = CONFIG / "settings.yaml"

# Each market has its own folder (data/US/, data/HE/, ...) containing these files.
TICKERS_FILE = "tickers.parquet"      # ticker list with name, exchange, ISIN, delisted flag
PRICES_FILE = "prices.parquet"        # adjusted close: for returns and factors
CLOSES_FILE = "closes.parquet"        # raw close: for traded value and price filters
VOLUME_FILE = "volume.parquet"
FAILED_FILE = "failed_tickers.json"   # tickers whose download failed


def market_dir(market: str) -> Path:
    return DATA / market
