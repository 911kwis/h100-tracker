"""
scrape_to_csv.py — Run by GitHub Actions daily.
Scrapes Neo-Cloud and Hyperscaler H100 index prices from silicondata.com
"""

import pandas as pd
from pathlib import Path
from datetime import date
import re
import yfinance as yf
import requests
from bs4 import BeautifulSoup

DATA_DIR = Path("data")
GPU_CSV = DATA_DIR / "gpu_prices.csv"
NVDA_CSV = DATA_DIR / "nvda_prices.csv"
TODAY = date.today().isoformat()
TARGET_URL = "https://www.silicondata.com/products/silicon-index"

HEADERS = {
    "User-Agent": "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
}


def scrape_with_requests() -> list[dict]:
    """Try plain requests first (faster, no timeout issues)."""
    print("Trying plain HTTP fetch...")
    try:
        resp = requests.get(TARGET_URL, headers=HEADERS, timeout=20)
        resp.raise_for_status()
        soup = BeautifulSoup(resp.text, "html.parser")
        text = soup.get_text()
        # Look for prices in range $1-$10 (H100 GPU/hr range)
        prices = re.findall(r'\b(\d+\.\d{2})\b', text)
        results = []
        for p in prices:
            val = float(p)
            if 1.0 <= val <= 10.0:
                results.append(val)
        print(f"Found candidate prices: {results[:5]}")
        return results
    except Exception as e:
        print(f"Plain fetch failed: {e}")
        return []


def scrape_with_playwright() -> list[dict]:
    """Use Playwright with faster load strategy."""
    from playwright.sync_api import sync_playwright

    records = []
    price_re = re.compile(r'\b(\d+\.\d{2})\b')

    print(f"Launching browser for {TARGET_URL}...")
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        context = browser.new_context(
            user_agent="Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 Chrome/120.0.0.0 Safari/537.36"
        )
        page = context.new_page()

        # Use "load" instead of "networkidle" — much faster
        try:
            page.goto(TARGET_URL, wait_until="load", timeout=45000)
            page.wait_for_timeout(5000)
        except Exception as e:
            print(f"Page load warning: {e}")

        content = page.content()
        text = BeautifulSoup(content, "html.parser").get_text()

        print("Page loaded. Scanning for prices...")
        print(f"Page text sample: {text[:500]}")

        # Find all decimal numbers in H100 price range
        prices = re.findall(r'\b(\d+\.\d{2})\b', text)
        valid = [float(x) for x in prices if 1.0 <= float(x) <= 10.0]
        print(f"Candidate prices found: {valid[:10]}")

        # Try clicking Hyperscaler tab too
        hyper_price = None
        try:
            page.get_by_text("Hyperscaler").first.click()
            page.wait_for_timeout(2000)
            hyper_text = BeautifulSoup(page.content(), "html.parser").get_text()
            hyper_prices = [float(x) for x in re.findall(r'\b(\d+\.\d{2})\b', hyper_text) if 1.0 <= float(x) <= 10.0]
            if hyper_prices:
                hyper_price = hyper_prices[0]
                print(f"Hyperscaler price: ${hyper_price}")
        except Exception as e:
            print(f"Hyperscaler tab: {e}")

        browser.close()

        if valid:
            records.append({
                "date": TODAY, "provider": "Neo-Cloud Index", "category": "Neo-Cloud",
                "gpu_count": 1, "price_per_hour": valid[0], "price_per_gpu_hour": valid[0],
            })
        if hyper_price:
            records.append({
                "date": TODAY, "provider": "Hyperscaler Index", "category": "Hyperscaler",
                "gpu_count": 1, "price_per_hour": hyper_price, "price_per_gpu_hour": hyper_price,
            })

    print(f"Scraped {len(records)} records")
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
        print(f"ERROR: {e}")
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
    print(f"Saved {len(combined)} rows to {path}")


if __name__ == "__main__":
    try:
        records = scrape_with_playwright()
        if records:
            save_csv(pd.DataFrame(records), GPU_CSV, key_cols=["date", "provider"])
        else:
            print("WARNING: No GPU data scraped")
    except Exception as e:
        print(f"ERROR: {e}")

    nvda_df = fetch_nvda()
    if not nvda_df.empty:
        save_csv(nvda_df, NVDA_CSV, key_cols=["date"])

    print("Done!")
