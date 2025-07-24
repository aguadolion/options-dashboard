"""
data_fetcher.py
~~~~~~~~~~~~~~~~

This module contains higher‑level functions for acquiring data used in the
options dashboard.  It performs the following tasks:

1. Retrieve the list of S&P 500 tickers.
2. Determine each company's trailing dividend yield and next ex‑dividend date.
3. Filter the list to companies whose dividend yield meets a threshold.
4. Download the full options chain for each selected ticker from Polygon.
5. Persist the resulting data in a local SQLite database.

The implementation relies on `yfinance` to obtain dividend information and
`requests` to call the Polygon API via a small client wrapper defined in
``polygon_client.py``.  The functions are written in a synchronous style for
simplicity.  A scheduler in ``main.py`` orchestrates repeated calls to
``update_data`` to keep the database up to date.
"""

from __future__ import annotations

import datetime as _dt
import logging
import os
import time
from typing import Dict, Iterable, List, Optional, Tuple

import pandas as pd
import requests
import yfinance as yf

from .polygon_client import PolygonClient
from . import database


# Configure basic logging for debugging.  Users can override this configuration
# in their own scripts if desired.
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
)
logger = logging.getLogger(__name__)

# Minimum dividend yield to include a company (e.g. 0.025 for 2.5 %).  This
# constant can be modified by the caller or via the DIVIDEND_YIELD_THRESHOLD
# environment variable.
DIVIDEND_YIELD_THRESHOLD = float(os.getenv("DIVIDEND_YIELD_THRESHOLD", "0.025"))


def get_sp500_tickers() -> List[str]:
    """Return the list of S&P 500 ticker symbols.

    The tickers are obtained using :func:`yfinance.tickers_sp500`, which
    scrapes the current S&P 500 constituents from Wikipedia.  The list is
    converted to upper case and returned as a Python list.

    Returns
    -------
    list[str]
        List of ticker symbols (e.g. ``['AAPL', 'MSFT', 'GOOGL', ...]``).
    """
    tickers = yf.tickers_sp500()
    return [ticker.upper() for ticker in tickers]


def get_dividend_info(ticker: str) -> Tuple[Optional[float], Optional[str]]:
    """Retrieve the trailing dividend yield and next ex‑dividend date for a ticker.

    Parameters
    ----------
    ticker: str
        The ticker symbol (case insensitive).

    Returns
    -------
    tuple
        A two‑element tuple ``(yield, ex_date)``.  The yield is a float
        representing the trailing 12‑month dividend yield (e.g. ``0.0325`` for
        3.25 %).  The ex‑dividend date is returned as an ISO date string
        (YYYY‑MM‑DD) or ``None`` if not available.  If either value is
        unavailable, ``None`` is returned for that element.
    """
    try:
        info = yf.Ticker(ticker).info
    except Exception as exc:
        logger.warning("yfinance failed to retrieve info for %s: %s", ticker, exc)
        return None, None
    div_yield = info.get("dividendYield")
    ex_ts = info.get("exDividendDate")
    ex_date: Optional[str] = None
    if isinstance(ex_ts, (int, float)) and ex_ts > 0:
        ex_date = _dt.date.fromtimestamp(ex_ts).isoformat()
    return div_yield, ex_date


def filter_by_dividend_yield(tickers: Iterable[str], threshold: float = DIVIDEND_YIELD_THRESHOLD) -> List[str]:
    """Filter tickers by dividend yield threshold.

    Iterates over the provided tickers, fetches dividend information and
    retains those with a trailing dividend yield greater than or equal to
    ``threshold``.  A NULL (``None``) yield is considered below the threshold
    and therefore excluded.

    Parameters
    ----------
    tickers: Iterable[str]
        The universe of ticker symbols to evaluate.
    threshold: float
        Minimum yield required to pass the filter.

    Returns
    -------
    list[str]
        A list of tickers meeting the yield criterion.
    """
    qualified: List[str] = []
    for ticker in tickers:
        yield_val, ex_date = get_dividend_info(ticker)
        database.upsert_company(database.connect(), ticker, yield_val, ex_date)
        if yield_val is not None and yield_val >= threshold:
            qualified.append(ticker)
            logger.info("Ticker %s qualifies with dividend yield %.2f%%", ticker, yield_val * 100)
        else:
            logger.debug("Ticker %s skipped due to low or missing yield.", ticker)
    return qualified


def fetch_and_store_options(ticker: str, client: PolygonClient, db_path: str = "options_data.db") -> None:
    """Fetch the full option chain for a ticker and store it in the database.

    Parameters
    ----------
    ticker: str
        Underlying ticker symbol.
    client: PolygonClient
        Configured Polygon API client.
    db_path: str
        Path to the SQLite database.
    """
    logger.info("Fetching options chain for %s", ticker)
    try:
        contracts = client.get_options_chain(ticker)
    except Exception as exc:
        logger.error("Failed to fetch options for %s: %s", ticker, exc)
        return
    logger.info("Retrieved %d contracts for %s", len(contracts), ticker)
    with database.get_connection(db_path) as conn:
        for contract in contracts:
            try:
                # Flatten nested structures into a flat dictionary suitable for insertion
                c = contract
                details = c.get("details", {})
                greeks = c.get("greeks", {}) or {}
                last_quote = c.get("last_quote", {}) or {}
                last_trade = c.get("last_trade", {}) or {}
                # Determine bid/ask/last price.  Not all fields may be present.
                bid = last_quote.get("p") if last_quote.get("p") is not None else last_quote.get("bid_price")
                ask = last_quote.get("P") if last_quote.get("P") is not None else last_quote.get("ask_price")
                last_price = last_trade.get("p")
                option_data = {
                    "contract_symbol": details.get("symbol") or c.get("option"),
                    "ticker": ticker,
                    "expiration_date": details.get("expiration_date"),
                    "strike_price": details.get("strike_price"),
                    "option_type": details.get("type"),
                    "bid": bid,
                    "ask": ask,
                    "last_price": last_price,
                    "volume": c.get("day", {}).get("volume"),
                    "open_interest": c.get("open_interest"),
                    "implied_volatility": c.get("implied_volatility"),
                    "delta": greeks.get("delta"),
                    "gamma": greeks.get("gamma"),
                    "theta": greeks.get("theta"),
                    "vega": greeks.get("vega"),
                }
                database.upsert_option(conn, option_data)
            except Exception as exc:
                logger.warning("Error processing contract for %s: %s", ticker, exc)


def update_data(client: PolygonClient, db_path: str = "options_data.db") -> None:
    """Fetch and update options data for all qualifying S&P 500 dividend payers.

    This function retrieves the current S&P 500 constituents, filters them by
    dividend yield and then iterates through each qualifying ticker, pulling its
    option chain from Polygon and storing it in the database.  Because the
    Polygon free tier is rate limited to five requests per minute, callers
    should take care to throttle calls to :func:`update_data` or use
    ``main.py`` which implements a round‑robin scheduler.

    Parameters
    ----------
    client: PolygonClient
        A configured Polygon client containing an API key.
    db_path: str
        Path to the SQLite database file.
    """
    logger.info("Retrieving S&P 500 constituents...")
    tickers = get_sp500_tickers()
    logger.info("%d tickers found", len(tickers))
    dividend_tickers = filter_by_dividend_yield(tickers, DIVIDEND_YIELD_THRESHOLD)
    logger.info("%d tickers qualify after yield filter", len(dividend_tickers))
    for ticker in dividend_tickers:
        fetch_and_store_options(ticker, client, db_path)


__all__ = [
    "get_sp500_tickers",
    "get_dividend_info",
    "filter_by_dividend_yield",
    "fetch_and_store_options",
    "update_data",
]