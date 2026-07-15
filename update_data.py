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
    text = text.replace(".", "-")
    if not re.match(r"^[A-Z0-9\-]+$", text):
        return None
    return text


def fetch_wikipedia_tables() -> list[pd.DataFrame]:
    response = requests.get(WIKI_URL, headers=HEADERS, timeout=30)
    response.raise_for_status()
    return pd.read_html(StringIO(response.text))


def flatten_column_name(column) -> str:
    if isinstance(column, tuple):
        parts = [
            str(x).strip()
            for x in column
            if str(x).strip().lower() not in {"", "nan"}
        ]
        return " ".join(parts)
    return str(column).strip()


def flatten_columns(df: pd.DataFrame) -> pd.DataFrame:
    out = df.copy()
    out.columns = [flatten_column_name(c) for c in out.columns]
    return out


def get_current_nasdaq100_tickers(tables: list[pd.DataFrame]) -> list[str]:
    candidates: list[list[str]] = []

    for table in tables:
        t = flatten_columns(table)
        for column in t.columns:
            normalized = re.sub(
                r"[^a-z0-9]+", " ", str(column).lower()
            ).strip()

            if "ticker" not in normalized and "symbol" not in normalized:
                continue

            tickers = (
                t[column]
                .map(clean_ticker)
                .dropna()
                .unique()
                .tolist()
            )

            if len(tickers) >= 90:
                candidates.append(sorted(tickers))

    if candidates:
        return min(candidates, key=lambda values: abs(len(values) - 101))

    raise RuntimeError(
        "Could not locate current Nasdaq-100 constituent table on Wikipedia."
    )


def load_cached_current_tickers() -> list[str]:
    if not CURRENT_TICKERS_FILE.exists():
        return []

    cached = pd.read_csv(CURRENT_TICKERS_FILE)
    if cached.empty:
        return []

    ticker_col = next(
        (
            c
            for c in cached.columns
            if "ticker" in str(c).lower()
            or "symbol" in str(c).lower()
        ),
        cached.columns[0],
    )

    return sorted(
        cached[ticker_col]
        .map(clean_ticker)
        .dropna()
        .unique()
        .tolist()
    )


def find_component_changes_table(
    tables: list[pd.DataFrame],
) -> pd.DataFrame:
    candidates: list[pd.DataFrame] = []

    for table in tables:
        t = flatten_columns(table)
        col_text = " ".join(str(c).lower() for c in t.columns)

        if (
            "date" in col_text
            and ("added" in col_text or "removed" in col_text)
        ):
            candidates.append(t)

    if not candidates:
        return pd.DataFrame(
            columns=["date", "added_ticker", "removed_ticker"]
        )

    return max(candidates, key=len)


def parse_component_changes(
    tables: list[pd.DataFrame],
) -> pd.DataFrame:
    raw = find_component_changes_table(tables)

    if raw.empty:
        return pd.DataFrame(
            columns=["date", "added_ticker", "removed_ticker"]
        )

    cols = list(raw.columns)
    lower = {c: str(c).lower() for c in cols}

    date_col = next(
        (c for c in cols if "date" in lower[c]),
        None,
    )

    if date_col is None:
        return pd.DataFrame(
            columns=["date", "added_ticker", "removed_ticker"]
        )

    added_cols = [
        c
        for c in cols
        if "added" in lower[c]
        and (
            "ticker" in lower[c]
            or "symbol" in lower[c]
        )
    ]

    removed_cols = [
        c
        for c in cols
        if "removed" in lower[c]
        and (
            "ticker" in lower[c]
            or "symbol" in lower[c]
        )
    ]

    if not added_cols:
        added_cols = [
            c for c in cols if "added" in lower[c]
        ]

    if not removed_cols:
        removed_cols = [
            c for c in cols if "removed" in lower[c]
        ]

    added_col = added_cols[0] if added_cols else None
    removed_col = removed_cols[0] if removed_cols else None

    records: list[dict] = []

    for _, row in raw.iterrows():
        date = pd.to_datetime(
            row.get(date_col),
            errors="coerce",
        )

        if pd.isna(date):
            continue

        added = (
            clean_ticker(row.get(added_col))
            if added_col
            else None
        )

        removed = (
            clean_ticker(row.get(removed_col))
            if removed_col
            else None
        )

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
        changes = (
            changes
            .sort_values("date")
            .reset_index(drop=True)
        )

    return changes


def historical_ticker_universe(
    current_tickers: list[str],
    changes: pd.DataFrame,
) -> list[str]:
    tickers = {
        t
        for t in (
            clean_ticker(x)
            for x in current_tickers
        )
        if t
    }

    if not changes.empty:
        for col in ["added_ticker", "removed_ticker"]:
            tickers.update(
                t
                for t in (
                    changes[col]
                    .map(clean_ticker)
                    .dropna()
                    .tolist()
                )
                if t
            )

    return sorted(tickers)


def download_adjusted_close(
    tickers: list[str],
    start: str,
) -> pd.DataFrame:
    raw = yf.download(
        tickers=tickers,
        start=start,
        auto_adjust=False,
        group_by="column",
        progress=False,
        threads=True,
    )

    if raw.empty:
        raise RuntimeError(
            "No price data downloaded from yfinance."
        )

    if isinstance(raw.columns, pd.MultiIndex):
        if "Adj Close" in raw.columns.get_level_values(0):
            prices = raw["Adj Close"].copy()
        elif "Close" in raw.columns.get_level_values(0):
            prices = raw["Close"].copy()
        else:
            raise RuntimeError(
                "Downloaded data does not contain "
                "Adj Close or Close."
            )
    else:
        col = (
            "Adj Close"
            if "Adj Close" in raw.columns
            else "Close"
        )
        prices = raw[[col]].rename(
            columns={col: tickers[0]}
        )

    prices.index = pd.to_datetime(prices.index)
    prices = (
        prices
        .sort_index()
        .dropna(axis=1, how="all")
    )
    prices.columns = [
        clean_ticker(c) or str(c)
        for c in prices.columns
    ]

    return prices


def main() -> None:
    DATA_DIR.mkdir(parents=True, exist_ok=True)

    tables: list[pd.DataFrame] = []

    try:
        tables = fetch_wikipedia_tables()
        current_tickers = (
            get_current_nasdaq100_tickers(tables)
        )
        print(
            "Fetched current Nasdaq-100 list "
            f"from Wikipedia ({len(current_tickers)} tickers)"
        )
    except Exception as exc:
        current_tickers = load_cached_current_tickers()

        if len(current_tickers) < 90:
            raise RuntimeError(
                "Wikipedia parsing failed and no valid cached "
                "Nasdaq-100 list is available."
            ) from exc

        print(
            "Warning: Wikipedia constituent retrieval failed; "
            f"using cached list with {len(current_tickers)} "
            f"tickers. Error: {exc}"
        )

    pd.DataFrame(
        {"ticker": current_tickers}
    ).to_csv(
        CURRENT_TICKERS_FILE,
        index=False,
    )

    print(
        "Saved current Nasdaq-100 list: "
        f"{CURRENT_TICKERS_FILE} "
        f"({len(current_tickers)} tickers)"
    )

    changes = parse_component_changes(tables)

    if (
        changes.empty
        and COMPONENT_CHANGES_FILE.exists()
    ):
        changes = pd.read_csv(
            COMPONENT_CHANGES_FILE,
            parse_dates=["date"],
        )
        print(
            "Warning: using cached component-change history."
        )

    changes.to_csv(
        COMPONENT_CHANGES_FILE,
        index=False,
    )

    print(
        "Saved component changes: "
        f"{COMPONENT_CHANGES_FILE} "
        f"({len(changes)} rows)"
    )

    all_tickers = historical_ticker_universe(
        current_tickers,
        changes,
    )

    pd.DataFrame(
        {"ticker": all_tickers}
    ).to_csv(
        ALL_HISTORICAL_TICKERS_FILE,
        index=False,
    )

    print(
        "Saved historical ticker universe: "
        f"{ALL_HISTORICAL_TICKERS_FILE} "
        f"({len(all_tickers)} unique tickers)"
    )

    prices = download_adjusted_close(
        all_tickers,
        START_DATE,
    )

    prices.to_csv(
        PRICE_FILE,
        index_label="date",
    )

    print(
        "Saved historical prices: "
        f"{PRICE_FILE}, shape={prices.shape}"
    )


if __name__ == "__main__":
    main()
