"""
scrape_to_csv.py - Scrapes H100 prices directly from cloud provider APIs.
No cookie walls. Runs daily via GitHub Actions.
Sources: RunPod (GraphQL), Lambda Labs (API), Vast.ai (API), Azure (retail API), GCP (pricelist), AWS
"""
import json, re, requests, pandas as pd
from pathlib import Path
from datetime import date

DATA_DIR = Path("data")
GPU_CSV = DATA_DIR / "gpu_prices.csv"
NVDA_CSV = DATA_DIR / "nvda_prices.csv"
TODAY = date.today().isoformat()
HDR = {"User-Agent": "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 Chrome/120.0.0.0 Safari/537.36"}

def fetch_runpod():
    print("Fetching RunPod...")
    try:
        r = requests.post("https://api.runpod.io/graphql",
            json={"query": "{ gpuTypes { id displayName securePrice communityPrice } }"},
            headers=HDR, timeout=15)
        for g in r.json().get("data", {}).get("gpuTypes", []):
            n = g.get("displayName","") or g.get("id","")
            if "H100" in n:
                p = g.get("securePrice") or g.get("communityPrice")
                if p and float(p) > 0:
                    print(f"  RunPod {n}: ${p}/GPU/hr")
                    return {"provider":"RunPod","category":"Neo-Cloud","price":float(p)}
    except Exception as e:
        print(f"  RunPod error: {e}")

def fetch_lambda():
    print("Fetching Lambda Labs...")
    try:
        r = requests.get("https://cloud.lambdalabs.com/api/v1/instance-types", headers=HDR, timeout=15)
        for name, info in r.json().get("data", {}).items():
            if "h100" in name.lower():
                specs = info.get("instance_type", {})
                cents = specs.get("price_cents_per_hour")
                if cents:
                    gpus = (specs.get("specs") or {}).get("gpus") or 1
                    p = round(cents / 100 / gpus, 4)
                    print(f"  Lambda {name}: ${p}/GPU/hr")
                    return {"provider":"Lambda Labs","category":"Neo-Cloud","price":p}
    except Exception as e:
        print(f"  Lambda error: {e}")

def fetch_vastai():
    print("Fetching Vast.ai...")
    try:
        params = {"q": json.dumps({"gpu_name":{"eq":"H100_SXM5_80GB"},"rentable":{"eq":True},"order":[["dph_total","asc"]],"limit":10})}
        r = requests.get("https://console.vast.ai/api/v0/bundles/", params=params, headers=HDR, timeout=15)
        offers = r.json().get("offers", [])
        prices = [o["dph_total"]/max(o.get("num_gpus",1),1) for o in offers if o.get("dph_total") and 0.5 <= o["dph_total"]/max(o.get("num_gpus",1),1) <= 15]
        if prices:
            avg = round(sum(prices[:5])/min(len(prices),5), 4)
            print(f"  Vast.ai H100 avg: ${avg}/GPU/hr")
            return {"provider":"Vast.ai","category":"Neo-Cloud","price":avg}
    except Exception as e:
        print(f"  Vast.ai error: {e}")

def fetch_azure():
    print("Fetching Azure...")
    try:
        params = {"$filter":"serviceName eq \'Virtual Machines\' and priceType eq \'Consumption\' and contains(skuName, \'H100\')","api-version":"2023-01-01-preview"}
        r = requests.get("https://prices.azure.com/api/retail/prices", params=params, headers=HDR, timeout=15)
        for item in r.json().get("Items", []):
            sku = item.get("skuName","")
            if "Windows" not in sku and "eastus" in item.get("armRegionName","").lower() and "Spot" not in sku:
                p = item.get("retailPrice", 0)
                if p and 1.0 <= float(p) <= 500:
                    print(f"  Azure {sku}: ${p}/hr")
                    return {"provider":"Azure","category":"Hyperscaler","price":float(p)}
    except Exception as e:
        print(f"  Azure error: {e}")

def fetch_gcp():
    print("Fetching GCP...")
    try:
        r = requests.get("https://cloudpricingcalculator.appspot.com/static/data/pricelist.json", headers=HDR, timeout=20)
        for key, val in r.json().get("gcp_price_list", {}).items():
            if "A3" in key.upper() and "HIGH" in key.upper():
                p = val.get("us", val.get("us-central1", 0))
                if p and float(p) > 0:
                    per_gpu = round(float(p)/8, 4)
                    print(f"  GCP {key}: ${per_gpu}/GPU/hr")
                    return {"provider":"GCP","category":"Hyperscaler","price":per_gpu}
    except Exception as e:
        print(f"  GCP error: {e}")

def fetch_aws():
    print("Fetching AWS...")
    try:
        r = requests.get("https://aws.amazon.com/ec2/pricing/on-demand/", headers=HDR, timeout=15)
        for pat in [r"p5\.48xlarge[^$]{0,200}\$\s*([\d,]+\.[\d]+)", r"\$\s*([\d,]+\.[\d]+)[^p]{0,200}p5\.48xlarge"]:
            m = re.search(pat, r.text, re.DOTALL)
            if m:
                total = float(m.group(1).replace(",",""))
                if 50 <= total <= 500:
                    per_gpu = round(total/8, 4)
                    print(f"  AWS p5.48xlarge: ${per_gpu}/GPU/hr")
                    return {"provider":"AWS","category":"Hyperscaler","price":per_gpu}
        print("  AWS: could not parse price")
    except Exception as e:
        print(f"  AWS error: {e}")

def fetch_nvda():
    import yfinance as yf
    print("Fetching NVDA...")
    start = "2023-01-01"
    if NVDA_CSV.exists():
        ex = pd.read_csv(NVDA_CSV)
        if not ex.empty: start = ex["date"].max()
    try:
        df = yf.Ticker("NVDA").history(start=start, auto_adjust=True)
        if df.empty: return pd.DataFrame()
        df.index = df.index.tz_localize(None)
        df = df[["Open","High","Low","Close","Volume"]].reset_index()
        df.columns = ["date","open","high","low","close","volume"]
        df["date"] = df["date"].dt.date.astype(str)
        print(f"  Fetched {len(df)} NVDA days")
        return df
    except Exception as e:
        print(f"  NVDA error: {e}")
        return pd.DataFrame()

def save_csv(new_df, path, key_cols):
    DATA_DIR.mkdir(exist_ok=True)
    if path.exists():
        ex = pd.read_csv(path)
        combined = pd.concat([ex, new_df], ignore_index=True).drop_duplicates(subset=key_cols, keep="last")
    else:
        combined = new_df
    combined.to_csv(path, index=False)
    print(f"  Saved {len(combined)} rows to {path}")

if __name__ == "__main__":
    print(f"=== Scraping H100 prices for {TODAY} ===\n")
    records = []
    for fetcher in [fetch_runpod, fetch_lambda, fetch_vastai, fetch_azure, fetch_gcp, fetch_aws]:
        result = fetcher()
        if result:
            records.append({"date":TODAY,"provider":result["provider"],"category":result["category"],
                "gpu_count":1,"price_per_hour":result["price"],"price_per_gpu_hour":result["price"]})
    print(f"\nTotal: {len(records)} providers scraped")
    for r in records:
    name, cat, price = r['provider'], r['category'], r['price_per_gpu_hour']
    print(f"  {name} ({cat}): ${price}/GPU/hr")
    if records:
        save_csv(pd.DataFrame(records), GPU_CSV, key_cols=["date","provider"])
    else:
        print("WARNING: No GPU data scraped")
    nvda = fetch_nvda()
    if not nvda.empty: save_csv(nvda, NVDA_CSV, key_cols=["date"])
    print("\nDone!")
