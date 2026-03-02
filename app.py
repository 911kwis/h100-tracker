"""
app.py — H100 GPU Rental Price Tracker vs NVDA Stock
Reads from data/gpu_prices.csv and data/nvda_prices.csv
which are updated daily by GitHub Actions.
"""

import streamlit as st
import pandas as pd
import plotly.graph_objects as go
from plotly.subplots import make_subplots
from datetime import date, timedelta
from pathlib import Path

st.set_page_config(page_title="H100 GPU Prices vs NVDA", page_icon="🖥️", layout="wide")

st.markdown("""
<style>
    @import url('https://fonts.googleapis.com/css2?family=IBM+Plex+Mono:wght@400;600&family=IBM+Plex+Sans:wght@300;400;600&display=swap');
    html, body, [class*="css"] { font-family: 'IBM Plex Sans', sans-serif; }
    .stApp { background: #0a0e1a; color: #e0e6f0; }
    .metric-card { background: #111827; border: 1px solid #1f2d45; border-radius: 8px; padding: 16px 20px; margin-bottom: 12px; }
    .metric-value { font-family: 'IBM Plex Mono', monospace; font-size: 1.6rem; font-weight: 600; color: #60a5fa; }
    .metric-label { font-size: 0.75rem; color: #6b7f9e; text-transform: uppercase; letter-spacing: 0.08em; }
    h1 { font-family: 'IBM Plex Mono', monospace !important; }
    div[data-testid="stSidebarContent"] { background: #090d18; border-right: 1px solid #1a2540; }
</style>
""", unsafe_allow_html=True)

GPU_CSV = Path("data/gpu_prices.csv")
NVDA_CSV = Path("data/nvda_prices.csv")

@st.cache_data(ttl=3600)
def load_gpu_data():
    if not GPU_CSV.exists():
        return pd.DataFrame()
    df = pd.read_csv(GPU_CSV)
    df["date"] = pd.to_datetime(df["date"])
    return df

@st.cache_data(ttl=3600)
def load_nvda_data():
    if not NVDA_CSV.exists():
        return pd.DataFrame()
    df = pd.read_csv(NVDA_CSV)
    df["date"] = pd.to_datetime(df["date"])
    return df.set_index("date")

gpu_raw = load_gpu_data()
nvda_raw = load_nvda_data()

with st.sidebar:
    st.markdown("## ⚙️ Controls")
    if st.button("🔄 Reload Data", use_container_width=True):
        st.cache_data.clear()
        st.rerun()
    st.divider()
    st.markdown("**Date Range**")
    c1, c2 = st.columns(2)
    start_date = c1.date_input("From", value=date.today() - timedelta(days=180))
    end_date = c2.date_input("To", value=date.today())
    st.markdown("**Provider Category**")
    show_hyper = st.checkbox("Hyperscalers", value=True)
    show_neo = st.checkbox("Neo-Clouds", value=True)
    categories = (["Hyperscaler"] if show_hyper else []) + (["Neo-Cloud"] if show_neo else [])
    all_providers = sorted(gpu_raw["provider"].unique().tolist()) if not gpu_raw.empty else []
    selected_providers = st.multiselect("Filter Providers (blank = all)", options=all_providers) if all_providers else []
    st.divider()
    st.markdown("**Chart Options**")
    price_metric = st.radio("GPU Price Metric", ["Price per GPU/hr", "Total Price/hr"], index=0)
    show_nvda = st.checkbox("Show NVDA Stock", value=True)
    show_avg = st.checkbox("Show Category Averages", value=True)
    show_individual = st.checkbox("Show Individual Providers", value=False)
    st.divider()
    if not gpu_raw.empty:
        st.caption(f"📦 {len(gpu_raw):,} GPU records")
        st.caption(f"📅 {gpu_raw['date'].min().date()} → {gpu_raw['date'].max().date()}")
    if not nvda_raw.empty:
        st.caption(f"📈 {len(nvda_raw):,} NVDA trading days")
    st.caption("⏰ Updated daily via GitHub Actions")

# Filter
gpu_data = gpu_raw.copy()
if not gpu_data.empty:
    gpu_data = gpu_data[(gpu_data["date"] >= pd.Timestamp(start_date)) & (gpu_data["date"] <= pd.Timestamp(end_date))]
    if categories:
        gpu_data = gpu_data[gpu_data["category"].isin(categories)]
    if selected_providers:
        gpu_data = gpu_data[gpu_data["provider"].isin(selected_providers)]

nvda_data = nvda_raw.copy()
if not nvda_data.empty:
    nvda_data = nvda_data[(nvda_data.index >= pd.Timestamp(start_date)) & (nvda_data.index <= pd.Timestamp(end_date))]

price_col = "price_per_gpu_hour" if price_metric == "Price per GPU/hr" else "price_per_hour"
price_label = "$/GPU/hr" if price_metric == "Price per GPU/hr" else "$/hr (total)"

st.markdown("# 🖥️ H100 GPU Rental vs NVDA")
latest_date = gpu_data["date"].max().date() if not gpu_data.empty else "never"
st.caption(f"Data: [silicon.fail](https://silicon.fail) · Stock: Yahoo Finance · Last updated: {latest_date} · Auto-refreshes daily via GitHub Actions")

if gpu_data.empty and nvda_data.empty:
    st.warning("No data yet. Go to your GitHub repo → **Actions** tab → **Daily H100 Price Scraper** → **Run workflow**", icon="⚠️")
elif gpu_data.empty:
    st.info("No GPU data yet — trigger the GitHub Action to add GPU prices. NVDA chart shown below.", icon="ℹ️")

# KPIs
if not gpu_data.empty:
    latest = gpu_data[gpu_data["date"] == gpu_data["date"].max()]
    hyper_avg = latest[latest["category"] == "Hyperscaler"][price_col].mean()
    neo_avg = latest[latest["category"] == "Neo-Cloud"][price_col].mean()
    cheapest = latest.loc[latest[price_col].idxmin()] if not latest.empty else None
    nvda_close = nvda_data["close"].iloc[-1] if not nvda_data.empty else 0
    cols = st.columns(4)
    with cols[0]:
        st.markdown(f'<div class="metric-card"><div class="metric-label">Hyperscaler Avg</div><div class="metric-value">${hyper_avg:.2f}</div></div>', unsafe_allow_html=True)
    with cols[1]:
        st.markdown(f'<div class="metric-card"><div class="metric-label">Neo-Cloud Avg</div><div class="metric-value">${neo_avg:.2f}</div></div>', unsafe_allow_html=True)
    with cols[2]:
        name = cheapest["provider"] if cheapest is not None else "—"
        val = f"${cheapest[price_col]:.2f}" if cheapest is not None else "—"
        st.markdown(f'<div class="metric-card"><div class="metric-label">Cheapest</div><div class="metric-value" style="font-size:1rem">{name}</div><div class="metric-label">{val} {price_label}</div></div>', unsafe_allow_html=True)
    with cols[3]:
        st.markdown(f'<div class="metric-card"><div class="metric-label">NVDA Stock</div><div class="metric-value">${nvda_close:.2f}</div></div>', unsafe_allow_html=True)
    st.divider()

# Chart
COLOR_MAP = {"Hyperscaler": "#60a5fa", "Neo-Cloud": "#34d399", "Other": "#a78bfa"}
NVDA_COLOR = "#f59e0b"

if not gpu_data.empty or not nvda_data.empty:
    fig = make_subplots(rows=1, cols=1, specs=[[{"secondary_y": True}]])

    if not gpu_data.empty:
        if show_individual:
            for provider in gpu_data["provider"].unique():
                p_df = gpu_data[gpu_data["provider"] == provider]
                cat = p_df["category"].iloc[0]
                daily = p_df.groupby("date")[price_col].mean().reset_index()
                fig.add_trace(go.Scatter(x=daily["date"], y=daily[price_col], mode="lines", name=provider,
                    line=dict(color=COLOR_MAP.get(cat, "#888"), width=1, dash="dot"), opacity=0.55,
                    hovertemplate=f"<b>{provider}</b><br>%{{x|%b %d}}<br>${{y:.2f}}<extra></extra>"), secondary_y=False)

        if show_avg:
            for category, color in COLOR_MAP.items():
                cat_df = gpu_data[gpu_data["category"] == category]
                if cat_df.empty: continue
                daily_avg = cat_df.groupby("date")[price_col].mean().reset_index()
                fig.add_trace(go.Scatter(x=daily_avg["date"], y=daily_avg[price_col], mode="lines+markers",
                    name=f"{category} Avg", line=dict(color=color, width=2.5), marker=dict(size=5),
                    hovertemplate=f"<b>{category}</b><br>%{{x|%b %d}}<br>${{y:.2f}}<extra></extra>"), secondary_y=False)

    if show_nvda and not nvda_data.empty:
        fig.add_trace(go.Scatter(x=nvda_data.index, y=nvda_data["close"], mode="lines", name="NVDA Close",
            line=dict(color=NVDA_COLOR, width=2),
            hovertemplate="<b>NVDA</b><br>%{x|%b %d}<br>$%{y:.2f}<extra></extra>"), secondary_y=True)
        fig.add_trace(go.Scatter(x=nvda_data.index, y=nvda_data["close"], fill="tozeroy",
            fillcolor="rgba(245,158,11,0.06)", line=dict(width=0), showlegend=False, hoverinfo="skip"), secondary_y=True)

    fig.update_layout(height=560, plot_bgcolor="#0d1424", paper_bgcolor="#0a0e1a",
        font=dict(family="IBM Plex Mono, monospace", color="#8da3c0"),
        legend=dict(bgcolor="#111827", bordercolor="#1f2d45", borderwidth=1),
        hovermode="x unified",
        xaxis=dict(gridcolor="#1a2540", zeroline=False, tickformat="%b '%y"),
        yaxis=dict(title=price_label, gridcolor="#1a2540", zeroline=False, tickprefix="$"),
        yaxis2=dict(title="NVDA Stock (USD)", tickprefix="$", gridcolor="rgba(0,0,0,0)"),
        margin=dict(l=60, r=60, t=30, b=40))
    st.plotly_chart(fig, use_container_width=True)

# Table
if not gpu_data.empty:
    st.markdown("### 📋 Latest Pricing Snapshot")
    latest_date = gpu_data["date"].max()
    snapshot = gpu_data[gpu_data["date"] == latest_date][["provider","category","gpu_count","price_per_hour","price_per_gpu_hour"]].sort_values(["category","price_per_gpu_hour"]).reset_index(drop=True)
    snapshot.columns = ["Provider","Category","GPUs","Total $/hr","$/GPU/hr"]
    snapshot["Total $/hr"] = snapshot["Total $/hr"].map("${:.2f}".format)
    snapshot["$/GPU/hr"] = snapshot["$/GPU/hr"].map("${:.4f}".format)
    st.dataframe(snapshot, use_container_width=True, height=300)

# 30-day trend
if not gpu_data.empty and len(gpu_data["date"].unique()) > 1:
    st.markdown("### 📉 Price Trend (30-day change)")
    recent = gpu_data[gpu_data["date"] >= (gpu_data["date"].max() - pd.Timedelta(days=30))]
    cols = st.columns(2)
    for col_ui, category in zip(cols, ["Hyperscaler", "Neo-Cloud"]):
        cat_data = recent[recent["category"] == category]
        if cat_data.empty: continue
        early_avg = cat_data[cat_data["date"] == cat_data["date"].min()][price_col].mean()
        late_avg = cat_data[cat_data["date"] == cat_data["date"].max()][price_col].mean()
        delta_pct = ((late_avg - early_avg) / early_avg * 100) if early_avg else 0
        col_ui.metric(f"{category} 30-day", f"${late_avg:.2f}/GPU/hr", f"{delta_pct:+.1f}%")

st.divider()
st.caption("Data: [silicon.fail](https://silicon.fail) · Stock: Yahoo Finance · Built with Streamlit + Plotly")
