"""
scrape_to_csv.py — Run by GitHub Actions daily.
Uses Playwright to render JavaScript and scrape H100 prices from silicon.fail.
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
TARGET_URL = "https://silicon.fail"

HYPERSCALERS = {"aws", "azure", "gcp", "google", "amazon", "microsoft"}
NEO_CLOUDS = {
    "coreweave", "lambda", "vast", "runpod", "together", "replicate",
    "crusoe", "fluidstack", "datacrunch", "oblivus", "vultr", "genesis",
    "hyperstack", "tensordock", "latitude", "lepton", "sfcompute",
    "shadeform", "novita", "ori", "cirrascale", "scaleway"
}

def classify_provider(name):
    n = name.lower()
    for h in HYPERSCALERS:
        if h in n: return "Hyperscaler"
    for c in NEO_CLOUDS:
        if c in n: return "Neo-Cloud"
    return "Neo-Cloud"

def scrape_with_playwright():
    from playwright.sync_api import sync_playwright
    from bs4 import BeautifulSoup
    price_re = re.compile(r"\$?([\d]+\.[\d]{1,4})")
    records = []
    print(f"Launching browser to fetch {TARGET_URL}...")
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        page = browser.new_page()
        page.goto(TARGET_URL, wait_until="networkidle", timeout=30000)
        page.wait_for_timeout(3000)
        html = page.content()
        browser.close()
    print("Page loaded, parsing...")
    soup = BeautifulSoup(html, "html.parser")
    for table in soup.find_all("table"):
        rows = table.find_all("tr")
        for row in rows[1:]:
            cells = row.find_all(["td", "th"])
            if len(cells) < 2: continue
            cell_texts = [c.get_text(strip=True) for c in cells]
            price = None
            provider = None
            gpu_count = 8
            for i, text in enumerate(cell_texts):
                m = price_re.search(text)
                if m:
                    candidate = float(m.group(1))
                    if 0.5 <= candidate <= 500:
                        price = candidate
                        provider = cell_texts[0] if i != 0 else (cell_texts[1] if len(cell_texts) > 1 else None)
                        break
                if re.match(r"^\d+$", text) and 1 <= int(text) <= 512:
                    gpu_count = int(text)
            if price and provider and len(provider) > 1:
                if any(s in provider.lower() for s in ["provider","cloud","name","vendor","#"]): continue
                records.append({"date": TODAY, "provider": provider, "category": classify_provider(provider),
                    "gpu_count": gpu_count, "price_per_hour": price, "price_per_gpu_hour": round(price/gpu_count,4)})
    if not records:
        print("No tables found, trying text scan...")
        lines = soup.get_text("\n").splitlines()
        for i, line in enumerate(lines):
            m = price_re.search(line)
            if not m: continue
            price = float(m.group(1))
            if not (0.5 <= price <= 500): continue
            provider_line = line.replace(m.group(0), "").strip(" |$\t-")
            if not provider_line and i > 0: provider_line = lines[i-1].strip()
            if provider_line and 1 < len(provider_line) < 60:
                records.append({"date": TODAY, "provider": provider_line, "category": classify_provider(provider_line),
                    "gpu_count": 8, "price_per_hour": price, "price_per_gpu_hour": round(price/8,4)})
    seen = set()
    unique = []
    for r in records:
        key = (r["provider"].lower(), r["price_per_hour"])
        if key not in seen:
            seen.add(key)
            unique.append(r)
    print(f"Found {len(unique)} GPU price records")
    return unique

def fetch_nvda():
    print("Fetching NVDA stock data...")
    start = "2023-01-01"
    if NVDA_CSV.exists():
        existing = pd.read_csv(NVDA_CSV)
        if not existing.empty: start = existing["date"].max()
    try:
        ticker = yf.Ticker("NVDA")
        df = ticker.history(start=start, auto_adjust=True)
        if df.empty: return pd.DataFrame()
        df.index = df.index.tz_localize(None)
        df = df[["Open","High","Low","Close","Volume"]].reset_index()
        df.columns = ["date","open","high","low","close","volume"]
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
        records = scrape_with_playwright()
        if records:
            save_csv(pd.DataFrame(records), GPU_CSV, key_cols=["date","provider","gpu_count"])
        else:
            print("WARNING: No GPU data scraped")
    except Exception as e:
        print(f"ERROR in GPU scrape: {e}")
    nvda_df = fetch_nvda()
    if not nvda_df.empty:
        save_csv(nvda_df, NVDA_CSV, key_cols=["date"])
    print("Done!")
