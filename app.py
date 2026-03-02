"""
app.py — H100 GPU Rental Price Tracker vs NVDA Stock
Streamlit dashboard with daily auto-refresh and persistent SQLite history.

Run: streamlit run app.py
"""

import streamlit as st
import pandas as pd
import plotly.graph_objects as go
from plotly.subplots import make_subplots
from datetime import date, datetime, timedelta
import time
import logging

from database import (
    initialize_db, save_gpu_prices, save_nvda_prices,
    load_gpu_prices, load_nvda_prices, get_last_scrape_date,
    get_providers, get_stats,
)
from scraper import get_latest_prices
from stocks import fetch_nvda_incremental

logging.basicConfig(level=logging.INFO)

# ── Page config ────────────────────────────────────────────────────────────────
st.set_page_config(
    page_title="H100 GPU Prices vs NVDA",
    page_icon="🖥️",
    layout="wide",
    initial_sidebar_state="expanded",
)

# ── Inject custom CSS ──────────────────────────────────────────────────────────
st.markdown("""
<style>
    @import url('https://fonts.googleapis.com/css2?family=IBM+Plex+Mono:wght@400;600&family=IBM+Plex+Sans:wght@300;400;600&display=swap');

    html, body, [class*="css"] {
        font-family: 'IBM Plex Sans', sans-serif;
    }
    .stApp { background: #0a0e1a; color: #e0e6f0; }
    .metric-card {
        background: #111827;
        border: 1px solid #1f2d45;
        border-radius: 8px;
        padding: 16px 20px;
        margin-bottom: 12px;
    }
    .metric-value {
        font-family: 'IBM Plex Mono', monospace;
        font-size: 1.6rem;
        font-weight: 600;
        color: #60a5fa;
    }
    .metric-label { font-size: 0.75rem; color: #6b7f9e; text-transform: uppercase; letter-spacing: 0.08em; }
    .status-ok { color: #34d399; }
    .status-warn { color: #fbbf24; }
    h1 { font-family: 'IBM Plex Mono', monospace !important; letter-spacing: -0.03em; }
    .stSelectbox label, .stMultiSelect label, .stSlider label { color: #8da3c0 !important; }
    div[data-testid="stSidebarContent"] { background: #090d18; border-right: 1px solid #1a2540; }
</style>
""", unsafe_allow_html=True)


# ── Initialize DB ──────────────────────────────────────────────────────────────
@st.cache_resource
def init():
    initialize_db()

init()


# ── Auto-refresh logic ─────────────────────────────────────────────────────────
def should_refresh() -> bool:
    """Return True if we haven't scraped today yet."""
    last = get_last_scrape_date()
    if last is None:
        return True
    return last < date.today().isoformat()


def run_daily_update(force: bool = False):
    """Scrape GPU prices + update NVDA stock data."""
    if not force and not should_refresh():
        return False

    with st.spinner("🔄 Fetching latest H100 prices from silicon.fail…"):
        gpu_df = get_latest_prices()
        if not gpu_df.empty:
            n = save_gpu_prices(gpu_df)
            st.toast(f"✅ Saved {n} new GPU price records", icon="🖥️")
        else:
            st.toast("⚠️ No GPU price data returned — site may have changed", icon="⚠️")

    with st.spinner("📈 Updating NVDA stock data…"):
        last_nvda = None  # Could query DB for last NVDA date
        nvda_df = fetch_nvda_incremental(last_nvda)
        if not nvda_df.empty:
            n = save_nvda_prices(nvda_df)
            st.toast(f"✅ Updated {n} NVDA trading days", icon="📈")

    return True


# ── Sidebar ────────────────────────────────────────────────────────────────────
with st.sidebar:
    st.markdown("## ⚙️ Controls")

    if st.button("🔄 Refresh Now", use_container_width=True):
        run_daily_update(force=True)
        st.rerun()

    st.divider()

    # Date range
    st.markdown("**Date Range**")
    col1, col2 = st.columns(2)
    default_start = date.today() - timedelta(days=180)
    start_date = col1.date_input("From", value=default_start, key="start")
    end_date = col2.date_input("To", value=date.today(), key="end")

    # Category filter
    st.markdown("**Provider Category**")
    show_hyperscalers = st.checkbox("Hyperscalers", value=True)
    show_neo = st.checkbox("Neo-Clouds", value=True)
    show_other = st.checkbox("Other", value=False)

    categories = []
    if show_hyperscalers: categories.append("Hyperscaler")
    if show_neo: categories.append("Neo-Cloud")
    if show_other: categories.append("Other")

    # Provider filter
    all_providers = get_providers()
    if all_providers:
        st.markdown("**Filter Providers**")
        selected_providers = st.multiselect(
            "Providers (blank = all)",
            options=all_providers,
            default=[],
            placeholder="All providers"
        )
    else:
        selected_providers = []

    # Chart options
    st.divider()
    st.markdown("**Chart Options**")
    price_metric = st.radio(
        "GPU Price Metric",
        ["Price per GPU/hr", "Total Price/hr"],
        index=0,
    )
    show_nvda = st.checkbox("Show NVDA Stock", value=True)
    show_avg = st.checkbox("Show Category Averages", value=True)
    show_individual = st.checkbox("Show Individual Providers", value=False)

    # Stats
    st.divider()
    stats = get_stats()
    st.markdown("**Database Stats**")
    st.caption(f"📦 {stats['total_records']:,} total records")
    st.caption(f"📅 {stats['earliest_date']} → {stats['latest_date']}")
    st.caption(f"🕐 Last scrape: {stats['last_scrape'][:16] if stats['last_scrape'] else 'Never'}")

    # Auto-refresh
    st.divider()
    auto_refresh = st.checkbox("Auto-refresh (daily)", value=True)
    if auto_refresh:
        st.caption("App will refresh data once per day on load.")


# ── Auto-refresh on load ───────────────────────────────────────────────────────
if auto_refresh:
    run_daily_update(force=False)


# ── Load data ──────────────────────────────────────────────────────────────────
gpu_data = load_gpu_prices(
    start_date=start_date.isoformat(),
    end_date=end_date.isoformat(),
    categories=categories if categories else None,
)

if selected_providers:
    gpu_data = gpu_data[gpu_data["provider"].isin(selected_providers)]

nvda_data = load_nvda_prices(start_date=start_date.isoformat()) if show_nvda else pd.DataFrame()
# Normalize column names (SQLite stores lowercase, yfinance uses Title case)
if not nvda_data.empty:
    nvda_data.columns = [c.title() for c in nvda_data.columns]


price_col = "price_per_gpu_hour" if price_metric == "Price per GPU/hr" else "price_per_hour"
price_label = "$/GPU/hr" if price_metric == "Price per GPU/hr" else "$/hr (total)"


# ── Header ─────────────────────────────────────────────────────────────────────
st.markdown("# 🖥️ H100 GPU Rental vs NVDA")
st.caption(
    f"Data sourced from [silicon.fail](https://silicon.fail) · "
    f"NVDA prices via Yahoo Finance · "
    f"Updated {stats['latest_date'] or 'never'}"
)

if gpu_data.empty:
    st.warning(
        "No data in database yet. Click **Refresh Now** in the sidebar to scrape today's prices. "
        "If the scraper returns no results, the site structure at silicon.fail may have changed — "
        "see `scraper.py` to update the selectors.",
        icon="⚠️"
    )


# ── KPI metrics row ────────────────────────────────────────────────────────────
if not gpu_data.empty:
    latest_date = gpu_data["date"].max()
    latest = gpu_data[gpu_data["date"] == latest_date]

    hyper_avg = latest[latest["category"] == "Hyperscaler"][price_col].mean()
    neo_avg = latest[latest["category"] == "Neo-Cloud"][price_col].mean()
    cheapest = latest.loc[latest[price_col].idxmin()] if not latest.empty else None

    cols = st.columns(4)
    with cols[0]:
        st.markdown(f"""
        <div class="metric-card">
            <div class="metric-label">Hyperscaler Avg ({price_label})</div>
            <div class="metric-value">${hyper_avg:.2f}</div>
        </div>
        """, unsafe_allow_html=True)
    with cols[1]:
        st.markdown(f"""
        <div class="metric-card">
            <div class="metric-label">Neo-Cloud Avg ({price_label})</div>
            <div class="metric-value">${neo_avg:.2f}</div>
        </div>
        """, unsafe_allow_html=True)
    with cols[2]:
        st.markdown(f"""
        <div class="metric-card">
            <div class="metric-label">Cheapest Provider</div>
            <div class="metric-value">{cheapest['provider'] if cheapest is not None else '—'}</div>
            <div class="metric-label">${cheapest[price_col]:.2f} {price_label}</div>
        </div>
        """, unsafe_allow_html=True)
    with cols[3]:
        nvda_close = nvda_data["Close"].iloc[-1] if not nvda_data.empty else None
        st.markdown(f"""
        <div class="metric-card">
            <div class="metric-label">NVDA Stock (latest)</div>
            <div class="metric-value">${nvda_close:.2f}</div>
        </div>
        """, unsafe_allow_html=True)

    st.divider()


# ── Main chart ─────────────────────────────────────────────────────────────────
def build_chart(gpu_data, nvda_data, price_col, price_label, show_avg, show_individual, show_nvda):
    specs = [[{"secondary_y": True}]]
    fig = make_subplots(rows=1, cols=1, specs=specs)

    COLOR_MAP = {
        "Hyperscaler": "#60a5fa",   # Blue
        "Neo-Cloud": "#34d399",     # Green
        "Other": "#a78bfa",         # Purple
    }

    NVDA_COLOR = "#f59e0b"          # Amber

    if not gpu_data.empty:
        # Individual provider traces
        if show_individual:
            for provider in gpu_data["provider"].unique():
                p_df = gpu_data[gpu_data["provider"] == provider].copy()
                cat = p_df["category"].iloc[0]
                daily = p_df.groupby("date")[price_col].mean().reset_index()
                fig.add_trace(
                    go.Scatter(
                        x=daily["date"], y=daily[price_col],
                        mode="lines",
                        name=provider,
                        line=dict(color=COLOR_MAP.get(cat, "#888"), width=1, dash="dot"),
                        opacity=0.55,
                        legendgroup=cat,
                        hovertemplate=f"<b>{provider}</b><br>%{{x|%b %d, %Y}}<br>${{y:.2f}} {price_label}<extra></extra>",
                    ),
                    secondary_y=False,
                )

        # Category average traces
        if show_avg:
            for category, color in COLOR_MAP.items():
                cat_df = gpu_data[gpu_data["category"] == category]
                if cat_df.empty:
                    continue
                daily_avg = cat_df.groupby("date")[price_col].mean().reset_index()
                fig.add_trace(
                    go.Scatter(
                        x=daily_avg["date"], y=daily_avg[price_col],
                        mode="lines+markers",
                        name=f"{category} Avg",
                        line=dict(color=color, width=2.5),
                        marker=dict(size=5),
                        legendgroup=category,
                        hovertemplate=f"<b>{category} Avg</b><br>%{{x|%b %d, %Y}}<br>${{y:.2f}} {price_label}<extra></extra>",
                    ),
                    secondary_y=False,
                )

    # NVDA stock trace
    if show_nvda and not nvda_data.empty:
        fig.add_trace(
            go.Scatter(
                x=nvda_data.index, y=nvda_data["Close"],
                mode="lines",
                name="NVDA Close",
                line=dict(color=NVDA_COLOR, width=2),
                hovertemplate="<b>NVDA</b><br>%{x|%b %d, %Y}<br>$%{y:.2f}<extra></extra>",
            ),
            secondary_y=True,
        )

        # Fill under NVDA
        fig.add_trace(
            go.Scatter(
                x=nvda_data.index, y=nvda_data["Close"],
                fill="tozeroy",
                fillcolor="rgba(245,158,11,0.06)",
                line=dict(width=0),
                showlegend=False,
                hoverinfo="skip",
            ),
            secondary_y=True,
        )

    fig.update_layout(
        height=560,
        plot_bgcolor="#0d1424",
        paper_bgcolor="#0a0e1a",
        font=dict(family="IBM Plex Mono, monospace", color="#8da3c0"),
        legend=dict(
            bgcolor="#111827", bordercolor="#1f2d45", borderwidth=1,
            font=dict(size=11)
        ),
        hovermode="x unified",
        xaxis=dict(
            gridcolor="#1a2540", zeroline=False,
            tickformat="%b '%y",
        ),
        yaxis=dict(
            title=price_label,
            gridcolor="#1a2540", zeroline=False,
            tickprefix="$",
        ),
        yaxis2=dict(
            title="NVDA Stock Price (USD)",
            tickprefix="$",
            gridcolor="rgba(0,0,0,0)",
        ),
        margin=dict(l=60, r=60, t=30, b=40),
    )

    return fig


if not gpu_data.empty or not nvda_data.empty:
    fig = build_chart(gpu_data, nvda_data, price_col, price_label, show_avg, show_individual, show_nvda)
    st.plotly_chart(fig, use_container_width=True)
else:
    st.info("Refresh data to populate the chart.", icon="📊")


# ── Latest pricing table ───────────────────────────────────────────────────────
if not gpu_data.empty:
    st.markdown("### 📋 Latest Pricing Snapshot")

    latest_date = gpu_data["date"].max()
    snapshot = (
        gpu_data[gpu_data["date"] == latest_date]
        [["provider", "category", "gpu_count", "price_per_hour", "price_per_gpu_hour"]]
        .sort_values(["category", "price_per_gpu_hour"])
        .reset_index(drop=True)
    )

    snapshot.columns = ["Provider", "Category", "GPUs", "Total $/hr", "$/GPU/hr"]
    snapshot["Total $/hr"] = snapshot["Total $/hr"].map("${:.2f}".format)
    snapshot["$/GPU/hr"] = snapshot["$/GPU/hr"].map("${:.4f}".format)

    st.dataframe(
        snapshot,
        use_container_width=True,
        height=300,
        column_config={
            "Category": st.column_config.TextColumn(width="small"),
            "GPUs": st.column_config.NumberColumn(width="small"),
        }
    )


# ── Trend comparison ───────────────────────────────────────────────────────────
if not gpu_data.empty and len(gpu_data["date"].unique()) > 1:
    st.markdown("### 📉 Price Trend (30-day change)")
    recent = gpu_data[gpu_data["date"] >= (gpu_data["date"].max() - pd.Timedelta(days=30))]
    earliest_recent = recent["date"].min()
    latest_recent = recent["date"].max()

    cols = st.columns(2)
    for col_ui, category in zip(cols, ["Hyperscaler", "Neo-Cloud"]):
        cat_data = recent[recent["category"] == category]
        if cat_data.empty:
            continue
        early_avg = cat_data[cat_data["date"] == earliest_recent][price_col].mean()
        late_avg = cat_data[cat_data["date"] == latest_recent][price_col].mean()
        delta_pct = ((late_avg - early_avg) / early_avg * 100) if early_avg else 0
        arrow = "▲" if delta_pct > 0 else "▼"
        color = "#f87171" if delta_pct > 0 else "#34d399"
        col_ui.metric(
            f"{category} 30-day",
            f"${late_avg:.2f}/GPU/hr",
            f"{arrow} {abs(delta_pct):.1f}%"
        )


# ── Footer ─────────────────────────────────────────────────────────────────────
st.divider()
st.caption(
    "Data: [silicon.fail](https://silicon.fail) • Stock: Yahoo Finance via yfinance • "
    "Built with Streamlit + Plotly • [View on GitHub](https://github.com)"
)
