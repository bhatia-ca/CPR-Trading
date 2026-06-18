# 📊 Paper Trading App

A Streamlit application that merges a trading scanner (CPR, ATR, pivots, confidence scoring) with a live dashboard.  
It simulates paper trades, logs them, and displays performance metrics and equity curve.

## Features
- CPR, ATR, and pivot-based scanner
- Confidence scoring for trade signals
- Paper trading engine with stop-loss and target exits
- Trade journal logging (`trade_journal.csv`)
- Streamlit dashboard with auto-refresh
- Performance metrics (win rate, net P&L, average profit/loss, max drawdown)
- Equity curve chart
- Mobile-friendly access via Streamlit Cloud

## Run locally
```bash
pip install -r requirements.txt
streamlit run app.py
