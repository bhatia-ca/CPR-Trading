import streamlit as st
import pandas as pd
import yfinance as yf
import csv
import time
from datetime import datetime

journal_file = "trade_journal.csv"

# Initialize journal file if not exists
try:
    pd.read_csv(journal_file)
except FileNotFoundError:
    with open(journal_file, mode="w", newline="") as file:
        writer = csv.writer(file)
        writer.writerow(["Timestamp","Symbol","Side","Qty","Entry","Exit","StopLoss","Target","PnL"])

portfolio = {}

# -------------------------------
# Scanner Functions (CPR, ATR, Pivots)
# -------------------------------
def calculate_cpr(df):
    high, low, close = df['High'].iloc[-2], df['Low'].iloc[-2], df['Close'].iloc[-2]
    pivot = (high + low + close) / 3
    bc = (high + low) / 2
    tc = (pivot + bc) / 2
    return {'Pivot': pivot, 'BC': bc, 'TC': tc, 'Range': abs(tc - bc)}

def calculate_atr(df, period=14):
    df['H-L'] = df['High'] - df['Low']
    df['H-C'] = abs(df['High'] - df['Close'].shift())
    df['L-C'] = abs(df['Low'] - df['Close'].shift())
    df['TR'] = df[['H-L','H-C','L-C']].max(axis=1)
    df['ATR'] = df['TR'].rolling(period).mean()
    return df['ATR'].iloc[-1]

def calculate_pivots(df):
    high, low, close = df['High'].iloc[-2], df['Low'].iloc[-2], df['Close'].iloc[-2]
    pp = (high + low + close) / 3
    r1 = (2 * pp) - low
    s1 = (2 * pp) - high
    return {'PP': pp, 'R1': r1, 'S1': s1}

def trend_bias(df, cpr):
    last_close = df['Close'].iloc[-1]
    if last_close > cpr['TC']:
        return "Bullish Bias"
    elif last_close < cpr['BC']:
        return "Bearish Bias"
    else:
        return "Neutral Bias"

def confidence_score(df, cpr, atr, pivots):
    score = 0
    last_close = df['Close'].iloc[-1]
    if cpr['Range'] < (0.1 * atr): score += 40
    bias = trend_bias(df, cpr)
    if bias == "Bullish Bias" and last_close > pivots['PP']: score += 30
    elif bias == "Bearish Bias" and last_close < pivots['PP']: score += 30
    if abs(last_close - pivots['R1']) < (0.05 * atr) or abs(last_close - pivots['S1']) < (0.05 * atr):
        score += 30
    return score, bias

# -------------------------------
# Paper Trading Engine
# -------------------------------
def log_trade(symbol, side, qty, entry, exit_price, stop_loss, target, pnl):
    with open(journal_file, mode="a", newline="") as file:
        writer = csv.writer(file)
        writer.writerow([datetime.now(), symbol, side, qty, entry, exit_price, stop_loss, target, round(pnl,2)])

def paper_trade(symbol, side, qty, entry, stop_loss, target):
    portfolio[symbol] = {"side": side,"qty": qty,"entry": entry,"stop_loss": stop_loss,"target": target}
    st.write(f"📥 Paper {side.upper()} {qty} {symbol} @ {entry} | SL={stop_loss}, Target={target}")

def check_exit(symbol, current_price):
    if symbol not in portfolio: return
    trade = portfolio[symbol]
    side = trade["side"]

    if side == "buy":
        if current_price <= trade["stop_loss"] or current_price >= trade["target"]:
            pnl = (current_price - trade["entry"]) * trade["qty"]
            log_trade(symbol, side, trade["qty"], trade["entry"], current_price, trade["stop_loss"], trade["target"], pnl)
            del portfolio[symbol]
    elif side == "sell":
        if current_price >= trade["stop_loss"] or current_price <= trade["target"]:
            pnl = (trade["entry"] - current_price) * trade["qty"]
            log_trade(symbol, side, trade["qty"], trade["entry"], current_price, trade["stop_loss"], trade["target"], pnl)
            del portfolio[symbol]

# -------------------------------
# Streamlit UI
# -------------------------------
st.set_page_config(page_title="Paper Trading App", layout="wide")
st.title("📊 Paper Trading App (Scanner + Live Dashboard)")

tickers = st.text_input("Enter tickers (comma separated)", "RELIANCE.NS,TCS.NS,INFY.NS").split(",")

if st.button("Run Scanner"):
    for ticker in tickers:
        df = yf.download(ticker.strip(), period="30d", interval="1d")
        cpr = calculate_cpr(df)
        atr = calculate_atr(df)
        pivots = calculate_pivots(df)
        score, bias = confidence_score(df, cpr, atr, pivots)

        if score >= 80:
            last_close = df['Close'].iloc[-1]
            if bias == "Bullish Bias":
                stop_loss = last_close - atr
                target = pivots['R1']
                paper_trade(ticker.strip(), "buy", qty=10, entry=last_close, stop_loss=stop_loss, target=target)
            elif bias == "Bearish Bias":
                stop_loss = last_close + atr
                target = pivots['S1']
                paper_trade(ticker.strip(), "sell", qty=10, entry=last_close, stop_loss=stop_loss, target=target)

# Live monitoring loop (runs while portfolio has trades)
if portfolio:
    st.subheader("🔄 Live Monitoring")
    st.write("Checking exits every 1 minute...")
    for symbol in list(portfolio.keys()):
        try:
            live_df = yf.download(symbol, period="1d", interval="1m")
            current_price = live_df['Close'].iloc[-1]
            check_exit(symbol, current_price)
        except Exception as e:
            st.write(f"Error fetching live data for {symbol}: {e}")

# Show trade journal
try:
    df = pd.read_csv(journal_file)
    st.subheader("Trade Journal")
    st.dataframe(df)

    # Performance metrics
    total_trades = len(df)
    wins = len(df[df['PnL'] > 0])
    losses = len(df[df['PnL'] <= 0])
    win_rate = (wins / total_trades) * 100 if total_trades > 0 else 0
    avg_profit = df['PnL'][df['PnL'] > 0].mean() if wins > 0 else 0
    avg_loss = df['PnL'][df['PnL'] <= 0].mean() if losses > 0 else 0
    net_pnl = df['PnL'].sum()
    equity_curve = df['PnL'].cumsum()

    st.subheader("Performance Metrics")
    col1, col2, col3 = st.columns(3)
    col1.metric("Total Trades", total_trades)
    col2.metric("Win Rate", f"{round(win_rate,2)}%")
    col3.metric("Net P&L", round(net_pnl,2))

    st.line_chart(equity_curve)

except Exception as e:
    st.warning("No trades logged yet.")
    st.text(f"Error: {e}")
