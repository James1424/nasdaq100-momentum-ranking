from __future__ import annotations

from datetime import datetime, timezone

import pandas as pd

from config import (
    LATEST_RANKING_FILES,
    MOMENTUM_WINDOWS,
    MONTHLY_TOP3_CROSS_WINDOW_FILE,
    README_FILE,
    RANKING_WINDOWS_FOR_MONTHLY_TABLE,
)


PCT_COLUMNS = {
    "momentum",
    "month_to_date_return",
    "hold_1m_return",
    "hold_2m_return",
    "hold_3m_return",
}


def fmt_pct(x) -> str:
    if pd.isna(x):
        return ""
    return f"{float(x):.2%}"


def fmt_price(x) -> str:
    if pd.isna(x):
        return ""
    return f"{float(x):.2f}"


def to_markdown(df: pd.DataFrame) -> str:
    if df.empty:
        return "_No data available._"
    return df.to_markdown(index=False)


def format_latest_table(df: pd.DataFrame) -> pd.DataFrame:
    out = df.copy()
    for col in ["start_price", "end_price", "current_price"]:
        if col in out.columns:
            out[col] = out[col].map(fmt_price)
    for col in ["momentum", "month_to_date_return"]:
        if col in out.columns:
            out[col] = out[col].map(fmt_pct)

    preferred_cols = [
        "rank",
        "Ticker",
        "decision_date",
        "current_price_date",
        "start_price",
        "end_price",
        "current_price",
        "month_to_date_return",
        "momentum",
    ]
    return out[[col for col in preferred_cols if col in out.columns]]


def format_monthly_table(df: pd.DataFrame) -> pd.DataFrame:
    out = df.copy()
    for col in out.columns:
        if col.startswith("momentum_") or col in PCT_COLUMNS or col.startswith("hold_"):
            out[col] = out[col].map(fmt_pct)

    preferred_cols = [
        "decision_month",
        "decision_date",
        "ranking_window",
        "rank",
        "Ticker",
        "hold_1m_return",
        "hold_2m_return",
        "hold_3m_return",
    ] + [f"momentum_{w}m" for w in MOMENTUM_WINDOWS]
    return out[[col for col in preferred_cols if col in out.columns]]


def build_latest_sections() -> str:
    parts = []
    for window in MOMENTUM_WINDOWS:
        path = LATEST_RANKING_FILES[window]
        if path.exists():
            table = format_latest_table(pd.read_csv(path))
            table_md = to_markdown(table)
        else:
            table_md = f"_Missing file: `{path}`. Run `python run_all.py` to generate it._"

        parts.append(
            f"""
## Latest Nasdaq-100 {window}-Month Momentum Top 10 Ranking

This table ranks the point-in-time Nasdaq-100 universe as of the latest available month-start decision date. Momentum is calculated from the month-start price {window} months earlier to the decision-date month-start price. `month_to_date_return` is the return from the decision-date month-start price to the latest available daily adjusted close price.

{table_md}

Saved file: `{path}`
""".strip()
        )
    return "\n\n---\n\n".join(parts)


def build_monthly_sections() -> str:
    if not MONTHLY_TOP3_CROSS_WINDOW_FILE.exists():
        return f"_Missing file: `{MONTHLY_TOP3_CROSS_WINDOW_FILE}`. Run `python run_all.py` to generate it._"

    df = pd.read_csv(MONTHLY_TOP3_CROSS_WINDOW_FILE)
    if df.empty:
        return "_No monthly cross-window momentum data available._"

    # The CSV is already written latest month first, but this keeps the README robust.
    df["_decision_date_sort"] = pd.to_datetime(df["decision_date"], errors="coerce")
    df = df.sort_values(["_decision_date_sort", "ranking_window", "rank"], ascending=[False, True, True])

    parts: list[str] = []
    for decision_month, month_df in df.groupby("decision_month", sort=False):
        parts.append(f"### {decision_month}")

        for ranking_window in RANKING_WINDOWS_FOR_MONTHLY_TABLE:
            sub = month_df[month_df["ranking_window"] == ranking_window].copy()
            if sub.empty:
                continue

            sub = sub.drop(columns=["_decision_date_sort"])
            sub = format_monthly_table(sub)
            parts.append(
                f"""
#### {ranking_window}M Momentum Top 10

{to_markdown(sub)}
""".strip()
            )

    return "\n\n".join(parts)


def build_monthly_section() -> str:
    table_sections = build_monthly_sections()
    return f"""
## Monthly Top 10 Cross-Window Momentum Tables

These tables are split by month, starting from the latest available month-start decision date and going backward to January 2016. For each month, the 4M, 5M, and 6M ranking windows are shown as separate Top 10 tables. For each selected stock, the tables report the stock's forward holding returns over the next 1M, 2M, and 3M, plus its 3M, 4M, 5M, 6M, and 7M momentum values at the same decision date. Blank hold-return cells mean the future month-start price is not available yet.

{table_sections}

Saved file: `{MONTHLY_TOP3_CROSS_WINDOW_FILE}`
""".strip()


def main() -> None:
    updated_at = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")
    latest_sections = build_latest_sections()
    monthly_section = build_monthly_section()

    readme = f"""# Nasdaq-100 Point-in-Time Momentum Ranking

This repository builds point-in-time Nasdaq-100 momentum ranking tables. It no longer assumes a fixed current Nasdaq-100 universe and it no longer forces a Top 3 portfolio backtest.

Author: Haoyang Luo

Last updated: **{updated_at}**

---

## Method

- Universe: point-in-time Nasdaq-100 constituents reconstructed from the current Nasdaq-100 list and historical component changes.
- Decision date: the first available trading day of each month.
- Momentum windows: 3, 4, 5, 6, and 7 months.
- Momentum definition: `end_price / start_price - 1` using month-start adjusted close prices.
- Latest ranking month-to-date return: latest available daily adjusted close price divided by decision-date month-start adjusted close price minus 1.
- Forward hold returns: `hold_1m_return`, `hold_2m_return`, and `hold_3m_return` measure returns from the decision-date month-start price to the month-start price 1, 2, and 3 months later.
- Ranking: each table ranks only stocks that were in the Nasdaq-100 universe at that decision date and have valid prices.

---

## Run Locally

```bash
pip install -r requirements.txt
python run_all.py
```

---

{latest_sections}

---

{monthly_section}

---

## Files

| File | Description |
|---|---|
| `data/nasdaq100_current_tickers.csv` | Current Nasdaq-100 constituents |
| `data/nasdaq100_component_changes.csv` | Nasdaq-100 added/removed history parsed from Wikipedia |
| `data/nasdaq100_all_historical_tickers.csv` | Current plus historical tickers used for price download |
| `data/nasdaq100_prices.csv` | Adjusted close price database |
| `output/latest_nasdaq100_3m_momentum_top10.csv` | Latest 3M momentum Top 10 ranking, including month-to-date return |
| `output/latest_nasdaq100_4m_momentum_top10.csv` | Latest 4M momentum Top 10 ranking, including month-to-date return |
| `output/latest_nasdaq100_5m_momentum_top10.csv` | Latest 5M momentum Top 10 ranking, including month-to-date return |
| `output/latest_nasdaq100_6m_momentum_top10.csv` | Latest 6M momentum Top 10 ranking, including month-to-date return |
| `output/latest_nasdaq100_7m_momentum_top10.csv` | Latest 7M momentum Top 10 ranking, including month-to-date return |
| `output/monthly_top10_cross_window_momentum.csv` | Monthly tables from latest month back to 2016-01: Top 10 by 4M/5M/6M, forward 1M/2M/3M holding returns, and 3M-7M momentum values |

---

## Disclaimer

This project is for educational and research purposes only. It is not financial advice. Momentum rankings can change quickly and historical performance does not guarantee future results.
"""

    README_FILE.write_text(readme, encoding="utf-8")
    print(f"Updated {README_FILE}")


if __name__ == "__main__":
    main()
