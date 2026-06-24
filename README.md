# Nasdaq-100 Point-in-Time Momentum Ranking

This repository has been refactored to use point-in-time Nasdaq-100 constituents and multi-window momentum rankings.

Run:

```bash
pip install -r requirements.txt
python run_all.py
```

After running, README.md will be regenerated with:

- Latest Nasdaq-100 3M / 4M / 5M / 6M / 7M momentum Top 10 ranking tables.
- A recent 24-month table selecting Top 1 / 2 / 3 stocks by 4M, 5M, and 6M ranking windows and showing each selected stock's 3M-7M momentum values.

The old fixed-universe Top 3 monthly backtest section has been removed.
