import streamlit as st
from auth import require_password

require_password()
import pandas as pd
import plotly.express as px
from datetime import date
from odoo_client import OdooClient

st.set_page_config(page_title="Nieuwe vs Bestaande Klanten", page_icon="👥", layout="wide")
st.title("👥 Nieuwe vs Bestaande Klanten")
st.caption(
    "Een klant is 'nieuw' in een maand als ze vóór die maand nog nooit een bestelling hadden geplaatst."
)

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

with st.spinner("Alle historische orders ophalen..."):
    try:
        all_records = client.search_read(
            "sale.order",
            [["state", "in", ["sale", "done"]]],
            ["partner_id", "date_order", "amount_untaxed"],
            limit=10000,
        )
    except Exception as e:
        st.error(f"Fout bij ophalen data: {e}")
        st.stop()

if not all_records:
    st.info("Geen orders gevonden.")
    st.stop()

df_all = pd.DataFrame(all_records)
df_all["_partner_id"] = df_all["partner_id"].apply(lambda x: x[0] if isinstance(x, list) else x)

# Zoek parent_id op voor alle unieke partners (bovenliggend bedrijf)
partner_ids = df_all["_partner_id"].unique().tolist()
with st.spinner("Bedrijfsstructuur ophalen..."):
    partner_records = client.search_read(
        "res.partner",
        [["id", "in", partner_ids]],
        ["id", "name", "parent_id"],
        limit=len(partner_ids) + 1,
    )

# Mapping: partner_id → (bedrijf_id, bedrijfsnaam)
partner_map = {}
for p in partner_records:
    if p["parent_id"]:
        partner_map[p["id"]] = (p["parent_id"][0], p["parent_id"][1])
    else:
        partner_map[p["id"]] = (p["id"], p["name"])

df_all["klant_id"] = df_all["_partner_id"].map(lambda x: partner_map.get(x, (x, str(x)))[0])
df_all["klant"] = df_all["_partner_id"].map(lambda x: partner_map.get(x, (x, str(x)))[1])
df_all["date_order"] = pd.to_datetime(df_all["date_order"])
df_all["maand"] = df_all["date_order"].dt.to_period("M")

# Eerste bestelling ooit per klant
eerste = df_all.groupby("klant_id")["date_order"].min().rename("eerste_order")
df_all = df_all.join(eerste, on="klant_id")
df_all["eerste_maand"] = df_all["eerste_order"].dt.to_period("M")

# Filter op geselecteerde periode
start_dt = pd.Timestamp(start)
end_dt = pd.Timestamp(end) + pd.Timedelta(hours=23, minutes=59, seconds=59)
df = df_all[(df_all["date_order"] >= start_dt) & (df_all["date_order"] <= end_dt)].copy()

if df.empty:
    st.info("Geen bevestigde orders in deze periode.")
    st.stop()

# Per maand: klant is nieuw als eerste_maand == huidige maand
df["type"] = df.apply(
    lambda r: "Nieuwe klant" if r["eerste_maand"] == r["maand"] else "Bestaande klant", axis=1
)

# --- KPIs over volledige periode ---
nieuw = df[df["type"] == "Nieuwe klant"]
bestaand = df[df["type"] == "Bestaande klant"]
totaal = df["amount_untaxed"].sum()

k1, k2, k3, k4 = st.columns(4)
k1.metric("Omzet nieuwe klanten", f"€ {nieuw['amount_untaxed'].sum():,.0f}",
          f"{nieuw['amount_untaxed'].sum() / totaal * 100:.1f}%" if totaal else "0%")
k2.metric("Omzet bestaande klanten", f"€ {bestaand['amount_untaxed'].sum():,.0f}",
          f"{bestaand['amount_untaxed'].sum() / totaal * 100:.1f}%" if totaal else "0%")
k3.metric("Nieuwe klanten (uniek)", nieuw["klant_id"].nunique())
k4.metric("Bestaande klanten (uniek)", bestaand["klant_id"].nunique())

st.divider()

# --- Gestapeld staafdiagram: aantal nieuwe klanten per maand ---
st.subheader("Nieuwe klanten per maand")

maand_nieuw = (
    df[df["type"] == "Nieuwe klant"]
    .groupby("maand")["klant_id"]
    .nunique()
    .reset_index()
)
maand_nieuw["maand"] = maand_nieuw["maand"].astype(str)
maand_nieuw.columns = ["Maand", "Nieuwe klanten"]

fig_klanten = px.bar(
    maand_nieuw, x="Maand", y="Nieuwe klanten",
    labels={"Nieuwe klanten": "Aantal nieuwe klanten"},
    color_discrete_sequence=["#2ecc71"],
    text="Nieuwe klanten",
)
fig_klanten.update_traces(textposition="outside")
fig_klanten.update_layout(margin=dict(t=20, b=20))
st.plotly_chart(fig_klanten, use_container_width=True)

st.divider()

# --- Omzet nieuw vs bestaand per maand ---
st.subheader("Omzet nieuwe vs bestaande klanten per maand")

maand_omzet = (
    df.groupby([df["maand"].astype(str), "type"])["amount_untaxed"]
    .sum()
    .reset_index()
)
maand_omzet.columns = ["Maand", "Type", "Omzet"]

fig_omzet = px.bar(
    maand_omzet, x="Maand", y="Omzet", color="Type", barmode="stack",
    labels={"Omzet": "Omzet excl. BTW (€)", "Type": ""},
    color_discrete_map={"Nieuwe klant": "#2ecc71", "Bestaande klant": "#3498db"},
)
fig_omzet.update_layout(margin=dict(t=20, b=20))
st.plotly_chart(fig_omzet, use_container_width=True)

st.divider()

# --- Tabel: nieuwe klanten per maand ---
st.subheader("Welke klanten waren nieuw per maand?")

maanden = sorted(df[df["type"] == "Nieuwe klant"]["maand"].unique(), reverse=True)
geselecteerde_maand = st.selectbox(
    "Selecteer maand",
    options=[str(m) for m in maanden],
)

if geselecteerde_maand:
    df_maand = df[
        (df["type"] == "Nieuwe klant") &
        (df["maand"].astype(str) == geselecteerde_maand)
    ]
    tabel = (
        df_maand.groupby(["klant_id", "klant"])
        .agg(omzet=("amount_untaxed", "sum"), orders=("amount_untaxed", "count"))
        .reset_index()
        .sort_values("omzet", ascending=False)
        .drop(columns="klant_id")
    )
    tabel.columns = ["Klant", "Omzet excl. BTW (€)", "Aantal orders"]
    st.dataframe(
        tabel,
        use_container_width=True,
        hide_index=True,
        column_config={"Omzet excl. BTW (€)": st.column_config.NumberColumn(format="€ %.0f")},
    )
