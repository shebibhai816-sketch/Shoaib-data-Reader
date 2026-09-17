import time
from datetime import datetime, timezone

import numpy as np
import pandas as pd
import plotly.graph_objects as go
import requests
import streamlit as st
from signalrcore.hub_connection_builder import HubConnectionBuilder


# ============================================================
# SHOAIB DATA READER — FINAL LIVE ARCHITECTURE
# ============================================================

st.set_page_config(
    page_title="Shoaib Data Reader",
    page_icon="📊",
    layout="wide",
    initial_sidebar_state="expanded",
)


# ============================================================
# LOCKED CORE
# ============================================================

LOCKED_PAIR = "EURUSD"
LOCKED_TIMEFRAME = "5 Minutes"

H20_START_UTC = 13
H20_END_UTC = 17

MIN_BARS = 60
STALE_LIMIT_MINUTES = 15

AUTO_TRADING = False
STRATEGY_LOCKED = True

H20_VALIDATED_SIGNALS = 245
H20_FWD6_WIN_RATE = 60.00
H20_FWD6_AVG_ATR = 0.556601
H20_FWD20_WIN_RATE = 68.57
H20_FWD20_AVG_ATR = 1.377593


# ============================================================
# UI CATALOG
# ============================================================

CURRENCY_PAIRS = [
    "EURUSD",
    "GBPUSD",
    "USDJPY",
    "USDCHF",
    "AUDUSD",
    "USDCAD",
    "NZDUSD",
    "EURGBP",
    "EURJPY",
    "GBPJPY",
    "EURAUD",
    "EURCHF",
    "AUDJPY",
    "CADJPY",
]

CANDLE_OPTIONS = [
    "10 Seconds",
    "15 Seconds",
    "30 Seconds",
    "1 Minute",
    "2 Minutes",
    "5 Minutes",
    "15 Minutes",
    "30 Minutes",
]

EXPIRY_OPTIONS = [
    "15 Seconds",
    "30 Seconds",
    "1 Minute",
    "2 Minutes",
    "3 Minutes",
    "5 Minutes",
    "10 Minutes",
    "15 Minutes",
    "30 Minutes",
    "60 Minutes",
    "100 Minutes",
]

API_INTERVALS = {
    "1 Minute": "1m",
    "5 Minutes": "5m",
    "15 Minutes": "15m",
    "30 Minutes": "30m",
}


# ============================================================
# TICK ENGINE
# ============================================================

TICK_INTERVALS = {
    "10 Seconds": "10s",
    "15 Seconds": "15s",
    "30 Seconds": "30s",
}

TICK_HUB_URL = "https://biquote.io/hubs/tick"

# Keep enough tick history to progressively build
# 60+ candles for the short-timeframe indicator engine.
TICK_BUFFER_MINUTES = 45
TICK_WARMUP_CANDLES = 60

def is_tick_timeframe(candle_name):
    return candle_name in TICK_INTERVALS


def collect_tick_stream(symbol, seconds=10):
    ticks = []
    hub = None

    def on_tick(args):
        try:
            payload = args[0] if isinstance(args, list) else args

            if not isinstance(payload, dict):
                return

            if payload.get("symbol") != symbol:
                return

            bid = payload.get("bid")
            ask = payload.get("ask")
            timestamp = payload.get("timestamp")

            if bid is None or ask is None or timestamp is None:
                return

            bid = float(bid)
            ask = float(ask)

            ticks.append(
                {
                    "symbol": symbol,
                    "bid": bid,
                    "ask": ask,
                    "mid": (bid + ask) / 2.0,
                    "timestamp": timestamp,
                }
            )

        except Exception:
            pass

    try:
        hub = (
            HubConnectionBuilder()
            .with_url(TICK_HUB_URL)
            .build()
        )

        hub.on("ReceiveTick", on_tick)
        hub.start()

        time.sleep(1)

        hub.send("Subscribe", [[symbol]])

        time.sleep(seconds)

    except Exception:
        return []

    finally:
        try:
            if hub is not None:
                hub.stop()
        except Exception:
            pass

    return ticks


def update_tick_buffer(symbol, ticks):
    if "tick_buffer" not in st.session_state:
        st.session_state.tick_buffer = {}

    if symbol not in st.session_state.tick_buffer:
        st.session_state.tick_buffer[symbol] = []

    buffer = st.session_state.tick_buffer[symbol]

    if ticks:
        buffer.extend(ticks)

    if not buffer:
        return []

    clean = []

    for tick in buffer:
        try:
            ts = pd.to_datetime(
                tick.get("timestamp"),
                utc=True,
                errors="coerce",
            )

            mid = float(tick.get("mid"))

            if pd.isna(ts):
                continue

            clean.append(
                {
                    "symbol": symbol,
                    "bid": float(tick.get("bid", mid)),
                    "ask": float(tick.get("ask", mid)),
                    "mid": mid,
                    "timestamp": ts,
                }
            )

        except Exception:
            continue

    if not clean:
        st.session_state.tick_buffer[symbol] = []
        return []

    df = pd.DataFrame(clean)

    # Do NOT remove ticks just because timestamps are equal.
    # Multiple ticks can legitimately share the same timestamp.
    df = (
        df.dropna(subset=["timestamp", "mid"])
        .sort_values("timestamp")
        .drop_duplicates(
            subset=["timestamp", "mid"],
            keep="last",
        )
        .reset_index(drop=True)
    )

    cutoff = (
        pd.Timestamp.now(tz="UTC")
        - pd.Timedelta(minutes=TICK_BUFFER_MINUTES)
    )

    df = df[df["timestamp"] >= cutoff].copy()

    st.session_state.tick_buffer[symbol] = df.to_dict("records")

    return st.session_state.tick_buffer[symbol]


def build_tick_candles(ticks, interval="10s"):
    if not ticks:
        return pd.DataFrame()

    tick_df = pd.DataFrame(ticks)

    required = ["timestamp", "mid"]

    if any(column not in tick_df.columns for column in required):
        return pd.DataFrame()

    tick_df["timestamp"] = pd.to_datetime(
        tick_df["timestamp"],
        utc=True,
        errors="coerce",
    )

    tick_df["mid"] = pd.to_numeric(
        tick_df["mid"],
        errors="coerce",
    )

    tick_df = (
        tick_df
        .dropna(subset=["timestamp", "mid"])
        .sort_values("timestamp")
        .reset_index(drop=True)
    )

    if tick_df.empty:
        return pd.DataFrame()

    candles = (
        tick_df
        .set_index("timestamp")["mid"]
        .resample(interval)
        .agg(
            open="first",
            high="max",
            low="min",
            close="last",
        )
        .dropna()
        .reset_index()
    )

    candles["Datetime"] = candles["timestamp"]

    candles["Candle_Close"] = (
        candles["Datetime"]
        + pd.Timedelta(interval)
    )

    now_utc = pd.Timestamp.now(tz="UTC")

    candles = candles[
        candles["Candle_Close"] <= now_utc
    ].copy()

    return candles.reset_index(drop=True)


def fetch_tick_live_data(symbol, candle_name, seconds=12):
    interval = TICK_INTERVALS.get(candle_name)

    if interval is None:
        raise ValueError(
            f"{candle_name} is not a tick-stream timeframe."
        )

    fresh_ticks = collect_tick_stream(
        symbol,
        seconds=seconds,
    )

    all_ticks = update_tick_buffer(
        symbol,
        fresh_ticks,
    )

    if not all_ticks:
        raise ValueError(
            "No live ticks received from Biquote SignalR."
        )

    candles = build_tick_candles(
        all_ticks,
        interval=interval,
    )

    if candles.empty:
        raise ValueError(
            "Waiting for a completed tick candle."
        )

    return candles


# ============================================================
# PAIR LABELS
# ============================================================

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


# ============================================================
# SESSION STATE
# ============================================================

DEFAULTS = {
    "running": False,
    "analysis_requested": False,
    "analysis_completed": False,
    "analysis_interval": 10,
    "last_analysis_request": None,
    "last_refresh": None,
    "signal_history": set(),
    "tick_buffer": {},
}

for key, value in DEFAULTS.items():
    if key not in st.session_state:
        st.session_state[key] = value


# ============================================================
# STYLE
# ============================================================

st.markdown(
    """
    <style>
    .block-container {
        max-width: 1500px;
        padding-top: 1rem;
    }

    .reader-title {
        font-size: 2rem;
        font-weight: 850;
        letter-spacing: .3px;
    }

    .reader-subtitle {
        color: #8b949e;
        margin-bottom: 1rem;
    }

    .signal-box {
        border-radius: 16px;
        padding: 18px;
        border: 1px solid rgba(128,128,128,.25);
        margin: 8px 0;
    }

    .signal-title {
        font-size: .8rem;
        color: #8b949e;
        text-transform: uppercase;
        letter-spacing: .5px;
    }

    .signal-value {
        font-size: 1.8rem;
        font-weight: 850;
    }

    .small-text {
        font-size: .78rem;
        color: #8b949e;
    }
    div.stButton > button[kind="primary"] {
    height: 58px;
    border-radius: 14px;
    font-size: 1.05rem;
    font-weight: 800;
    letter-spacing: .3px;
}
    </style>
    """,
    unsafe_allow_html=True,
)


# ============================================================
# HEADER
# ============================================================

st.markdown(
    '<div class="reader-title">📊 SHOAIB DATA READER</div>',
    unsafe_allow_html=True,
)

st.markdown(
    '<div class="reader-subtitle">'
    'Professional multi-pair / multi-timeframe research reader'
    '</div>',
    unsafe_allow_html=True,
)


# ============================================================
# DATA FUNCTIONS
# ============================================================

def get_api_interval(candle_name):
    return API_INTERVALS.get(candle_name)


def api_url(symbol):
    return f"https://biquote.io/api/{symbol}/ohlc"


@st.cache_data(ttl=4, show_spinner=False)
def fetch_live_data(symbol, candle_name):
    interval = get_api_interval(candle_name)

    if interval is None:
        raise ValueError(
            f"{candle_name} does not have a native OHLC interval."
        )

    response = requests.get(
        api_url(symbol),
        params={
            "interval": interval,
            "limit": 101,
        },
        headers={
            "User-Agent": "Mozilla/5.0",
        },
        timeout=10,
    )

    response.raise_for_status()

    payload = response.json()

    if "bars" not in payload or not payload["bars"]:
        raise ValueError(
            "No live candles received."
        )

    df = pd.DataFrame(payload["bars"])

    required = [
        "openTime",
        "open",
        "high",
        "low",
        "close",
    ]

    missing = [
        column
        for column in required
        if column not in df.columns
    ]

    if missing:
        raise ValueError(
            f"Missing feed columns: {missing}"
        )

    df["Datetime"] = pd.to_datetime(
        df["openTime"],
        utc=True,
        errors="coerce",
    )

    for column in [
        "open",
        "high",
        "low",
        "close",
    ]:
        df[column] = pd.to_numeric(
            df[column],
            errors="coerce",
        )

    df = (
        df
        .dropna(
            subset=[
                "Datetime",
                "open",
                "high",
                "low",
                "close",
            ]
        )
        .drop_duplicates(
            "Datetime",
            keep="last",
        )
        .sort_values("Datetime")
        .reset_index(drop=True)
    )

    if len(df) < MIN_BARS:
        raise ValueError(
            f"Only {len(df)} valid candles received; "
            f"{MIN_BARS} required."
        )

    bad = (
        (df.high < df.low)
        | (df.high < df.open)
        | (df.high < df.close)
        | (df.low > df.open)
        | (df.low > df.close)
    )

    if bad.any():
        raise ValueError(
            "OHLC integrity check failed."
        )

    return df


def add_indicators(df):
    x = df.copy()

    x["EMA20"] = (
        x.close
        .ewm(span=20, adjust=False)
        .mean()
    )

    x["EMA50"] = (
        x.close
        .ewm(span=50, adjust=False)
        .mean()
    )

    previous_close = x.close.shift(1)

    x["TR"] = pd.concat(
        [
            x.high - x.low,
            (x.high - previous_close).abs(),
            (x.low - previous_close).abs(),
        ],
        axis=1,
    ).max(axis=1)

    x["ATR14"] = (
        x.TR
        .rolling(14)
        .mean()
    )

    x["Support20"] = (
        x.low
        .shift(1)
        .rolling(20)
        .min()
    )

    x["Resistance20"] = (
        x.high
        .shift(1)
        .rolling(20)
        .max()
    )

    x["EMA_DIRECTION"] = np.where(
        x.EMA20 > x.EMA50,
        "BULL",
        "BEAR",
    )

    return x


def candle_minutes(candle_name):
    mapping = {
        "1 Minute": 1,
        "2 Minutes": 2,
        "5 Minutes": 5,
        "15 Minutes": 15,
        "30 Minutes": 30,
    }

    return mapping.get(candle_name)


def completed_candles(df, candle_name):
    minutes = candle_minutes(candle_name)

    if minutes is None:
        raise ValueError(
            f"Completed-candle logic is not connected "
            f"to {candle_name}."
        )

    now = datetime.now(timezone.utc)

    completion = (
        df.Datetime
        + pd.Timedelta(minutes=minutes)
    )

    mask = (
        completion
        <= pd.Timestamp(now)
    )

    if "isOpen" in df.columns:
        mask &= (
            ~df.isOpen.astype(bool)
        )

    out = df.loc[mask].copy()

    if out.empty:
        raise ValueError(
            "No completed candle is currently available."
        )

    return out, now


def locked_h20_signal(row):
    session_active = (
        H20_START_UTC
        <= int(row.Datetime.hour)
        < H20_END_UTC
    )

    bearish = (
        row.EMA_DIRECTION == "BEAR"
    )

    if session_active and bearish:
        return (
            "SELL",
            "H20 LOCKED: BEAR EMA direction + NY Core session",
            True,
        )

    if not session_active:
        return (
            "NO SIGNAL",
            "Outside H20 NY Core session",
            False,
        )

    return (
        "NO SIGNAL",
        "EMA direction is not BEAR",
        False,
    )


def validated_status(
    selected_pair,
    selected_candle,
    selected_expiry,
    signal,
):
    if (
        selected_pair != LOCKED_PAIR
        or selected_candle != LOCKED_TIMEFRAME
        or signal != "SELL"
    ):
        return (
            "WAIT",
            None,
            None,
            "NOT VALIDATED",
        )

    if selected_expiry == "30 Minutes":
        return (
            "SELL",
            H20_FWD6_WIN_RATE,
            H20_FWD6_AVG_ATR,
            "VALIDATED",
        )

    if selected_expiry == "100 Minutes":
        return (
            "SELL",
            H20_FWD20_WIN_RATE,
            H20_FWD20_AVG_ATR,
            "VALIDATED",
        )

    return (
        "SELL",
        None,
        None,
        "ACTIVE / NOT DIRECTLY VALIDATED",
    )


# ============================================================
# FINAL TRADING TERMINAL CONTROLS
# ============================================================

st.markdown("### 🎯 EUR/USD H20")

c1, c2, c3, c4 = st.columns([1.15, 1.15, 1.15, 1.5])

with c1:
    pair = st.selectbox(
        "Pair",
        ["EURUSD"],
        format_func=lambda x: "EUR/USD",
        key="selected_pair",
    )

with c2:
    candle_selection = st.selectbox(
        "Timeframe",
        ["5 Minutes"],
        index=0,
        key="selected_candle",
    )

with c3:
    expiry_selection = st.selectbox(
        "Expiry",
        ["30 Minutes", "100 Minutes"],
        index=0,
        key="selected_expiry",
    )

with c4:
    analyze_button = st.button(
        "🔎 ANALYZE",
        use_container_width=True,
        type="primary",
    )

if analyze_button:
    st.session_state.running = True
    st.session_state.analysis_requested = True
    st.session_state.analysis_completed = False

    st.session_state.last_analysis_request = {
        "pair": pair,
        "candle": candle_selection,
        "expiry": expiry_selection,
        "at": datetime.now(timezone.utc),
    }

st.caption(
    "🔒 EUR/USD H20 LOCKED • "
    "5M • Auto Analysis Active • "
    "Auto Trading Disabled"
)

# ============================================================
# LIVE DATA ENGINE
# ============================================================

raw = pd.DataFrame()
df = pd.DataFrame()
completed_df = pd.DataFrame()

latest = None

signal = "NO SIGNAL"
reason = "Live feed unavailable"

ny_core = False

price = np.nan
ema20 = np.nan
ema50 = np.nan
atr14 = np.nan
support = np.nan
resistance = np.nan

trend = "UNKNOWN"

candle_time = None
candle_age = None

market_status = "FEED ERROR"
freshness_ok = False

data_error = None


try:

    # --------------------------------------------------------
    # SHORT TIMEFRAMES — SIGNALR TICK ENGINE
    # --------------------------------------------------------

    if is_tick_timeframe(candle_selection):

        collection_seconds = {
            "10 Seconds": 12,
            "15 Seconds": 20,
            "30 Seconds": 35,
        }.get(
            candle_selection,
            12,
        )

        raw = fetch_tick_live_data(
            pair,
            candle_selection,
            seconds=collection_seconds,
        )

        df = add_indicators(raw)

        if df.empty:
            raise ValueError(
                "No completed tick candles available."
            )

        completed_df = df.copy()

        latest = completed_df.iloc[-1]

        interval = TICK_INTERVALS[
            candle_selection
        ]

        candle_time = latest.Datetime

        close_time = (
            candle_time
            + pd.Timedelta(interval)
        )

        now_utc = pd.Timestamp.now(
            tz="UTC"
        )

        candle_age = (
            now_utc
            - close_time
        ).total_seconds() / 60

        signal = "NO SIGNAL"

        reason = (
            "Tick Engine active — short timeframe "
            "is research/live-data only; no validated "
            "trading rule is assigned."
        )

        ny_core = False

        weekend = (
            now_utc.weekday() >= 5
        )

        market_status = (
            "CLOSED — WEEKEND"
            if weekend
            else "OPEN"
        )

        freshness_ok = (
            weekend
            or (
        0
                <= candle_age
                <= STALE_LIMIT_MINUTES
            )
        )

        price = float(latest.close)

        ema20 = (
            float(latest.EMA20)
            if pd.notna(latest.EMA20)
            else np.nan
        )

        ema50 = (
            float(latest.EMA50)
            if pd.notna(latest.EMA50)
            else np.nan
        )

        atr14 = (
            float(latest.ATR14)
            if pd.notna(latest.ATR14)
            else np.nan
        )

        support = (
            float(latest.Support20)
            if pd.notna(latest.Support20)
            else np.nan
        )

        resistance = (
            float(latest.Resistance20)
            if pd.notna(latest.Resistance20)
            else np.nan
        )

        trend = (
            latest.EMA_DIRECTION
            if pd.notna(latest.EMA_DIRECTION)
            else "UNKNOWN"
        )

        st.session_state.last_refresh = (
            now_utc
        )


    # --------------------------------------------------------
    # NATIVE OHLC TIMEFRAMES
    # --------------------------------------------------------

    else:

        raw = fetch_live_data(
            pair,
            candle_selection,
        )

        df = add_indicators(raw)

        completed_df, now_utc = (
            completed_candles(
                df,
                candle_selection,
            )
        )

        latest = completed_df.iloc[-1]

        minutes = candle_minutes(
            candle_selection
        )

        close_time = (
            latest.Datetime
            + pd.Timedelta(
                minutes=minutes
            )
        )

        candle_time = latest.Datetime

        candle_age = (
            pd.Timestamp(now_utc)
            - close_time
        ).total_seconds() / 60

        if (
            pair == LOCKED_PAIR
            and candle_selection
            == LOCKED_TIMEFRAME
        ):

            signal, reason, ny_core = (
                locked_h20_signal(
                    latest
                )
            )

        else:

            signal = "NO SIGNAL"

            reason = (
                "This pair/timeframe is available "
                "for research, but no locked "
                "validation rule is assigned."
            )

            ny_core = False

        weekend = (
            now_utc.weekday() >= 5
        )

        market_status = (
            "CLOSED — WEEKEND"
            if weekend
            else "OPEN"
        )

        freshness_ok = (
            weekend
            or (
                0
                <= candle_age
                <= STALE_LIMIT_MINUTES
            )
        )

        price = float(latest.close)

        ema20 = float(
            latest.EMA20
        )

        ema50 = float(
            latest.EMA50
        )

        atr14 = (
            float(latest.ATR14)
            if pd.notna(latest.ATR14)
            else np.nan
        )

        support = (
            float(latest.Support20)
            if pd.notna(latest.Support20)
            else np.nan
        )

        resistance = (
            float(latest.Resistance20)
            if pd.notna(latest.Resistance20)
            else np.nan
        )

        trend = latest.EMA_DIRECTION

        st.session_state.last_refresh = (
            now_utc
        )


except Exception as exc:

    data_error = str(exc)

# ============================================================
# ANALYSIS — CONTINUOUS 5-SECOND LIVE LOOP
# ============================================================

if (
    st.session_state.running
    and st.session_state.analysis_requested
):

    with st.spinner(
        "🔄 Live H20 analysis running..."
    ):
        time.sleep(5)

    # SELL مل گیا تو loop ختم
    if signal == "SELL":

        st.session_state.running = False
        st.session_state.analysis_completed = True

    # ابھی SELL نہیں ملا — loop جاری رکھیں
    else:

        st.session_state.analysis_completed = True

        time.sleep(
            max(
                5,
                int(
                    st.session_state.analysis_interval
                ),
            )
        )

        st.rerun()

# ============================================================
# TOP METRICS
# ============================================================

m1, m2, m3, m4, m5 = st.columns(5)

m1.metric(
    "Live Price",
    f"{price:.5f}"
    if pd.notna(price)
    else "—",
)

m2.metric(
    "Trend",
    trend,
)

m3.metric(
    "EMA20",
    f"{ema20:.5f}"
    if pd.notna(ema20)
    else "—",
)

m4.metric(
    "EMA50",
    f"{ema50:.5f}"
    if pd.notna(ema50)
    else "—",
)

m5.metric(
    "ATR14",
    f"{atr14:.5f}"
    if pd.notna(atr14)
    else "—",
)


# ============================================================
# LAST REQUEST
# ============================================================

if st.session_state.last_analysis_request:

    q = st.session_state.last_analysis_request

    st.info(
        f"🔎 Selected setup: "
        f"{PAIR_LABELS.get(q['pair'], q['pair'])} • "
        f"{q['candle']} • "
        f"{q['expiry']}"
    )


# ============================================================
# SELECTION STATUS
# ============================================================

st.markdown(
    "### 🎛️ Selected Market Setup"
)

s1, s2, s3, s4 = st.columns(4)

s1.metric(
    "Pair",
    PAIR_LABELS.get(
        pair,
        pair,
    ),
)

s2.metric(
    "Candle",
    candle_selection,
)

s3.metric(
    "Expiry",
    expiry_selection,
)

if (
    pair == LOCKED_PAIR
    and candle_selection
    == LOCKED_TIMEFRAME
):

    s4.metric(
        "Strategy",
        "H20 LOCKED",
    )

else:

    s4.metric(
        "Strategy",
        "RESEARCH ONLY",
    )


# ============================================================
# TIMEFRAME MESSAGE
# ============================================================

if (
    candle_selection not in API_INTERVALS
    and not is_tick_timeframe(
        candle_selection
    )
):

    st.warning(
        f"⚠️ {candle_selection} is currently "
        "an interface/research option without "
        "a connected live feed."
    )

elif is_tick_timeframe(
    candle_selection
):

    st.success(
        f"🟢 Tick Engine connected for "
        f"{candle_selection}."
    )


if (
    pair != LOCKED_PAIR
    or candle_selection
    != LOCKED_TIMEFRAME
):

    st.info(
        "ℹ️ This pair/timeframe is selectable, "
        "but it has no validated trading rule yet. "
        "The reader will not manufacture a BUY/SELL "
        "prediction for it."
    )


# ============================================================
# CURRENT SIGNAL
# ============================================================

st.markdown(
    "### 🎯 Current Signal"
)

a, b, c = st.columns([1, 2, 1])

with a:

    css = (
        "#2ecc71"
        if signal == "SELL"
        else "#e67e22"
    )

    st.markdown(
        f'''
        <div class="signal-box">
            <div class="signal-title">SIGNAL</div>
            <div class="signal-value"
                 style="color:{css}">
                {signal}
            </div>
        </div>
        ''',
        unsafe_allow_html=True,
    )


with b:

    st.markdown(
        f'''
        <div class="signal-box">
            <div class="signal-title">REASON</div>
            <div style="font-size:1rem;
                        font-weight:650">
                {reason}
            </div>
        </div>
        ''',
        unsafe_allow_html=True,
    )


with c:

    st.markdown(
        f'''
        <div class="signal-box">
            <div class="signal-title">NY CORE</div>
            <div class="signal-value">
                {"ACTIVE" if ny_core else "INACTIVE"}
            </div>
        </div>
        ''',
        unsafe_allow_html=True,
    )


# ============================================================
# PROFESSIONAL ANALYSIS
# ============================================================

st.markdown(
    "### 🧠 Professional Analysis"
)

p1, p2, p3 = st.columns(3)

p1.metric(
    "Direction",
    "DOWN"
    if signal == "SELL"
    else "NO CLEAR DIRECTION",
)

p2.metric(
    "Analysis",
    "H20 ACTIVE"
    if signal == "SELL"
    else "NO SIGNAL",
)

p3.metric(
    "Current Trend",
    trend,
)


if signal == "SELL":

    st.success(
        "🔻 H20 ANALYSIS: "
        "DOWN / SELL CONDITION CONFIRMED"
    )

else:

    st.info(
        "⏸️ No confirmed locked H20 direction "
        "at this moment."
    )


# ============================================================
# VALIDATED PREDICTION
# ============================================================

if st.session_state.analysis_completed:

    st.markdown(
        "### 🎯 Validated Prediction"
    )

    (
        prediction,
        rate,
        avg_atr,
        validation,
    ) = validated_status(
        pair,
        candle_selection,
        expiry_selection,
        signal,
    )

    v1, v2, v3 = st.columns(3)

    v1.metric(
        "Prediction",
        prediction,
    )

    v2.metric(
        "Historical Rate",
        f"{rate:.2f}%"
        if rate is not None
        else "N/A",
    )

    v3.metric(
        "Status",
        validation,
    )

    if validation == "VALIDATED":

        st.success(
            "🔻 VALIDATED H20 SELL PREDICTION"
        )

        st.caption(
            f"Locked OOS evidence • "
            f"{H20_VALIDATED_SIGNALS:,} signals • "
            f"Historical rate {rate:.2f}% • "
            f"Average directional move "
            f"{avg_atr:.6f} ATR"
        )

    elif validation == (
        "ACTIVE / NOT DIRECTLY VALIDATED"
    ):

        st.warning(
            "⚠️ H20 SELL is active, but this "
            "selected expiry does not have a "
            "directly locked validation horizon."
        )

    else:

        st.info(
            "⏸️ WAIT — No validated prediction "
            "is active for this setup."
        )


# ============================================================
# LIVE CHART
# ============================================================

st.markdown(
    "### 📈 Live Candlestick Chart"
)

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
            name=PAIR_LABELS.get(
                pair,
                pair,
            ),
        )
    )

    fig.add_trace(
        go.Scatter(
            x=chart_df.Datetime,
            y=chart_df.EMA20,
            name="EMA20",
            mode="lines",
        )
    )

    fig.add_trace(
        go.Scatter(
            x=chart_df.Datetime,
            y=chart_df.EMA50,
            name="EMA50",
            mode="lines",
        )
    )

    fig.add_trace(
        go.Scatter(
            x=chart_df.Datetime,
            y=chart_df.Support20,
            name="Support 20",
            mode="lines",
            line=dict(dash="dot"),
        )
    )

    fig.add_trace(
        go.Scatter(
            x=chart_df.Datetime,
            y=chart_df.Resistance20,
            name="Resistance 20",
            mode="lines",
            line=dict(dash="dot"),
        )
    )

    if pd.notna(price):

        fig.add_hline(
            y=price,
            line_dash="dash",
            annotation_text=f"{price:.5f}",
            annotation_position="top right",
        )

    if (
        signal == "SELL"
        and pd.notna(atr14)
    ):

        fig.add_trace(
            go.Scatter(
                x=[candle_time],
                y=[
                    float(latest.high)
                    + float(atr14) * 0.25
                ],
                mode="markers+text",
                marker=dict(
                    symbol="triangle-down",
                    size=16,
                ),
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
        margin=dict(
            l=10,
            r=10,
            t=35,
            b=10,
        ),
        legend=dict(
            orientation="h",
            y=1.01,
            x=0,
        ),
    )

    st.markdown(
        "### 🔎 Chart Analysis Result"
    )

    chart_result = (
        "🔻 DOWN — H20 SELL"
        if signal == "SELL"
        else "⚪ NO CONFIRMED SIGNAL"
    )

    st.markdown(
        f'''
        <div class="signal-box">
            <div class="signal-title">
                CURRENT ANALYSIS
            </div>
            <div class="signal-value">
                {chart_result}
            </div>
            <div style="margin-top:8px">
                {reason}
            </div>
        </div>
        ''',
        unsafe_allow_html=True,
    )

    st.caption(
        f"Pair: "
        f"{PAIR_LABELS.get(pair, pair)} • "
        f"Candle: {candle_selection} • "
        f"Session: "
        f"{'ACTIVE' if ny_core else 'INACTIVE'} • "
        f"Trend: {trend}"
    )

    st.plotly_chart(
        fig,
        use_container_width=True,
        config={
            "displaylogo": False,
            "responsive": True,
        },
    )

else:

    st.warning(
        "Live chart data is currently unavailable."
    )


# ============================================================
# MARKET DETAILS
# ============================================================

st.markdown(
    "### 📍 Market Details"
)

d1, d2, d3, d4 = st.columns(4)

d1.metric(
    "Support 20",
    f"{support:.5f}"
    if pd.notna(support)
    else "—",
)

d2.metric(
    "Resistance 20",
    f"{resistance:.5f}"
    if pd.notna(resistance)
    else "—",
)

d3.metric(
    "Completed Candle",
    candle_time.strftime(
        "%H:%M UTC"
    )
    if candle_time is not None
    else "—",
)

d4.metric(
    "Candle Age",
    f"{candle_age:.1f} min"
    if candle_age is not None
    else "—",
)


if latest is not None:

    st.markdown(
        "### 🕯️ Latest Completed Candle"
    )

    o1, o2, o3, o4 = st.columns(4)

    o1.metric(
        "Open",
        f"{latest.open:.5f}",
    )

    o2.metric(
        "High",
        f"{latest.high:.5f}",
    )

    o3.metric(
        "Low",
        f"{latest.low:.5f}",
    )

    o4.metric(
        "Close",
        f"{latest.close:.5f}",
    )


# ============================================================
# SYSTEM STATUS
# ============================================================

st.markdown(
    "### 🛡️ System Status"
)

t1, t2, t3, t4, t5 = st.columns(5)

t1.markdown(
    "**LIVE FEED**  \n"
    + (
        "🟢 PASS"
        if data_error is None
        else "🔴 ERROR"
    )
)

t2.markdown(
    "**INDICATORS**  \n"
    + (
        "🟢 PASS"
        if latest is not None
        else "🟠 WAIT"
    )
)

t3.markdown(
    "**H20 RULE**  \n🔒 LOCKED"
)

t4.markdown(
    "**AUTO TRADING**  \n🚫 DISABLED"
)

t5.markdown(
    "**FRESHNESS**  \n"
    + (
        "🟢 PASS"
        if freshness_ok
        else "🟠 REVIEW"
    )
)


# ============================================================
# READER STATUS
# ============================================================

st.markdown(
    "### 🌐 Reader Status"
)

r1, r2, r3 = st.columns(3)

r1.write(
    f"**Market:** {market_status}"
)

r2.write(
    f"**Analysis Interval:** "
    f"{st.session_state.analysis_interval}s"
)

last_refresh_text = (
    st.session_state.last_refresh.strftime(
        "%Y-%m-%d %H:%M:%S UTC"
    )
    if st.session_state.last_refresh is not None
    else "—"
)

r3.write(
    f"**Last Refresh:** "
    f"{last_refresh_text}"
)


if data_error:

    st.error(
        f"Reader error: {data_error}"
    )


# ============================================================
# FOOTER
# ============================================================

st.divider()

st.markdown(
    """
    <div class="small-text">
    Live source: Biquote OHLC + Biquote SignalR Tick Engine.
    The live feed is not claimed to be identical to the historical
    BID dataset.

    EUR/USD 5-minute H20 is the only currently locked validated
    strategy in this application.

    Other pairs/timeframes are research selections until their own
    historical and unseen validation is completed.

    10s / 15s / 30s candles are constructed from the live tick stream.
    Their construction is technically validated, but they are not
    presented as validated trading strategies.

    No automatic order execution is enabled.
    </div>
    """,
    unsafe_allow_html=True,
)
