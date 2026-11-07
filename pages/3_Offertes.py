import streamlit as st
from auth import require_password

require_password()
import pandas as pd
import plotly.graph_objects as go
from datetime import date
from odoo_client import OdooClient

st.set_page_config(page_title="Offertes & Bevestigingen", page_icon="📋", layout="wide")
st.title("📋 Offertes & Bevestigingen")

st.info(
    "**Gemaakt** = alle offertes aangemaakt op die dag (op basis van aanmaakdatum) · "
    "**Bevestigd** = alle orders bevestigd op die dag (op basis van bevestigingsdatum) — dit zijn onafhankelijke cijfers."
)

@st.cache_resource
def get_client():
    return OdooClient()

client = get_client()

col_f1, col_f2 = st.columns(2)
with col_f1:
    start = st.date_input("Van", value=date.today().replace(month=1, day=1))
with col_f2:
    end = st.date_input("Tot", value=date.today())

if start > end:
    st.error("Begindatum mag niet na einddatum liggen.")
    st.stop()

with st.spinner("Data ophalen..."):
    try:
        records_gemaakt = client.search_read(
            "sale.order",
            [["create_date", ">=", str(start)], ["create_date", "<=", str(end) + " 23:59:59"]],
            ["create_date", "amount_total", "user_id", "state"],
            limit=5000,
        )
        records_bevestigd = client.search_read(
            "sale.order",
            [
                ["date_order", ">=", str(start)],
                ["date_order", "<=", str(end) + " 23:59:59"],
                ["state", "in", ["sale", "done"]],
            ],
            ["date_order", "amount_total", "user_id"],
            limit=5000,
        )
    except Exception as e:
        st.error(f"Fout bij ophalen data: {e}")
        st.stop()

df_g = pd.DataFrame(records_gemaakt)
df_g["datum"] = pd.to_datetime(df_g["create_date"]).dt.date
df_g["verkoper"] = df_g["user_id"].apply(lambda x: x[1] if isinstance(x, list) else "Onbekend")
df_g["bevestigd"] = df_g["state"].isin(["sale", "done", "sale_validation"])
df_g["geannuleerd"] = df_g["state"] == "cancel"
df_g["open"] = df_g["state"].isin(["draft", "sent"])

df_b = pd.DataFrame(records_bevestigd)
df_b["datum"] = pd.to_datetime(df_b["date_order"]).dt.date
df_b["verkoper"] = df_b["user_id"].apply(lambda x: x[1] if isinstance(x, list) else "Onbekend")

# --- Verkopersfilter ---
alle_verkopers = sorted(set(df_g["verkoper"].unique()) | set(df_b["verkoper"].unique()))
sel_verkopers = st.multiselect("Verkoper(s)", alle_verkopers, placeholder="Alle verkopers")
if sel_verkopers:
    df_g = df_g[df_g["verkoper"].isin(sel_verkopers)]
    df_b = df_b[df_b["verkoper"].isin(sel_verkopers)]

# Groepeer per dag
gemaakt_dag = df_g.groupby("datum").agg(
    aantal_gemaakt=("id", "count"),
    omzet_gemaakt=("amount_total", "sum"),
).reset_index()

bevestigd_dag = df_b.groupby("datum").agg(
    aantal_bevestigd=("id", "count"),
    omzet_bevestigd=("amount_total", "sum"),
).reset_index()

daily = pd.merge(gemaakt_dag, bevestigd_dag, on="datum", how="outer").fillna(0).sort_values("datum")
daily["datum_dt"] = pd.to_datetime(daily["datum"])
daily["conversie_bedrag_pct"] = (daily["omzet_bevestigd"] / daily["omzet_gemaakt"] * 100).where(daily["omzet_gemaakt"] > 0).round(1)
daily["conversie_aantal_pct"] = (daily["aantal_bevestigd"] / daily["aantal_gemaakt"] * 100).where(daily["aantal_gemaakt"] > 0).round(1)

# Groepeer per maand
df_g["maand"] = pd.to_datetime(df_g["create_date"]).dt.to_period("M").astype(str)
df_b["maand"] = pd.to_datetime(df_b["date_order"]).dt.to_period("M").astype(str)

gemaakt_maand = df_g.groupby("maand").agg(aantal_gemaakt=("id","count"), omzet_gemaakt=("amount_total","sum")).reset_index()
bevestigd_maand = df_b.groupby("maand").agg(aantal_bevestigd=("id","count"), omzet_bevestigd=("amount_total","sum")).reset_index()
monthly = pd.merge(gemaakt_maand, bevestigd_maand, on="maand", how="outer").fillna(0).sort_values("maand")
monthly["conversie_bedrag_pct"] = (monthly["omzet_bevestigd"] / monthly["omzet_gemaakt"] * 100).where(monthly["omzet_gemaakt"] > 0).round(1)
monthly["conversie_aantal_pct"] = (monthly["aantal_bevestigd"] / monthly["aantal_gemaakt"] * 100).where(monthly["aantal_gemaakt"] > 0).round(1)

# --- KPIs ---
k1, k2, k3, k4 = st.columns(4)
totaal_gemaakt = df_g["amount_total"].sum()
totaal_bevestigd = df_b["amount_total"].sum()
aantal_gemaakt = int(df_g["id"].count())
aantal_bevestigd = int(df_b["id"].count())
conv_bedrag = totaal_bevestigd / totaal_gemaakt * 100 if totaal_gemaakt else 0
conv_aantal = aantal_bevestigd / aantal_gemaakt * 100 if aantal_gemaakt else 0
k1.metric("Offertes gemaakt", aantal_gemaakt)
k2.metric("Omzet gemaakt", f"€ {totaal_gemaakt:,.0f}")
k3.metric("Orders bevestigd", aantal_bevestigd, delta=f"{conv_aantal:.1f}% op aantal")
k4.metric("Omzet bevestigd", f"€ {totaal_bevestigd:,.0f}", delta=f"{conv_bedrag:.1f}% op bedrag")

st.divider()

# --- Grafiek per dag: omzet ---
st.subheader("Omzet per dag (€)")
fig_dag = go.Figure()
fig_dag.add_bar(x=daily["datum_dt"], y=daily["omzet_gemaakt"], name="Gemaakt (€)", marker_color="#90CAF9")
fig_dag.add_bar(x=daily["datum_dt"], y=daily["omzet_bevestigd"], name="Bevestigd (€)", marker_color="#1976D2")
fig_dag.update_layout(
    barmode="group",
    margin=dict(t=20, b=20),
    legend=dict(orientation="h", yanchor="bottom", y=1.02),
    xaxis_title="",
    yaxis=dict(title="Omzet (€)", tickformat=",.0f"),
)
st.plotly_chart(fig_dag, use_container_width=True)

# Dagtabel
with st.expander("Dagtabel bekijken"):
    dag_display = daily[["datum", "aantal_gemaakt", "omzet_gemaakt", "aantal_bevestigd", "omzet_bevestigd", "conversie_aantal_pct", "conversie_bedrag_pct"]].copy()
    dag_display["datum"] = pd.to_datetime(dag_display["datum"]).dt.strftime("%d/%m/%Y")
    dag_display.columns = ["Datum", "# Gemaakt", "Omzet gemaakt (€)", "# Bevestigd", "Omzet bevestigd (€)", "Conversie % aantal", "Conversie % bedrag"]
    st.dataframe(
        dag_display, use_container_width=True, hide_index=True,
        column_config={
            "Omzet gemaakt (€)": st.column_config.NumberColumn(format="€ %.2f"),
            "Omzet bevestigd (€)": st.column_config.NumberColumn(format="€ %.2f"),
            "Conversie % aantal": st.column_config.NumberColumn(format="%.1f %%"),
            "Conversie % bedrag": st.column_config.NumberColumn(format="%.1f %%"),
        },
    )

st.divider()

# --- Grafiek per maand: omzet ---
st.subheader("Omzet per maand (€)")
fig_maand = go.Figure()
fig_maand.add_bar(x=monthly["maand"], y=monthly["omzet_gemaakt"], name="Gemaakt (€)", marker_color="#90CAF9")
fig_maand.add_bar(x=monthly["maand"], y=monthly["omzet_bevestigd"], name="Bevestigd (€)", marker_color="#1976D2")
fig_maand.add_scatter(
    x=monthly["maand"], y=monthly["conversie_bedrag_pct"],
    name="Conversie % bedrag", mode="lines+markers",
    marker=dict(size=8), line=dict(color="#F57C00", width=2),
    yaxis="y2",
)
fig_maand.add_scatter(
    x=monthly["maand"], y=monthly["conversie_aantal_pct"],
    name="Conversie % aantal", mode="lines+markers",
    marker=dict(size=8), line=dict(color="#7B1FA2", width=2, dash="dot"),
    yaxis="y2",
)
fig_maand.update_layout(
    barmode="group",
    margin=dict(t=20, b=20),
    legend=dict(orientation="h", yanchor="bottom", y=1.02),
    xaxis_title="",
    yaxis=dict(title="Omzet (€)", tickformat=",.0f"),
    yaxis2=dict(title="Conversie %", overlaying="y", side="right", range=[0, 150], ticksuffix="%"),
)
st.plotly_chart(fig_maand, use_container_width=True)

# Maandtabel
maand_display = monthly[["maand", "aantal_gemaakt", "omzet_gemaakt", "aantal_bevestigd", "omzet_bevestigd", "conversie_aantal_pct", "conversie_bedrag_pct"]].copy()
maand_display.columns = ["Maand", "# Gemaakt", "Omzet gemaakt (€)", "# Bevestigd", "Omzet bevestigd (€)", "Conversie % aantal", "Conversie % bedrag"]
st.dataframe(
    maand_display, use_container_width=True, hide_index=True,
    column_config={
        "Omzet gemaakt (€)": st.column_config.NumberColumn(format="€ %.2f"),
        "Omzet bevestigd (€)": st.column_config.NumberColumn(format="€ %.2f"),
        "Conversie % aantal": st.column_config.NumberColumn(format="%.1f %%"),
        "Conversie % bedrag": st.column_config.NumberColumn(format="%.1f %%"),
    },
)

st.divider()

# --- Cohort: uitkomst per aanmaakmaand ---
st.subheader("Cohort: uitkomst van offertes per aanmaakmaand")
st.caption("Per aanmaakmaand de huidige status van alle offertes — onafhankelijk van wanneer ze bevestigd werden.")

lopende_maand = date.today().strftime("%Y-%m")

df_g["maand_aanmaak"] = pd.to_datetime(df_g["create_date"]).dt.to_period("M").astype(str)

cohort = df_g.groupby("maand_aanmaak").agg(
    gemaakt=("id", "count"),
    bevestigd=("bevestigd", "sum"),
    geannuleerd=("geannuleerd", "sum"),
    open=("open", "sum"),
    omzet_gemaakt=("amount_total", "sum"),
    omzet_bevestigd=("amount_total", lambda x: x[df_g.loc[x.index, "bevestigd"]].sum()),
).reset_index()

cohort["conv_aantal_pct"] = (cohort["bevestigd"] / cohort["gemaakt"] * 100).round(1)
cohort["conv_bedrag_pct"] = (cohort["omzet_bevestigd"] / cohort["omzet_gemaakt"] * 100).round(1)
cohort["lopend"] = cohort["maand_aanmaak"] == lopende_maand
cohort["Maand"] = cohort.apply(
    lambda r: f"⚠️ {r['maand_aanmaak']} (lopend)" if r["lopend"] else r["maand_aanmaak"], axis=1
)

cohort_display = cohort[["Maand", "gemaakt", "bevestigd", "open", "geannuleerd", "conv_aantal_pct", "omzet_gemaakt", "omzet_bevestigd", "conv_bedrag_pct"]].copy()
cohort_display.columns = ["Maand", "Gemaakt", "Bevestigd", "Nog open", "Geannuleerd", "Conv. % aantal", "Omzet gemaakt (€)", "Omzet bevestigd (€)", "Conv. % bedrag"]

st.dataframe(
    cohort_display,
    use_container_width=True,
    hide_index=True,
    column_config={
        "Conv. % aantal": st.column_config.NumberColumn(format="%.1f %%"),
        "Conv. % bedrag": st.column_config.NumberColumn(format="%.1f %%"),
        "Omzet gemaakt (€)": st.column_config.NumberColumn(format="€ %.0f"),
        "Omzet bevestigd (€)": st.column_config.NumberColumn(format="€ %.0f"),
    },
)
