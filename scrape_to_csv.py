"""
scrape_to_csv.py — Run by GitHub Actions daily.
Scrapes Neo-Cloud and Hyperscaler H100 index prices from silicondata.com
and appends to data/gpu_prices.csv and data/nvda_prices.csv.
"""

import pandas as pd
from pathlib import Path
from datetime import date
import re
import yfinance as yf

DATA_DIR = Path("data")
GPU_CSV = DATA_DIR / "gpu_prices.csv"
NVDA_CSV = DATA_DIR / "nvda_prices.csv"
TODAY = date.today().isoformat()
TARGET_URL = "https://www.silicondata.com/products/silicon-index"


def scrape_silicon_data() -> list[dict]:
    """Use Playwright to scrape Neo-Cloud and Hyperscaler H100 index prices."""
    from playwright.sync_api import sync_playwright

    records = []
    price_re = re.compile(r"(\d+\.\d+)")

    print(f"Launching browser for {TARGET_URL}...")
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        page = browser.new_page()
        page.goto(TARGET_URL, wait_until="networkidle", timeout=30000)
        page.wait_for_timeout(4000)

        # --- Scrape Neo-Cloud tab (default visible tab) ---
        try:
            # Look for the big price number on the page
            price_text = page.locator("text=/^\\d+\\.\\d+$/").first.text_content(timeout=5000)
            m = price_re.search(price_text or "")
            if m:
                records.append({
                    "date": TODAY,
                    "provider": "Neo-Cloud Index",
                    "category": "Neo-Cloud",
                    "gpu_count": 1,
                    "price_per_hour": float(m.group(1)),
                    "price_per_gpu_hour": float(m.group(1)),
                })
                print(f"Neo-Cloud H100 index: ${m.group(1)}/GPU/hr")
        except Exception as e:
            print(f"Could not find Neo-Cloud price: {e}")
            # Fallback: scan all text for price patterns near "Neo-Cloud"
            content = page.content()
            prices = price_re.findall(content)
            for p_val in prices:
                val = float(p_val)
                if 1.0 <= val <= 10.0:  # H100 prices are typically $1-10/GPU/hr
                    records.append({
                        "date": TODAY,
                        "provider": "Neo-Cloud Index",
                        "category": "Neo-Cloud",
                        "gpu_count": 1,
                        "price_per_hour": val,
                        "price_per_gpu_hour": val,
                    })
                    print(f"Neo-Cloud H100 index (fallback): ${val}/GPU/hr")
                    break

        # --- Click Hyperscaler tab and scrape ---
        try:
            page.get_by_text("Hyperscaler", exact=False).first.click()
            page.wait_for_timeout(2000)
            price_text = page.locator("text=/^\\d+\\.\\d+$/").first.text_content(timeout=5000)
            m = price_re.search(price_text or "")
            if m:
                records.append({
                    "date": TODAY,
                    "provider": "Hyperscaler Index",
                    "category": "Hyperscaler",
                    "gpu_count": 1,
                    "price_per_hour": float(m.group(1)),
                    "price_per_gpu_hour": float(m.group(1)),
                })
                print(f"Hyperscaler H100 index: ${m.group(1)}/GPU/hr")
        except Exception as e:
            print(f"Could not find Hyperscaler price: {e}")

        browser.close()

    print(f"Scraped {len(records)} index records for {TODAY}")
    return records


def fetch_nvda() -> pd.DataFrame:
    print("Fetching NVDA stock data...")
    start = "2023-01-01"
    if NVDA_CSV.exists():
        existing = pd.read_csv(NVDA_CSV)
        if not existing.empty:
            start = existing["date"].max()
    try:
        ticker = yf.Ticker("NVDA")
        df = ticker.history(start=start, auto_adjust=True)
        if df.empty:
            return pd.DataFrame()
        df.index = df.index.tz_localize(None)
        df = df[["Open", "High", "Low", "Close", "Volume"]].reset_index()
        df.columns = ["date", "open", "high", "low", "close", "volume"]
        df["date"] = df["date"].dt.date.astype(str)
        print(f"Fetched {len(df)} NVDA trading days")
        return df
    except Exception as e:
        print(f"ERROR fetching NVDA: {e}")
        return pd.DataFrame()


def save_csv(new_df, path, key_cols):
    DATA_DIR.mkdir(exist_ok=True)
    if path.exists():
        existing = pd.read_csv(path)
        combined = pd.concat([existing, new_df], ignore_index=True)
        combined = combined.drop_duplicates(subset=key_cols, keep="last")
    else:
        combined = new_df
    combined.to_csv(path, index=False)
    print(f"Saved {len(combined)} total rows to {path}")


if __name__ == "__main__":
    try:
        records = scrape_silicon_data()
        if records:
            save_csv(pd.DataFrame(records), GPU_CSV, key_cols=["date", "provider"])
        else:
            print("WARNING: No GPU index data scraped")
    except Exception as e:
        print(f"ERROR in GPU scrape: {e}")

    nvda_df = fetch_nvda()
    if not nvda_df.empty:
        save_csv(nvda_df, NVDA_CSV, key_cols=["date"])

    print("Done!")
