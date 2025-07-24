from __future__ import annotations

import argparse
import itertools
import logging
import os
import time

# Import modules either as absolute when run as a script, or relative when packaged
try:
    # When part of a package, these relative imports will work
    from . import data_fetcher  # type: ignore
    from .polygon_client import PolygonClient  # type: ignore
except ImportError:
    # Fallback to absolute imports when running as a standalone script
    import data_fetcher  # type: ignore
    from polygon_client import PolygonClient  # type: ignore

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
