"""
scrape_to_csv.py — Run by GitHub Actions daily.
Scrapes silicon.fail for H100 prices and fetches NVDA stock data.
Appends new rows to data/gpu_prices.csv and data/nvda_prices.csv.
"""

import requests
from bs4 import BeautifulSoup
import pandas as pd
from pathlib import Path
from datetime import date, datetime
import re
import yfinance as yf

# ── Config ─────────────────────────────────────────────────────────────────────
TARGET_URL = "https://silicon.fail"
DATA_DIR = Path("data")
GPU_CSV = DATA_DIR / "gpu_prices.csv"
NVDA_CSV = DATA_DIR / "nvda_prices.csv"
TODAY = date.today().isoformat()

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/120.0.0.0 Safari/537.36"
    )
}

HYPERSCALERS = {"aws", "azure", "gcp", "google", "amazon", "microsoft"}
NEO_CLOUDS = {
    "coreweave", "lambda", "vast", "runpod", "together", "replicate",
    "crusoe", "fluidstack", "datacrunch", "oblivus", "vultr", "genesis",
    "hyperstack", "tensordock", "latitude", "lepton", "sfcompute",
    "shadeform", "novita", "ori", "cirrascale", "scaleway"
}


def classify_provider(name: str) -> str:
    n = name.lower()
    for h in HYPERSCALERS:
        if h in n:
            return "Hyperscaler"
    for c in NEO_CLOUDS:
        if c in n:
            return "Neo-Cloud"
    return "Neo-Cloud"


# ── Scrape GPU prices ──────────────────────────────────────────────────────────
def scrape_gpu_prices() -> pd.DataFrame:
    print(f"Fetching {TARGET_URL}...")
    try:
        resp = requests.get(TARGET_URL, headers=HEADERS, timeout=20)
        resp.raise_for_status()
    except Exception as e:
        print(f"ERROR fetching page: {e}")
        return pd.DataFrame()

    soup = BeautifulSoup(resp.text, "html.parser")
    records = []
    price_re = re.compile(r"\$?([\d]+\.[\d]{1,4})")

    # Strategy 1: tables
    for table in soup.find_all("table"):
        rows = table.find_all("tr")
        for row in rows[1:]:
            cells = row.find_all(["td", "th"])
            if len(cells) < 2:
                continue
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
                if any(s in provider.lower() for s in ["provider", "cloud", "name", "vendor"]):
                    continue
                records.append({
                    "date": TODAY,
                    "provider": provider,
                    "category": classify_provider(provider),
                    "gpu_count": gpu_count,
                    "price_per_hour": price,
                    "price_per_gpu_hour": round(price / gpu_count, 4),
                })

    # Strategy 2: text scan fallback
    if not records:
        print("No tables found, trying text scan...")
        lines = soup.get_text("\n").splitlines()
        for i, line in enumerate(lines):
            m = price_re.search(line)
            if not m:
                continue
            price = float(m.group(1))
            if not (0.5 <= price <= 500):
                continue
            provider_line = line.replace(m.group(0), "").strip(" |$\t-")
            if not provider_line and i > 0:
                provider_line = lines[i - 1].strip()
            if provider_line and 1 < len(provider_line) < 60:
                records.append({
                    "date": TODAY,
                    "provider": provider_line,
                    "category": classify_provider(provider_line),
                    "gpu_count": 8,
                    "price_per_hour": price,
                    "price_per_gpu_hour": round(price / 8, 4),
                })

    # Deduplicate
    seen = set()
    unique = []
    for r in records:
        key = (r["provider"].lower(), r["price_per_hour"])
        if key not in seen:
            seen.add(key)
            unique.append(r)

    print(f"Scraped {len(unique)} GPU price records for {TODAY}")
    return pd.DataFrame(unique)


# ── Fetch NVDA stock ───────────────────────────────────────────────────────────
def fetch_nvda() -> pd.DataFrame:
    print("Fetching NVDA stock data...")
    # Determine start date
    start = "2023-01-01"
    if NVDA_CSV.exists():
        existing = pd.read_csv(NVDA_CSV)
        if not existing.empty:
            start = existing["date"].max()  # Only fetch from last stored date

    try:
        ticker = yf.Ticker("NVDA")
        df = ticker.history(start=start, auto_adjust=True)
        if df.empty:
            print("No NVDA data returned")
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


# ── Save to CSV (append, no duplicates) ───────────────────────────────────────
def save_csv(new_df: pd.DataFrame, path: Path, key_cols: list[str]):
    DATA_DIR.mkdir(exist_ok=True)
    if path.exists():
        existing = pd.read_csv(path)
        combined = pd.concat([existing, new_df], ignore_index=True)
        combined = combined.drop_duplicates(subset=key_cols, keep="last")
    else:
        combined = new_df
    combined.to_csv(path, index=False)
    print(f"Saved {len(combined)} total rows to {path}")


# ── Main ───────────────────────────────────────────────────────────────────────
if __name__ == "__main__":
    gpu_df = scrape_gpu_prices()
    if not gpu_df.empty:
        save_csv(gpu_df, GPU_CSV, key_cols=["date", "provider", "gpu_count"])
    else:
        print("WARNING: No GPU data scraped today")

    nvda_df = fetch_nvda()
    if not nvda_df.empty:
        save_csv(nvda_df, NVDA_CSV, key_cols=["date"])

    print("Done!")
