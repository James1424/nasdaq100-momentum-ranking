from __future__ import annotations

import pandas as pd

from config import (
    BACKTEST_START,
    COMPONENT_CHANGES_FILE,
    CURRENT_TICKERS_FILE,
    LATEST_RANKING_FILES,
    MOMENTUM_WINDOWS,
    MONTHLY_TOP3_CROSS_WINDOW_FILE,
    OUTPUT_DIR,
    PRICE_FILE,
    RANKING_WINDOWS_FOR_MONTHLY_TABLE,
    TOP_N_LATEST,
    TOP_N_MONTHLY,
)


def clean_ticker(value) -> str | None:
    if value is None or pd.isna(value):
        return None
    text = str(value).strip().upper().replace(".", "-")
    return text if text and text not in {"NAN", "NONE", "—", "-"} else None


def load_current_tickers() -> set[str]:
    df = pd.read_csv(CURRENT_TICKERS_FILE)
    return {t for t in df["ticker"].map(clean_ticker).dropna().tolist() if t}


def load_component_changes() -> pd.DataFrame:
    df = pd.read_csv(COMPONENT_CHANGES_FILE)
    if df.empty:
        return pd.DataFrame(columns=["date", "added_ticker", "removed_ticker"])
    df["date"] = pd.to_datetime(df["date"], errors="coerce")
    df["added_ticker"] = df.get("added_ticker", pd.Series(index=df.index, dtype=object)).map(clean_ticker)
    df["removed_ticker"] = df.get("removed_ticker", pd.Series(index=df.index, dtype=object)).map(clean_ticker)
    return df.dropna(subset=["date"]).sort_values("date").reset_index(drop=True)


def universe_as_of(decision_date: pd.Timestamp, current_tickers: set[str], changes: pd.DataFrame) -> set[str]:
    """Reconstruct Nasdaq-100 constituents effective at decision_date.

    Start from today's current list and reverse every component change whose date
    is after the decision date. A change on or before the decision date remains
    reflected in the current-forward timeline.
    """
    membership = set(current_tickers)
    if changes.empty:
        return membership

    future_changes = changes[changes["date"] > decision_date].sort_values("date", ascending=False)
    for _, row in future_changes.iterrows():
        added = clean_ticker(row.get("added_ticker"))
        removed = clean_ticker(row.get("removed_ticker"))
        if added:
            membership.discard(added)
        if removed:
            membership.add(removed)
    return membership


def get_month_start_prices(daily_prices: pd.DataFrame) -> pd.DataFrame:
    daily_prices = daily_prices.sort_index()
    groups = daily_prices.groupby(daily_prices.index.to_period("M"))
    first_rows = []
    first_dates = []
    for _, group in groups:
        if group.empty:
            continue
        first_rows.append(group.iloc[0])
        first_dates.append(group.index[0])
    out = pd.DataFrame(first_rows, index=pd.DatetimeIndex(first_dates))
    out.index.name = "decision_date"
    return out


def compute_window_momentum(month_start_prices: pd.DataFrame, window: int) -> pd.DataFrame:
    """N-month momentum based on month-start adjusted close prices.

    At a month-start decision date, the window starts N month-start anchors ago
    and ends at the decision date. Momentum = end_price / start_price - 1.
    """
    return month_start_prices / month_start_prices.shift(window) - 1


def latest_completed_decision_date(month_start_prices: pd.DataFrame) -> pd.Timestamp:
    if len(month_start_prices) == 0:
        raise ValueError("No month-start prices available.")
    return month_start_prices.index[-1]


def valid_universe_for_date(
    decision_date: pd.Timestamp,
    month_start_prices: pd.DataFrame,
    current_tickers: set[str],
    changes: pd.DataFrame,
) -> list[str]:
    raw_universe = universe_as_of(decision_date, current_tickers, changes)
    universe = sorted(t for t in raw_universe if t in month_start_prices.columns)
    price_row = month_start_prices.loc[decision_date]
    return [t for t in universe if pd.notna(price_row.get(t, pd.NA))]


def build_latest_ranking(
    month_start_prices: pd.DataFrame,
    momentum_by_window: dict[int, pd.DataFrame],
    current_tickers: set[str],
    changes: pd.DataFrame,
    window: int,
) -> pd.DataFrame:
    decision_date = latest_completed_decision_date(month_start_prices)
    start_pos = month_start_prices.index.get_loc(decision_date) - window
    if start_pos < 0:
        raise ValueError(f"Not enough month-start history for {window}M momentum.")
    start_date = month_start_prices.index[start_pos]

    valid = valid_universe_for_date(decision_date, month_start_prices, current_tickers, changes)
    scores = momentum_by_window[window].loc[decision_date, valid].dropna().sort_values(ascending=False)
    top = scores.head(TOP_N_LATEST)

    rows = []
    for rank, (ticker, score) in enumerate(top.items(), start=1):
        rows.append(
            {
                "rank": rank,
                "Ticker": ticker,
                "decision_date": decision_date.strftime("%Y-%m-%d"),
                "start_price": float(month_start_prices.loc[start_date, ticker]),
                "end_price": float(month_start_prices.loc[decision_date, ticker]),
                "momentum": float(score),
            }
        )
    return pd.DataFrame(rows)


def build_monthly_cross_window_table(
    month_start_prices: pd.DataFrame,
    momentum_by_window: dict[int, pd.DataFrame],
    current_tickers: set[str],
    changes: pd.DataFrame,
) -> pd.DataFrame:
    """Build monthly Top-3 cross-window momentum records from latest month back to 2016-01."""
    backtest_start = pd.Timestamp(BACKTEST_START)
    dates = [d for d in month_start_prices.index if d >= backtest_start]
    dates = sorted(dates, reverse=True)
    rows: list[dict] = []

    for decision_date in dates:
        valid = valid_universe_for_date(decision_date, month_start_prices, current_tickers, changes)
        if not valid:
            continue

        for ranking_window in RANKING_WINDOWS_FOR_MONTHLY_TABLE:
            ranking_scores = momentum_by_window[ranking_window].loc[decision_date, valid].dropna().sort_values(ascending=False)
            selected = ranking_scores.head(TOP_N_MONTHLY)
            for rank, ticker in enumerate(selected.index.tolist(), start=1):
                row = {
                    "decision_month": decision_date.strftime("%Y-%m"),
                    "decision_date": decision_date.strftime("%Y-%m-%d"),
                    "ranking_window": ranking_window,
                    "rank": rank,
                    "Ticker": ticker,
                }
                for w in MOMENTUM_WINDOWS:
                    value = momentum_by_window[w].loc[decision_date].get(ticker, pd.NA)
                    row[f"momentum_{w}m"] = value if pd.notna(value) else pd.NA
                rows.append(row)

    return pd.DataFrame(rows)


def main() -> None:
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

    daily_prices = pd.read_csv(PRICE_FILE, index_col="date", parse_dates=True).sort_index()
    month_start_prices = get_month_start_prices(daily_prices)
    current_tickers = load_current_tickers()
    changes = load_component_changes()

    momentum_by_window = {
        window: compute_window_momentum(month_start_prices, window)
        for window in MOMENTUM_WINDOWS
    }

    for window in MOMENTUM_WINDOWS:
        latest = build_latest_ranking(
            month_start_prices=month_start_prices,
            momentum_by_window=momentum_by_window,
            current_tickers=current_tickers,
            changes=changes,
            window=window,
        )
        latest.to_csv(LATEST_RANKING_FILES[window], index=False)
        print(f"Saved {LATEST_RANKING_FILES[window]}")

    monthly = build_monthly_cross_window_table(
        month_start_prices=month_start_prices,
        momentum_by_window=momentum_by_window,
        current_tickers=current_tickers,
        changes=changes,
    )
    monthly.to_csv(MONTHLY_TOP3_CROSS_WINDOW_FILE, index=False)
    print(f"Saved {MONTHLY_TOP3_CROSS_WINDOW_FILE}")


if __name__ == "__main__":
    main()
