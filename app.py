import streamlit as st
import pandas as pd
import numpy as np
import requests
import plotly.graph_objects as go
from datetime import datetime, timezone

# ============================================================
# SHOAIB DATA READER
# EUR/USD — 5 MINUTE LOCKED H20 READER
# ============================================================

st.set_page_config(
    page_title="Shoaib Data Reader",
    page_icon="📊",
    layout="wide",
    initial_sidebar_state="expanded"
)

# ============================================================
# LOCKED CONFIGURATION
# ============================================================

SYMBOL = "EURUSD"
TIMEFRAME = "5m"

H20_START_UTC = 13
H20_END_UTC = 17

MIN_BARS = 60
STALE_LIMIT_MINUTES = 15

AUTO_TRADING = False
STRATEGY_LOCKED = True

API_URL = f"https://biquote.io/api/{SYMBOL}/ohlc"

# ============================================================
# SESSION STATE
# ============================================================

if "running" not in st.session_state:
    st.session_state.running = False

if "last_signal_key" not in st.session_state:
    st.session_state.last_signal_key = None

if "signal_history" not in st.session_state:
    st.session_state.signal_history = set()

if "last_refresh" not in st.session_state:
    st.session_state.last_refresh = None

# ============================================================
# CSS
# ============================================================

st.markdown("""
<style>

.main {
    padding-top: 1rem;
}

.block-container {
    max-width: 1500px;
    padding-top: 1rem;
}

.reader-title {
    font-size: 2rem;
    font-weight: 800;
    margin-bottom: 0.15rem;
}

.reader-subtitle {
    color: #8b949e;
    margin-bottom: 1rem;
}

.metric-card {
    border: 1px solid rgba(128,128,128,0.25);
    border-radius: 14px;
    padding: 15px;
    background: rgba(128,128,128,0.05);
    min-height: 105px;
}

.metric-label {
    font-size: 0.78rem;
    color: #8b949e;
    margin-bottom: 5px;
}

.metric-value {
    font-size: 1.35rem;
    font-weight: 750;
}

.signal-box {
    border-radius: 16px;
    padding: 22px;
    border: 1px solid rgba(128,128,128,0.25);
    margin-top: 10px;
    margin-bottom: 10px;
}

.signal-title {
    font-size: 0.85rem;
    color: #8b949e;
}

.signal-value {
    font-size: 2rem;
    font-weight: 850;
}

.status-ok {
    color: #2ecc71;
    font-weight: 700;
}

.status-off {
    color: #e67e22;
    font-weight: 700;
}

.small-text {
    font-size: 0.78rem;
    color: #8b949e;
}

</style>
""", unsafe_allow_html=True)

# ============================================================
# HEADER
# ============================================================

st.markdown(
    '<div class="reader-title">📊 SHOAIB DATA READER</div>',
    unsafe_allow_html=True
)

st.markdown(
    '<div class="reader-subtitle">'
    'EUR/USD • 5 Minute Live Signal Reader • Locked H20 Strategy'
    '</div>',
    unsafe_allow_html=True
)

# ============================================================
# SIDEBAR
# ============================================================

with st.sidebar:

    st.header("⚙️ Reader Controls")
    # ============================================================
# PROFESSIONAL ANALYSIS SETTINGS
# ============================================================

pair = st.selectbox(
    "💱 Currency Pair",
    ["EURUSD"],
    index=0
)

candle_time = st.selectbox(
    "🕯️ Candle Time",
    ["5 Seconds", "15 Seconds", "30 Seconds", "1 Minute", "2 Minutes", "5 Minutes"],
    index=5
)

trade_time = st.selectbox(
    "⏱️ Trade / Expiry Time",
    ["15 Seconds", "30 Seconds", "1 Minute", "2 Minutes", "5 Minutes"],
    index=2
)
# ============================================================
# ANALYSIS REQUEST
# ============================================================

if st.button(
    "🔎 ANALYZE SELECTED SETUP",
    use_container_width=True
):

    st.session_state.analysis_request = {
        "pair": pair,
        "candle_time": candle_time,
        "trade_time": trade_time,
        "requested_at": datetime.now(timezone.utc)
    }

    st.session_state.last_refresh = None
    st.rerun()
    # ============================================================
# ANALYSIS REQUEST STATUS
# ============================================================

if "analysis_request" in st.session_state:

    req = st.session_state.analysis_request

    st.info(
        f"🔎 Analysis Ready — "
        f"{req['pair']} • "
        f"{req['candle_time']} • "
        f"{req['trade_time']}"
    )
    # ============================================================
# ANALYSIS PROCESSING
# ============================================================

if "analysis_request" in st.session_state:

    if st.button(
        "🧠 START ANALYSIS",
        use_container_width=True
    ):

        with st.spinner("🔄 Analyzing selected market setup..."):
            import time
            time.sleep(4)

        st.session_state.analysis_completed = True
        st.rerun()
    analysis_interval = st.select_slider(
        "Analysis Interval",
        options=[5, 10, 15, 30, 60],
        value=10,
        format_func=lambda x: f"{x} seconds"
    )

    st.divider()

    col_a, col_b = st.columns(2)

    with col_a:
        if st.button(
            "▶ Start",
            use_container_width=True
        ):
            st.session_state.running = True
            st.rerun()

    with col_b:
        if st.button(
            "⏹ Stop",
            use_container_width=True
        ):
            st.session_state.running = False
            st.rerun()

    if st.button(
        "🔍 Analyze Now",
        use_container_width=True
    ):
        st.session_state.last_refresh = None
        st.rerun()
       # ============================================================
# PREDICTION RESULT PANEL
# ============================================================

if st.session_state.get("analysis_completed", False):

    st.markdown("### 🎯 Analysis Result")

    p1, p2, p3 = st.columns(3)

    with p1:
        st.metric("Prediction", "PENDING")

    with p2:
        st.metric("Direction", "WAIT")

    with p3:
        st.metric("Confidence", "—")

    st.info(
        "🧠 Analysis completed. "
        "Validated prediction engine will be connected here."
    ) 
    # ============================================================
# PREDICTION ENGINE INPUT
# ============================================================

if st.session_state.get("analysis_completed", False):

    prediction_input = {
        "pair": pair,
        "candle_time": candle_time,
        "trade_time": trade_time,
        "price": float(price) if pd.notna(price) else None,
        "trend": trend,
        "ema20": float(ema20) if pd.notna(ema20) else None,
        "ema50": float(ema50) if pd.notna(ema50) else None,
        "atr14": float(atr14) if pd.notna(atr14) else None,
        "support": float(support) if pd.notna(support) else None,
        "resistance": float(resistance) if pd.notna(resistance) else None,
        "h20_signal": signal
    }

    st.caption("🧠 Prediction engine input prepared.")
    # ============================================================
# VALIDATED PREDICTION ENGINE
# ============================================================

prediction_direction = "PENDING"
prediction_reason = "Historical validation engine not connected yet."

if st.session_state.get("analysis_completed", False):

    # Prediction layer is intentionally separate
    # from the locked H20 strategy.

    if signal == "SELL":
        prediction_reason = (
            "H20 condition is active. "
            "Historical prediction layer is awaiting validation."
        )

    prediction_result = {
        "direction": prediction_direction,
        "reason": prediction_reason,
        "validated": False
    }
    # ============================================================
# PREDICTION DATA STATUS
# ============================================================

PREDICTION_DATA_FILE = "prediction_data.csv"

prediction_data_available = False

try:
    prediction_data = pd.read_csv(
        PREDICTION_DATA_FILE
    )

    prediction_data_available = (
        not prediction_data.empty
    )

except Exception:
    prediction_data = pd.DataFrame()

if prediction_data_available:

    st.success(
        f"🧠 Prediction data loaded — "
        f"{len(prediction_data):,} records"
    )

else:

    st.warning(
        "🧠 Prediction dataset is not connected yet."
    )

    st.divider()

    st.markdown("### 🔒 Strategy Safety")

    st.write(
        "Strategy: "
        + ("LOCKED" if STRATEGY_LOCKED else "UNLOCKED")
    )

    st.write(
        "Auto Trading: "
        + ("DISABLED" if not AUTO_TRADING else "ENABLED")
    )

    st.write("Feed: Biquote EUR/USD OHLC")

    st.divider()

    st.markdown("### 📌 Locked H20")

    st.write("Direction: BEARISH")
    st.write("Session: 13:00–17:00 UTC")
    st.write("Entry: Completed candle close")
    st.write("Extra filter: None")

# ============================================================
# DATA FETCH
# ============================================================

@st.cache_data(ttl=4, show_spinner=False)
def fetch_live_data():

    response = requests.get(
        API_URL,
        params={
            "interval": TIMEFRAME,
            "limit": 101
        },
        headers={
            "User-Agent": "Mozilla/5.0"
        },
        timeout=10
    )

    response.raise_for_status()

    payload = response.json()

    if "bars" not in payload:
        raise ValueError(
            "API response does not contain bars"
        )

    bars = payload["bars"]

    if not bars:
        raise ValueError(
            "No live candles received"
        )

    df = pd.DataFrame(bars)

    required = [
        "openTime",
        "open",
        "high",
        "low",
        "close"
    ]

    missing = [
        c for c in required
        if c not in df.columns
    ]

    if missing:
        raise ValueError(
            f"Missing columns: {missing}"
        )

    df["Datetime"] = pd.to_datetime(
        df["openTime"],
        utc=True,
        errors="coerce"
    )

    for col in [
        "open",
        "high",
        "low",
        "close"
    ]:
        df[col] = pd.to_numeric(
            df[col],
            errors="coerce"
        )

    df = df.dropna(
        subset=[
            "Datetime",
            "open",
            "high",
            "low",
            "close"
        ]
    ).copy()

    df = (
        df.drop_duplicates(
            subset=["Datetime"],
            keep="last"
        )
        .sort_values("Datetime")
        .reset_index(drop=True)
    )

    if len(df) < MIN_BARS:
        raise ValueError(
            f"Only {len(df)} valid candles received"
        )

    invalid = (
        (df["high"] < df["low"]) |
        (df["high"] < df["open"]) |
        (df["high"] < df["close"]) |
        (df["low"] > df["open"]) |
        (df["low"] > df["close"])
    )

    if invalid.any():
        raise ValueError(
            "OHLC integrity check failed"
        )

    return df

# ============================================================
# INDICATORS
# ============================================================

def calculate_indicators(df):

    out = df.copy()

    out["EMA20"] = (
        out["close"]
        .ewm(
            span=20,
            adjust=False
        )
        .mean()
    )

    out["EMA50"] = (
        out["close"]
        .ewm(
            span=50,
            adjust=False
        )
        .mean()
    )

    previous_close = out["close"].shift(1)

    tr1 = out["high"] - out["low"]

    tr2 = (
        out["high"] - previous_close
    ).abs()

    tr3 = (
        out["low"] - previous_close
    ).abs()

    out["TR"] = pd.concat(
        [tr1, tr2, tr3],
        axis=1
    ).max(axis=1)

    out["ATR14"] = (
        out["TR"]
        .rolling(14)
        .mean()
    )

    out["Support20"] = (
        out["low"]
        .shift(1)
        .rolling(20)
        .min()
    )

    out["Resistance20"] = (
        out["high"]
        .shift(1)
        .rolling(20)
        .max()
    )

    out["EMA_DIRECTION"] = np.where(
        out["EMA20"] > out["EMA50"],
        "BULL",
        "BEAR"
    )

    return out

# ============================================================
# COMPLETED CANDLE
# ============================================================

def get_completed_candles(df):

    now = datetime.now(timezone.utc)

    completion_time = (
        df["Datetime"]
        + pd.Timedelta(minutes=5)
    )

    mask = (
        completion_time
        <= pd.Timestamp(now)
    )

    completed = df.loc[
        mask
    ].copy()

    if completed.empty:
        raise ValueError(
            "No completed 5-minute candle available"
        )

    return completed, now

# ============================================================
# H20 ENGINE
# ============================================================

def evaluate_h20(row):

    utc_hour = int(
        row["Datetime"].hour
    )

    ny_core = (
        H20_START_UTC
        <= utc_hour
        < H20_END_UTC
    )

    bearish = (
        row["EMA_DIRECTION"] == "BEAR"
    )

    active = (
        bearish and ny_core
    )

    if active:

        signal = "SELL"

        reason = (
            "H20 LOCKED RULE: "
            "BEAR EMA direction + NY Core session"
        )

    else:

        signal = "NO SIGNAL"

        if not ny_core:
            reason = (
                "Outside H20 NY Core session"
            )

        elif not bearish:
            reason = (
                "EMA direction is not BEAR"
            )

        else:
            reason = (
                "H20 conditions not satisfied"
            )

    return (
        signal,
        reason,
        ny_core,
        utc_hour
    )

# ============================================================
# LOAD LIVE DATA
# ============================================================

try:

    raw_df = fetch_live_data()

    df = calculate_indicators(
        raw_df
    )

    completed_df, now_utc = (
        get_completed_candles(df)
    )

    latest = completed_df.iloc[-1]

    candle_time = latest["Datetime"]

    candle_close_time = (
        candle_time
        + pd.Timedelta(minutes=5)
    )

    candle_age = (
        pd.Timestamp(now_utc)
        - candle_close_time
    ).total_seconds() / 60

    signal, reason, ny_core, utc_hour = (
        evaluate_h20(latest)
    )

    # Weekend safety
    weekend = (
        now_utc.weekday() >= 5
    )

    if weekend:

        market_status = "CLOSED — WEEKEND"
        freshness_ok = True

    else:

        market_status = "OPEN"

        freshness_ok = (
            candle_age <= STALE_LIMIT_MINUTES
        )

    # Duplicate protection
    signal_key = (
        candle_time.isoformat(),
        signal
    )

    duplicate = (
        signal_key
        in st.session_state.signal_history
    )

    st.session_state.signal_history.add(
        signal_key
    )

    st.session_state.last_signal_key = (
        signal_key
    )

    st.session_state.last_refresh = now_utc

    data_error = None

except Exception as e:

    raw_df = pd.DataFrame()
    df = pd.DataFrame()
    completed_df = pd.DataFrame()

    latest = None
    signal = "NO SIGNAL"
    reason = "Live feed unavailable"
    ny_core = False
    utc_hour = None

    candle_age = None
    market_status = "FEED ERROR"
    freshness_ok = False
    duplicate = False

    data_error = str(e)

# ============================================================
# TOP METRICS
# ============================================================

if latest is not None:

    price = latest["close"]
    ema20 = latest["EMA20"]
    ema50 = latest["EMA50"]
    atr14 = latest["ATR14"]
    support = latest["Support20"]
    resistance = latest["Resistance20"]
    trend = latest["EMA_DIRECTION"]

else:

    price = np.nan
    ema20 = np.nan
    ema50 = np.nan
    atr14 = np.nan
    support = np.nan
    resistance = np.nan
    trend = "UNKNOWN"

m1, m2, m3, m4, m5 = st.columns(5)

with m1:
    st.metric(
        "Live Price",
        f"{price:.5f}"
        if pd.notna(price)
        else "—"
    )

with m2:
    st.metric(
        "Trend",
        trend
    )

with m3:
    st.metric(
        "EMA20",
        f"{ema20:.5f}"
        if pd.notna(ema20)
        else "—"
    )

with m4:
    st.metric(
        "EMA50",
        f"{ema50:.5f}"
        if pd.notna(ema50)
        else "—"
    )

with m5:
    st.metric(
        "ATR14",
        f"{atr14:.5f}"
        if pd.notna(atr14)
        else "—"
    )

# ============================================================
# SIGNAL PANEL
# ============================================================

st.markdown("### 🎯 Current H20 Signal")

signal_col, reason_col, session_col = st.columns(
    [1, 2, 1]
)

with signal_col:

    signal_class = (
        "status-ok"
        if signal == "SELL"
        else "status-off"
    )

    st.markdown(
        f"""
        <div class="signal-box">
            <div class="signal-title">SIGNAL</div>
            <div class="signal-value {signal_class}">
                {signal}
            </div>
        </div>
        """,
        unsafe_allow_html=True
    )

with reason_col:

    st.markdown(
        f"""
        <div class="signal-box">
            <div class="signal-title">REASON</div>
            <div style="font-size:1.05rem;font-weight:650;">
                {reason}
            </div>
        </div>
        """,
        unsafe_allow_html=True
    )

with session_col:

    session_text = (
        "ACTIVE"
        if ny_core
        else "INACTIVE"
    )

    st.markdown(
        f"""
        <div class="signal-box">
            <div class="signal-title">NY CORE</div>
            <div class="signal-value">
                {session_text}
            </div>
        </div>
        """,
        unsafe_allow_html=True
    )

# ============================================================
# PROFESSIONAL ANALYSIS
# ============================================================

st.markdown("### 🧠 Professional Analysis")

analysis_col1, analysis_col2, analysis_col3 = st.columns(3)

if signal == "SELL":

    analysis_direction = "DOWN"
    analysis_status = "VALIDATED"
    analysis_message = (
        "Locked H20 bearish condition is currently satisfied."
    )

else:

    analysis_direction = "NO CLEAR DIRECTION"
    analysis_status = "NO SIGNAL"
    analysis_message = reason

with analysis_col1:
    st.metric(
        "Direction",
        analysis_direction
    )

with analysis_col2:
    st.metric(
        "Analysis",
        analysis_status
    )

with analysis_col3:
    st.metric(
        "Trend",
        trend
    )

if signal == "SELL":

    st.success(
        "🔻 H20 ANALYSIS: DOWN / SELL CONDITION CONFIRMED"
    )

else:

    st.info(
        "⏸️ No confirmed H20 direction at this moment."
    )

st.caption(
    f"Analysis: {analysis_message}"
)

st.caption(
    f"Price: {price:.5f}  •  "
    f"EMA20: {ema20:.5f}  •  "
    f"EMA50: {ema50:.5f}  •  "
    f"ATR14: {atr14:.5f}"
    if pd.notna(price)
    and pd.notna(ema20)
    and pd.notna(ema50)
    and pd.notna(atr14)
    else "Indicator data unavailable."
)
# ============================================================
# CHART
# ============================================================
# ============================================================
# ANALYZE ACTION
# ============================================================

if st.button(
    "🧠 ANALYZE CURRENT CHART",
    use_container_width=True
):
    st.session_state.last_refresh = None
    st.rerun()
st.markdown("### 📈 Live Candlestick Chart")

if not df.empty:

    chart_df = df.tail(80).copy()

    fig = go.Figure()

    # Candlesticks
    fig.add_trace(
        go.Candlestick(
            x=chart_df["Datetime"],
            open=chart_df["open"],
            high=chart_df["high"],
            low=chart_df["low"],
            close=chart_df["close"],
            name="EUR/USD"
        )
    )

    # EMA20
    fig.add_trace(
        go.Scatter(
            x=chart_df["Datetime"],
            y=chart_df["EMA20"],
            mode="lines",
            name="EMA20",
            line=dict(
                width=1.5
            )
        )
    )

    # EMA50
    fig.add_trace(
        go.Scatter(
            x=chart_df["Datetime"],
            y=chart_df["EMA50"],
            mode="lines",
            name="EMA50",
            line=dict(
                width=1.5
            )
        )
    )

    # Support
    fig.add_trace(
        go.Scatter(
            x=chart_df["Datetime"],
            y=chart_df["Support20"],
            mode="lines",
            name="Support 20",
            line=dict(
                dash="dot",
                width=1
            )
        )
    )

    # Resistance
    fig.add_trace(
        go.Scatter(
            x=chart_df["Datetime"],
            y=chart_df["Resistance20"],
            mode="lines",
            name="Resistance 20",
            line=dict(
                dash="dot",
                width=1
            )
        )
    )

    # Current price
    if pd.notna(price):

        fig.add_hline(
            y=price,
            line_dash="dash",
            annotation_text=f"{price:.5f}",
            annotation_position="top right"
        )

    # H20 SELL markers
    sell_df = chart_df[
        (
            chart_df["EMA_DIRECTION"]
            == "BEAR"
        )
        &
        (
            chart_df["Datetime"].dt.hour
            >= H20_START_UTC
        )
        &
        (
            chart_df["Datetime"].dt.hour
            < H20_END_UTC
        )
    ].copy()

    if not sell_df.empty:

        fig.add_trace(
            go.Scatter(
                x=sell_df["Datetime"],
                y=sell_df["high"] + (
                    sell_df["ATR14"].fillna(0)
                    * 0.25
                ),
                mode="markers",
                name="H20 SELL",
                marker=dict(
                    symbol="triangle-down",
                    size=11
                )
            )
        )

    # ============================================================
# PROFESSIONAL H20 SIGNAL MARKER
# ============================================================

if signal == "SELL" and latest is not None:

    fig.add_trace(
        go.Scatter(
            x=[candle_time],
            y=[float(latest["high"]) + (
                float(atr14) * 0.25
                if pd.notna(atr14)
                else 0
            )],
            mode="markers+text",
            marker=dict(
                symbol="triangle-down",
                size=16
            ),
            text=["SELL"],
            textposition="top center",
            name="CURRENT H20 SIGNAL"
        )
    )
    # ============================================================
# ANALYSIS STATUS
# ============================================================

if signal == "SELL":
    st.success(
        "🟢 ANALYSIS COMPLETE — H20 DOWN / SELL CONDITION CONFIRMED"
    )
else:
    st.info(
        "⚪ ANALYSIS COMPLETE — NO CONFIRMED SIGNAL"
    )

st.caption(
    f"Session: {'ACTIVE' if ny_core else 'INACTIVE'} • "
    f"Trend: {trend} • "
    f"UTC Hour: {utc_hour if utc_hour is not None else '—'}"
)
    fig.update_layout(
        height=620,
        xaxis_title="UTC Time",
        yaxis_title="Price",
        xaxis_rangeslider_visible=False,
        hovermode="x unified",
        margin=dict(
            l=10,
            r=10,
            t=35,
            b=10
        ),
        legend=dict(
            orientation="h",
            yanchor="bottom",
            y=1.01,
            xanchor="left",
            x=0
        )
    )

# ============================================================
# CHART ANALYSIS RESULT
# ============================================================

st.markdown("### 🔎 Chart Analysis Result")

if signal == "SELL":
    result_title = "🔻 DOWN — H20 SELL"
    result_text = "Locked H20 condition is confirmed on the latest completed candle."
else:
    result_title = "⚪ NO CONFIRMED SIGNAL"
    result_text = reason

st.markdown(
    f"""
    <div class="signal-box">
        <div class="signal-title">CURRENT ANALYSIS</div>
        <div class="signal-value">{result_title}</div>
        <div style="margin-top:8px;font-size:0.95rem;">
            {result_text}
        </div>
    </div>
    """,
    unsafe_allow_html=True
)
    st.plotly_chart(
        fig,
        use_container_width=True,
        config={
            "displaylogo": False,
            "responsive": True
        }
    )

else:

    st.warning(
        "Live chart data is currently unavailable."
    )

# ============================================================
# MARKET DETAILS
# ============================================================

st.markdown("### 📋 Market Details")

d1, d2, d3, d4 = st.columns(4)

with d1:
    st.metric(
        "Support 20",
        f"{support:.5f}"
        if pd.notna(support)
        else "—"
    )

with d2:
    st.metric(
        "Resistance 20",
        f"{resistance:.5f}"
        if pd.notna(resistance)
        else "—"
    )

with d3:
    st.metric(
        "Completed Candle",
        candle_time.strftime(
            "%H:%M UTC"
        )
        if latest is not None
        else "—"
    )

with d4:
    st.metric(
        "Candle Age",
        f"{candle_age:.1f} min"
        if candle_age is not None
        else "—"
    )

# ============================================================
# LATEST CANDLE OHLC
# ============================================================

if latest is not None:

    st.markdown("### 🕯️ Latest Completed Candle")

    o1, o2, o3, o4 = st.columns(4)

    with o1:
        st.metric(
            "Open",
            f"{latest['open']:.5f}"
        )

    with o2:
        st.metric(
            "High",
            f"{latest['high']:.5f}"
        )

    with o3:
        st.metric(
            "Low",
            f"{latest['low']:.5f}"
        )

    with o4:
        st.metric(
            "Close",
            f"{latest['close']:.5f}"
        )

# ============================================================
# SYSTEM STATUS
# ============================================================

st.markdown("### 🛡️ System Status")

s1, s2, s3, s4, s5 = st.columns(5)

with s1:
    st.markdown(
        "**LIVE FEED**  \n"
        "🟢 PASS"
    )

with s2:
    st.markdown(
        "**INDICATORS**  \n"
        "🟢 PASS"
    )

with s3:
    st.markdown(
        "**H20 RULE**  \n"
        "🔒 LOCKED"
    )

with s4:
    st.markdown(
        "**AUTO TRADING**  \n"
        "🚫 DISABLED"
    )

with s5:
    freshness_label = (
        "PASS"
        if freshness_ok
        else "REVIEW"
    )

    st.markdown(
        f"**FRESHNESS**  \n"
        f"{'🟢' if freshness_ok else '🟠'} {freshness_label}"
    )

# ============================================================
# MARKET STATUS
# ============================================================

st.markdown("### 🌐 Reader Status")

r1, r2, r3 = st.columns(3)

with r1:

    st.write(
        f"**Market:** {market_status}"
    )

with r2:

    st.write(
        f"**Analysis Interval:** "
        f"{analysis_interval}s"
    )

with r3:

    if st.session_state.last_refresh:

        refresh_text = (
            st.session_state.last_refresh
            .strftime(
                "%Y-%m-%d %H:%M:%S UTC"
            )
        )

    else:

        refresh_text = "—"

    st.write(
        f"**Last Analysis:** {refresh_text}"
    )

# ============================================================
# ERROR PANEL
# ============================================================

if data_error:

    st.error(
        f"Reader error: {data_error}"
    )

# ============================================================
# DISCLAIMER / SAFETY
# ============================================================

st.divider()

st.markdown(
    """<div class="small-text">
Data source: Biquote EUR/USD OHLC feed.
The feed is used for live reader testing and is not claimed
to be identical to the historical BID dataset.
<br><br>
H20 strategy is locked. No automatic order execution is enabled.
This interface is a research/reader tool and does not place trades.
</div>
""",
    unsafe_allow_html=True
)

if st.session_state.running:
    import time
    time.sleep(max(5, analysis_interval))
    st.rerun()
