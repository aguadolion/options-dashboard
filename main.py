"""
main.py
~~~~~~~

Entry point for running the background data fetch loop.  This script uses the
functions defined in :mod:`data_fetcher` to build and maintain the local
database of options data.  It cycles through the list of dividend‑paying
S&P 500 tickers, updating four symbols per minute to respect Polygon's free
plan rate limits.  After all tickers have been processed, the loop starts
again from the beginning.

To run the updater manually, execute:

```
python main.py
```

Ensure that the ``POLYGON_API_KEY`` environment variable is set or define it
via a `.streamlit/secrets.toml` file when deploying to Streamlit Cloud.  You
can also specify a different database path via the ``--db`` CLI argument.
"""

from __future__ import annotations

import argparse
import itertools
import logging
import os
import time

from . import data_fetcher
from .polygon_client import PolygonClient


logger = logging.getLogger(__name__)


def parse_args() -> argparse.Namespace:
    """Parse command‑line arguments."""
    parser = argparse.ArgumentParser(description="Run the options data updater loop")
    parser.add_argument(
        "--db",
        type=str,
        default="options_data.db",
        help="Path to the SQLite database file",
    )
    parser.add_argument(
        "--interval",
        type=int,
        default=15,
        help="Number of seconds to wait between API calls (default: 15)",
    )
    return parser.parse_args()


def run_loop(db_path: str, interval: int) -> None:
    """Continuously update options data on a round‑robin schedule.

    Parameters
    ----------
    db_path: str
        Path to the SQLite database.
    interval: int
        Seconds to wait between API calls.  With four calls per minute, a
        15‑second interval meets the free tier limit of five calls per minute
        while leaving a small buffer.
    """
    client = PolygonClient()
    while True:
        # Retrieve tickers and filter by dividend yield once per cycle
        tickers = data_fetcher.get_sp500_tickers()
        qualified = data_fetcher.filter_by_dividend_yield(tickers, data_fetcher.DIVIDEND_YIELD_THRESHOLD)
        if not qualified:
            logger.warning("No tickers qualified; sleeping for one hour before retrying")
            time.sleep(3600)
            continue
        # Cycle through tickers indefinitely
        for ticker in itertools.cycle(qualified):
            start_time = time.time()
            try:
                data_fetcher.fetch_and_store_options(ticker, client, db_path)
            except Exception as exc:
                logger.error("Unexpected error updating %s: %s", ticker, exc)
            # Sleep to respect rate limits
            elapsed = time.time() - start_time
            sleep_time = max(0, interval - elapsed)
            time.sleep(sleep_time)


def main() -> None:
    args = parse_args()
    logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
    run_loop(args.db, args.interval)


if __name__ == "__main__":
    main()