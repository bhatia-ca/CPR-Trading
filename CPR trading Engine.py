import streamlit as st
import pandas as pd
import yfinance as yf
import csv
from datetime import datetime
from zoneinfo import ZoneInfo

try:
    from streamlit_autorefresh import st_autorefresh
    AUTOREFRESH_AVAILABLE = True
except ImportError:
    AUTOREFRESH_AVAILABLE = False

IST = ZoneInfo("Asia/Kolkata")
journal_file = "trade_journal.csv"

# Initialize journal file if not exists
try:
    pd.read_csv(journal_file)
except FileNotFoundError:
    with open(journal_file, mode="w", newline="") as file:
        writer = csv.writer(file)
        writer.writerow(["Timestamp", "Symbol", "Side", "Qty", "Entry", "Exit", "StopLoss", "Target", "PnL"])

# -------------------------------
# Session state (fixes the "portfolio resets every rerun" bug)
# -------------------------------
if "portfolio" not in st.session_state:
    st.session_state.portfolio = {}

# -------------------------------
# Scanner Functions (CPR, ATR, Pivots)
# -------------------------------
def normalize_columns(df):
    """yfinance can return MultiIndex columns even for a single ticker depending on version."""
    if isinstance(df.columns, pd.MultiIndex):
        df.columns = df.columns.get_level_values(0)
    return df

def calculate_cpr(df):
    high, low, close = df['High'].iloc[-2], df['Low'].iloc[-2], df['Close'].iloc[-2]
    pivot = (high + low + close) / 3
    bc = (high + low) / 2
    tc = (pivot + bc) / 2
    return {'Pivot': pivot, 'BC': bc, 'TC': tc, 'Range': abs(tc - bc)}

def calculate_atr(df, period=14):
    df = df.copy()  # don't mutate the caller's dataframe
    df['H-L'] = df['High'] - df['Low']
    df['H-C'] = abs(df['High'] - df['Close'].shift())
    df['L-C'] = abs(df['Low'] - df['Close'].shift())
    df['TR'] = df[['H-L', 'H-C', 'L-C']].max(axis=1)
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
    if cpr['Range'] < (0.1 * atr):
        score += 40
    bias = trend_bias(df, cpr)
    if bias == "Bullish Bias" and last_close > pivots['PP']:
        score += 30
    elif bias == "Bearish Bias" and last_close < pivots['PP']:
        score += 30
    if abs(last_close - pivots['R1']) < (0.05 * atr) or abs(last_close - pivots['S1']) < (0.05 * atr):
        score += 30
    return score, bias

# -------------------------------
# Paper Trading Engine
# -------------------------------
def log_trade(symbol, side, qty, entry, exit_price, stop_loss, target, pnl):
    with open(journal_file, mode="a", newline="") as file:
        writer = csv.writer(file)
        writer.writerow([datetime.now(IST), symbol, side, qty, entry, exit_price, stop_loss, target, round(pnl, 2)])

def paper_trade(symbol, side, qty, entry, stop_loss, target):
    st.session_state.portfolio[symbol] = {
        "side": side, "qty": qty, "entry": entry,
        "stop_loss": stop_loss, "target": target
    }
    st.write(f"📥 Paper {side.upper()} {qty} {symbol} @ {entry:.2f} | SL={stop_loss:.2f}, Target={target:.2f}")

def check_exit(symbol, current_price):
    portfolio = st.session_state.portfolio
    if symbol not in portfolio:
        return
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
# Data fetch helpers
# -------------------------------
@st.cache_data(ttl=300)
def fetch_daily(ticker, period="30d", interval="1d"):
    df = yf.download(ticker, period=period, interval=interval, progress=False)
    return normalize_columns(df)

def fetch_live(ticker, period="1d", interval="1m"):
    df = yf.download(ticker, period=period, interval=interval, progress=False)
    return normalize_columns(df)

# -------------------------------
# Streamlit UI
# -------------------------------
st.set_page_config(page_title="Paper Trading App", layout="wide")
st.title("📊 Paper Trading App (Scanner + Live Dashboard)")

tickers = st.text_input("Enter tickers (comma separated)", "RELIANCE.NS,TCS.NS,INFY.NS").split(",")

col_run, col_clear = st.columns([1, 1])
with col_run:
    run_scanner = st.button("Run Scanner")
with col_clear:
    if st.button("Clear Open Positions"):
        st.session_state.portfolio = {}
        st.success("Open positions cleared.")

if run_scanner:
    for raw_ticker in tickers:
        ticker = raw_ticker.strip()
        if not ticker:
            continue
        try:
            df = fetch_daily(ticker)
            if df is None or df.empty or len(df) < 15:
                st.warning(f"⚠️ Not enough data for {ticker}, skipping.")
                continue

            cpr = calculate_cpr(df)
            atr = calculate_atr(df)
            pivots = calculate_pivots(df)

            if pd.isna(atr):
                st.warning(f"⚠️ ATR unavailable for {ticker} (not enough history), skipping.")
                continue

            score, bias = confidence_score(df, cpr, atr, pivots)

            if score >= 80:
                last_close = df['Close'].iloc[-1]
                if bias == "Bullish Bias":
                    stop_loss = last_close - atr
                    target = pivots['R1']
                    paper_trade(ticker, "buy", qty=10, entry=last_close, stop_loss=stop_loss, target=target)
                elif bias == "Bearish Bias":
                    stop_loss = last_close + atr
                    target = pivots['S1']
                    paper_trade(ticker, "sell", qty=10, entry=last_close, stop_loss=stop_loss, target=target)
            else:
                st.write(f"{ticker}: score {score}, {bias} — no trade (needs ≥80)")

        except Exception as e:
            st.error(f"❌ Error processing {ticker}: {e}")

# -------------------------------
# Live monitoring (auto-refreshes if streamlit-autorefresh is installed)
# -------------------------------
if st.session_state.portfolio:
    st.subheader("🔄 Live Monitoring")

    if AUTOREFRESH_AVAILABLE:
        st_autorefresh(interval=60_000, key="live_monitor_refresh")
        st.caption("Auto-refreshing every 60 seconds to check exits.")
    else:
        st.caption(
            "Install `streamlit-autorefresh` (`pip install streamlit-autorefresh`) "
            "for automatic periodic exit checks. Showing a manual refresh button instead."
        )
        st.button("🔁 Refresh prices now")

    for symbol in list(st.session_state.portfolio.keys()):
        try:
            live_df = fetch_live(symbol)
            if live_df is None or live_df.empty:
                st.write(f"No live data for {symbol} right now (market may be closed).")
                continue
            current_price = live_df['Close'].iloc[-1]
            check_exit(symbol, current_price)
        except Exception as e:
            st.write(f"Error fetching live data for {symbol}: {e}")

    if st.session_state.portfolio:
        st.write("**Open positions:**")
        st.dataframe(pd.DataFrame.from_dict(st.session_state.portfolio, orient="index"))

# -------------------------------
# Show trade journal
# -------------------------------
try:
    journal_df = pd.read_csv(journal_file)
    st.subheader("Trade Journal")
    st.dataframe(journal_df)

    # Performance metrics
    total_trades = len(journal_df)
    wins = len(journal_df[journal_df['PnL'] > 0])
    losses = len(journal_df[journal_df['PnL'] <= 0])
    win_rate = (wins / total_trades) * 100 if total_trades > 0 else 0
    avg_profit = journal_df.loc[journal_df['PnL'] > 0, 'PnL'].mean() if wins > 0 else 0
    avg_loss = journal_df.loc[journal_df['PnL'] <= 0, 'PnL'].mean() if losses > 0 else 0
    net_pnl = journal_df['PnL'].sum()
    equity_curve = journal_df['PnL'].cumsum()

    st.subheader("Performance Metrics")
    col1, col2, col3 = st.columns(3)
    col1.metric("Total Trades", total_trades)
    col2.metric("Win Rate", f"{round(win_rate, 2)}%")
    col3.metric("Net P&L", round(net_pnl, 2))

    st.line_chart(equity_curve)

except Exception as e:
    st.warning("No trades logged yet.")
    st.text(f"Error: {e}")
