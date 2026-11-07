import streamlit as st
from auth import require_password

require_password()
import pandas as pd
import plotly.graph_objects as go
from datetime import date
from odoo_client import OdooClient

st.set_page_config(page_title="Brutomarge", page_icon="📊", layout="wide")
st.title("📊 Brutomarge (70 − 60 rekeningen)")

@st.cache_resource
def get_client():
    return OdooClient()

@st.cache_data(ttl=600)
def get_account_ids():
    client = get_client()
    accounts = client.search_read("account.account", [], ["id", "code", "name"], limit=500)
    ids_6 = {a["id"]: f"{a['code']} {a['name']}" for a in accounts if str(a["code"]).startswith("60")}
    ids_7 = {a["id"]: f"{a['code']} {a['name']}" for a in accounts if str(a["code"]).startswith("70")}
    return ids_6, ids_7

client = get_client()
ids_6, ids_7 = get_account_ids()

# --- Periode filter ---
maandnamen = ["Januari","Februari","Maart","April","Mei","Juni",
              "Juli","Augustus","September","Oktober","November","December"]
huidig_jaar = date.today().year
kwartaal_maanden = {"Q1":[1,2,3],"Q2":[4,5,6],"Q3":[7,8,9],"Q4":[10,11,12]}

col_f1, col_f2, col_f3 = st.columns(3)
with col_f1:
    jaar = st.selectbox("Jaar", list(range(huidig_jaar, 2024, -1)), index=0)
with col_f2:
    periode_type = st.selectbox("Periode", ["Volledig jaar", "Kwartaal", "Maand"])
with col_f3:
    if periode_type == "Kwartaal":
        sel_kwartalen = st.multiselect("Kwartaal", ["Q1","Q2","Q3","Q4"],
            default=[f"Q{(date.today().month-1)//3+1}"] if jaar == huidig_jaar else ["Q1"])
        geselecteerde_maanden = sorted({m for q in sel_kwartalen for m in kwartaal_maanden[q]}) if sel_kwartalen else list(range(1,13))
    elif periode_type == "Maand":
        sel_maanden = st.multiselect("Maand", list(range(1,13)),
            format_func=lambda x: maandnamen[x-1],
            default=[date.today().month] if jaar == huidig_jaar else [1])
        geselecteerde_maanden = sorted(sel_maanden) if sel_maanden else list(range(1,13))
    else:
        geselecteerde_maanden = list(range(1,13))
        st.write(f"📅 {jaar}")

start_jaar = f"{jaar}-01-01"
eind_jaar = f"{jaar}-12-31"

@st.cache_data(ttl=300)
def load_lines(jaar, start, eind):
    client = get_client()
    ids_6, ids_7 = get_account_ids()
    lines_6 = client.search_read("account.move.line",
        [["account_id","in",list(ids_6.keys())],["move_id.state","=","posted"],
         ["date",">=",start],["date","<=",eind]],
        ["date","account_id","debit","credit"], limit=20000)
    lines_7 = client.search_read("account.move.line",
        [["account_id","in",list(ids_7.keys())],["move_id.state","=","posted"],
         ["date",">=",start],["date","<=",eind]],
        ["date","account_id","debit","credit"], limit=20000)
    return lines_6, lines_7

with st.spinner("Boekingslijnen ophalen..."):
    try:
        lines_6, lines_7 = load_lines(jaar, start_jaar, eind_jaar)
    except Exception as e:
        st.error(f"Fout: {e}")
        st.stop()

df6 = pd.DataFrame(lines_6)
df7 = pd.DataFrame(lines_7)

if df6.empty or df7.empty:
    st.info("Geen data gevonden.")
    st.stop()

df6["maand_nr"] = pd.to_datetime(df6["date"]).dt.month
df7["maand_nr"] = pd.to_datetime(df7["date"]).dt.month
df6["maand"] = pd.to_datetime(df6["date"]).dt.to_period("M").astype(str)
df7["maand"] = pd.to_datetime(df7["date"]).dt.to_period("M").astype(str)

# Maandfilter toepassen
df6 = df6[df6["maand_nr"].isin(geselecteerde_maanden)]
df7 = df7[df7["maand_nr"].isin(geselecteerde_maanden)]

# Kosten = debit - credit op 6x rekeningen
# Omzet = credit - debit op 7x rekeningen
kosten_totaal = df6["debit"].sum() - df6["credit"].sum()
omzet_totaal = df7["credit"].sum() - df7["debit"].sum()
brutomarge = omzet_totaal - kosten_totaal
marge_pct = brutomarge / omzet_totaal * 100 if omzet_totaal else 0

# --- KPIs ---
k1, k2, k3, k4 = st.columns(4)
k1.metric("Omzet (70)", f"€ {omzet_totaal:,.2f}")
k2.metric("Kosten (60)", f"€ {kosten_totaal:,.2f}")
k3.metric("Brutomarge", f"€ {brutomarge:,.2f}")
k4.metric("Marge %", f"{marge_pct:.1f}%")

st.divider()

# --- Maandoverzicht ---
st.subheader("Per maand")

g6 = df6.groupby("maand").apply(lambda x: (x["debit"] - x["credit"]).sum()).reset_index()
g6.columns = ["maand", "kosten"]
g7 = df7.groupby("maand").apply(lambda x: (x["credit"] - x["debit"]).sum()).reset_index()
g7.columns = ["maand", "omzet"]

monthly = g7.merge(g6, on="maand", how="outer").fillna(0).sort_values("maand")
monthly["brutomarge"] = monthly["omzet"] - monthly["kosten"]
monthly["marge_pct"] = (monthly["brutomarge"] / monthly["omzet"] * 100).where(monthly["omzet"] != 0).round(1)

fig = go.Figure()
fig.add_bar(x=monthly["maand"], y=monthly["omzet"], name="Omzet 70 (€)", marker_color="#42A5F5")
fig.add_bar(x=monthly["maand"], y=monthly["kosten"], name="Kosten 60 (€)", marker_color="#EF5350")
fig.add_scatter(x=monthly["maand"], y=monthly["brutomarge"], name="Brutomarge (€)",
    mode="lines+markers", line=dict(color="#66BB6A", width=3), marker=dict(size=8))
fig.add_scatter(x=monthly["maand"], y=monthly["marge_pct"], name="Marge %",
    mode="lines+markers", line=dict(color="#FFA726", width=2, dash="dot"), marker=dict(size=7),
    yaxis="y2")
fig.update_layout(
    barmode="group",
    margin=dict(t=20, b=20),
    legend=dict(orientation="h", yanchor="bottom", y=1.02),
    xaxis_title="",
    yaxis=dict(title="Bedrag (€)", tickformat=",.0f"),
    yaxis2=dict(title="Marge %", overlaying="y", side="right", ticksuffix="%"),
)
st.plotly_chart(fig, use_container_width=True)

# Maandtabel
maand_display = monthly[["maand","omzet","kosten","brutomarge","marge_pct"]].copy()
maand_display.columns = ["Maand","Omzet 70 (€)","Kosten 60 (€)","Brutomarge (€)","Marge %"]
st.dataframe(
    maand_display, use_container_width=True, hide_index=True,
    column_config={
        "Omzet 70 (€)": st.column_config.NumberColumn(format="€ %.2f"),
        "Kosten 60 (€)": st.column_config.NumberColumn(format="€ %.2f"),
        "Brutomarge (€)": st.column_config.NumberColumn(format="€ %.2f"),
        "Marge %": st.column_config.NumberColumn(format="%.1f %%"),
    },
)

st.divider()

# --- Detail per rekeninggroep ---
with st.expander("Detail per rekening"):
    tab6, tab7 = st.tabs(["60 Kosten", "70 Omzet"])

    with tab6:
        df6["rekening"] = df6["account_id"].apply(lambda x: x[1] if isinstance(x, list) else str(x))
        detail6 = df6.groupby("rekening").apply(lambda x: (x["debit"]-x["credit"]).sum()).reset_index()
        detail6.columns = ["Rekening","Bedrag (€)"]
        detail6 = detail6[detail6["Bedrag (€)"] != 0].sort_values("Bedrag (€)", ascending=False)
        st.dataframe(detail6, use_container_width=True, hide_index=True,
            column_config={"Bedrag (€)": st.column_config.NumberColumn(format="€ %.2f")})

    with tab7:
        df7["rekening"] = df7["account_id"].apply(lambda x: x[1] if isinstance(x, list) else str(x))
        detail7 = df7.groupby("rekening").apply(lambda x: (x["credit"]-x["debit"]).sum()).reset_index()
        detail7.columns = ["Rekening","Bedrag (€)"]
        detail7 = detail7[detail7["Bedrag (€)"] != 0].sort_values("Bedrag (€)", ascending=False)
        st.dataframe(detail7, use_container_width=True, hide_index=True,
            column_config={"Bedrag (€)": st.column_config.NumberColumn(format="€ %.2f")})
