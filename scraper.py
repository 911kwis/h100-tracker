"""
scraper.py — Fetches H100 GPU rental prices from silicon.fail
(Silicon H100 GPU Rental Price Tracker)

The site renders pricing tables for hyperscalers (AWS, Azure, GCP, CoreWeave, etc.)
and neo-cloud providers. This module parses those tables and returns structured data.
"""

import requests
from bs4 import BeautifulSoup
import pandas as pd
from datetime import datetime, date
import logging

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

TARGET_URL = "https://silicon.fail"  # Update if the URL changes

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/120.0.0.0 Safari/537.36"
    )
}

# Provider classification — expand as needed
HYPERSCALERS = {"AWS", "Azure", "GCP", "Google", "Amazon", "Microsoft"}
NEO_CLOUDS = {
    "CoreWeave", "Lambda", "Vast.ai", "RunPod", "Together", "Replicate",
    "Crusoe", "Fluidstack", "DataCrunch", "Oblivus", "Vultr", "Genesis Cloud"
}


def fetch_page(url: str = TARGET_URL) -> BeautifulSoup | None:
    """Fetch and parse the target page."""
    try:
        response = requests.get(url, headers=HEADERS, timeout=15)
        response.raise_for_status()
        return BeautifulSoup(response.text, "html.parser")
    except requests.RequestException as e:
        logger.error(f"Failed to fetch {url}: {e}")
        return None


def classify_provider(name: str) -> str:
    """Classify a provider as hyperscaler, neo-cloud, or other."""
    for h in HYPERSCALERS:
        if h.lower() in name.lower():
            return "Hyperscaler"
    for n in NEO_CLOUDS:
        if n.lower() in name.lower():
            return "Neo-Cloud"
    return "Other"


def parse_prices(soup: BeautifulSoup) -> list[dict]:
    """
    Parse H100 pricing tables from silicon.fail.

    The site uses <table> elements with provider name, GPU count, and price/hr.
    Adjust selectors here if the site's HTML structure changes.
    """
    records = []
    scraped_date = date.today().isoformat()

    # silicon.fail uses a main pricing table — attempt multiple selector strategies
    tables = soup.find_all("table")

    for table in tables:
        headers_row = table.find("tr")
        if not headers_row:
            continue

        col_headers = [th.get_text(strip=True).lower() for th in headers_row.find_all(["th", "td"])]

        # Identify relevant columns (flexible matching)
        provider_col = next((i for i, h in enumerate(col_headers) if "provider" in h or "cloud" in h or "vendor" in h), None)
        price_col = next((i for i, h in enumerate(col_headers) if "price" in h or "cost" in h or "$/hr" in h or "hour" in h), None)
        gpu_col = next((i for i, h in enumerate(col_headers) if "gpu" in h or "count" in h or "qty" in h), None)

        if provider_col is None or price_col is None:
            continue  # Not a pricing table

        rows = table.find_all("tr")[1:]  # Skip header row
        for row in rows:
            cells = row.find_all(["td", "th"])
            if len(cells) <= max(filter(None, [provider_col, price_col, gpu_col])):
                continue

            try:
                provider = cells[provider_col].get_text(strip=True)
                price_text = cells[price_col].get_text(strip=True).replace("$", "").replace(",", "").strip()
                price = float(price_text)
                gpu_count = int(cells[gpu_col].get_text(strip=True)) if gpu_col is not None else 8

                records.append({
                    "date": scraped_date,
                    "provider": provider,
                    "category": classify_provider(provider),
                    "gpu_count": gpu_count,
                    "price_per_hour": price,
                    "price_per_gpu_hour": round(price / gpu_count, 4) if gpu_count else price,
                })
            except (ValueError, IndexError):
                continue

    # Fallback: try parsing any structured divs or cards if no table found
    if not records:
        records = _parse_card_layout(soup, scraped_date)

    logger.info(f"Scraped {len(records)} pricing records for {scraped_date}")
    return records


def _parse_card_layout(soup: BeautifulSoup, scraped_date: str) -> list[dict]:
    """
    Fallback parser for card/div-based layouts.
    Looks for elements containing provider names and price patterns.
    """
    import re
    records = []
    price_pattern = re.compile(r"\$?([\d.]+)\s*/\s*hr", re.IGNORECASE)

    # Try common card selectors
    cards = soup.select(".provider-card, .pricing-row, .gpu-listing, [data-provider]")
    for card in cards:
        text = card.get_text(" ", strip=True)
        match = price_pattern.search(text)
        if not match:
            continue

        # Extract provider name (first significant text before price)
        provider = card.select_one(".provider-name, .name, h3, h4")
        provider_name = provider.get_text(strip=True) if provider else "Unknown"

        try:
            records.append({
                "date": scraped_date,
                "provider": provider_name,
                "category": classify_provider(provider_name),
                "gpu_count": 8,
                "price_per_hour": float(match.group(1)),
                "price_per_gpu_hour": round(float(match.group(1)) / 8, 4),
            })
        except ValueError:
            continue

    return records


def get_latest_prices() -> pd.DataFrame:
    """Main entry point: scrape and return a DataFrame of today's prices."""
    soup = fetch_page()
    if soup is None:
        return pd.DataFrame()

    records = parse_prices(soup)
    if not records:
        logger.warning("No pricing records found. The site structure may have changed.")
        return pd.DataFrame()

    return pd.DataFrame(records)
