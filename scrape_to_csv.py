"""
scrape_to_csv.py
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


def scrape_with_playwright():
    from playwright.sync_api import sync_playwright
    from bs4 import BeautifulSoup
    records = []
    print(f"Launching browser for {TARGET_URL}...")
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        context = browser.new_context(
            user_agent="Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 Chrome/120.0.0.0 Safari/537.36",
            extra_http_headers={"Cookie": "cookieconsent_status=allow; CookieConsent=true"}
        )
        page = context.new_page()
        page.route("**/*.{png,jpg,jpeg,gif,webp,woff,woff2,ttf}", lambda r: r.abort())
        try:
            page.goto(TARGET_URL, wait_until="load", timeout=45000)
        except Exception as e:
            print(f"Load warning: {e}")
        for selector in ["button:has-text(\"Accept\")", "button:has-text(\"Allow\")", "button:has-text(\"OK\")", "[id*=accept]"]:
            try:
                page.locator(selector).first.click(timeout=2000)
                print(f"Dismissed cookie banner")
                page.wait_for_timeout(2000)
                break
            except:
                pass
        page.wait_for_timeout(6000)

        def extract_price(html):
            text = BeautifulSoup(html, "html.parser").get_text(" ")
            print(f"Page text sample: {text[:800]}")
            for pat in [r"\$(\d+\.\d{2})", r"(\d+\.\d{2})\s*USD", r"(?:^|\s)(\d\.\d{2})(?:\s|$)"]:
                matches = re.findall(pat, text)
                valid = [float(x) for x in matches if 1.0 <= float(x) <= 10.0]
                if valid:
                    return valid[0]
            all_d = re.findall(r"\b(\d+\.\d{2})\b", text)
            valid = [float(x) for x in all_d if 1.0 <= float(x) <= 10.0]
            return valid[0] if valid else None

        neo = extract_price(page.content())
        if neo:
            records.append({"date": TODAY, "provider": "Neo-Cloud Index", "category": "Neo-Cloud",
                "gpu_count": 1, "price_per_hour": neo, "price_per_gpu_hour": neo})
            print(f"Neo-Cloud: ${neo}")
        else:
            print("No Neo-Cloud price found")
        try:
            page.get_by_text("Hyperscaler").first.click()
            page.wait_for_timeout(3000)
            hyper = extract_price(page.content())
            if hyper:
                records.append({"date": TODAY, "provider": "Hyperscaler Index", "category": "Hyperscaler",
                    "gpu_count": 1, "price_per_hour": hyper, "price_per_gpu_hour": hyper})
                print(f"Hyperscaler: ${hyper}")
        except Exception as e:
            print(f"Hyperscaler tab: {e}")
        browser.close()
    print(f"Scraped {len(records)} records")
    return records


def fetch_nvda():
    print("Fetching NVDA...")
    start = "2023-01-01"
    if NVDA_CSV.exists():
        ex = pd.read_csv(NVDA_CSV)
        if not ex.empty:
            start = ex["date"].max()
    try:
        df = yf.Ticker("NVDA").history(start=start, auto_adjust=True)
        if df.empty:
            return pd.DataFrame()
        df.index = df.index.tz_localize(None)
        df = df[["Open","High","Low","Close","Volume"]].reset_index()
        df.columns = ["date","open","high","low","close","volume"]
        df["date"] = df["date"].dt.date.astype(str)
        print(f"Fetched {len(df)} NVDA days")
        return df
    except Exception as e:
        print(f"NVDA error: {e}")
        return pd.DataFrame()


def save_csv(new_df, path, key_cols):
    DATA_DIR.mkdir(exist_ok=True)
    if path.exists():
        ex = pd.read_csv(path)
        combined = pd.concat([ex, new_df], ignore_index=True).drop_duplicates(subset=key_cols, keep="last")
    else:
        combined = new_df
    combined.to_csv(path, index=False)
    print(f"Saved {len(combined)} rows to {path}")


if __name__ == "__main__":
    try:
        records = scrape_with_playwright()
        if records:
            save_csv(pd.DataFrame(records), GPU_CSV, key_cols=["date","provider"])
        else:
            print("WARNING: No GPU data")
    except Exception as e:
        print(f"ERROR: {e}")
    nvda = fetch_nvda()
    if not nvda.empty:
        save_csv(nvda, NVDA_CSV, key_cols=["date"])
    print("Done!")
