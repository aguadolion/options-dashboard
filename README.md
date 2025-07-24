# Options Dashboard

This repository contains a fully autonomous system for tracking real‑time options data on dividend‑paying S&P 500 companies.  The goal is to surface high‑premium put options for a selling strategy and call options on stocks already held.  A Streamlit web application provides a live dashboard with interactive tables and charts.

## Features

- **Ticker Selection** – The system pulls the current list of S&P 500 constituents and filters to those with a trailing dividend yield of at least **2.5 %**.  Dividend yield and the next ex‑dividend date are collected to provide context when evaluating option premiums.
- **Options Data** – For each selected ticker the full option chain is downloaded from the Polygon.io snapshot endpoint.  Key metrics such as strike price, expiration date, bid/ask, last trade, volume, open interest, implied volatility and the option Greeks (delta, gamma, theta, vega) are stored in a local SQLite database.
- **Cycling Fetcher** – A background process iterates through four tickers per minute to respect rate limits on the free Polygon plan.  After reaching the end of the list it loops back to the beginning so that the data stays fresh throughout the trading day.
- **Streamlit Dashboard** – A front‑end built with Streamlit displays the data in tabular form with filters for expiration date, premium threshold and strike proximity.  It also presents an IV‑versus‑strike scatter plot and a heatmap highlighting contracts with the largest premiums.  The dashboard automatically refreshes on the same cadence as the back‑end fetcher.
- **Deployment** – The repository is ready for deployment on Streamlit Cloud.  After connecting this private GitHub repository to your Streamlit account you can configure the app to run from `app.py` with no additional setup.  Secrets such as the Polygon API key are read from environment variables or from `.streamlit/secrets.toml`.

## Project Structure

```
options-dashboard/
├── app.py              # Streamlit application entry point
├── data_fetcher.py     # Functions to pull S&P 500 constituents, dividends and options data
├── database.py         # SQLite schema definitions and helper functions
├── main.py             # Scheduler that runs the background data fetch loop
├── polygon_client.py   # Thin wrapper around the Polygon REST API
├── requirements.txt    # Python dependencies (installed on Streamlit Cloud)
├── README.md           # This file
├── .gitignore          # Git ignore rules
└── .streamlit/
    └── secrets.toml    # (Optional) local secrets file for API keys (not committed)
```

## Setup

1. **Clone the repository**

   ```bash
   git clone https://github.com/aguadolion/options-dashboard.git
   cd options-dashboard
   ```

2. **Create a virtual environment and install dependencies**

   ```bash
   python -m venv venv
   source venv/bin/activate
   pip install -r requirements.txt
   ```

3. **Configure secrets** – Create a file called `.streamlit/secrets.toml` with your Polygon API key.  For example:

   ```toml
   [secrets]
   polygon_api_key = "YOUR_POLYGON_API_KEY"
   ```

   Alternatively you can export `POLYGON_API_KEY` in your environment before running the app.

4. **Run the data fetcher** – To populate the database, start the background fetch loop:

   ```bash
   python main.py
   ```

   This will create a SQLite database file called `options_data.db` and continuously update it.

5. **Launch the Streamlit dashboard** – In a separate terminal, run:

   ```bash
   streamlit run app.py
   ```

   The dashboard will open in your default browser and automatically refresh as new data arrives.

## Modifying Tickers and Filters

Ticker filtering is based on the dividend yield threshold defined in `data_fetcher.py`.  Adjust the `DIVIDEND_YIELD_THRESHOLD` constant to include more or fewer companies.  The Streamlit UI exposes interactive widgets for adjusting premium thresholds, expiration windows and strike distances at run time.

## Redeployment Steps

1. Commit and push any changes to your private GitHub repository.
2. On Streamlit Cloud, navigate to your app and click **Deploy** to trigger a new build.
3. Ensure that the Polygon API key is set in the Streamlit Cloud **Secrets** configuration.

## Disclaimer

This project is for educational and informational purposes only.  Nothing in this repository constitutes financial advice.  Use of the data and the dashboard is at your own risk.