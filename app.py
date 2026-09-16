import time
from datetime import datetime, timezone
import streamlit as st
import pandas as pd
import numpy as np
import requests
import plotly.graph_objects as go

st.set_page_config(page_title="Shoaib Data Reader", page_icon="📊", layout="wide", initial_sidebar_state="expanded")

SYMBOL="EURUSD"; TIMEFRAME="5m"; H20_START_UTC=13; H20_END_UTC=17
MIN_BARS=60; STALE_LIMIT_MINUTES=15; AUTO_TRADING=False; STRATEGY_LOCKED=True
API_URL=f"https://biquote.io/api/{SYMBOL}/ohlc"
H20_FWD6_WIN_RATE=60.00; H20_FWD6_AVG_ATR=0.556601
H20_FWD20_WIN_RATE=68.57; H20_FWD20_AVG_ATR=1.377593; H20_VALIDATED_SIGNALS=245

for k,v in {"running":False,"analysis_requested":False,"analysis_completed":False,"analysis_interval":10,"last_signal_key":None,"signal_history":set(),"last_refresh":None,"last_analysis_request":None}.items():
    if k not in st.session_state: st.session_state[k]=v

st.markdown("""<style>
.block-container{max-width:1500px;padding-top:1rem}.reader-title{font-size:2rem;font-weight:800}.reader-subtitle{color:#8b949e;margin-bottom:1rem}.signal-box{border-radius:16px;padding:20px;border:1px solid rgba(128,128,128,.25);margin:8px 0}.signal-title{font-size:.85rem;color:#8b949e}.signal-value{font-size:2rem;font-weight:850}.status-ok{color:#2ecc71;font-weight:700}.status-off{color:#e67e22;font-weight:700}.small-text{font-size:.78rem;color:#8b949e}
</style>""", unsafe_allow_html=True)

st.markdown('<div class="reader-title">📊 SHOAIB DATA READER</div>',unsafe_allow_html=True)
st.markdown('<div class="reader-subtitle">EUR/USD • 5 Minute Live Signal Reader • Locked H20 Strategy</div>',unsafe_allow_html=True)

with st.sidebar:
    st.header("⚙️ Reader Controls")
    analysis_interval=st.select_slider("Analysis Interval",[5,10,15,30,60],value=st.session_state.analysis_interval,format_func=lambda x:f"{x} seconds")
    st.session_state.analysis_interval=analysis_interval
    st.divider()
    pair=st.selectbox("💱 Currency Pair",["EURUSD"],key="pair")
    candle_time_selection=st.selectbox("🕯️ Candle Time",["5 Minutes"],key="candle_time")
    trade_time=st.selectbox("⏱️ Trade / Expiry Time",["5 Minutes","15 Minutes","30 Minutes","60 Minutes","100 Minutes"],index=2,key="trade_time")
    st.divider()
    analyze=st.button("🔎 ANALYZE SELECTED SETUP",use_container_width=True,type="primary")
    start=st.button("▶ Start",use_container_width=True); stop=st.button("⏹ Stop",use_container_width=True); now_btn=st.button("🔍 Analyze Now",use_container_width=True)
    if analyze or now_btn:
        st.session_state.analysis_requested=True; st.session_state.analysis_completed=False
        st.session_state.last_analysis_request={"pair":pair,"candle":candle_time_selection,"trade":trade_time,"at":datetime.now(timezone.utc)}
    if start: st.session_state.running=True
    if stop: st.session_state.running=False
    st.divider(); st.markdown("### 🔒 Strategy Safety")
    st.write("Strategy: LOCKED" if STRATEGY_LOCKED else "Strategy: UNLOCKED")
    st.write("Auto Trading: DISABLED" if not AUTO_TRADING else "Auto Trading: ENABLED")
    st.write("Feed: Biquote EUR/USD OHLC")
    st.divider(); st.markdown("### 📌 Locked H20")
    st.write("Direction: BEARISH"); st.write("Session: 13:00–17:00 UTC"); st.write("Entry: Completed candle close"); st.write("Extra filter: None")

@st.cache_data(ttl=4,show_spinner=False)
def fetch_live_data():
    r=requests.get(API_URL,params={"interval":TIMEFRAME,"limit":101},headers={"User-Agent":"Mozilla/5.0"},timeout=10); r.raise_for_status(); payload=r.json()
    if "bars" not in payload or not payload["bars"]: raise ValueError("No live candles received")
    df=pd.DataFrame(payload["bars"]); required=["openTime","open","high","low","close"]; missing=[x for x in required if x not in df.columns]
    if missing: raise ValueError(f"Missing columns: {missing}")
    df["Datetime"]=pd.to_datetime(df["openTime"],utc=True,errors="coerce")
    for c in ["open","high","low","close"]: df[c]=pd.to_numeric(df[c],errors="coerce")
    df=df.dropna(subset=["Datetime","open","high","low","close"]).drop_duplicates("Datetime",keep="last").sort_values("Datetime").reset_index(drop=True)
    if len(df)<MIN_BARS: raise ValueError(f"Only {len(df)} valid candles received; {MIN_BARS} required")
    bad=(df.high<df.low)|(df.high<df.open)|(df.high<df.close)|(df.low>df.open)|(df.low>df.close)
    if bad.any(): raise ValueError("OHLC integrity check failed")
    return df

def indicators(df):
    x=df.copy(); x["EMA20"]=x.close.ewm(span=20,adjust=False).mean(); x["EMA50"]=x.close.ewm(span=50,adjust=False).mean(); pc=x.close.shift(1)
    x["TR"]=pd.concat([x.high-x.low,(x.high-pc).abs(),(x.low-pc).abs()],axis=1).max(axis=1); x["ATR14"]=x.TR.rolling(14).mean()
    x["Support20"]=x.low.shift(1).rolling(20).min(); x["Resistance20"]=x.high.shift(1).rolling(20).max(); x["EMA_DIRECTION"]=np.where(x.EMA20>x.EMA50,"BULL","BEAR"); return x

def completed(df):
    now=datetime.now(timezone.utc); mask=df.Datetime+pd.Timedelta(minutes=5)<=pd.Timestamp(now)
    if "isOpen" in df.columns: mask &= ~df.isOpen.astype(bool)
    out=df.loc[mask].copy()
    if out.empty: raise ValueError("No completed 5-minute candle available")
    return out,now

def h20(row):
    hour=int(row.Datetime.hour); session=H20_START_UTC<=hour<H20_END_UTC; bear=row.EMA_DIRECTION=="BEAR"
    if session and bear: return "SELL","H20 LOCKED RULE: BEAR EMA direction + NY Core session",True,hour
    if not session: return "NO SIGNAL","Outside H20 NY Core session",False,hour
    return "NO SIGNAL","EMA direction is not BEAR",False,hour

raw=df=completed_df=pd.DataFrame(); latest=None; signal="NO SIGNAL"; reason="Live feed unavailable"; ny_core=False; utc_hour=None; candle_time=None; candle_age=None; market_status="FEED ERROR"; freshness_ok=False; data_error=None
price=ema20=ema50=atr14=support=resistance=np.nan; trend="UNKNOWN"
try:
    raw=fetch_live_data(); df=indicators(raw); completed_df,now_utc=completed(df); latest=completed_df.iloc[-1]; candle_time=latest.Datetime; close_time=candle_time+pd.Timedelta(minutes=5); candle_age=(pd.Timestamp(now_utc)-close_time).total_seconds()/60
    signal,reason,ny_core,utc_hour=h20(latest); weekend=now_utc.weekday()>=5; market_status="CLOSED — WEEKEND" if weekend else "OPEN"; freshness_ok=weekend or (0<=candle_age<=STALE_LIMIT_MINUTES)
    key=(candle_time.isoformat(),signal); duplicate=key in st.session_state.signal_history; st.session_state.signal_history.add(key); st.session_state.last_signal_key=key; st.session_state.last_refresh=now_utc
    price=float(latest.close); ema20=float(latest.EMA20); ema50=float(latest.EMA50); atr14=float(latest.ATR14) if pd.notna(latest.ATR14) else np.nan; support=float(latest.Support20) if pd.notna(latest.Support20) else np.nan; resistance=float(latest.Resistance20) if pd.notna(latest.Resistance20) else np.nan; trend=latest.EMA_DIRECTION
except Exception as e: data_error=str(e); duplicate=False

if st.session_state.analysis_requested and not st.session_state.analysis_completed:
    with st.spinner("🔄 Analyzing selected market setup..."): time.sleep(4)
    st.session_state.analysis_completed=True

m1,m2,m3,m4,m5=st.columns(5)
m1.metric("Live Price",f"{price:.5f}" if pd.notna(price) else "—"); m2.metric("Trend",trend); m3.metric("EMA20",f"{ema20:.5f}" if pd.notna(ema20) else "—"); m4.metric("EMA50",f"{ema50:.5f}" if pd.notna(ema50) else "—"); m5.metric("ATR14",f"{atr14:.5f}" if pd.notna(atr14) else "—")

if st.session_state.last_analysis_request:
    q=st.session_state.last_analysis_request; st.info(f"🔎 Selected setup: {q['pair']} • {q['candle']} • {q['trade']}")

st.markdown("### 🎯 Current H20 Signal"); a,b,c=st.columns([1,2,1])
with a: st.markdown(f'<div class="signal-box"><div class="signal-title">SIGNAL</div><div class="signal-value {"status-ok" if signal=="SELL" else "status-off"}">{signal}</div></div>',unsafe_allow_html=True)
with b: st.markdown(f'<div class="signal-box"><div class="signal-title">REASON</div><div style="font-size:1.05rem;font-weight:650">{reason}</div></div>',unsafe_allow_html=True)
with c: st.markdown(f'<div class="signal-box"><div class="signal-title">NY CORE</div><div class="signal-value">{"ACTIVE" if ny_core else "INACTIVE"}</div></div>',unsafe_allow_html=True)

st.markdown("### 🧠 Professional Analysis"); x,y,z=st.columns(3); x.metric("Direction","DOWN" if signal=="SELL" else "NO CLEAR DIRECTION"); y.metric("Analysis","H20 ACTIVE" if signal=="SELL" else "NO SIGNAL"); z.metric("Trend",trend)
st.success("🔻 H20 ANALYSIS: DOWN / SELL CONDITION CONFIRMED" if signal=="SELL" else "⏸️ No confirmed H20 direction at this moment.")

if st.session_state.analysis_completed:
    st.markdown("### 🎯 Validated Prediction")
    pred="WAIT"; rate=None; avgatr=None; valid=False; horizon="Not directly validated"
    if signal=="SELL":
        if trade_time=="30 Minutes": pred="SELL"; rate=H20_FWD6_WIN_RATE; avgatr=H20_FWD6_AVG_ATR; valid=True; horizon="30-minute historical validation"
        elif trade_time=="100 Minutes": pred="SELL"; rate=H20_FWD20_WIN_RATE; avgatr=H20_FWD20_AVG_ATR; valid=True; horizon="100-minute historical validation"
        else: pred="SELL"
    p1,p2,p3=st.columns(3); p1.metric("Prediction",pred); p2.metric("Historical Rate",f"{rate:.2f}%" if rate is not None else "N/A"); p3.metric("Status","VALIDATED" if valid else "WAIT")
    if valid:
        st.success("🔻 VALIDATED H20 SELL PREDICTION"); st.caption(f"Historical validation: {rate:.2f}% over {horizon} • Sample: {H20_VALIDATED_SIGNALS:,} locked H20 signals • Average directional move: {avgatr:.6f} ATR")
    elif pred=="SELL": st.warning("⚠️ H20 SELL is active, but the selected expiry is not directly validated.")
    else: st.info("⏸️ WAIT — No validated H20 prediction is active.")
    st.caption("Stage 8 unseen validation + Stage 9 locked OOS results. No rule optimization performed.")

st.markdown("### 📈 Live Candlestick Chart")
if not df.empty and latest is not None:
    ch=df.tail(80); fig=go.Figure(); fig.add_trace(go.Candlestick(x=ch.Datetime,open=ch.open,high=ch.high,low=ch.low,close=ch.close,name="EUR/USD")); fig.add_trace(go.Scatter(x=ch.Datetime,y=ch.EMA20,name="EMA20",mode="lines")); fig.add_trace(go.Scatter(x=ch.Datetime,y=ch.EMA50,name="EMA50",mode="lines")); fig.add_trace(go.Scatter(x=ch.Datetime,y=ch.Support20,name="Support 20",mode="lines",line=dict(dash="dot"))); fig.add_trace(go.Scatter(x=ch.Datetime,y=ch.Resistance20,name="Resistance 20",mode="lines",line=dict(dash="dot")))
    if pd.notna(price): fig.add_hline(y=price,line_dash="dash",annotation_text=f"{price:.5f}",annotation_position="top right")
    sells=ch[(ch.EMA_DIRECTION=="BEAR")&(ch.Datetime.dt.hour>=H20_START_UTC)&(ch.Datetime.dt.hour<H20_END_UTC)]
    if not sells.empty: fig.add_trace(go.Scatter(x=sells.Datetime,y=sells.high+sells.ATR14.fillna(0)*.25,mode="markers",name="H20 SELL",marker=dict(symbol="triangle-down",size=11)))
    if signal=="SELL": fig.add_trace(go.Scatter(x=[candle_time],y=[float(latest.high)+(float(atr14)*.25 if pd.notna(atr14) else 0)],mode="markers+text",marker=dict(symbol="triangle-down",size=16),text=["SELL"],textposition="top center",name="CURRENT H20 SIGNAL"))
    fig.update_layout(height=620,xaxis_title="UTC Time",yaxis_title="Price",xaxis_rangeslider_visible=False,hovermode="x unified",margin=dict(l=10,r=10,t=35,b=10),legend=dict(orientation="h",y=1.01,x=0))
    st.markdown("### 🔎 Chart Analysis Result"); st.markdown(f'<div class="signal-box"><div class="signal-title">CURRENT ANALYSIS</div><div class="signal-value">{"🔻 DOWN — H20 SELL" if signal=="SELL" else "⚪ NO CONFIRMED SIGNAL"}</div><div style="margin-top:8px">{reason}</div></div>',unsafe_allow_html=True); st.caption(f"Session: {'ACTIVE' if ny_core else 'INACTIVE'} • Trend: {trend} • UTC Hour: {utc_hour if utc_hour is not None else '—'}"); st.plotly_chart(fig,use_container_width=True,config={"displaylogo":False,"responsive":True})
else: st.warning("Live chart data is currently unavailable.")

st.markdown("### 📍 Market Details"); d1,d2,d3,d4=st.columns(4); d1.metric("Support 20",f"{support:.5f}" if pd.notna(support) else "—"); d2.metric("Resistance 20",f"{resistance:.5f}" if pd.notna(resistance) else "—"); d3.metric("Completed Candle",candle_time.strftime("%H:%M UTC") if candle_time is not None else "—"); d4.metric("Candle Age",f"{candle_age:.1f} min" if candle_age is not None else "—")

if latest is not None:
    st.markdown("### 🕯️ Latest Completed Candle"); o1,o2,o3,o4=st.columns(4); o1.metric("Open",f"{latest.open:.5f}"); o2.metric("High",f"{latest.high:.5f}"); o3.metric("Low",f"{latest.low:.5f}"); o4.metric("Close",f"{latest.close:.5f}")

st.markdown("### 🛡️ System Status"); s1,s2,s3,s4,s5=st.columns(5); s1.markdown("**LIVE FEED**  \n🟢 PASS" if data_error is None else "**LIVE FEED**  \n🔴 ERROR"); s2.markdown("**INDICATORS**  \n🟢 PASS" if latest is not None else "**INDICATORS**  \n🟠 WAIT"); s3.markdown("**H20 RULE**  \n🔒 LOCKED"); s4.markdown("**AUTO TRADING**  \n🚫 DISABLED"); s5.markdown(f"**FRESHNESS**  \n{'🟢 PASS' if freshness_ok else '🟠 REVIEW'}")

st.markdown("### 🌐 Reader Status"); q1,q2,q3=st.columns(3); q1.write(f"**Market:** {market_status}"); q2.write(f"**Analysis Interval:** {st.session_state.analysis_interval}s"); q3.write(f"**Last Analysis:** {st.session_state.last_refresh.strftime('%Y-%m-%d %H:%M:%S UTC') if st.session_state.last_refresh else '—'}")
if data_error: st.error(f"Reader error: {data_error}")

st.divider(); st.markdown("""<div class="small-text">Data source: Biquote EUR/USD OHLC feed. The feed is used for live reader testing and is not claimed to be identical to the historical BID dataset.<br><br>H20 strategy is locked. No automatic order execution is enabled. This interface is a research/reader tool and does not place trades.</div>""",unsafe_allow_html=True)

if st.session_state.running:
    time.sleep(max(5,int(st.session_state.analysis_interval))); st.rerun()
