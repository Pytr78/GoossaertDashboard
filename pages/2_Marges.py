import streamlit as st
from auth import require_password

require_password()
import pandas as pd
import plotly.express as px
from odoo_client import OdooClient

st.set_page_config(page_title="Marges per product", page_icon="💰", layout="wide")
st.title("💰 Marges per product")

@st.cache_resource
def get_client():
    return OdooClient()

@st.cache_data(ttl=300)
def load_products():
    client = get_client()
    return client.search_read(
        "product.template",
        [["sale_ok", "=", True], ["active", "=", True]],
        ["name", "list_price", "standard_price", "categ_id"],
        limit=5000,
    )

with st.spinner("Producten ophalen..."):
    try:
        records = load_products()
    except Exception as e:
        st.error(f"Fout bij ophalen data: {e}")
        st.stop()

df = pd.DataFrame(records)
df["categorie"] = df["categ_id"].apply(lambda x: x[1].split(" / ")[-1] if isinstance(x, list) else "")
df = df.rename(columns={"name": "product", "list_price": "verkoopprijs", "standard_price": "inkoopprijs"})

# Bereken marge % op basis van verkoopprijs
df["marge_pct"] = df.apply(
    lambda r: round((r["verkoopprijs"] - r["inkoopprijs"]) / r["verkoopprijs"] * 100, 1)
    if r["verkoopprijs"] > 0 else None,
    axis=1,
)

# Filter producten zonder prijzen
df_valid = df[df["verkoopprijs"] > 0].copy()
df_missing = df[df["verkoopprijs"] == 0].copy()

# --- Filters ---
col_f1, col_f2 = st.columns([2, 1])
with col_f1:
    categorieen = sorted(df_valid["categorie"].unique())
    selectie = st.multiselect("Categorie", categorieen, placeholder="Alle categorieën")
with col_f2:
    min_m, max_m = st.slider("Marge % filter", -100, 100, (0, 100))

filtered = df_valid.copy()
if selectie:
    filtered = filtered[filtered["categorie"].isin(selectie)]
filtered = filtered[
    (filtered["marge_pct"] >= min_m) & (filtered["marge_pct"] <= max_m)
]
filtered = filtered.sort_values("marge_pct", ascending=False)

# --- KPIs ---
k1, k2, k3, k4 = st.columns(4)
k1.metric("Producten (met prijs)", len(df_valid))
k2.metric("Gefilterd", len(filtered))
k3.metric("Gem. marge %", f"{filtered['marge_pct'].mean():.1f}%" if len(filtered) else "—")
k4.metric("Zonder verkoopprijs", len(df_missing))

st.divider()

# --- Grafiek: verdeling marge % ---
st.subheader("Verdeling marge %")
fig = px.histogram(
    filtered,
    x="marge_pct",
    nbins=30,
    labels={"marge_pct": "Marge %", "count": "Aantal producten"},
    color_discrete_sequence=["#2196F3"],
)
fig.update_layout(margin=dict(t=20, b=20), bargap=0.05)
st.plotly_chart(fig, use_container_width=True)

st.divider()

# --- Tabel ---
st.subheader("Producten")
display = filtered[["product", "categorie", "inkoopprijs", "verkoopprijs", "marge_pct"]].copy()
display.columns = ["Product", "Categorie", "Inkoopprijs (€)", "Verkoopprijs (€)", "Marge %"]

st.dataframe(
    display,
    use_container_width=True,
    hide_index=True,
    column_config={
        "Inkoopprijs (€)": st.column_config.NumberColumn(format="€ %.2f"),
        "Verkoopprijs (€)": st.column_config.NumberColumn(format="€ %.2f"),
        "Marge %": st.column_config.NumberColumn(format="%.1f %%"),
    },
)
