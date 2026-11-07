import streamlit as st
import pandas as pd
import plotly.express as px
from datetime import date, timedelta
from odoo_client import OdooClient

st.set_page_config(page_title="Verkoop", page_icon="📈", layout="wide")
st.title("📈 Verkoopoverzicht")

@st.cache_resource
def get_client():
    return OdooClient()

client = get_client()

# --- Datumfilter ---
col_f1, col_f2 = st.columns(2)
with col_f1:
    start = st.date_input("Van", value=date.today().replace(day=1))
with col_f2:
    end = st.date_input("Tot", value=date.today())

if start > end:
    st.error("Begindatum mag niet na einddatum liggen.")
    st.stop()

domain = [
    ["date_order", ">=", str(start)],
    ["date_order", "<=", str(end) + " 23:59:59"],
    ["state", "in", ["sale", "done"]],
]

fields = ["name", "partner_id", "date_order", "amount_total", "amount_untaxed", "state"]

with st.spinner("Data ophalen..."):
    try:
        records = client.search_read("sale.order", domain, fields, limit=1000)
    except Exception as e:
        st.error(f"Fout bij ophalen data: {e}")
        st.stop()

if not records:
    st.info("Geen bevestigde orders in deze periode.")
    st.stop()

df = pd.DataFrame(records)
df["klant"] = df["partner_id"].apply(lambda x: x[1] if isinstance(x, list) else x)
df["date_order"] = pd.to_datetime(df["date_order"])
df["datum"] = df["date_order"].dt.date

# --- KPIs ---
st.subheader("KPIs")
k1, k2, k3, k4 = st.columns(4)
k1.metric("Bevestigde orders", len(df))
k2.metric("Omzet (incl. BTW)", f"€ {df['amount_total'].sum():,.2f}")
k3.metric("Omzet (excl. BTW)", f"€ {df['amount_untaxed'].sum():,.2f}")
k4.metric("Gem. orderwaarde", f"€ {df['amount_total'].mean():,.2f}")

st.divider()

# --- Grafiek: dagelijkse omzet ---
st.subheader("Omzet per dag")
daily = df.groupby("datum")["amount_total"].sum().reset_index()
daily.columns = ["Datum", "Omzet"]
fig = px.bar(daily, x="Datum", y="Omzet", labels={"Omzet": "Omzet (€)"})
fig.update_layout(margin=dict(t=20, b=20))
st.plotly_chart(fig, use_container_width=True)

st.divider()

# --- Tabel: orders ---
st.subheader("Orders")
display = df[["name", "klant", "date_order", "amount_untaxed", "amount_total"]].copy()
display.columns = ["Referentie", "Klant", "Datum", "Excl. BTW (€)", "Incl. BTW (€)"]
display["Datum"] = display["Datum"].dt.strftime("%d/%m/%Y %H:%M")
display = display.sort_values("Datum", ascending=False)

st.dataframe(
    display,
    use_container_width=True,
    hide_index=True,
    column_config={
        "Excl. BTW (€)": st.column_config.NumberColumn(format="€ %.2f"),
        "Incl. BTW (€)": st.column_config.NumberColumn(format="€ %.2f"),
    },
)
