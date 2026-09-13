
import streamlit as st
import pandas as pd
import numpy as np
import requests
from datetime import timezone

# ============================================================
# SHOAIB DATA READER — LOCKED H20 LIVE READER
# ============================================================

st.set_page_config(
    page_title="Shoaib Data Reader",
    page_icon="📊",
    layout="wide"
)

APP_NAME = "SHOAIB DATA READER"

PAIR_OPTIONS = [
    "EUR/USD",
    "GBP/USD",
    "USD/JPY",
    "AUD/USD",
    "USD/CAD",
    "USD/CHF",
    "NZD/USD"
]

TIMEFRAME_OPTIONS = [
    "5-Minute",
    "15-Minute",
    "30-Minute",
    "1-Hour"
]

API_URL = "https://biquote.io/api/EURUSD/ohlc?interval=5m&limit=100"

LOOKBACK = 20
ATR_PERIOD = 14

# ============================================================
# LOCKED H20 STRATEGY — DO NOT MODIFY
# ============================================================

LOCKED_STRATEGY = "H20_BEARISH_NY"

NY_START_UTC = 13
NY_END_UTC = 17

AUTO_TRADING = False
STRATEGY_LOCKED = True


# ============================================================
# LIVE DATA
# ============================================================

def get_live_data():

    r = requests.get(API_URL, timeout=15)
    r.raise_for_status()

    data = r.json()
    bars = data.get("bars", [])

    if not bars:
        raise ValueError("No live candles received.")

    df = pd.DataFrame(bars)

    required = [
        "openTime",
        "open",
        "high",
        "low",
        "close"
    ]

    for col in required:
        if col not in df.columns:
            raise ValueError(f"Missing column: {col}")

    df["Datetime"] = pd.to_datetime(
        df["openTime"],
        unit="ms",
        utc=True
    )

    for col in ["open", "high", "low", "close"]:
        df[col] = pd.to_numeric(
            df[col],
            errors="coerce"
        )

    df = (
        df
        .sort_values("Datetime")
        .drop_duplicates(
            subset=["Datetime"]
        )
        .reset_index(drop=True)
    )

    df = df.dropna(
        subset=[
            "Datetime",
            "open",
            "high",
            "low",
            "close"
        ]
    )

    return df


# ============================================================
# INDICATORS
# ============================================================

def calculate_indicators(df):

    df = df.copy()

    previous_close = df["close"].shift(1)

    tr1 = df["high"] - df["low"]
    tr2 = (df["high"] - previous_close).abs()
    tr3 = (df["low"] - previous_close).abs()

    df["TR"] = pd.concat(
        [tr1, tr2, tr3],
        axis=1
    ).max(axis=1)

    df["ATR14"] = (
        df["TR"]
        .rolling(ATR_PERIOD)
        .mean()
    )

    df["EMA20"] = (
        df["close"]
        .ewm(
            span=20,
            adjust=False
        )
        .mean()
    )

    df["EMA50"] = (
        df["close"]
        .ewm(
            span=50,
            adjust=False
        )
        .mean()
    )

    df["EMA_DIRECTION"] = np.where(
        df["EMA20"] > df["EMA50"],
        "BULL",
        "BEAR"
    )

    return df


# ============================================================
# COMPLETED 5-MINUTE CANDLE
# ============================================================

def get_completed_candle(df):

    now = pd.Timestamp.now(tz="UTC")

    completed_limit = now.floor("5min")

    completed = df[
        df["Datetime"]
        + pd.Timedelta(minutes=5)
        <= completed_limit
    ].copy()

    if completed.empty:
        return None

    return completed.iloc[-1]


# ============================================================
# LOCKED H20 SIGNAL ENGINE
# ============================================================

def get_signal(row):

    if row is None:

        return {
            "signal": "NO SIGNAL",
            "confidence": "NONE",
            "reason": "NO COMPLETED CANDLE"
        }

    candle_time = row["Datetime"]

    hour = candle_time.hour

    trend = row["EMA_DIRECTION"]

    # Weekend safety
    if candle_time.weekday() >= 5:

        return {
            "signal": "NO SIGNAL",
            "confidence": "NONE",
            "reason": "MARKET CLOSED — WEEKEND"
        }

    # ========================================================
    # LOCKED H20 RULE
    # ========================================================

    if NY_START_UTC <= hour < NY_END_UTC:

        if trend == "BEAR":

            return {
                "signal": "SELL",
                "confidence": "HIGH",
                "reason": (
                    "H20 BEARISH NY CORE "
                    "CONDITION SATISFIED"
                )
            }

        return {
            "signal": "NO SIGNAL",
            "confidence": "NONE",
            "reason": (
                "NY CORE ACTIVE BUT "
                "EMA TREND IS NOT BEARISH"
            )
        }

    return {
        "signal": "NO SIGNAL",
        "confidence": "NONE",
        "reason": "OUTSIDE NY CORE SESSION"
    }


# ============================================================
# HEADER
# ============================================================

st.title("📊 SHOAIB DATA READER")

st.caption(
    "Locked H20 EUR/USD 5-Minute Signal Reader"
)

st.divider()


# ============================================================
# CONTROLS
# ============================================================

c1, c2, c3 = st.columns(3)

with c1:

    selected_pair = st.selectbox(
        "Currency Pair",
        PAIR_OPTIONS
    )

with c2:

    selected_timeframe = st.selectbox(
        "Timeframe",
        TIMEFRAME_OPTIONS
    )

with c3:

    analysis_interval = st.slider(
        "Analysis Interval (seconds)",
        min_value=5,
        max_value=300,
        value=30,
        step=5
    )


# ============================================================
# SESSION STATE
# ============================================================

if "analysis_running" not in st.session_state:

    st.session_state.analysis_running = False


b1, b2, b3 = st.columns(3)

with b1:

    if st.button(
        "▶️ START ANALYSIS",
        use_container_width=True
    ):

        st.session_state.analysis_running = True
        st.rerun()


with b2:

    if st.button(
        "⏹️ STOP ANALYSIS",
        use_container_width=True
    ):

        st.session_state.analysis_running = False
        st.rerun()


with b3:

    analyze_now = st.button(
        "🔄 ANALYZE NOW",
        use_container_width=True
    )


if st.session_state.analysis_running:

    st.success(
        f"🟢 AUTO ANALYSIS RUNNING — "
        f"Every {analysis_interval} seconds"
    )

else:

    st.info(
        "⚪ AUTO ANALYSIS STOPPED"
    )


st.divider()


# ============================================================
# VALIDATION
# ============================================================

if (
    selected_pair != "EUR/USD"
    or selected_timeframe != "5-Minute"
):

    st.warning(
        "⚠️ H20 signal engine صرف "
        "EUR/USD 5-Minute کے لیے "
        "validated اور locked ہے۔"
    )

    st.info(
        "دوسرے pairs/timeframes کو signal "
        "دینے کے لیے الگ validation ضروری ہوگی۔"
    )


# ============================================================
# LIVE READER
# ============================================================

run_every_value = (
    f"{analysis_interval}s"
    if st.session_state.analysis_running
    else None
)


@st.fragment(run_every=run_every_value)
def live_reader():

    try:

        df = get_live_data()

        df = calculate_indicators(df)

        completed = get_completed_candle(df)

        if completed is None:

            st.error(
                "Completed 5-minute candle "
                "available نہیں ہے۔"
            )

            return


        signal_data = get_signal(completed)

        candle_time = completed["Datetime"]

        price = completed["close"]

        ema20 = completed["EMA20"]

        ema50 = completed["EMA50"]

        atr14 = completed["ATR14"]

        trend = completed["EMA_DIRECTION"]

        ny_active = (
            NY_START_UTC
            <= candle_time.hour
            < NY_END_UTC
        )


        # ====================================================
        # MAIN METRICS
        # ====================================================

        m1, m2, m3, m4 = st.columns(4)

        with m1:

            st.metric(
                "Live Price",
                f"{price:.5f}"
            )

        with m2:

            st.metric(
                "EMA20",
                f"{ema20:.5f}"
            )

        with m3:

            st.metric(
                "EMA50",
                f"{ema50:.5f}"
            )

        with m4:

            st.metric(
                "ATR14",
                f"{atr14:.6f}"
            )


        st.divider()


        # ====================================================
        # STATUS
        # ====================================================

        s1, s2, s3, s4 = st.columns(4)

        with s1:

            st.write("### Trend")

            st.write(
                f"**{trend}**"
            )

        with s2:

            st.write("### NY Core")

            st.write(
                "**ACTIVE**"
                if ny_active
                else "**INACTIVE**"
            )

        with s3:

            st.write("### Signal")

            if signal_data["signal"] == "SELL":

                st.error(
                    "**SELL**"
                )

            else:

                st.write(
                    f"**{signal_data['signal']}**"
                )

        with s4:

            st.write("### Confidence")

            st.write(
                f"**{signal_data['confidence']}**"
            )


        st.divider()


        # ====================================================
        # REASON
        # ====================================================

        st.subheader(
            "🧠 Reader Reason"
        )

        st.info(
            signal_data["reason"]
        )


        # ====================================================
        # COMPLETED CANDLE
        # ====================================================

        st.subheader(
            "🕯️ Completed Candle"
        )

        candle_info = pd.DataFrame({

            "Item": [

                "Candle Time (UTC)",
                "Open",
                "High",
                "Low",
                "Close",
                "EMA20",
                "EMA50",
                "ATR14"

            ],

            "Value": [

                str(candle_time),

                f"{completed['open']:.5f}",

                f"{completed['high']:.5f}",

                f"{completed['low']:.5f}",

                f"{completed['close']:.5f}",

                f"{completed['EMA20']:.5f}",

                f"{completed['EMA50']:.5f}",

                f"{completed['ATR14']:.6f}"

            ]

        })


        st.dataframe(
            candle_info,
            use_container_width=True,
            hide_index=True
        )


        # ====================================================
        # SYSTEM STATUS
        # ====================================================

        st.subheader(
            "⚙️ System Status"
        )

        st.success(
            "LIVE DATA FEED : PASS"
        )

        st.success(
            "INDICATOR ENGINE : PASS"
        )

        st.success(
            "H20 RULE : LOCKED"
        )

        st.success(
            "STRATEGY MODIFICATION : DISABLED"
        )

        st.success(
            "AUTO TRADING : DISABLED"
        )

        st.caption(
            f"Analysis interval selected: "
            f"{analysis_interval} seconds"
        )

        st.caption(
            f"Reader status: "
            f"{'RUNNING' if st.session_state.analysis_running else 'STOPPED'}"
        )


    except Exception as e:

        st.error(
            f"Live reader error: {e}"
        )


# ============================================================
# RUN LIVE READER
# ============================================================

live_reader()
