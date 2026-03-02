"""
stocks.py — Fetches NVIDIA (NVDA) stock price history via yfinance.
"""

import yfinance as yf
import pandas as pd
from datetime import date, timedelta
import logging

logger = logging.getLogger(__name__)


def fetch_nvda(start_date: str = "2023-01-01", end_date: str | None = None) -> pd.DataFrame:
    """
    Download NVDA historical daily OHLCV data from Yahoo Finance.

    Args:
        start_date: ISO date string e.g. '2023-01-01'
        end_date: ISO date string; defaults to today

    Returns:
        DataFrame with DatetimeIndex and columns: Open, High, Low, Close, Volume
    """
    if end_date is None:
        end_date = date.today().isoformat()

    try:
        ticker = yf.Ticker("NVDA")
        df = ticker.history(start=start_date, end=end_date, auto_adjust=True)
        if df.empty:
            logger.warning("yfinance returned empty DataFrame for NVDA")
            return pd.DataFrame()

        df.index = df.index.tz_localize(None)  # Remove timezone for clean SQLite storage
        logger.info(f"Fetched {len(df)} NVDA trading days ({start_date} → {end_date})")
        return df[["Open", "High", "Low", "Close", "Volume"]]

    except Exception as e:
        logger.error(f"Failed to fetch NVDA data: {e}")
        return pd.DataFrame()


def fetch_nvda_incremental(last_stored_date: str | None) -> pd.DataFrame:
    """
    Only fetch NVDA data newer than what we already have stored.
    Adds a 5-day buffer to catch any delayed data.
    """
    if last_stored_date:
        # Go back 5 days from the last stored date to catch corrections
        from datetime import datetime
        start = (datetime.fromisoformat(last_stored_date) - timedelta(days=5)).date().isoformat()
    else:
        start = "2023-01-01"  # Default historical start

    return fetch_nvda(start_date=start)
