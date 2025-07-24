"""
database.py
~~~~~~~~~~~~

This module encapsulates all interactions with the local SQLite database used by
the options dashboard.  It defines the schema for the ``companies`` and
``options`` tables and provides helper functions for inserting, updating and
querying records.  SQLite is a lightweight, file‑based database that requires
no external server and is therefore well suited for local caching of data.

Two tables are defined:

* **companies** – stores metadata about each S&P 500 ticker, including
  dividend yield and next ex‑dividend date.
* **options** – stores snapshot data for every option contract retrieved from
  Polygon.  Records are keyed by the contract symbol and include pricing
  information, open interest, volume, greeks and implied volatility.

The database file defaults to ``options_data.db`` in the current working
directory, but can be overridden by passing a different path to
:func:`connect`.
"""

from __future__ import annotations

import sqlite3
from contextlib import contextmanager
from datetime import datetime
from typing import Iterator, Optional, Tuple


def connect(db_path: str = "options_data.db") -> sqlite3.Connection:
    """Open a connection to the SQLite database and ensure that the schema exists.

    If the database file does not exist, it will be created along with the
    required tables.  This function also enables foreign keys for the session.

    Parameters
    ----------
    db_path: str
        Path to the SQLite database file.  Defaults to ``options_data.db``.

    Returns
    -------
    sqlite3.Connection
        A connection object with foreign keys enabled and the schema created.
    """
    conn = sqlite3.connect(db_path, detect_types=sqlite3.PARSE_DECLTYPES)
    conn.row_factory = sqlite3.Row
    with conn:
        conn.execute("PRAGMA foreign_keys = ON;")
        # Create companies table
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS companies (
                ticker TEXT PRIMARY KEY,
                dividend_yield REAL,
                ex_dividend_date DATE,
                updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            );
            """
        )
        # Create options table
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS options (
                contract_symbol TEXT PRIMARY KEY,
                ticker TEXT NOT NULL,
                expiration_date DATE NOT NULL,
                strike_price REAL NOT NULL,
                option_type TEXT NOT NULL CHECK (option_type IN ('call','put')),
                bid REAL,
                ask REAL,
                last_price REAL,
                volume INTEGER,
                open_interest INTEGER,
                implied_volatility REAL,
                delta REAL,
                gamma REAL,
                theta REAL,
                vega REAL,
                updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (ticker) REFERENCES companies(ticker) ON DELETE CASCADE
            );
            """
        )
    return conn


@contextmanager
def get_connection(db_path: str = "options_data.db") -> Iterator[sqlite3.Connection]:
    """Context manager that yields a database connection and closes it on exit."""
    conn = connect(db_path)
    try:
        yield conn
    finally:
        conn.close()


def upsert_company(conn: sqlite3.Connection, ticker: str, dividend_yield: Optional[float], ex_dividend_date: Optional[str]) -> None:
    """Insert or update a company record.

    Parameters
    ----------
    conn: sqlite3.Connection
        Active database connection.
    ticker: str
        The ticker symbol.
    dividend_yield: float | None
        Trailing dividend yield (e.g. 0.0325 for 3.25 %).  ``None`` values are
        stored as NULL.
    ex_dividend_date: str | None
        Next ex‑dividend date in ISO format (YYYY‑MM‑DD) or ``None``.
    """
    with conn:
        conn.execute(
            """
            INSERT INTO companies (ticker, dividend_yield, ex_dividend_date, updated_at)
            VALUES (?, ?, ?, CURRENT_TIMESTAMP)
            ON CONFLICT(ticker) DO UPDATE SET
                dividend_yield=excluded.dividend_yield,
                ex_dividend_date=excluded.ex_dividend_date,
                updated_at=CURRENT_TIMESTAMP;
            """,
            (ticker, dividend_yield, ex_dividend_date),
        )


def upsert_option(conn: sqlite3.Connection, data: dict) -> None:
    """Insert or update a single option contract record.

    The ``data`` dictionary should contain the keys defined in the options table
    schema.  Missing keys are set to ``None`` automatically.  The contract
    symbol is used as the primary key to perform an upsert.

    Parameters
    ----------
    conn: sqlite3.Connection
        Active database connection.
    data: dict
        A dictionary representing a single option contract.
    """
    fields = [
        "contract_symbol",
        "ticker",
        "expiration_date",
        "strike_price",
        "option_type",
        "bid",
        "ask",
        "last_price",
        "volume",
        "open_interest",
        "implied_volatility",
        "delta",
        "gamma",
        "theta",
        "vega",
    ]
    values = [data.get(field) for field in fields]
    placeholders = ", ".join(["?" for _ in fields])
    update_assignments = ", ".join([f"{field}=excluded.{field}" for field in fields[1:]])
    with conn:
        conn.execute(
            f"""
            INSERT INTO options ({', '.join(fields)})
            VALUES ({placeholders})
            ON CONFLICT(contract_symbol) DO UPDATE SET
                {update_assignments},
                updated_at=CURRENT_TIMESTAMP;
            """,
            values,
        )


def query_options(
    conn: sqlite3.Connection,
    ticker: Optional[str] = None,
    expiration_from: Optional[str] = None,
    expiration_to: Optional[str] = None,
    premium_min: Optional[float] = None,
    premium_max: Optional[float] = None,
    option_type: Optional[str] = None,
) -> Tuple[sqlite3.Row, ...]:
    """Query the options table with optional filters.

    Parameters
    ----------
    conn: sqlite3.Connection
        Active database connection.
    ticker: str | None
        Filter results by underlying ticker symbol.
    expiration_from: str | None
        Minimum expiration date (YYYY‑MM‑DD) inclusive.
    expiration_to: str | None
        Maximum expiration date (YYYY‑MM‑DD) inclusive.
    premium_min: float | None
        Minimum option premium (bid price) to filter on.
    premium_max: float | None
        Maximum option premium (bid price) to filter on.
    option_type: str | None
        Filter by ``"call"`` or ``"put"``.  If ``None`` both are returned.

    Returns
    -------
    tuple[sqlite3.Row, ...]
        A tuple of rows matching the filters.  Each row behaves like a mapping.
    """
    query = ["SELECT * FROM options WHERE 1 = 1"]
    params: list = []
    if ticker:
        query.append("AND ticker = ?")
        params.append(ticker.upper())
    if expiration_from:
        query.append("AND expiration_date >= ?")
        params.append(expiration_from)
    if expiration_to:
        query.append("AND expiration_date <= ?")
        params.append(expiration_to)
    if premium_min is not None:
        query.append("AND bid >= ?")
        params.append(premium_min)
    if premium_max is not None:
        query.append("AND bid <= ?")
        params.append(premium_max)
    if option_type:
        query.append("AND option_type = ?")
        params.append(option_type.lower())
    sql = " ".join(query) + " ORDER BY expiration_date ASC, strike_price ASC"
    cur = conn.execute(sql, params)
    return cur.fetchall()


__all__ = [
    "connect",
    "get_connection",
    "upsert_company",
    "upsert_option",
    "query_options",
]