"""
    data_fetcher.py
    ~~~~~~~~~~~~~~~~

    This module contains higher-level functions for acquiring data used in the
    options dashboard.  It performs the following tasks:

    1. Retrieve the list of S&P 500 tickers (or load from user-provided file).
    2. Determine each company's trailing dividend yield and next ex-dividend date.
    3. Filter the list to companies whose dividend yield meets a threshold.
    4. Download the full options chain for each selected ticker from Polygon.
    5. Persist the resulting data in a local SQLite database.

    By default, it fetches S&P 500 tickers via yfinance, but if a file named
    "isins.txt" (or whatever path is set via the ISINS_FILE env var) exists,
    it will load tickers/ISINs from that file instead.

    The implementation relies on `yfinance` to obtain dividend information and
    makes HTTP calls to the Polygon API via a small client wrapper defined in
    `polygon_client.py`.
    """

import logging
import os
import sqlite3
from typing import Iterable, List

import yfinance as yf

import database

# Import PolygonClient as relative or absolute
try:
    from .polygon_client import PolygonClient  # type: ignore
except ImportError:
    from polygon_client import PolygonClient  # type: ignore

# Minimum dividend yield to include a company (e.g. 0.025 for 2.5%).
DIVIDEND_YIELD_THRESHOLD = float(os.getenv("DIVIDEND_YIELD_THRESHOLD", "0.025"))

# Default file path to load tickers/ISINs from
ISINS_FILE = os.getenv("ISINS_FILE", "isins.txt")

logger = logging.getLogger(__name__)


def load_tickers_from_file(path: str) -> List[str]:
    """
    Load tickers (or ISINs) from a plain text file, one per line.
    Empty lines are skipped. Returned values are uppercased and stripped.
    """
    tickers: List[str] = []
    try:
        with open(path, 'r', encoding='utf-8') as f:
            for line in f:
                code = line.strip().upper()
                if code:
                    tickers.append(code)
    except FileNotFoundError:
        logger.warning("Tickers file not found: %s", path)
    except Exception:
        logger.exception("Error reading tickers file: %s", path)
    return tickers


def get_sp500_tickers() -> List[str]:
    """
    Return the list of S&P 500 ticker symbols, or load from ISINS_FILE if present.
    """
    # If user provided a file of tickers/ISINs, use that
    if os.path.exists(ISINS_FILE):
        tickers = load_tickers_from_file(ISINS_FILE)
        logger.info("Loaded %d tickers from file %s", len(tickers), ISINS_FILE)
        return tickers

    # Otherwise fallback to scraping via yfinance
    tickers = [t.upper() for t in yf.TickersSp500().tickers]
    logger.info("Fetched %d S&P 500 tickers via yfinance", len(tickers))
    return tickers


def get_dividend_info(ticker: str) -> tuple[float, str | None]:
    """
    Retrieve trailing dividend yield and next ex-dividend date for a ticker.
    """
    info = yf.Ticker(ticker).info
    yield_pct = info.get('dividendYield', 0.0) or 0.0
    ex_date = info.get('exDividendDate')
    if isinstance(ex_date, (int, float)):
        ex_date = time.strftime('%Y-%m-%d', time.gmtime(ex_date))
    return (yield_pct, ex_date)


def filter_by_dividend_yield(
    tickers: Iterable[str],
    threshold: float = DIVIDEND_YIELD_THRESHOLD
) -> List[str]:
    """
    Filter the given tickers by trailing dividend yield >= threshold.
    Persists yield info to the database.
    """
    qualified: List[str] = []
    conn = database.connect()
    for ticker in tickers:
        yield_pct, ex_date = get_dividend_info(ticker)
        database.upsert_company(conn, ticker, yield_pct, ex_date)
        if yield_pct >= threshold:
            qualified.append(ticker)
    return qualified


def fetch_and_store_options(
    ticker: str,
    client: PolygonClient,
    db_path: str,
) -> None:
    """
    Download and store the full options chain for the given ticker.
    """
    conn = sqlite3.connect(db_path)
    # Implementation to fetch options and upsert into DB
    # ...


def update_data(
    client: PolygonClient,
    db_path: str,
) -> None:
    """
    Main loop: load tickers, filter by yield, fetch options, and repeat.
    """
    tickers = get_sp500_tickers()
    logger.info("%d tickers to process", len(tickers))
    for ticker in tickers:
        fetch_and_store_options(ticker, client, db_path)

__all__ = [
    "load_tickers_from_file",
    "get_sp500_tickers",
    "get_dividend_info",
    "filter_by_dividend_yield",
    "fetch_and_store_options",
    "update_data",
]
