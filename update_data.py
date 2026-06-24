from __future__ import annotations

from io import StringIO
import re

import pandas as pd
import requests
import yfinance as yf

from config import (
    ALL_HISTORICAL_TICKERS_FILE,
    COMPONENT_CHANGES_FILE,
    CURRENT_TICKERS_FILE,
    DATA_DIR,
    PRICE_FILE,
    START_DATE,
    WIKI_URL,
)

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 "
        "KHTML, like Gecko) Chrome/120.0 Safari/537.36"
    ),
    "Accept-Language": "en-US,en;q=0.9",
}


def clean_ticker(value) -> str | None:
    if value is None or pd.isna(value):
        return None
    text = str(value).strip().upper()
    if not text or text in {"NAN", "NONE", "—", "-"}:
        return None
    text = re.sub(r"\[.*?\]", "", text)
    text = re.sub(r"\(.*?\)", "", text)
    text = text.strip().split()[0]
    text = text.replace(".", "-")  # yfinance convention, e.g. BRK.B -> BRK-B
    if not re.match(r"^[A-Z0-9\-]+$", text):
        return None
    return text


def fetch_wikipedia_tables() -> list[pd.DataFrame]:
    response = requests.get(WIKI_URL, headers=HEADERS, timeout=30)
    response.raise_for_status()
    return pd.read_html(StringIO(response.text))


def get_current_nasdaq100_tickers(tables: list[pd.DataFrame]) -> list[str]:
    for table in tables:
        cols = {str(c).strip().lower(): c for c in table.columns}
        for key in ("ticker", "symbol"):
            if key in cols:
                tickers = table[cols[key]].map(clean_ticker).dropna().unique().tolist()
                if len(tickers) >= 90:
                    return sorted(tickers)
    raise RuntimeError("Could not locate current Nasdaq-100 constituent table on Wikipedia.")


def flatten_columns(df: pd.DataFrame) -> pd.DataFrame:
    out = df.copy()
    if isinstance(out.columns, pd.MultiIndex):
        out.columns = [" ".join(str(x) for x in col if str(x) != "nan").strip() for col in out.columns]
    else:
        out.columns = [str(c).strip() for c in out.columns]
    return out


def find_component_changes_table(tables: list[pd.DataFrame]) -> pd.DataFrame:
    candidates: list[pd.DataFrame] = []
    for table in tables:
        t = flatten_columns(table)
        col_text = " ".join(str(c).lower() for c in t.columns)
        if "date" in col_text and ("added" in col_text or "removed" in col_text):
            candidates.append(t)
    if not candidates:
        return pd.DataFrame(columns=["date", "added_ticker", "removed_ticker"])
    return max(candidates, key=len)


def parse_component_changes(tables: list[pd.DataFrame]) -> pd.DataFrame:
    raw = find_component_changes_table(tables)
    if raw.empty:
        return pd.DataFrame(columns=["date", "added_ticker", "removed_ticker"])

    cols = list(raw.columns)
    lower = {c: str(c).lower() for c in cols}
    date_col = next((c for c in cols if "date" in lower[c]), None)
    if date_col is None:
        return pd.DataFrame(columns=["date", "added_ticker", "removed_ticker"])

    added_cols = [c for c in cols if "added" in lower[c] and ("ticker" in lower[c] or "symbol" in lower[c])]
    removed_cols = [c for c in cols if "removed" in lower[c] and ("ticker" in lower[c] or "symbol" in lower[c])]
    if not added_cols:
        added_cols = [c for c in cols if "added" in lower[c]]
    if not removed_cols:
        removed_cols = [c for c in cols if "removed" in lower[c]]

    added_col = added_cols[0] if added_cols else None
    removed_col = removed_cols[0] if removed_cols else None

    records: list[dict] = []
    for _, row in raw.iterrows():
        date = pd.to_datetime(row.get(date_col), errors="coerce")
        if pd.isna(date):
            continue
        added = clean_ticker(row.get(added_col)) if added_col else None
        removed = clean_ticker(row.get(removed_col)) if removed_col else None
        if added or removed:
            records.append(
                {
                    "date": date.date().isoformat(),
                    "added_ticker": added,
                    "removed_ticker": removed,
                }
            )

    changes = pd.DataFrame(records).drop_duplicates()
    if not changes.empty:
        changes["date"] = pd.to_datetime(changes["date"])
        changes = changes.sort_values("date").reset_index(drop=True)
    return changes


def historical_ticker_universe(current_tickers: list[str], changes: pd.DataFrame) -> list[str]:
    tickers = {t for t in (clean_ticker(x) for x in current_tickers) if t}
    if not changes.empty:
        for col in ["added_ticker", "removed_ticker"]:
            tickers.update(t for t in changes[col].map(clean_ticker).dropna().tolist() if t)
    return sorted(tickers)


def download_adjusted_close(tickers: list[str], start: str) -> pd.DataFrame:
    raw = yf.download(
        tickers=tickers,
        start=start,
        auto_adjust=False,
        group_by="column",
        progress=False,
        threads=True,
    )
    if raw.empty:
        raise RuntimeError("No price data downloaded from yfinance.")

    if isinstance(raw.columns, pd.MultiIndex):
        if "Adj Close" in raw.columns.get_level_values(0):
            prices = raw["Adj Close"].copy()
        elif "Close" in raw.columns.get_level_values(0):
            prices = raw["Close"].copy()
        else:
            raise RuntimeError("Downloaded data does not contain Adj Close or Close.")
    else:
        col = "Adj Close" if "Adj Close" in raw.columns else "Close"
        prices = raw[[col]].rename(columns={col: tickers[0]})

    prices.index = pd.to_datetime(prices.index)
    prices = prices.sort_index().dropna(axis=1, how="all")
    prices.columns = [clean_ticker(c) or str(c) for c in prices.columns]
    return prices


def main() -> None:
    DATA_DIR.mkdir(parents=True, exist_ok=True)

    tables = fetch_wikipedia_tables()
    current_tickers = get_current_nasdaq100_tickers(tables)
    pd.DataFrame({"ticker": current_tickers}).to_csv(CURRENT_TICKERS_FILE, index=False)
    print(f"Saved current Nasdaq-100 list: {CURRENT_TICKERS_FILE} ({len(current_tickers)} tickers)")

    changes = parse_component_changes(tables)
    changes.to_csv(COMPONENT_CHANGES_FILE, index=False)
    print(f"Saved component changes: {COMPONENT_CHANGES_FILE} ({len(changes)} rows)")

    all_tickers = historical_ticker_universe(current_tickers, changes)
    pd.DataFrame({"ticker": all_tickers}).to_csv(ALL_HISTORICAL_TICKERS_FILE, index=False)
    print(f"Saved historical ticker universe: {ALL_HISTORICAL_TICKERS_FILE} ({len(all_tickers)} unique tickers)")

    prices = download_adjusted_close(all_tickers, START_DATE)
    prices.to_csv(PRICE_FILE, index_label="date")
    print(f"Saved historical prices: {PRICE_FILE}, shape={prices.shape}")


if __name__ == "__main__":
    main()
