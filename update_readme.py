from __future__ import annotations

from datetime import datetime, timezone

import pandas as pd

from config import (
    LATEST_RANKING_FILES,
    MOMENTUM_WINDOWS,
    MONTHLY_TOP3_CROSS_WINDOW_FILE,
    README_FILE,
)


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
    for col in ["start_price", "end_price"]:
        if col in out.columns:
            out[col] = out[col].map(fmt_price)
    if "momentum" in out.columns:
        out["momentum"] = out["momentum"].map(fmt_pct)
    return out[["rank", "Ticker", "decision_date", "start_price", "end_price", "momentum"]]


def format_monthly_table(df: pd.DataFrame) -> pd.DataFrame:
    out = df.copy()
    for col in out.columns:
        if col.startswith("momentum_"):
            out[col] = out[col].map(fmt_pct)
    return out


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

This table ranks the point-in-time Nasdaq-100 universe as of the latest available month-start decision date. Momentum is calculated from the month-start price {window} months earlier to the decision-date month-start price.

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
    for decision_month, sub in df.groupby("decision_month", sort=False):
        sub = sub.drop(columns=["_decision_date_sort"])
        sub = format_monthly_table(sub)
        parts.append(
            f"""
### {decision_month}

{to_markdown(sub)}
""".strip()
        )

    return "\n\n".join(parts)


def build_monthly_section() -> str:
    table_sections = build_monthly_sections()
    return f"""
## Monthly Top 3 Cross-Window Momentum Tables

These tables are split by month, starting from the latest available month-start decision date and going backward to January 2016. For each month, the table first selects rank 1 / 2 / 3 stocks using the 4M, 5M, and 6M momentum strategies. For each selected stock, it then reports that stock's 3M, 4M, 5M, 6M, and 7M momentum values at the same decision date.

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
| `output/latest_nasdaq100_3m_momentum_top10.csv` | Latest 3M momentum Top 10 ranking |
| `output/latest_nasdaq100_4m_momentum_top10.csv` | Latest 4M momentum Top 10 ranking |
| `output/latest_nasdaq100_5m_momentum_top10.csv` | Latest 5M momentum Top 10 ranking |
| `output/latest_nasdaq100_6m_momentum_top10.csv` | Latest 6M momentum Top 10 ranking |
| `output/latest_nasdaq100_7m_momentum_top10.csv` | Latest 7M momentum Top 10 ranking |
| `output/monthly_top3_cross_window_momentum.csv` | Monthly tables from latest month back to 2016-01: Top 3 by 4M/5M/6M and their 3M-7M momentum values |

---

## Disclaimer

This project is for educational and research purposes only. It is not financial advice. Momentum rankings can change quickly and historical performance does not guarantee future results.
"""

    README_FILE.write_text(readme, encoding="utf-8")
    print(f"Updated {README_FILE}")


if __name__ == "__main__":
    main()
