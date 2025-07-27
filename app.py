import streamlit as st
import pandas as pd
import altair as alt

from datetime import date
from database import connect, query_options
import data_fetcher

# ─── Configuración de la página ──────────────────────────────────────
st.set_page_config(
    page_title="📈 Dividend Options Premium Dashboard",
    layout="wide",
)

# ─── Título y descripción ─────────────────────────────────────────────
st.title("📈 Dividend Options Premium Dashboard")
st.markdown(
    """
    Explora datos en tiempo real de contratos de opciones para tickers desde `isins.txt`.
    Usa los filtros de la barra lateral para refinar resultados.
    """
)

# ─── Botón de refresco ──────────────────────────────────────────────────
if st.button("🔄 Refrescar lista de tickers"):
    st.session_state.pop("tickers_list", None)

# ─── Carga cacheada de la lista de tickers ─────────────────────────────
if "tickers_list" not in st.session_state:
    st.session_state.tickers_list = data_fetcher.get_sp500_tickers()

tickers = st.session_state.tickers_list

# ─── Sidebar de filtros ────────────────────────────────────────────────
with st.sidebar:
    st.header("Filtros")

    selected = st.multiselect(
        "Select tickers",
        options=tickers,
        default=(tickers[:2] if len(tickers) >= 2 else tickers),
    )

    option_type_choice = st.selectbox(
        "Option type",
        ["Both", "call", "put"],
        index=0,
    )

    bid_min, bid_max = st.slider(
        "Bid premium range",
        min_value=0.0,
        max_value=100.0,
        value=(0.0, 10.0),
        step=0.1,
    )

    ex_date = st.date_input(
        "Expiry date on or after",
        value=date.today()
    )

# ─── Validaciones ──────────────────────────────────────────────────────
if not selected:
    st.warning("Please select at least one ticker.")
    st.stop()

# ─── Consultas a la BD ───────────────────────────────────────────────────
expiration_from = ex_date.strftime("%Y-%m-%d")
conn = connect()
all_rows = []

for ticker in selected:
    rows = query_options(
        conn,
        ticker=ticker,
        expiration_from=expiration_from,
        expiration_to=None,
        premium_min=bid_min,
        premium_max=bid_max,
        option_type=None if option_type_choice == "Both" else option_type_choice,
    )
    all_rows.extend(rows)

conn.close()

# Convertimos a DataFrame
if all_rows:
    # Cada row es un sqlite3.Row; transformamos a dict
    df = pd.DataFrame([dict(r) for r in all_rows])
else:
    df = pd.DataFrame(columns=[
        "contract_symbol", "ticker", "expiration_date", "strike_price",
        "option_type", "bid", "ask", "volume", "open_interest",
        "implied_volatility", "delta", "gamma", "theta", "vega"
    ])

# ─── Presentación de resultados ─────────────────────────────────────────
if df.empty:
    st.info("No option contracts found for the selected filters. Try adjusting the criteria.")
    st.stop()

# Resumen
st.subheader("Resumen")
col1, col2 = st.columns(2)
col1.metric("Total contracts", f"{len(df)}")
col2.metric("Tickers displayed", f"{df['ticker'].nunique()}")

# Tabla detallada
st.subheader("Contract Details")
st.dataframe(
    df.sort_values(["ticker","expiration_date","strike_price"]).reset_index(drop=True),
    use_container_width=True
)

# Gráfico IV vs Strike
st.subheader("Implied Volatility vs Strike")
chart_iv = (
    alt.Chart(df)
    .mark_circle(size=60)
    .encode(
        x="strike_price:Q",
        y="implied_volatility:Q",
        color="option_type:N",
        tooltip=[
            "contract_symbol","ticker","expiration_date","strike_price",
            "option_type","bid","ask","volume","open_interest",
            "delta","gamma","theta","vega"
        ],
    )
    .interactive()
)
st.altair_chart(chart_iv, use_container_width=True)

# Heatmap de primas
st.subheader("Premium Heatmap")
heatmap_df = df.copy()
heatmap_df["expiration_date"] = pd.to_datetime(heatmap_df["expiration_date"]).dt.strftime("%Y-%m-%d")
chart_heat = (
    alt.Chart(heatmap_df)
    .mark_rect()
    .encode(
        x=alt.X("strike_price:O", title="Strike Price", sort="ascending"),
        y=alt.Y("expiration_date:O", title="Expiration Date", sort="ascending"),
        color=alt.Color("bid:Q", title="Bid Price", scale=alt.Scale(scheme="reds")),
        tooltip=[
            "contract_symbol","ticker","expiration_date","strike_price",
            "option_type","bid","ask","volume","open_interest"
        ],
    )
)
st.altair_chart(chart_heat, use_container_width=True)
