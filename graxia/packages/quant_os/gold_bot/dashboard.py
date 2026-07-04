"""
Gold Bot Dashboard - Streamlit real-time monitoring
Run: streamlit run gold_bot/dashboard.py
"""

import streamlit as st
import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
from pathlib import Path
from datetime import datetime, timedelta
import glob
import os
import json

LOG_DIR = Path(r"C:\Users\menum\graxia os\graxia\packages\quant_os\logs")
BOT_LOG = LOG_DIR / "paper_7day.log"
PID_FILE = LOG_DIR / "paper_7day.pid"
HEALTH_LOG = LOG_DIR / "health_check.log"
HEALTH_JSON = LOG_DIR / "health_report_latest.json"
ERR_LOG = LOG_DIR / "paper_7day_err.log"
ALT_CSV_DIR = Path(r"C:\Users\menum\graxia os\graxia\packages\quant_os\gold_bot\logs")

st.set_page_config(
    page_title="Gold Bot Dashboard",
    page_icon=":chart_with_upwards_trend:",
    layout="wide",
    initial_sidebar_state="collapsed",
)

st.markdown(
    """
    <style>
    .stApp { background-color: #0e1117; color: #fafafa; }
    [data-testid="stMetric"] {
        background: #1a1d23; border-radius: 8px; padding: 12px;
        border: 1px solid #2a2d35;
    }
    [data-testid="stMetric"] label { color: #8b8fa3; font-size: 0.85rem; }
    [data-testid="stMetric"] [data-testid="stMetricValue"] { color: #fafafa; }
    .status-alive { color: #00d26a; font-weight: bold; }
    .status-dead { color: #ff4757; font-weight: bold; }
    .tier-S { color: #ffd700; font-weight: bold; }
    .tier-A { color: #00d26a; font-weight: bold; }
    .tier-B { color: #ffa502; font-weight: bold; }
    .tier-C { color: #ff6348; font-weight: bold; }
    .tier-BENCH { color: #747d8c; font-weight: bold; }
    .win { color: #00d26a; }
    .loss { color: #ff4757; }
    .block-container { padding-top: 1.5rem; }
    </style>
    """,
    unsafe_allow_html=True,
)


def _read_safe(path, encoding="cp1252"):
    if not path.exists():
        return ""
    try:
        return path.read_text(encoding=encoding)
    except Exception:
        try:
            return path.read_text(encoding="utf-8", errors="replace")
        except Exception:
            return ""


def _get_latest_csv():
    csvs = sorted(glob.glob(str(LOG_DIR / "paper_trades_*.csv")))
    if not csvs:
        csvs = sorted(glob.glob(str(ALT_CSV_DIR / "paper_trades_*.csv")))
    return Path(csvs[-1]) if csvs else None


def _load_trades():
    csv_path = _get_latest_csv()
    if csv_path is None:
        return pd.DataFrame(), None
    try:
        df = pd.read_csv(csv_path, encoding="cp1252", on_bad_lines="skip")
    except Exception:
        try:
            df = pd.read_csv(csv_path, encoding="utf-8", on_bad_lines="skip")
        except Exception:
            return pd.DataFrame(), csv_path
    for col in ["entry", "exit", "sl", "tp", "quantity", "pnl", "pnl_pct", "score"]:
        if col in df.columns:
            df[col] = pd.to_numeric(df[col], errors="coerce")
    return df, csv_path


def _parse_bot_status():
    text = _read_safe(BOT_LOG)
    lines = text.strip().splitlines()
    r = {
        "alive": False, "mt5_connected": False, "started": None,
        "symbol": "XAUUSD", "capital": 0.0, "risk_pct": 0.25,
        "max_dd": 8.0, "cycle_count": 0, "open_count": 0,
        "closed_count": 0, "strategies_loaded": 0, "last_line": "",
        "last_error": "", "uptime_str": "N/A", "pid": None,
    }
    for line in lines:
        s = line.strip()
        if "MT5 Connected:" in s:
            val = s.split("MT5 Connected:")[-1].strip()
            r["mt5_connected"] = "Pepperstone" in val or "ON" in val
        if "Started:" in s:
            r["started"] = s.split("Started:")[-1].strip()
        if "Capital:" in s:
            try:
                r["capital"] = float(s.split("Capital:")[-1].strip().replace("$", "").replace(",", ""))
            except Exception:
                pass
        if "Risk/Trade:" in s:
            try:
                r["risk_pct"] = float(s.split("Risk/Trade:")[-1].strip().replace("%", ""))
            except Exception:
                pass
        if "Max DD:" in s:
            try:
                r["max_dd"] = float(s.split("Max DD:")[-1].strip().replace("%", ""))
            except Exception:
                pass
        if "Registered" in s and "strategies" in s:
            try:
                r["strategies_loaded"] = int(s.split("Registered")[-1].strip().split()[0])
            except Exception:
                pass
        if "[Heartbeat]" in s:
            r["last_line"] = s
            for p in s.split("|"):
                p = p.strip()
                if p.startswith("Open:"):
                    try:
                        r["open_count"] = int(p.split(":")[-1].strip())
                    except Exception:
                        pass
                elif p.startswith("Closed:"):
                    try:
                        r["closed_count"] = int(p.split(":")[-1].strip())
                    except Exception:
                        pass
                elif p.startswith("Cycle "):
                    try:
                        r["cycle_count"] = int(p.replace("Cycle", "").strip().split()[0])
                    except Exception:
                        pass
        if "Error:" in s:
            r["last_error"] = s
    pid_text = _read_safe(PID_FILE).strip()
    if pid_text:
        try:
            r["pid"] = int(pid_text)
            r["alive"] = True
        except Exception:
            pass
    if r["started"]:
        try:
            start = datetime.strptime(r["started"], "%Y-%m-%d %H:%M:%S UTC")
            delta = datetime.utcnow() - start
            hours = delta.total_seconds() / 3600
            r["uptime_str"] = f"{int(hours)}h {int((hours % 1) * 60)}m"
        except Exception:
            pass
    return r


def _parse_health():
    text = _read_safe(HEALTH_LOG)
    lines = text.strip().splitlines()
    r = {
        "timestamp": "N/A", "bot_status": "UNKNOWN", "mt5_status": "UNKNOWN",
        "log_growing": "UNKNOWN", "trades": 0, "action": "N/A", "errors": [],
    }
    block_start = None
    for i, line in enumerate(lines):
        if "HEALTH CHECK START" in line:
            block_start = i
    if block_start is not None:
        for line in lines[block_start:]:
            s = line.strip()
            if "Bot process:" in s:
                r["bot_status"] = s.split("Bot process:")[-1].strip()
            elif "MT5 terminal:" in s:
                r["mt5_status"] = s.split("MT5 terminal:")[-1].strip()
            elif "Log growing:" in s:
                r["log_growing"] = s.split("Log growing:")[-1].strip()
            elif "Trades:" in s:
                try:
                    r["trades"] = int(s.split("Trades:")[-1].strip().split()[0])
                except Exception:
                    pass
            elif "ACTION:" in s:
                r["action"] = s.split("ACTION:")[-1].strip()
            elif "ERR:" in s:
                r["errors"].append(s)
            if r["timestamp"] == "N/A" and s.startswith("["):
                try:
                    r["timestamp"] = s.split("]")[0].replace("[", "")
                except Exception:
                    pass
    if HEALTH_JSON.exists():
        try:
            data = json.loads(_read_safe(HEALTH_JSON))
            r["json_bot_alive"] = data.get("bot_alive")
            r["json_pid"] = data.get("bot_pid")
            r["json_mt5"] = data.get("mt5_running")
            r["json_action"] = data.get("action")
            r["json_trades"] = data.get("trades", 0)
            r["json_timestamp"] = data.get("timestamp", "")
        except Exception:
            pass
    return r


def _compute_performance(df):
    r = {
        "total_pnl": 0.0, "win_count": 0, "loss_count": 0,
        "win_rate": 0.0, "profit_factor": 0.0, "max_drawdown": 0.0,
        "avg_win": 0.0, "avg_loss": 0.0, "best_trade": 0.0,
        "worst_trade": 0.0, "total_trades": 0,
    }
    if df.empty or "pnl" not in df.columns:
        return r
    closed = df[df["status"] != "OPEN"].copy() if "status" in df.columns else df.copy()
    if closed.empty or closed["pnl"].isna().all():
        return r
    pnl = closed["pnl"].dropna()
    r["total_trades"] = len(pnl)
    r["total_pnl"] = float(pnl.sum())
    r["win_count"] = int((pnl > 0).sum())
    r["loss_count"] = int((pnl <= 0).sum())
    r["win_rate"] = (r["win_count"] / r["total_trades"] * 100) if r["total_trades"] > 0 else 0.0
    wins = pnl[pnl > 0]
    losses = pnl[pnl <= 0]
    r["avg_win"] = float(wins.mean()) if len(wins) > 0 else 0.0
    r["avg_loss"] = float(losses.mean()) if len(losses) > 0 else 0.0
    r["best_trade"] = float(pnl.max())
    r["worst_trade"] = float(pnl.min())
    total_wins = float(wins.sum()) if len(wins) > 0 else 0.0
    total_losses = abs(float(losses.sum())) if len(losses) > 0 else 0.0
    r["profit_factor"] = (total_wins / total_losses) if total_losses > 0 else (999.0 if total_wins > 0 else 0.0)
    equity = pnl.cumsum()
    peak = equity.cummax()
    dd = peak - equity
    r["max_drawdown"] = float(dd.max())
    return r


def _strategy_performance(df):
    if df.empty or "strategies" not in df.columns:
        return pd.DataFrame()
    closed = df[df["status"] != "OPEN"].copy() if "status" in df.columns else df.copy()
    if closed.empty:
        return pd.DataFrame()
    strat_map = {}
    for _, row in closed.iterrows():
        names_str = str(row.get("strategies", ""))
        pnl_val = row.get("pnl", 0)
        if pd.isna(pnl_val):
            pnl_val = 0
        for name in names_str.split(","):
            name = name.strip()
            if not name:
                continue
            if name not in strat_map:
                strat_map[name] = {"trades": 0, "wins": 0, "pnl": 0.0}
            strat_map[name]["trades"] += 1
            strat_map[name]["pnl"] += float(pnl_val)
            if float(pnl_val) > 0:
                strat_map[name]["wins"] += 1
    rows = []
    for name, stats in sorted(strat_map.items(), key=lambda x: x[1]["pnl"], reverse=True):
        wr = (stats["wins"] / stats["trades"] * 100) if stats["trades"] > 0 else 0.0
        tier = "A"
        if stats["trades"] >= 10 and wr >= 60:
            tier = "S"
        elif stats["trades"] >= 5 and wr >= 50:
            tier = "A"
        elif stats["trades"] >= 3 and wr >= 45:
            tier = "B"
        elif stats["trades"] > 0:
            tier = "C"
        rows.append({
            "Strategy": name, "Trades": stats["trades"], "Wins": stats["wins"],
            "Win%": round(wr, 1), "P&L": round(stats["pnl"], 2), "Tier": tier,
        })
    return pd.DataFrame(rows)


# ---- RefRESH ----
if "last_refresh" not in st.session_state:
    st.session_state.last_refresh = 0

now_ts = time.time()
auto_refresh = st.sidebar.checkbox("Auto-refresh (30s)", value=True)
if auto_refresh and (now_ts - st.session_state.last_refresh) > 30:
    st.session_state.last_refresh = now_ts
    st.rerun()

if st.sidebar.button("Refresh Now"):
    st.session_state.last_refresh = now_ts
    st.rerun()

st.sidebar.caption(f"Last refresh: {datetime.now().strftime('%H:%M:%S')}")


# ---- LOAD DATA ----
bot = _parse_bot_status()
health = _parse_health()
trades_df, csv_path = _load_trades()
perf = _compute_performance(trades_df)
strat_df = _strategy_performance(trades_df)


# ---- HEADER ----
st.title("XAUUSD Gold Bot Dashboard")
st.caption(f"Symbol: {bot['symbol']} | Capital: ${bot['capital']:,.2f} | Risk: {bot['risk_pct']}% | Max DD: {bot['max_dd']}%")
st.divider()


# ---- 1. BOT STATUS ----
st.header("Bot Status")
c1, c2, c3, c4, c5 = st.columns(5)
with c1:
    status_cls = "status-alive" if bot["alive"] else "status-dead"
    status_txt = f"ALIVE (PID {bot['pid']})" if bot["alive"] and bot["pid"] else ("ALIVE" if bot["alive"] else "DEAD")
    st.markdown(f'<div class="{status_cls}">{status_txt}</div>', unsafe_allow_html=True)
with c2:
    mt5_cls = "status-alive" if bot["mt5_connected"] else "status-dead"
    st.markdown(f'MT5: <span class="{mt5_cls}">{"CONNECTED" if bot["mt5_connected"] else "DISCONNECTED"}</span>', unsafe_allow_html=True)
with c3:
    st.metric("Uptime", bot["uptime_str"])
with c4:
    st.metric("Cycles", f"{bot['cycle_count']:,}")
with c5:
    st.metric("Strategies", bot["strategies_loaded"])
st.divider()


# ---- 2. OPEN TRADES ----
st.header("Open Trades")
if not trades_df.empty and "status" in trades_df.columns:
    open_df = trades_df[trades_df["status"] == "OPEN"].copy()
else:
    open_df = pd.DataFrame()

# Also show open count from heartbeat
st.caption(f"Open positions (heartbeat): {bot['open_count']}")

if not open_df.empty:
    show_cols = [c for c in ["timestamp", "direction", "entry", "sl", "tp", "quantity", "score", "strategies"] if c in open_df.columns]
    st.dataframe(open_df[show_cols], use_container_width=True, hide_index=True)
else:
    st.info("No open trades in CSV. Check heartbeat count above.")
st.divider()


# ---- 3. CLOSED TRADES ----
st.header("Closed Trades")
if not trades_df.empty and "status" in trades_df.columns:
    closed_df = trades_df[trades_df["status"] != "OPEN"].copy()
else:
    closed_df = pd.DataFrame()

if not closed_df.empty and "pnl" in closed_df.columns:
    closed_df = closed_df.sort_values("timestamp", ascending=False) if "timestamp" in closed_df.columns else closed_df
    show_cols = [c for c in ["timestamp", "direction", "entry", "exit", "sl", "tp", "quantity", "pnl", "strategies", "status"] if c in closed_df.columns]
    st.dataframe(closed_df[show_cols], use_container_width=True, hide_index=True)
else:
    st.info("No closed trades yet.")
st.divider()


# ---- 4. PERFORMANCE ----
st.header("Performance")
pc1, pc2, pc3, pc4 = st.columns(4)
with pc1:
    pnl_color = "normal" if perf["total_pnl"] >= 0 else "inverse"
    st.metric("Total P&L", f"${perf['total_pnl']:+,.2f}")
with pc2:
    st.metric("Win Rate", f"{perf['win_rate']:.1f}%")
with pc3:
    st.metric("Profit Factor", f"{perf['profit_factor']:.2f}")
with pc4:
    st.metric("Max Drawdown", f"${perf['max_drawdown']:,.2f}")

pc5, pc6, pc7, pc8 = st.columns(4)
with pc5:
    st.metric("Total Trades", perf["total_trades"])
with pc6:
    st.metric("Wins / Losses", f"{perf['win_count']} / {perf['loss_count']}")
with pc7:
    st.metric("Avg Win", f"${perf['avg_win']:+,.2f}")
with pc8:
    st.metric("Avg Loss", f"${perf['avg_loss']:+,.2f}")

# Equity curve
if not trades_df.empty and "pnl" in trades_df.columns:
    closed_all = trades_df[trades_df["status"] != "OPEN"].copy() if "status" in trades_df.columns else trades_df.copy()
    if not closed_all.empty and "pnl" in closed_all.columns and closed_all["pnl"].notna().any():
        closed_sorted = closed_all.sort_values("timestamp") if "timestamp" in closed_all.columns else closed_all
        equity_curve = closed_sorted["pnl"].cumsum().fillna(0)
        fig_eq = go.Figure()
        fig_eq.add_trace(go.Scatter(
            y=equity_curve.values, mode="lines+markers",
            line=dict(color="#00d26a", width=2),
            marker=dict(size=4), name="Cumulative P&L",
        ))
        fig_eq.update_layout(
            title="Equity Curve", template="plotly_dark",
            height=300, margin=dict(l=0, r=0, t=40, b=0),
            xaxis_title="Trade #", yaxis_title="Cumulative P&L ($)",
        )
        st.plotly_chart(fig_eq, use_container_width=True)
st.divider()


# ---- 5. STRATEGY PERFORMANCE ----
st.header("Strategy Performance")
if not strat_df.empty:
    st.dataframe(strat_df, use_container_width=True, hide_index=True)
    fig_strat = px.bar(
        strat_df, x="Strategy", y="P&L", color="Tier",
        color_discrete_map={"S": "#ffd700", "A": "#00d26a", "B": "#ffa502", "C": "#ff6348"},
        title="P&L by Strategy",
    )
    fig_strat.update_layout(template="plotly_dark", height=350, margin=dict(l=0, r=0, t=40, b=0))
    st.plotly_chart(fig_strat, use_container_width=True)
else:
    st.info("No strategy data available yet.")
st.divider()


# ---- 6. TRADE LOG ----
st.header("Trade Log (CSV)")
if csv_path is not None:
    st.caption(f"File: {csv_path.name}")
    if not trades_df.empty:
        st.dataframe(trades_df, use_container_width=True, hide_index=True, height=400)
    else:
        st.info("CSV exists but contains no data.")
else:
    st.warning("No trade CSV files found.")
st.divider()


# ---- 7. HEALTH CHECK ----
st.header("Health Check")
hc1, hc2, hc3, hc4 = st.columns(4)
with hc1:
    h_status = health.get("bot_status", "UNKNOWN")
    h_cls = "status-alive" if "ALIVE" in h_status else "status-dead"
    st.markdown(f'Bot: <span class="{h_cls}">{h_status}</span>', unsafe_allow_html=True)
with hc2:
    mt5_h = health.get("mt5_status", "UNKNOWN")
    st.metric("MT5", mt5_h)
with hc3:
    st.metric("Log Growing", health.get("log_growing", "N/A"))
with hc4:
    st.metric("Action", health.get("action", "N/A"))

st.caption(f"Last check: {health.get('timestamp', 'N/A')}")
if health.get("errors"):
    st.warning("Health check errors:")
    for err in health["errors"]:
        st.code(err, language=None)

# JSON health report
if "json_bot_alive" in health:
    with st.expander("JSON Health Report"):
        st.json({
            "bot_alive": health.get("json_bot_alive"),
            "bot_pid": health.get("json_pid"),
            "mt5_running": health.get("json_mt5"),
            "action": health.get("json_action"),
            "trades": health.get("json_trades"),
            "timestamp": health.get("json_timestamp"),
        })

# ---- FOOTER ----
st.divider()
st.caption("Gold Bot Dashboard | Auto-refresh: 30s | Data from logs/")