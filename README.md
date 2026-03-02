# 🖥️ H100 GPU Rental Price Tracker vs NVDA Stock

A Streamlit dashboard that tracks H100 GPU cloud rental prices from [silicon.fail](https://silicon.fail), stores historical data locally, and charts it against NVIDIA (NVDA) stock price.

![Dashboard Preview](preview.png)

## Features

- **Daily auto-scrape** from silicon.fail (hyperscalers + neo-clouds)
- **Persistent SQLite history** — data accumulates every day automatically
- **NVDA stock overlay** via Yahoo Finance (yfinance)
- **Dual-axis Plotly chart** — GPU prices (left) + NVDA stock (right)
- **Category averages** for Hyperscalers vs Neo-Clouds
- **30-day trend** comparison with % change
- **Filterable** by date range, provider category, and individual provider

---

## Quick Start

### 1. Clone the repo
```bash
git clone https://github.com/YOUR_USERNAME/h100-tracker.git
cd h100-tracker
```

### 2. Install dependencies
```bash
pip install -r requirements.txt
```

### 3. Run the app
```bash
streamlit run app.py
```

The app will open at `http://localhost:8501`. On first load, click **🔄 Refresh Now** in the sidebar to seed the database.

---

## Project Structure

```
h100-tracker/
├── app.py          # Streamlit dashboard (UI + charts)
├── scraper.py      # Web scraper for silicon.fail
├── database.py     # SQLite persistence layer
├── stocks.py       # NVDA stock price fetcher (yfinance)
├── requirements.txt
├── .gitignore      # Excludes data/ folder from git
└── data/           # Auto-created; stores tracker.db (gitignored)
```

---

## Updating the Scraper

If silicon.fail changes its HTML structure, edit `scraper.py`:

1. Open the site in your browser and inspect the pricing table
2. Find the CSS selectors or HTML element structure for provider names and prices
3. Update `parse_prices()` or `_parse_card_layout()` accordingly

The scraper tries two strategies automatically:
- **Table parsing** — looks for `<table>` with provider/price columns
- **Card parsing** — looks for div/card elements with price patterns

---

## Deploying to Streamlit Community Cloud

1. Push to GitHub (the `data/` folder is gitignored)
2. Go to [share.streamlit.io](https://share.streamlit.io) and connect your repo
3. **⚠️ Important:** Streamlit Cloud has an ephemeral filesystem — data resets on restart.
   To persist data, use one of:
   - **Streamlit Community Cloud + GitHub Actions** (commit DB to a separate branch nightly)
   - **Railway / Render / Fly.io** — mount a persistent volume at `data/`
   - **Supabase / PlanetScale** — swap `database.py` for a cloud Postgres connection

---

## Data Sources

| Source | What | How |
|--------|------|-----|
| [silicon.fail](https://silicon.fail) | H100 rental prices | BeautifulSoup scraper |
| Yahoo Finance | NVDA stock OHLCV | yfinance library |

---

## License

MIT
