import streamlit as st
from auth import require_password

require_password()
import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
from datetime import date
from odoo_client import OdooClient

st.set_page_config(page_title="Nieuwe vs Bestaande Klanten", page_icon="👥", layout="wide")
st.title("👥 Nieuwe vs Bestaande Klanten")
st.caption("Een klant is 'nieuw' als hun allereerste bestelling binnen de geselecteerde periode valt.")

@st.cache_resource
def get_client():
    return OdooClient()

client = get_client()

# --- Datumfilter ---
col_f1, col_f2 = st.columns(2)
with col_f1:
    start = st.date_input("Van", value=date.today().replace(month=1, day=1))
with col_f2:
    end = st.date_input("Tot", value=date.today())

if start > end:
    st.error("Begindatum mag niet na einddatum liggen.")
    st.stop()

fields = ["partner_id", "date_order", "amount_untaxed"]
domain_confirmed = [["state", "in", ["sale", "done"]]]

with st.spinner("Alle historische orders ophalen..."):
    try:
        all_records = client.search_read("sale.order", domain_confirmed, fields, limit=10000)
    except Exception as e:
        st.error(f"Fout bij ophalen data: {e}")
        st.stop()

if not all_records:
    st.info("Geen orders gevonden.")
    st.stop()

df_all = pd.DataFrame(all_records)
df_all["klant_id"] = df_all["partner_id"].apply(lambda x: x[0] if isinstance(x, list) else x)
df_all["klant"] = df_all["partner_id"].apply(lambda x: x[1] if isinstance(x, list) else str(x))
df_all["date_order"] = pd.to_datetime(df_all["date_order"])

# Eerste bestelling per klant (ooit)
eerste_bestelling = df_all.groupby("klant_id")["date_order"].min().rename("eerste_order")
df_all = df_all.join(eerste_bestelling, on="klant_id")

# Filter op geselecteerde periode
start_dt = pd.Timestamp(start)
end_dt = pd.Timestamp(end) + pd.Timedelta(hours=23, minutes=59, seconds=59)
df = df_all[(df_all["date_order"] >= start_dt) & (df_all["date_order"] <= end_dt)].copy()

if df.empty:
    st.info("Geen bevestigde orders in deze periode.")
    st.stop()

# Classificatie
df["type"] = df["eerste_order"].apply(
    lambda x: "Nieuwe klant" if start_dt <= x <= end_dt else "Bestaande klant"
)

# --- KPIs ---
nieuw = df[df["type"] == "Nieuwe klant"]
bestaand = df[df["type"] == "Bestaande klant"]
totaal = df["amount_untaxed"].sum()

k1, k2, k3, k4 = st.columns(4)
k1.metric("Omzet nieuwe klanten", f"€ {nieuw['amount_untaxed'].sum():,.0f}",
          f"{nieuw['amount_untaxed'].sum() / totaal * 100:.1f}%" if totaal else "0%")
k2.metric("Omzet bestaande klanten", f"€ {bestaand['amount_untaxed'].sum():,.0f}",
          f"{bestaand['amount_untaxed'].sum() / totaal * 100:.1f}%" if totaal else "0%")
k3.metric("Aantal nieuwe klanten", nieuw["klant_id"].nunique())
k4.metric("Aantal bestaande klanten", bestaand["klant_id"].nunique())

st.divider()

# --- Donut chart ---
col1, col2 = st.columns(2)

with col1:
    st.subheader("Omzetverdeling")
    split = df.groupby("type")["amount_untaxed"].sum().reset_index()
    fig_donut = px.pie(
        split, values="amount_untaxed", names="type", hole=0.5,
        color="type",
        color_discrete_map={"Nieuwe klant": "#2ecc71", "Bestaande klant": "#3498db"},
    )
    fig_donut.update_traces(textinfo="percent+value", texttemplate="%{percent}<br>€ %{value:,.0f}")
    fig_donut.update_layout(margin=dict(t=20, b=20))
    st.plotly_chart(fig_donut, use_container_width=True)

# --- Maandelijkse trend ---
with col2:
    st.subheader("Trend per maand")
    df["maand"] = df["date_order"].dt.to_period("M").astype(str)
    maand = df.groupby(["maand", "type"])["amount_untaxed"].sum().reset_index()
    fig_bar = px.bar(
        maand, x="maand", y="amount_untaxed", color="type", barmode="stack",
        labels={"amount_untaxed": "Omzet (€)", "maand": "Maand", "type": ""},
        color_discrete_map={"Nieuwe klant": "#2ecc71", "Bestaande klant": "#3498db"},
    )
    fig_bar.update_layout(margin=dict(t=20, b=20))
    st.plotly_chart(fig_bar, use_container_width=True)

st.divider()

# --- Tabel nieuwe klanten ---
st.subheader("Nieuwe klanten in deze periode")
if nieuw.empty:
    st.info("Geen nieuwe klanten in deze periode.")
else:
    tabel_nieuw = (
        nieuw.groupby(["klant_id", "klant"])
        .agg(omzet=("amount_untaxed", "sum"), orders=("amount_untaxed", "count"))
        .reset_index()
        .sort_values("omzet", ascending=False)
        .drop(columns="klant_id")
    )
    tabel_nieuw.columns = ["Klant", "Omzet (€)", "Aantal orders"]
    st.dataframe(
        tabel_nieuw,
        use_container_width=True,
        hide_index=True,
        column_config={"Omzet (€)": st.column_config.NumberColumn(format="€ %.0f")},
    )
