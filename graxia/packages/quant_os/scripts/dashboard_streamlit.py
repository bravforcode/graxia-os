"""Real-time Quant OS Dashboard — Streamlit app.

Run: cd graxia/packages && streamlit run quant_os/scripts/dashboard_streamlit.py
"""

import json
from pathlib import Path

# ponytail: Streamlit is already installed in the project
import streamlit as st

st.set_page_config(page_title="Quant OS Dashboard", layout="wide")

st.title("Quant OS — Real-Time Dashboard")

# Load data from files
METRICS_PATH = Path("quant_os/logs/pipeline_metrics.jsonl")
NEWS_PATH = Path("quant_os/logs/news_digest.jsonl")

col1, col2, col3, col4 = st.columns(4)

# Pipeline status
with col1:
    st.subheader("Pipeline Status")
    # Read latest from news_pipeline.log
    log_path = Path("quant_os/logs/news_pipeline.log")
    if log_path.exists():
        lines = log_path.read_text(encoding="utf-8").strip().split("\n")
        last_line = lines[-1] if lines else "No data"
        st.code(last_line, language=None)
    else:
        st.warning("No pipeline log found")

# Current regime
with col2:
    st.subheader("Current Regime")
    try:
        from quant_os.core.canonical.macro_regime import get_macro_regime

        regime = get_macro_regime()
        st.metric("Regime", regime.regime_label)
        st.metric("Position Mult", f"{regime.position_multiplier:.2f}")
        st.metric("Confidence", f"{regime.confidence:.2%}")
    except Exception:
        st.info("No regime data yet")

# Risk budget
with col3:
    st.subheader("Risk Budget")
    try:
        from quant_os.core.risk_budget import RiskBudget

        budget = RiskBudget()
        st.metric("Daily PnL", f"{budget.current_daily_pnl:.2f}%")
        st.metric("Weekly PnL", f"{budget.current_weekly_pnl:.2f}%")
        st.metric("Open Positions", budget.open_positions)
    except Exception:
        st.info("No risk data yet")

# Model performance
with col4:
    st.subheader("Model Performance")
    try:
        from quant_os.core.ml.performance_tracker import get_recent_performance

        perfs = get_recent_performance(7)
        if perfs:
            latest = perfs[-1]
            st.metric("Accuracy", f"{latest.accuracy:.2%}")
            st.metric("OOS Accuracy", f"{latest.oos_accuracy:.2%}")
            st.metric("Version", latest.model_version)
        else:
            st.info("No performance data")
    except Exception:
        st.info("No model data yet")

# News feed
st.subheader("Recent News")
try:
    # Show last 10 headlines from log
    news_log = Path("quant_os/logs/news_analyzed.jsonl")
    if news_log.exists():
        lines = news_log.read_text(encoding="utf-8").strip().split("\n")[-10:]
        for line in reversed(lines):
            try:
                item = json.loads(line)
                impact = item.get("impact", "MEDIUM")
                color = {"CRISIS": "red", "HIGH": "orange", "MEDIUM": "blue"}.get(impact, "gray")
                st.markdown(f"**: {color}[{impact}]** {item.get('title', 'Unknown')}")
            except json.JSONDecodeError:
                continue
    else:
        st.info("No news data yet")
except Exception:
    st.info("News feed unavailable")

# Refresh
if st.button("Refresh"):
    st.rerun()
