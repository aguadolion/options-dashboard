#!/usr/bin/env python3
# main.py
# ~~~~~~~
#
# Entry point for running the background data fetch loop.  This script uses the
# functions defined in :mod:`data_fetcher` to build and maintain the local
# database of options data.  It cycles through the list of dividend‑paying
# S&P 500 tickers (o lee tus ISIN desde un fichero “isins.txt”), actualizando
# cuatro símbolos por minuto para respetar los límites de la cuenta gratuita
# de Polygon.  Tras procesar todos, vuelve a empezar.
#
# Para ejecutarlo manualmente:
#     python -m main
#
# Asegúrate de tener la variable de entorno POLYGON_API_KEY configurada,
# o inclúyela en .streamlit/secrets.toml en Streamlit Cloud.

from __future__ import annotations

import argparse
import itertools
import logging
import os
import time

# Import modules either as absolute when run as a script, or relative when packaged
try:
    # Cuando forma parte de un paquete, estas importaciones relativas funcionan:
    from . import data_fetcher         # type: ignore
    from .polygon_client import PolygonClient  # type: ignore
except ImportError:
    # Si falla, usar las importaciones absolutas al ejecutarse como script:
    import data_fetcher               # type: ignore
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
    """Continuously update options data on a round‑robin schedule."""
    client = PolygonClient()
    while True:
        # Carga tickers (o ISINs desde isins.txt) y filtra por dividendo
        tickers = data_fetcher.get_sp500_tickers()
        qualified = data_fetcher.filter_by_dividend_yield(
            tickers, data_fetcher.DIVIDEND_YIELD_THRESHOLD
        )
        if not qualified:
            logger.warning("No tickers qualified; sleeping for one hour before retrying")
            time.sleep(3600)
            continue

        # Recorre ciclicamente los tickers cualificados
        for ticker in itertools.cycle(qualified):
            start_time = time.time()
            try:
                data_fetcher.fetch_and_store_options(ticker, client, db_path)
            except Exception as exc:
                logger.error("Unexpected error updating %s: %s", ticker, exc)
            # Ajusta el sueño para respetar el intervalo
            elapsed = time.time() - start_time
            sleep_time = max(0, interval - elapsed)
            time.sleep(sleep_time)


def main() -> None:
    args = parse_args()
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [%(levelname)s] %(message)s",
    )
    run_loop(args.db, args.interval)


if __name__ == "__main__":
    main()
