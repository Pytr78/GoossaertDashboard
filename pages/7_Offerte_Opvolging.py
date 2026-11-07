import streamlit as st
from auth import require_password

require_password()
import pandas as pd
import plotly.graph_objects as go
from odoo_client import OdooClient

st.set_page_config(page_title="Offerte Opvolging", page_icon="🔔", layout="wide")
st.title("🔔 Offerte Opvolging")

st.info(
    "Alle open offertes (concept + gezonden) ingedeeld op urgentie. "
    "**Dringend** = geen wijziging in > 30 dagen en geen follow-up gepland. "
    "**Opvolgen** = 7–30 dagen stilstand. "
    "**Recent** = gewijzigd in de afgelopen 7 dagen. "
    "**Actief** = follow-up activiteit gepland in Odoo."
)

URGENTIE_VOLGORDE = ["Dringend", "Opvolgen", "Recent", "Actief"]
URGENTIE_KLEUREN = {
    "Actief":   "#4CAF50",
    "Recent":   "#2196F3",
    "Opvolgen": "#FF9800",
    "Dringend": "#F44336",
}

@st.cache_resource
def get_client():
    return OdooClient()

client = get_client()

with st.spinner("Data ophalen..."):
    try:
        records = client.search_read(
            "sale.order",
            [["state", "in", ["draft", "sent"]]],
            ["name", "create_date", "write_date", "user_id", "amount_total",
             "partner_id", "state", "activity_ids", "activity_state"],
            limit=5000,
            order="amount_total desc",
        )
    except Exception as e:
        st.error(f"Fout bij ophalen data: {e}")
        st.stop()

df = pd.DataFrame(records)
if df.empty:
    st.success("Geen open offertes gevonden.")
    st.stop()

df["create_date"] = pd.to_datetime(df["create_date"])
df["write_date"] = pd.to_datetime(df["write_date"])
now = pd.Timestamp.now()
df["open_dagen"] = (now - df["create_date"]).dt.total_seconds() / 86400
df["stilstand_dagen"] = (now - df["write_date"]).dt.total_seconds() / 86400
df["verkoper"] = df["user_id"].apply(lambda x: x[1] if isinstance(x, list) else "Onbekend")
df["klant"] = df["partner_id"].apply(lambda x: x[1] if isinstance(x, list) else "Onbekend")
df["heeft_activiteit"] = df["activity_ids"].apply(lambda x: len(x) > 0 if isinstance(x, list) else False)

def bepaal_urgentie(row):
    if row["heeft_activiteit"]:
        return "Actief"
    if row["stilstand_dagen"] <= 7:
        return "Recent"
    if row["stilstand_dagen"] <= 30:
        return "Opvolgen"
    return "Dringend"

df["urgentie"] = df.apply(bepaal_urgentie, axis=1)

# --- Filters ---
alle_verkopers = sorted(df["verkoper"].unique())
sel_verkopers = st.multiselect("Verkoper(s)", alle_verkopers, placeholder="Alle verkopers")
if sel_verkopers:
    df = df[df["verkoper"].isin(sel_verkopers)]

# --- KPIs ---
k1, k2, k3, k4 = st.columns(4)
n_dringend = int((df["urgentie"] == "Dringend").sum())
w_dringend = df[df["urgentie"] == "Dringend"]["amount_total"].sum()
n_actief = int(df["heeft_activiteit"].sum())

k1.metric("Open offertes", len(df))
k2.metric("Totale waarde", f"€ {df['amount_total'].sum():,.0f}")
k3.metric("Dringend (> 30d stilstand)", n_dringend,
          delta=f"€ {w_dringend:,.0f}", delta_color="inverse")
k4.metric("Met geplande follow-up", n_actief)

st.divider()

# --- Grafiek: verdeling per verkoper (gestapeld op waarde) ---
st.subheader("Openstaande waarde per verkoper")

verk_totaal = df.groupby("verkoper")["amount_total"].sum().sort_values(ascending=False)
verk_volgorde = verk_totaal.index.tolist()
verk_data = df.groupby(["verkoper", "urgentie"])["amount_total"].sum().reset_index()

fig = go.Figure()
for cat in URGENTIE_VOLGORDE:
    sub = (
        verk_data[verk_data["urgentie"] == cat]
        .set_index("verkoper")
        .reindex(verk_volgorde)
        .fillna(0)
        .reset_index()
    )
    fig.add_bar(
        x=sub["verkoper"],
        y=sub["amount_total"],
        name=cat,
        marker_color=URGENTIE_KLEUREN[cat],
    )

fig.update_layout(
    barmode="stack",
    margin=dict(t=20, b=20),
    legend=dict(orientation="h", yanchor="bottom", y=1.02),
    yaxis=dict(title="Waarde (€)", tickformat=",.0f"),
    xaxis_title="",
)
st.plotly_chart(fig, use_container_width=True)

st.divider()

# --- Actielijst ---
st.subheader("Actielijst")

col_f1, col_f2 = st.columns([2, 1])
with col_f1:
    sel_urgentie = st.multiselect(
        "Urgentie",
        URGENTIE_VOLGORDE,
        default=["Dringend", "Opvolgen"],
    )
with col_f2:
    min_bedrag = st.number_input("Minimum bedrag (€)", min_value=0, value=0, step=100)

df_tabel = df.copy()
if sel_urgentie:
    df_tabel = df_tabel[df_tabel["urgentie"].isin(sel_urgentie)]
if min_bedrag > 0:
    df_tabel = df_tabel[df_tabel["amount_total"] >= min_bedrag]

df_tabel = df_tabel.sort_values(
    ["urgentie", "amount_total"],
    ascending=[True, False],
    key=lambda col: col.map(dict(zip(URGENTIE_VOLGORDE, range(len(URGENTIE_VOLGORDE))))) if col.name == "urgentie" else col,
)

weergave = pd.DataFrame({
    "Urgentie":      df_tabel["urgentie"].values,
    "Offerte":       df_tabel["name"].values,
    "Klant":         df_tabel["klant"].values,
    "Verkoper":      df_tabel["verkoper"].values,
    "Bedrag (€)":    df_tabel["amount_total"].values,
    "Open (d)":      df_tabel["open_dagen"].round(0).astype(int).values,
    "Stilstand (d)": df_tabel["stilstand_dagen"].round(0).astype(int).values,
    "Status":        df_tabel["state"].map({"draft": "Concept", "sent": "Gezonden"}).values,
    "Follow-up":     df_tabel["heeft_activiteit"].map({True: "✓", False: "—"}).values,
})

st.dataframe(
    weergave,
    use_container_width=True,
    hide_index=True,
    column_config={
        "Bedrag (€)": st.column_config.NumberColumn(format="€ %.0f"),
        "Open (d)":      st.column_config.NumberColumn(format="%d d"),
        "Stilstand (d)": st.column_config.NumberColumn(format="%d d"),
    },
)
st.caption(f"{len(df_tabel)} offertes · Totale waarde: €{df_tabel['amount_total'].sum():,.0f}")
