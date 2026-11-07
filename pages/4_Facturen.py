import streamlit as st
from auth import require_password

require_password()
import pandas as pd
import plotly.express as px
from datetime import date
from odoo_client import OdooClient

st.set_page_config(page_title="Verkoopfacturen", page_icon="🧾", layout="wide")
st.title("🧾 Verkoopfacturen per klant")

@st.cache_resource
def get_client():
    return OdooClient()

client = get_client()

# --- Periode filter ---
maandnamen = ["Januari","Februari","Maart","April","Mei","Juni",
              "Juli","Augustus","September","Oktober","November","December"]
huidig_jaar = date.today().year
huidig_kwartaal = (date.today().month - 1) // 3 + 1
huidige_maand = date.today().month

kwartaal_maanden = {"Q1": [1,2,3], "Q2": [4,5,6], "Q3": [7,8,9], "Q4": [10,11,12]}

col_f1, col_f2, col_f3 = st.columns(3)

with col_f1:
    jaar = st.selectbox("Jaar", list(range(huidig_jaar, 2024, -1)), index=0)

with col_f2:
    periode_type = st.selectbox("Periode", ["Volledig jaar", "Kwartaal", "Maand"])

with col_f3:
    if periode_type == "Kwartaal":
        sel_kwartalen = st.multiselect(
            "Kwartaal", ["Q1","Q2","Q3","Q4"],
            default=[f"Q{huidig_kwartaal}"] if jaar == huidig_jaar else ["Q1"],
        )
        geselecteerde_maanden = sorted({m for q in sel_kwartalen for m in kwartaal_maanden[q]}) if sel_kwartalen else list(range(1,13))
    elif periode_type == "Maand":
        sel_maanden = st.multiselect(
            "Maand", list(range(1,13)),
            format_func=lambda x: maandnamen[x-1],
            default=[huidige_maand] if jaar == huidig_jaar else [1],
        )
        geselecteerde_maanden = sorted(sel_maanden) if sel_maanden else list(range(1,13))
    else:
        geselecteerde_maanden = list(range(1, 13))
        st.write(f"📅 {jaar}")

start = date(jaar, 1, 1)
eind = date(jaar, 12, 31)

domain = [
    ["move_type", "=", "out_invoice"],
    ["state", "=", "posted"],
    ["invoice_date", ">=", str(start)],
    ["invoice_date", "<=", str(eind)],
    ["partner_id", "!=", 1],
]

domain_credit = [
    ["move_type", "=", "out_refund"],
    ["state", "=", "posted"],
    ["invoice_date", ">=", str(start)],
    ["invoice_date", "<=", str(eind)],
    ["partner_id", "!=", 1],
]

with st.spinner("Facturen ophalen..."):
    try:
        records = client.search_read(
            "account.move", domain,
            ["partner_id", "invoice_date", "amount_untaxed", "amount_total", "payment_state"],
            limit=5000,
        )
        records_credit = client.search_read(
            "account.move", domain_credit,
            ["partner_id", "invoice_date", "amount_untaxed", "amount_total"],
            limit=5000,
        )
    except Exception as e:
        st.error(f"Fout: {e}")
        st.stop()

if not records:
    st.info("Geen facturen gevonden voor deze periode.")
    st.stop()

df = pd.DataFrame(records)
df["klant"] = df["partner_id"].apply(lambda x: x[1] if isinstance(x, list) else str(x))
df["invoice_date"] = pd.to_datetime(df["invoice_date"])
df["betaald"] = df["payment_state"].isin(["paid", "in_payment"])
df = df[df["invoice_date"].dt.month.isin(geselecteerde_maanden)]

df_credit = pd.DataFrame(records_credit) if records_credit else pd.DataFrame(
    columns=["partner_id", "amount_untaxed", "amount_total"])
df_credit["klant"] = df_credit["partner_id"].apply(lambda x: x[1] if isinstance(x, list) else str(x)) if len(df_credit) else ""
if len(df_credit):
    df_credit["invoice_date"] = pd.to_datetime(df_credit["invoice_date"])
    df_credit = df_credit[df_credit["invoice_date"].dt.month.isin(geselecteerde_maanden)]

credit_per_klant = df_credit.groupby("klant").agg(
    credit_excl=("amount_untaxed", "sum"),
    credit_incl=("amount_total", "sum"),
).reset_index() if len(df_credit) else pd.DataFrame(columns=["klant","credit_excl","credit_incl"])

# --- KPIs ---
totaal_excl = df["amount_untaxed"].sum()
totaal_incl = df["amount_total"].sum()
totaal_credit_excl = df_credit["amount_untaxed"].sum() if len(df_credit) else 0
totaal_credit_incl = df_credit["amount_total"].sum() if len(df_credit) else 0
betaald_pct = df["betaald"].sum() / len(df) * 100

k1, k2, k3, k4 = st.columns(4)
k1.metric("Facturen / creditnota's", f"{len(df)} / {len(df_credit)}")
k2.metric("Netto omzet excl. BTW", f"€ {totaal_excl - totaal_credit_excl:,.2f}",
          delta=f"- € {totaal_credit_excl:,.0f} creditnota's", delta_color="inverse")
k3.metric("Netto omzet incl. BTW", f"€ {totaal_incl - totaal_credit_incl:,.2f}",
          delta=f"- € {totaal_credit_incl:,.0f} creditnota's", delta_color="inverse")
k4.metric("Betaald", f"{int(df['betaald'].sum())} / {len(df)}", delta=f"{betaald_pct:.0f}%")

st.divider()

# --- Per klant ---
st.subheader("Per klant — hoog naar laag")

col_s1, col_s2 = st.columns([2, 1])
with col_s1:
    zoek = st.text_input("Zoek klant", placeholder="Typ klantnaam...")
with col_s2:
    toon_bedrag = st.radio("Bedrag", ["Excl. BTW", "Incl. BTW"], horizontal=True)

bedrag_col = "excl_btw" if toon_bedrag == "Excl. BTW" else "incl_btw"

per_klant = df.groupby("klant").agg(
    aantal_facturen=("id", "count"),
    excl_btw=("amount_untaxed", "sum"),
    incl_btw=("amount_total", "sum"),
    betaald=("betaald", "sum"),
).reset_index()

per_klant = per_klant.merge(credit_per_klant, on="klant", how="left").fillna({"credit_excl": 0, "credit_incl": 0})
per_klant["netto_excl"] = per_klant["excl_btw"] - per_klant["credit_excl"]
per_klant["netto_incl"] = per_klant["incl_btw"] - per_klant["credit_incl"]

sort_col = "netto_excl" if toon_bedrag == "Excl. BTW" else "netto_incl"
per_klant = per_klant.sort_values(sort_col, ascending=False)

if zoek:
    per_klant = per_klant[per_klant["klant"].str.contains(zoek, case=False, na=False)]

# Grafiek top 15
top15 = per_klant.head(15).copy()
fig = px.bar(
    top15.sort_values(sort_col),
    x=sort_col,
    y="klant",
    orientation="h",
    labels={sort_col: f"Netto omzet {toon_bedrag} (€)", "klant": ""},
    color=sort_col,
    color_continuous_scale="Blues",
)
fig.update_layout(margin=dict(t=20, b=20), height=450, showlegend=False, coloraxis_showscale=False)
st.plotly_chart(fig, use_container_width=True)

# Tabel alle klanten
tabel = per_klant[["klant", "aantal_facturen", "excl_btw", "credit_excl", "netto_excl", "netto_incl", "betaald"]].copy()
tabel.columns = ["Klant", "# Facturen", "Omzet excl. BTW (€)", "Creditnota's excl. (€)", "Netto excl. BTW (€)", "Netto incl. BTW (€)", "Betaald"]
tabel["Betaald"] = tabel["Betaald"].astype(int)

st.dataframe(
    tabel,
    use_container_width=True,
    hide_index=True,
    column_config={
        "Omzet excl. BTW (€)": st.column_config.NumberColumn(format="€ %.2f"),
        "Creditnota's excl. (€)": st.column_config.NumberColumn(format="€ %.2f"),
        "Netto excl. BTW (€)": st.column_config.NumberColumn(format="€ %.2f"),
        "Netto incl. BTW (€)": st.column_config.NumberColumn(format="€ %.2f"),
    },
)