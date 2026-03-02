"""
database.py — SQLite persistence layer for H100 prices and NVDA stock data.

Data is stored locally in `data/tracker.db` and persists across app restarts.
On cloud deployments, mount a volume at `data/` to preserve the database.
"""

import sqlite3
import pandas as pd
from pathlib import Path
from datetime import date, datetime
import logging

logger = logging.getLogger(__name__)

DB_PATH = Path("data/tracker.db")


def get_connection() -> sqlite3.Connection:
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    return sqlite3.connect(DB_PATH)


def initialize_db():
    """Create tables if they don't exist."""
    with get_connection() as conn:
        conn.executescript("""
            CREATE TABLE IF NOT EXISTS gpu_prices (
                id          INTEGER PRIMARY KEY AUTOINCREMENT,
                date        TEXT NOT NULL,
                provider    TEXT NOT NULL,
                category    TEXT NOT NULL,          -- 'Hyperscaler' | 'Neo-Cloud' | 'Other'
                gpu_count   INTEGER DEFAULT 8,
                price_per_hour      REAL NOT NULL,
                price_per_gpu_hour  REAL NOT NULL,
                created_at  TEXT DEFAULT (datetime('now')),
                UNIQUE(date, provider, gpu_count)   -- prevent duplicate entries
            );

            CREATE TABLE IF NOT EXISTS nvda_prices (
                id          INTEGER PRIMARY KEY AUTOINCREMENT,
                date        TEXT NOT NULL UNIQUE,
                open        REAL,
                high        REAL,
                low         REAL,
                close       REAL NOT NULL,
                volume      INTEGER,
                created_at  TEXT DEFAULT (datetime('now'))
            );

            CREATE TABLE IF NOT EXISTS scrape_log (
                id          INTEGER PRIMARY KEY AUTOINCREMENT,
                scraped_at  TEXT DEFAULT (datetime('now')),
                records     INTEGER,
                success     INTEGER,
                message     TEXT
            );
        """)
    logger.info("Database initialized.")


def save_gpu_prices(df: pd.DataFrame) -> int:
    """Insert new GPU price records; skip duplicates. Returns rows inserted."""
    if df.empty:
        return 0

    required = {"date", "provider", "category", "gpu_count", "price_per_hour", "price_per_gpu_hour"}
    if not required.issubset(df.columns):
        logger.error(f"Missing columns: {required - set(df.columns)}")
        return 0

    inserted = 0
    with get_connection() as conn:
        for _, row in df.iterrows():
            try:
                conn.execute("""
                    INSERT OR IGNORE INTO gpu_prices
                        (date, provider, category, gpu_count, price_per_hour, price_per_gpu_hour)
                    VALUES (?, ?, ?, ?, ?, ?)
                """, (
                    row["date"], row["provider"], row["category"],
                    int(row["gpu_count"]), float(row["price_per_hour"]),
                    float(row["price_per_gpu_hour"])
                ))
                if conn.execute("SELECT changes()").fetchone()[0]:
                    inserted += 1
            except Exception as e:
                logger.warning(f"Failed to insert row {row.to_dict()}: {e}")

    log_scrape(inserted, True, f"Inserted {inserted} new GPU price records")
    return inserted


def save_nvda_prices(df: pd.DataFrame) -> int:
    """Upsert NVDA stock prices. Returns rows inserted."""
    if df.empty:
        return 0

    inserted = 0
    with get_connection() as conn:
        for dt, row in df.iterrows():
            date_str = dt.date().isoformat() if hasattr(dt, "date") else str(dt)[:10]
            try:
                conn.execute("""
                    INSERT OR REPLACE INTO nvda_prices (date, open, high, low, close, volume)
                    VALUES (?, ?, ?, ?, ?, ?)
                """, (
                    date_str,
                    float(row.get("Open", 0)),
                    float(row.get("High", 0)),
                    float(row.get("Low", 0)),
                    float(row.get("Close", 0)),
                    int(row.get("Volume", 0)),
                ))
                inserted += 1
            except Exception as e:
                logger.warning(f"Failed to insert NVDA row {date_str}: {e}")

    return inserted


def load_gpu_prices(
    start_date: str | None = None,
    end_date: str | None = None,
    categories: list[str] | None = None,
) -> pd.DataFrame:
    """Load GPU price history with optional filters."""
    query = "SELECT * FROM gpu_prices WHERE 1=1"
    params = []

    if start_date:
        query += " AND date >= ?"
        params.append(start_date)
    if end_date:
        query += " AND date <= ?"
        params.append(end_date)
    if categories:
        placeholders = ",".join("?" * len(categories))
        query += f" AND category IN ({placeholders})"
        params.extend(categories)

    query += " ORDER BY date ASC, provider ASC"

    with get_connection() as conn:
        df = pd.read_sql_query(query, conn, params=params)

    if not df.empty:
        df["date"] = pd.to_datetime(df["date"])
    return df


def load_nvda_prices(start_date: str | None = None) -> pd.DataFrame:
    """Load NVDA stock price history."""
    query = "SELECT * FROM nvda_prices"
    params = []
    if start_date:
        query += " WHERE date >= ?"
        params.append(start_date)
    query += " ORDER BY date ASC"

    with get_connection() as conn:
        df = pd.read_sql_query(query, conn, params=params if params else None)

    if not df.empty:
        df["date"] = pd.to_datetime(df["date"])
        df.set_index("date", inplace=True)
    return df


def get_last_scrape_date() -> str | None:
    """Return the most recent date for which GPU prices exist."""
    with get_connection() as conn:
        result = conn.execute("SELECT MAX(date) FROM gpu_prices").fetchone()
    return result[0] if result and result[0] else None


def log_scrape(records: int, success: bool, message: str = ""):
    with get_connection() as conn:
        conn.execute(
            "INSERT INTO scrape_log (records, success, message) VALUES (?, ?, ?)",
            (records, int(success), message)
        )


def get_providers() -> list[str]:
    """Return all unique provider names in the database."""
    with get_connection() as conn:
        rows = conn.execute("SELECT DISTINCT provider FROM gpu_prices ORDER BY provider").fetchall()
    return [r[0] for r in rows]


def get_stats() -> dict:
    """Return summary statistics for the sidebar."""
    with get_connection() as conn:
        gpu_count = conn.execute("SELECT COUNT(*) FROM gpu_prices").fetchone()[0]
        date_range = conn.execute("SELECT MIN(date), MAX(date) FROM gpu_prices").fetchone()
        last_scrape = conn.execute(
            "SELECT scraped_at FROM scrape_log ORDER BY scraped_at DESC LIMIT 1"
        ).fetchone()

    return {
        "total_records": gpu_count,
        "earliest_date": date_range[0],
        "latest_date": date_range[1],
        "last_scrape": last_scrape[0] if last_scrape else "Never",
    }
