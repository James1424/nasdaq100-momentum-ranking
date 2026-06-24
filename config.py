from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent
DATA_DIR = PROJECT_ROOT / "data"
OUTPUT_DIR = PROJECT_ROOT / "output"

# Need extra history so 2016-01 can have valid 3M-7M signals.
START_DATE = "2014-01-01"
BACKTEST_START = "2016-01-01"

WIKI_URL = "https://en.wikipedia.org/wiki/Nasdaq-100"
MOMENTUM_WINDOWS = [3, 4, 5, 6, 7]
RANKING_WINDOWS_FOR_MONTHLY_TABLE = [4, 5, 6]
TOP_N_LATEST = 10
TOP_N_MONTHLY = 3

CURRENT_TICKERS_FILE = DATA_DIR / "nasdaq100_current_tickers.csv"
COMPONENT_CHANGES_FILE = DATA_DIR / "nasdaq100_component_changes.csv"
ALL_HISTORICAL_TICKERS_FILE = DATA_DIR / "nasdaq100_all_historical_tickers.csv"
PRICE_FILE = DATA_DIR / "nasdaq100_prices.csv"

README_FILE = PROJECT_ROOT / "README.md"

LATEST_RANKING_FILES = {
    window: OUTPUT_DIR / f"latest_nasdaq100_{window}m_momentum_top10.csv"
    for window in MOMENTUM_WINDOWS
}
MONTHLY_TOP3_CROSS_WINDOW_FILE = OUTPUT_DIR / "monthly_top3_cross_window_momentum.csv"
