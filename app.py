import time
from datetime import datetime, timezone

import numpy as np
import pandas as pd
import plotly.graph_objects as go
import requests
import streamlit as st

# ============================================================
# SHOAIB DATA READER — FINAL BASE / EXPANDABLE ARCHITECTURE
# ============================================================

st.set_page_config(
    page_title="Shoaib Data Reader",
    page_icon="📊",
    layout="wide",
    initial_sidebar_state="expanded",
)

# ------------------------- LOCKED CORE -------------------------
LOCKED_PAIR = "EURUSD"
LOCKED_TIMEFRAME = "5 Minutes"
H20_START_UTC = 13
H20_END_UTC = 17
MIN_BARS = 60
STALE_LIMIT_MINUTES = 15
AUTO_TRADING = False
STRATEGY_LOCKED = True

# Validated H20 evidence — do not optimize from OOS results.
H20_VALIDATED_SIGNALS = 245
H20_FWD6_WIN_RATE = 60.00
H20_FWD6_AVG_ATR = 0.556601
H20_FWD20_WIN_RATE = 68.57
H20_FWD20_AVG_ATR = 1.377593

# ------------------------- UI CATALOG -------------------------
# These are interface choices. A choice becomes "validated" only
# after its own historical/OOS research has been completed.
CURRENCY_PAIRS = [
    "EURUSD", "GBPUSD", "USDJPY", "USDCHF", "AUDUSD", "USDCAD", "NZDUSD",
    "EURGBP", "EURJPY", "GBPJPY", "EURAUD", "EURCHF", "AUDJPY", "CADJPY",
]

CANDLE_OPTIONS = [
    "10 Seconds", "15 Seconds", "30 Seconds", "1 Minute", "2 Minutes",
    "5 Minutes", "15 Minutes", "30 Minutes",
]

EXPIRY_OPTIONS = [
    "15 Seconds", "30 Seconds", "1 Minute", "2 Minutes", "3 Minutes",
    "5 Minutes", "10 Minutes", "15 Minutes", "30 Minutes", "60 Minutes",
    "100 Minutes",
]

# Biquote OHLC intervals currently used by this live reader.
API_INTERVALS = {
    "1 Minute": "1m",
    "5 Minutes": "5m",
    "15 Minutes": "15m",
    "30 Minutes": "30m",
}

PAIR_LABELS = {
    "EURUSD": "EUR/USD",
    "GBPUSD": "GBP/USD",
    "USDJPY": "USD/JPY",
    "USDCHF": "USD/CHF",
    "AUDUSD": "AUD/USD",
    "USDCAD": "USD/CAD",
    "NZDUSD": "NZD/USD",
    "EURGBP": "EUR/GBP",
    "EURJPY": "EUR/JPY",
    "GBPJPY": "GBP/JPY",
    "EURAUD": "EUR/AUD",
    "EURCHF": "EUR/CHF",
    "AUDJPY": "AUD/JPY",
    "CADJPY": "CAD/JPY",
}

# ------------------------- SESSION STATE -------------------------
DEFAULTS = {
    "running": False,
    "analysis_requested": False,
    "analysis_completed": False,
    "analysis_interval": 10,
    "last_analysis_request": None,
    "last_refresh": None,
    "signal_history": set(),
}
for key, value in DEFAULTS.items():
    if key not in st.session_state:
        st.session_state[key] = value

# ------------------------- STYLE -------------------------
st.markdown(
    """
    <style>
    .block-container {max-width: 1500px; padding-top: 1rem;}
    .reader-title {font-size: 2rem; font-weight: 850; letter-spacing: .3px;}
    .reader-subtitle {color:#8b949e; margin-bottom:1rem;}
    .signal-box {border-radius:16px; padding:18px; border:1px solid rgba(128,128,128,.25); margin:8px 0;}
    .signal-title {font-size:.8rem; color:#8b949e; text-transform:uppercase; letter-spacing:.5px;}
    .signal-value {font-size:1.8rem; font-weight:850;}
    .small-text {font-size:.78rem; color:#8b949e;}
    </style>
    """,
    unsafe_allow_html=True,
)

st.markdown('<div class="reader-title">📊 SHOAIB DATA READER</div>', unsafe_allow_html=True)
st.markdown(
    '<div class="reader-subtitle">Professional multi-pair / multi-timeframe research reader</div>',
    unsafe_allow_html=True,
)

# ------------------------- SIDEBAR -------------------------
with st.sidebar:
    st.header("⚙️ Reader Controls")

    analysis_interval = st.select_slider(
        "Analysis Interval",
        options=[5, 10, 15, 30, 60],
        value=st.session_state.analysis_interval,
        format_func=lambda x: f"{x} seconds",
    )
    st.session_state.analysis_interval = analysis_interval

    st.divider()
    pair = st.selectbox(
        "💱 Currency Pair",
        CURRENCY_PAIRS,
        format_func=lambda x: PAIR_LABELS.get(x, x),
        key="selected_pair",
    )
    candle_selection = st.selectbox("🕯️ Candle Time", CANDLE_OPTIONS, key="selected_candle")
    expiry_selection = st.selectbox("⏱️ Trade / Expiry Time", EXPIRY_OPTIONS, index=5, key="selected_expiry")

    st.divider()
    analyze_button = st.button("🔎 ANALYZE SELECTED SETUP", use_container_width=True, type="primary")
    start_button = st.button("▶ Start", use_container_width=True)
    stop_button = st.button("⏹ Stop", use_container_width=True)
    now_button = st.button("🔍 Analyze Now", use_container_width=True)

    if analyze_button or now_button:
        st.session_state.analysis_requested = True
        st.session_state.analysis_completed = False
        st.session_state.last_analysis_request = {
            "pair": pair,
            "candle": candle_selection,
            "expiry": expiry_selection,
            "at": datetime.now(timezone.utc),
        }

    if start_button:
        st.session_state.running = True
    if stop_button:
        st.session_state.running = False

    st.divider()
    st.markdown("### 🔒 Strategy Safety")
    st.write("Strategy: LOCKED" if STRATEGY_LOCKED else "Strategy: UNLOCKED")
    st.write("Auto Trading: DISABLED" if not AUTO_TRADING else "Auto Trading: ENABLED")
    st.write("OOS optimization: DISABLED")

    st.divider()
    st.markdown("### 📌 Locked EUR/USD H20")
    st.write("Direction: BEARISH")
    st.write("Session: 13:00–17:00 UTC")
    st.write("Entry: Completed candle close")
    st.write("Extra filter: None")

# ------------------------- DATA FUNCTIONS -------------------------
def get_api_interval(candle_name):
    return API_INTERVALS.get(candle_name)


def api_url(symbol):
    return f"https://biquote.io/api/{symbol}/ohlc"


@st.cache_data(ttl=4, show_spinner=False)
def fetch_live_data(symbol, candle_name):
    interval = get_api_interval(candle_name)
    if interval is None:
        raise ValueError(
            f"{candle_name} is an interface option, but the current OHLC feed does not provide a native interval for it."
        )

    response = requests.get(
        api_url(symbol),
        params={"interval": interval, "limit": 101},
        headers={"User-Agent": "Mozilla/5.0"},
        timeout=10,
    )
    response.raise_for_status()
    payload = response.json()

    if "bars" not in payload or not payload["bars"]:
        raise ValueError("No live candles received")

    df = pd.DataFrame(payload["bars"])
    required = ["openTime", "open", "high", "low", "close"]
    missing = [c for c in required if c not in df.columns]
    if missing:
        raise ValueError(f"Missing feed columns: {missing}")

    df["Datetime"] = pd.to_datetime(df["openTime"], utc=True, errors="coerce")
    for column in ["open", "high", "low", "close"]:
        df[column] = pd.to_numeric(df[column], errors="coerce")

    df = (
        df.dropna(subset=["Datetime", "open", "high", "low", "close"])
        .drop_duplicates("Datetime", keep="last")
        .sort_values("Datetime")
        .reset_index(drop=True)
    )

    if len(df) < MIN_BARS:
        raise ValueError(f"Only {len(df)} valid candles received; {MIN_BARS} required")

    bad = (
        (df.high < df.low)
        | (df.high < df.open)
        | (df.high < df.close)
        | (df.low > df.open)
        | (df.low > df.close)
    )
    if bad.any():
        raise ValueError("OHLC integrity check failed")

    return df


def add_indicators(df):
    x = df.copy()
    x["EMA20"] = x.close.ewm(span=20, adjust=False).mean()
    x["EMA50"] = x.close.ewm(span=50, adjust=False).mean()
    previous_close = x.close.shift(1)
    x["TR"] = pd.concat(
        [
            x.high - x.low,
            (x.high - previous_close).abs(),
            (x.low - previous_close).abs(),
        ],
        axis=1,
    ).max(axis=1)
    x["ATR14"] = x.TR.rolling(14).mean()
    x["Support20"] = x.low.shift(1).rolling(20).min()
    x["Resistance20"] = x.high.shift(1).rolling(20).max()
    x["EMA_DIRECTION"] = np.where(x.EMA20 > x.EMA50, "BULL", "BEAR")
    return x


def candle_minutes(candle_name):
    mapping = {"1 Minute": 1, "2 Minutes": 2, "5 Minutes": 5, "15 Minutes": 15, "30 Minutes": 30}
    return mapping.get(candle_name)


def completed_candles(df, candle_name):
    minutes = candle_minutes(candle_name)
    if minutes is None:
        raise ValueError(f"Completed-candle logic is not yet connected to {candle_name}.")

    now = datetime.now(timezone.utc)
    completion = df.Datetime + pd.Timedelta(minutes=minutes)
    mask = completion <= pd.Timestamp(now)
    if "isOpen" in df.columns:
        mask &= ~df.isOpen.astype(bool)

    out = df.loc[mask].copy()
    if out.empty:
        raise ValueError("No completed candle is currently available")
    return out, now


def locked_h20_signal(row):
    session_active = H20_START_UTC <= int(row.Datetime.hour) < H20_END_UTC
    bearish = row.EMA_DIRECTION == "BEAR"

    if session_active and bearish:
        return "SELL", "H20 LOCKED: BEAR EMA direction + NY Core session", True
    if not session_active:
        return "NO SIGNAL", "Outside H20 NY Core session", False
    return "NO SIGNAL", "EMA direction is not BEAR", False


def validated_status(selected_pair, selected_candle, selected_expiry, signal):
    # Only the already validated EUR/USD 5m H20 horizons are labelled validated.
    if selected_pair != LOCKED_PAIR or selected_candle != LOCKED_TIMEFRAME or signal != "SELL":
        return "WAIT", None, None, "NOT VALIDATED"

    if selected_expiry == "30 Minutes":
        return "SELL", H20_FWD6_WIN_RATE, H20_FWD6_AVG_ATR, "VALIDATED"
    if selected_expiry == "100 Minutes":
        return "SELL", H20_FWD20_WIN_RATE, H20_FWD20_AVG_ATR, "VALIDATED"
    return "SELL", None, None, "ACTIVE / NOT DIRECTLY VALIDATED"


# ------------------------- LIVE DATA -------------------------
raw = pd.DataFrame()
df = pd.DataFrame()
completed_df = pd.DataFrame()
latest = None
signal = "NO SIGNAL"
reason = "Live feed unavailable"
ny_core = False
price = ema20 = ema50 = atr14 = support = resistance = np.nan
trend = "UNKNOWN"
candle_time = None
candle_age = None
market_status = "FEED ERROR"
freshness_ok = False
data_error = None

try:
    # The locked H20 engine remains tied to EUR/USD 5-minute data.
    # Other selections can load supported live data, but are not labelled validated.
    raw = fetch_live_data(pair, candle_selection)
    df = add_indicators(raw)
    completed_df, now_utc = completed_candles(df, candle_selection)
    latest = completed_df.iloc[-1]

    minutes = candle_minutes(candle_selection)
    close_time = latest.Datetime + pd.Timedelta(minutes=minutes)
    candle_time = latest.Datetime
    candle_age = (pd.Timestamp(now_utc) - close_time).total_seconds() / 60

    # H20 is intentionally evaluated only on its locked EUR/USD 5-minute setup.
    if pair == LOCKED_PAIR and candle_selection == LOCKED_TIMEFRAME:
        signal, reason, ny_core = locked_h20_signal(latest)
    else:
        signal = "NO SIGNAL"
        reason = "This pair/timeframe is available for research, but no locked validation rule is assigned."
        ny_core = False

    weekend = now_utc.weekday() >= 5
    market_status = "CLOSED — WEEKEND" if weekend else "OPEN"
    freshness_ok = weekend or (0 <= candle_age <= STALE_LIMIT_MINUTES)

    price = float(latest.close)
    ema20 = float(latest.EMA20)
    ema50 = float(latest.EMA50)
    atr14 = float(latest.ATR14) if pd.notna(latest.ATR14) else np.nan
    support = float(latest.Support20) if pd.notna(latest.Support20) else np.nan
    resistance = float(latest.Resistance20) if pd.notna(latest.Resistance20) else np.nan
    trend = latest.EMA_DIRECTION
    st.session_state.last_refresh = now_utc
except Exception as exc:
    data_error = str(exc)

# ------------------------- ANALYSIS -------------------------
if st.session_state.analysis_requested and not st.session_state.analysis_completed:
    with st.spinner("🔄 Analyzing selected market setup..."):
        time.sleep(4)
    st.session_state.analysis_completed = True

# ------------------------- TOP METRICS -------------------------
m1, m2, m3, m4, m5 = st.columns(5)
m1.metric("Live Price", f"{price:.5f}" if pd.notna(price) else "—")
m2.metric("Trend", trend)
m3.metric("EMA20", f"{ema20:.5f}" if pd.notna(ema20) else "—")
m4.metric("EMA50", f"{ema50:.5f}" if pd.notna(ema50) else "—")
m5.metric("ATR14", f"{atr14:.5f}" if pd.notna(atr14) else "—")

if st.session_state.last_analysis_request:
    q = st.session_state.last_analysis_request
    st.info(f"🔎 Selected setup: {PAIR_LABELS.get(q['pair'], q['pair'])} • {q['candle']} • {q['expiry']}")

# ------------------------- SELECTION STATUS -------------------------
st.markdown("### 🎛️ Selected Market Setup")
s1, s2, s3, s4 = st.columns(4)
s1.metric("Pair", PAIR_LABELS.get(pair, pair))
s2.metric("Candle", candle_selection)
s3.metric("Expiry", expiry_selection)
if pair == LOCKED_PAIR and candle_selection == LOCKED_TIMEFRAME:
    s4.metric("Strategy", "H20 LOCKED")
else:
    s4.metric("Strategy", "RESEARCH ONLY")

if candle_selection not in API_INTERVALS:
    st.warning(
        f"⚠️ {candle_selection} is visible as a future short-timeframe option, but the current OHLC endpoint does not provide a native candle for it. "
        "It will require tick-stream aggregation before live analysis can be enabled."
    )

if pair != LOCKED_PAIR or candle_selection != LOCKED_TIMEFRAME:
    st.info(
        "ℹ️ This pair/timeframe is selectable, but it has no validated trading rule yet. "
        "The reader will not manufacture a BUY/SELL prediction for it."
    )

# ------------------------- CURRENT SIGNAL -------------------------
st.markdown("### 🎯 Current Signal")
a, b, c = st.columns([1, 2, 1])
with a:
    css = "#2ecc71" if signal == "SELL" else "#e67e22"
    st.markdown(
        f'<div class="signal-box"><div class="signal-title">SIGNAL</div>'
        f'<div class="signal-value" style="color:{css}">{signal}</div></div>',
        unsafe_allow_html=True,
    )
with b:
    st.markdown(
        f'<div class="signal-box"><div class="signal-title">REASON</div>'
        f'<div style="font-size:1rem;font-weight:650">{reason}</div></div>',
        unsafe_allow_html=True,
    )
with c:
    st.markdown(
        f'<div class="signal-box"><div class="signal-title">NY CORE</div>'
        f'<div class="signal-value">{"ACTIVE" if ny_core else "INACTIVE"}</div></div>',
        unsafe_allow_html=True,
    )

# ------------------------- PROFESSIONAL ANALYSIS -------------------------
st.markdown("### 🧠 Professional Analysis")
p1, p2, p3 = st.columns(3)
p1.metric("Direction", "DOWN" if signal == "SELL" else "NO CLEAR DIRECTION")
p2.metric("Analysis", "H20 ACTIVE" if signal == "SELL" else "NO SIGNAL")
p3.metric("Current Trend", trend)

if signal == "SELL":
    st.success("🔻 H20 ANALYSIS: DOWN / SELL CONDITION CONFIRMED")
else:
    st.info("⏸️ No confirmed locked H20 direction at this moment.")

# ------------------------- VALIDATED PREDICTION -------------------------
if st.session_state.analysis_completed:
    st.markdown("### 🎯 Validated Prediction")
    prediction, rate, avg_atr, validation = validated_status(pair, candle_selection, expiry_selection, signal)

    v1, v2, v3 = st.columns(3)
    v1.metric("Prediction", prediction)
    v2.metric("Historical Rate", f"{rate:.2f}%" if rate is not None else "N/A")
    v3.metric("Status", validation)

    if validation == "VALIDATED":
        st.success("🔻 VALIDATED H20 SELL PREDICTION")
        st.caption(
            f"Locked OOS evidence • {H20_VALIDATED_SIGNALS:,} signals • "
            f"Historical rate {rate:.2f}% • Average directional move {avg_atr:.6f} ATR"
        )
    elif validation == "ACTIVE / NOT DIRECTLY VALIDATED":
        st.warning("⚠️ H20 SELL is active, but this selected expiry does not have a directly locked validation horizon.")
    else:
        st.info("⏸️ WAIT — No validated prediction is active for this setup.")

# ------------------------- CHART -------------------------
st.markdown("### 📈 Live Candlestick Chart")
if not df.empty and latest is not None:
    chart_df = df.tail(100)
    fig = go.Figure()
    fig.add_trace(
        go.Candlestick(
            x=chart_df.Datetime,
            open=chart_df.open,
            high=chart_df.high,
            low=chart_df.low,
            close=chart_df.close,
            name=PAIR_LABELS.get(pair, pair),
        )
    )
    fig.add_trace(go.Scatter(x=chart_df.Datetime, y=chart_df.EMA20, name="EMA20", mode="lines"))
    fig.add_trace(go.Scatter(x=chart_df.Datetime, y=chart_df.EMA50, name="EMA50", mode="lines"))
    fig.add_trace(go.Scatter(x=chart_df.Datetime, y=chart_df.Support20, name="Support 20", mode="lines", line=dict(dash="dot")))
    fig.add_trace(go.Scatter(x=chart_df.Datetime, y=chart_df.Resistance20, name="Resistance 20", mode="lines", line=dict(dash="dot")))

    if pd.notna(price):
        fig.add_hline(y=price, line_dash="dash", annotation_text=f"{price:.5f}", annotation_position="top right")

    if signal == "SELL" and pd.notna(atr14):
        fig.add_trace(
            go.Scatter(
                x=[candle_time],
                y=[float(latest.high) + float(atr14) * 0.25],
                mode="markers+text",
                marker=dict(symbol="triangle-down", size=16),
                text=["SELL"],
                textposition="top center",
                name="CURRENT H20 SELL",
            )
        )

    fig.update_layout(
        height=620,
        xaxis_title="UTC Time",
        yaxis_title="Price",
        xaxis_rangeslider_visible=False,
        hovermode="x unified",
        margin=dict(l=10, r=10, t=35, b=10),
        legend=dict(orientation="h", y=1.01, x=0),
    )

    st.markdown("### 🔎 Chart Analysis Result")
    chart_result = "🔻 DOWN — H20 SELL" if signal == "SELL" else "⚪ NO CONFIRMED SIGNAL"
    st.markdown(
        f'<div class="signal-box"><div class="signal-title">CURRENT ANALYSIS</div>'
        f'<div class="signal-value">{chart_result}</div><div style="margin-top:8px">{reason}</div></div>',
        unsafe_allow_html=True,
    )
    st.caption(
        f"Pair: {PAIR_LABELS.get(pair, pair)} • Candle: {candle_selection} • "
        f"Session: {'ACTIVE' if ny_core else 'INACTIVE'} • Trend: {trend}"
    )
    st.plotly_chart(fig, use_container_width=True, config={"displaylogo": False, "responsive": True})
else:
    st.warning("Live chart data is currently unavailable.")

# ------------------------- MARKET DETAILS -------------------------
st.markdown("### 📍 Market Details")
d1, d2, d3, d4 = st.columns(4)
d1.metric("Support 20", f"{support:.5f}" if pd.notna(support) else "—")
d2.metric("Resistance 20", f"{resistance:.5f}" if pd.notna(resistance) else "—")
d3.metric("Completed Candle", candle_time.strftime("%H:%M UTC") if candle_time is not None else "—")
d4.metric("Candle Age", f"{candle_age:.1f} min" if candle_age is not None else "—")

if latest is not None:
    st.markdown("### 🕯️ Latest Completed Candle")
    o1, o2, o3, o4 = st.columns(4)
    o1.metric("Open", f"{latest.open:.5f}")
    o2.metric("High", f"{latest.high:.5f}")
    o3.metric("Low", f"{latest.low:.5f}")
    o4.metric("Close", f"{latest.close:.5f}")

# ------------------------- SYSTEM STATUS -------------------------
st.markdown("### 🛡️ System Status")
t1, t2, t3, t4, t5 = st.columns(5)
t1.markdown("**LIVE FEED**  \n🟢 PASS" if data_error is None else "**LIVE FEED**  \n🔴 ERROR")
t2.markdown("**INDICATORS**  \n🟢 PASS" if latest is not None else "**INDICATORS**  \n🟠 WAIT")
t3.markdown("**H20 RULE**  \n🔒 LOCKED")
t4.markdown("**AUTO TRADING**  \n🚫 DISABLED")
t5.markdown(f"**FRESHNESS**  \n{'🟢 PASS' if freshness_ok else '🟠 REVIEW'}")

st.markdown("### 🌐 Reader Status")
r1, r2, r3 = st.columns(3)
r1.write(f"**Market:** {market_status}")
r2.write(f"**Analysis Interval:** {st.session_state.analysis_interval}s")
r3.write(
    f"**Last Refresh:** {st.session_state.last_refresh.strftime('%Y-%m-%d %H:%M:%S UTC') if st.session_state.
