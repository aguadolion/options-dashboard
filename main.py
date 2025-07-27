#!/usr/bin/env python3
"""
main.py
~~~~~~~

Entry point for running the background data fetch loop. This script uses the
functions defined in :mod:`data_fetcher` to build and maintain the local
database of options data. It cycles through the list of dividend‑paying
S&P 500 tickers (o lee tus ISIN desde un fichero “isins.txt”), actualizando
cuatro símbolos por minuto para respetar los límites de la cuenta gratuita
de Polygon. Tras procesar todos, vuelve a empezar.

Para ejecutarlo manualmente:
    python main.py

Para CI / GitHub Actions (una sola pasada):
    python -m main --once
"""

from __future__ import annotations

import argparse
import itertools
import logging
import os
import time

# Import modules either as absolute when run as a script, or relative when packaged
try:
    from . import data_fetcher               # type: ignore
    from .polygon_client import PolygonClient  # type: ignore
except ImportError:
    import data_fetcher                      # type: ignore
    from polygon_client import PolygonClient  # type: ignore

logger = logging.getLogger(__name__)


def parse_args() -> argparse.Namespace:
    """Parse command‑line arguments."""
    parser = argparse.ArgumentParser(description="Run the options data updater")
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
        help="Seconds to wait between each symbol update (default: 15)",
    )
    parser.add_argument(
        "--once",
        action="store_true",
        help="Run one full pass and exit (for CI)",
    )
    return parser.parse_args()


def run_loop(db_path: str, interval: int) -> None:
    """Continuously update options data on a round‑robin schedule."""
    client = PolygonClient()
    while True:
        tickers = data_fetcher.get_sp500_tickers()
        qualified = data_fetcher.filter_by_dividend_yield(
            tickers, data_fetcher.DIVIDEND_YIELD_THRESHOLD
        )
        if not qualified:
            logger.warning("No tickers qualified; sleeping for 1h before retrying")
            time.sleep(3600)
            continue

        for ticker in itertools.cycle(qualified):
            start = time.time()
            try:
                data_fetcher.fetch_and_store_options(ticker, client, db_path)
            except Exception as exc:
                logger.error("Error updating %s: %s", ticker, exc)
            elapsed = time.time() - start
            time.sleep(max(0, interval - elapsed))


def main() -> None:
    args = parse_args()
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [%(levelname)s] %(message)s",
    )

    if args.once:
        # Single pass for CI
        client = PolygonClient()
        tickers = data_fetcher.get_sp500_tickers()
        qualified = data_fetcher.filter_by_dividend_yield(
            tickers, data_fetcher.DIVIDEND_YIELD_THRESHOLD
        )
        for ticker in qualified:
            try:
                data_fetcher.fetch_and_store_options(ticker, client, args.db)
            except Exception as exc:
                logger.error("Error updating %s: %s", ticker, exc)
    else:
        # Continuous loop for production
        run_loop(args.db, args.interval)


if __name__ == "__main__":
    main()
