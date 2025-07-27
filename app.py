"""
Streamlit Application
=====================

This module implements the front‑end dashboard for exploring options data on
dividend‑paying S&P 500 companies.  It connects to the local SQLite database
populated by ``main.py`` and presents interactive filters along with
visualisations to help identify attractive option premiums.  The dashboard is
designed to be self‑contained and easy to deploy on Streamlit Cloud.

Key Features
------------

* **Ticker selection** – choose one or more tickers from the filtered list of
  dividend‑paying companies.
* **Option type filter** – view calls, puts or both.
* **Expiration range** – restrict contracts by their expiration dates.
* **Premium range** – filter on bid prices to surface the most lucrative
  contracts.
* **Data table** – an interactive table showing the contract details and
  greeks.
* **Scatter plot** – implied volatility versus strike price with point size
  proportional to the bid premium.
* **Heatmap** – a grid of strike versus expiration coloured by bid price.

Before running the app, ensure that ``main.py`` has been executed to
populate the database and that the ``POLYGON_API_KEY`` secret is set in
``.streamlit/secrets.toml`` or as an environment variable.  See the
``README.md`` for more details.
"""

from __future__ import annotations

import os
from datetime import date, datetime
from typing import List, Optional, Tuple

import pandas as pd
import streamlit as st
import altair as alt

from database import connect, query_options
from datetime import date    # <-- añadir esto para get_date_bounds

def get_companies() -> pd.DataFrame:
    """Load the list of companies from the database.

    Returns
    -------
    pandas.DataFrame
        A DataFrame with columns ``ticker``, ``dividend_yield`` and
        ``ex_dividend_date``.  If the database is empty the returned
        DataFrame will also be empty.
    """
    with connect() as conn:
        return pd.read_sql_query(
            "SELECT ticker, dividend_yield, ex_dividend_date FROM companies ORDER BY ticker ASC",
            conn,
        )


def get_date_bounds() -> Tuple[Optional[date], Optional[date]]:
    """Determine the minimum and maximum expiration dates available.

    Returns
    -------
    tuple[date | None, date | None]
        A tuple containing the earliest and latest expiration dates in the
        options table.  If the table is empty, ``(None, None)`` is returned.
    """
    with connect() as conn:
        row = conn.execute("SELECT MIN(expiration_date), MAX(expiration_date) FROM options").fetchone()
    min_date_str, max_date_str = row
    min_date: Optional[date] = None
    max_date: Optional[date] = None
    if min_date_str:
        min_date = datetime.strptime(min_date_str, "%Y-%m-%d").date()
    if max_date_str:
        max_date = datetime.strptime(max_date_str, "%Y-%m-%d").date()
    return min_date, max_date


def get_premium_bounds() -> Tuple[Optional[float], Optional[float]]:
    """Determine the minimum and maximum bid prices in the database.

    Returns
    -------
    tuple[float | None, float | None]
        A tuple containing the minimum and maximum bid price.  ``None`` is
        returned for each bound if the table is empty or the values are NULL.
    """
    with connect() as conn:
        row = conn.execute("SELECT MIN(bid), MAX(bid) FROM options").fetchone()
    return row[0], row[1]


@st.cache_data(show_spinner=False)
def load_options(
    tickers: List[str],
    expiration_from: Optional[str],
    expiration_to: Optional[str],
    premium_min: Optional[float],
    premium_max: Optional[float],
    option_type: Optional[str],
) -> pd.DataFrame:
    """Load options from the database based on the provided filters.

    The results for all selected tickers are concatenated into a single
    DataFrame.  If no rows are returned, an empty DataFrame with the
    expected columns is returned.

    Parameters
    ----------
    tickers: list[str]
        Underlying ticker symbols to include.
    expiration_from: str | None
        Lower bound for the expiration date (YYYY‑MM‑DD) or None.
    expiration_to: str | None
        Upper bound for the expiration date (YYYY‑MM‑DD) or None.
    premium_min: float | None
        Minimum bid price to include.
    premium_max: float | None
        Maximum bid price to include.
    option_type: str | None
        Either "call", "put" or None to include both.

    Returns
    -------
    pandas.DataFrame
        A DataFrame containing the filtered options.  It includes all
        columns defined in the database schema.
    """
    frames: List[pd.DataFrame] = []
    for ticker in tickers:
        with connect() as conn:
            rows = query_options(
                conn,
                ticker=ticker,
                expiration_from=expiration_from,
                expiration_to=expiration_to,
                premium_min=premium_min,
                premium_max=premium_max,
                option_type=option_type,
            )
            if rows:
                df = pd.DataFrame(rows, columns=rows[0].keys())
                frames.append(df)
    if not frames:
        # Return an empty DataFrame with the expected columns when no data is available
        columns = [
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
            "updated_at",
        ]
        return pd.DataFrame(columns=columns)
    df_all = pd.concat(frames, ignore_index=True)
    return df_all


def render_scatter_chart(df: pd.DataFrame) -> None:
    """Render an Altair scatter plot of implied volatility vs strike price.

    Parameters
    ----------
    df: pandas.DataFrame
        The DataFrame containing options data after filtering.  Must include
        ``strike_price``, ``implied_volatility``, ``bid`` and ``option_type``.
    """
    chart = (
        alt.Chart(df)
        .mark_circle()
        .encode(
            x=alt.X("strike_price:Q", title="Strike Price"),
            y=alt.Y("implied_volatility:Q", title="Implied Volatility"),
            color=alt.Color(
                "option_type:N",
                title="Option Type",
                scale=alt.Scale(domain=["call", "put"], range=["#1f77b4", "#d62728"]),
            ),
            size=alt.Size("bid:Q", title="Bid Price", scale=alt.Scale(range=[20, 200])),
            tooltip=[
                "contract_symbol",
                "ticker",
                "expiration_date",
                "strike_price",
                "option_type",
                "bid",
                "ask",
                "implied_volatility",
                "delta",
                "theta",
                "vega",
            ],
        )
        .properties(title="Implied Volatility vs. Strike Price", height=400)
        .interactive()
    )
    st.altair_chart(chart, use_container_width=True)


def render_heatmap(df: pd.DataFrame) -> None:
    """Render a heatmap of premiums by strike and expiration.

    Parameters
    ----------
    df: pandas.DataFrame
        The DataFrame containing options data after filtering.  Must include
        ``expiration_date``, ``strike_price`` and ``bid``.
    """
    # Prepare categorical axes to prevent excessive cardinality
    heatmap_df = df.copy()
    # Convert expiration_date to string to avoid date sorting issues in Altair
    heatmap_df["expiration_date"] = pd.to_datetime(heatmap_df["expiration_date"]).dt.strftime("%Y-%m-%d")
    chart = (
        alt.Chart(heatmap_df)
        .mark_rect()
        .encode(
            x=alt.X("strike_price:O", title="Strike Price", sort="ascending"),
            y=alt.Y("expiration_date:O", title="Expiration Date", sort="ascending"),
            color=alt.Color(
                "bid:Q",
                title="Bid Price",
                scale=alt.Scale(scheme="reds"),
            ),
            tooltip=[
                "contract_symbol",
                "ticker",
                "expiration_date",
                "strike_price",
                "option_type",
                "bid",
                "ask",
                "volume",
                "open_interest",
            ],
        )
        .properties(title="Premium Heatmap", height=400)
    )
    st.altair_chart(chart, use_container_width=True)


def main() -> None:
    """Main entry point for the Streamlit app."""
    st.set_page_config(page_title="Options Premium Dashboard", layout="wide")
    st.title("📈 Dividend Options Premium Dashboard")
    st.write(
        "Explore real‑time options data for dividend‑paying S&P 500 companies. "
        "Use the filters below to narrow down contracts and identify the most attractive premiums."
    )

    # Load company list
    companies_df = get_companies()
    if companies_df.empty:
        st.warning(
            "The database appears to be empty. Please run the data fetcher ``main.py`` to populate it."
        )
        return

    tickers = companies_df["ticker"].tolist()

    # Sidebar for filters
    st.sidebar.header("Filters")
    selected_tickers = st.sidebar.multiselect(
        "Select tickers", options=tickers, default=tickers, help="Underlying companies to include in the analysis."
    )
    option_type_choice = st.sidebar.selectbox(
        "Option type", options=["Both", "call", "put"], index=0, help="Choose call, put or both types."
    )
    # Expiration date range
    min_date, max_date = get_date_bounds()
    if min_date and max_date:
        date_range = st.sidebar.date_input(
            "Expiration date range",
            (min_date, max_date),
            min_value=min_date,
            max_value=max_date,
            help="Select the window of expiration dates to consider.",
        )
        expiration_from = date_range[0].strftime("%Y-%m-%d")
        expiration_to = date_range[1].strftime("%Y-%m-%d")
    else:
        expiration_from = None
        expiration_to = None

    # Premium range (bid) slider
    min_bid, max_bid = get_premium_bounds()
    # Provide fallback values if None
    min_bid_val = float(min_bid) if min_bid is not None else 0.0
    max_bid_val = float(max_bid) if max_bid is not None else 10.0
    premium_range = st.sidebar.slider(
        "Bid premium range",
        min_value=float(min_bid_val),
        max_value=float(max_bid_val if max_bid_val > min_bid_val else min_bid_val + 1.0),
        value=(float(min_bid_val), float(max_bid_val if max_bid_val > min_bid_val else min_bid_val + 1.0)),
        step=max((max_bid_val - min_bid_val) / 100.0, 0.01),
        help="Filter contracts by bid price."
    )
    premium_min, premium_max = premium_range

    # Convert "Both" to None for the query
    option_type_filter: Optional[str] = None if option_type_choice == "Both" else option_type_choice

    # Load options data based on filters
    df = load_options(
        tickers=selected_tickers,
        expiration_from=expiration_from,
        expiration_to=expiration_to,
        premium_min=premium_min,
        premium_max=premium_max,
        option_type=option_type_filter,
    )

    if df.empty:
        st.info("No option contracts found for the selected filters. Try adjusting the criteria.")
        return

    # Display metrics at a glance
    st.subheader("Summary")
    num_contracts = len(df)
    num_unique_tickers = df["ticker"].nunique()
    col1, col2 = st.columns(2)
    col1.metric("Total contracts", f"{num_contracts}")
    col2.metric("Tickers displayed", f"{num_unique_tickers}")

    # Display data table with sorting and filtering
    st.subheader("Contract Details")
    st.dataframe(
        df.sort_values(["ticker", "expiration_date", "strike_price"])
        .reset_index(drop=True),
        use_container_width=True,
    )

    # Charts
    st.subheader("Visualisations")
    render_scatter_chart(df)
    render_heatmap(df)

    st.caption(
        "Data updates automatically as the background fetcher populates the database."
    )


if __name__ == "__main__":
    main()
