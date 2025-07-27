import streamlit as st
import pandas as pd
import altair as alt

from datetime import date
from database import connect, query_options
import data_fetcher

# Configuración de página
st.set_page_config(
    page_title="📊 Dividend Options Premium Dashboard",
    layout="wide",
)

# Título principal
st.title("📈 Dividend Options Premium Dashboard")
st.markdown(
    """
    Explore real-time options data for dividend-paying S&P 500 companies
    (o tus propios tickers desde `isins.txt`). Usa los filtros de la barra
    lateral para refinar los contratos y encontrar las primas más atractivas.
    """
)

# ─── Botón para refrescar la lista de tickers ──────────────────────────────
if st.button("🔄 Refrescar lista de tickers"):
    # Elimina el cache de tickers en la sesión
    st.session_state.pop("tickers_list", None)

# Carga la lista de tickers y la guarda en session_state
if "tickers_list" not in st.session_state:
    st.session_state.tickers_list = data_fetcher.get_sp500_tickers()

tickers = st.session_state.tickers_list
# ──────────────────────────────────────────────────────────────────────────

# Sidebar con filtros
with st.sidebar:
    st.header("Filtros")

    # Selección de tickers
    selected = st.multiselect(
        "Select tickers",
        tickers,
        default=(tickers[:2] if len(tickers) >= 2 else tickers),
    )

    # Tipo de opción
    option_type = st.selectbox(
        "Option type",
        ["Both", "CALL", "PUT"],
        index=0,
    )

    # Rango de primas
    bid_min, bid_max = st.slider(
        "Bid premium range",
        min_value=0.0,
        max_value=100.0,
        value=(0.0, 10.0),
        step=0.1,
    )

    # Fecha de expiración mínima
    ex_date = st.date_input(
        "Expiry date on or after",
        value=date.today()
    )

# Validaciones básicas
if not selected:
    st.warning("Please select at least one ticker.")
    st.stop()

# Conexión a la base de datos y consulta
conn = connect()
df = query_options(
    conn,
    tickers=selected,
    option_type=None if option_type == "Both" else option_type,
    bid_range=(bid_min, bid_max),
    ex_date=ex_date,
)

# Mostrar resultados
if df.empty:
    st.info("No option contracts found for the selected filters. Try adjusting the criteria.")
else:
    # Tabla de datos
    st.dataframe(df, use_container_width=True)

    # Gráfico IV vs Strike (scatter)
    iv_chart = (
        alt.Chart(df)
        .mark_circle(size=60)
        .encode(
            x="strike:Q",
            y="implied_volatility:Q",
            color="bid:Q",
            tooltip=[
                "ticker",
                "strike",
                "bid",
                "implied_volatility",
                "volume",
                "open_interest",
            ],
        )
        .properties(title="IV vs Strike")
        .interactive()
    )
    st.altair_chart(iv_chart, use_container_width=True)

    # Heatmap de primas (premium heatmap)
    heatmap = (
        alt.Chart(df)
        .mark_rect()
        .encode(
            x="strike:O",
            y="expiration:O",
            color="bid:Q",
            tooltip=[
                "ticker",
                "strike",
                "expiration",
                "bid",
                "volume",
                "open_interest",
            ],
        )
        .properties(title="Premium Heatmap")
    )
    st.altair_chart(heatmap, use_container_width=True)
