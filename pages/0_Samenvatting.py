import streamlit as st
from auth import require_password

require_password()
import pandas as pd
import plotly.graph_objects as go
from datetime import date
from odoo_client import OdooClient

st.set_page_config(page_title="Management Samenvatting", page_icon="🏠", layout="wide")
st.title("🏠 Management Samenvatting")

today = date.today()
maand_start = today.replace(day=1)
jaar_start = today.replace(month=1, day=1)
maand_naam = ["januari","februari","maart","april","mei","juni",
              "juli","augustus","september","oktober","november","december"][today.month - 1]

st.caption(f"Gegevens tot en met {today.strftime('%d/%m/%Y')} · YTD = 1 januari {today.year} t/m vandaag")

@st.cache_resource
def get_client():
    return OdooClient()

client = get_client()

@st.cache_data(ttl=300)
def load_all(jaar_start_str, maand_start_str, today_str):
    c = get_client()

    # Orders voor verkopergrafiek en pijplijn
    orders = c.search_read("sale.order",
        [["state","in",["sale","done","sale_validation"]],
         ["date_order",">=",jaar_start_str],["date_order","<=",today_str]],
        ["date_order","amount_total","user_id"], limit=5000)

    # Open offertes (pijplijn)
    pipeline = c.search_read("sale.order",
        [["state","in",["draft","sent"]]],
        ["amount_total","user_id"], limit=5000)

    # Gefactureerde omzet YTD (excl. Goossaert BV)
    facturen = c.search_read("account.move",
        [["move_type","=","out_invoice"],["state","=","posted"],
         ["invoice_date",">=",jaar_start_str],["invoice_date","<=",today_str],
         ["partner_id","!=",1]],
        ["invoice_date","amount_untaxed","amount_total","partner_id"], limit=5000)

    # Openstaande facturen
    open_inv = c.search_read("account.move",
        [["move_type","=","out_invoice"],["state","=","posted"],
         ["payment_state","in",["not_paid","partial"]],["partner_id","!=",1]],
        ["amount_residual","invoice_date_due","partner_id"], limit=5000)

    # Boekingslijnen 60/70 voor brutomarge YTD
    accounts = c.search_read("account.account", [], ["id","code"], limit=500)
    ids_60 = [a["id"] for a in accounts if str(a["code"]).startswith("60")]
    ids_70 = [a["id"] for a in accounts if str(a["code"]).startswith("70")]

    lines_60 = c.search_read("account.move.line",
        [["account_id","in",ids_60],["move_id.state","=","posted"],
         ["date",">=",jaar_start_str],["date","<=",today_str]],
        ["date","debit","credit"], limit=20000)
    lines_70 = c.search_read("account.move.line",
        [["account_id","in",ids_70],["move_id.state","=","posted"],
         ["date",">=",jaar_start_str],["date","<=",today_str]],
        ["date","debit","credit"], limit=20000)

    return orders, pipeline, facturen, open_inv, lines_60, lines_70

with st.spinner("Data ophalen..."):
    try:
        orders, pipeline, facturen, open_inv, lines_60, lines_70 = load_all(
            str(jaar_start), str(maand_start), str(today))
    except Exception as e:
        st.error(f"Fout: {e}")
        st.stop()

# --- Dataframes ---
df_o = pd.DataFrame(orders)
df_o["datum"] = pd.to_datetime(df_o["date_order"])
df_o["maand"] = df_o["datum"].dt.to_period("M").astype(str)
df_o["verkoper"] = df_o["user_id"].apply(lambda x: x[1] if isinstance(x, list) else "Onbekend")
df_o_maand = df_o[df_o["datum"].dt.date >= maand_start]

df_p = pd.DataFrame(pipeline)

df_f = pd.DataFrame(facturen)
df_f["klant"] = df_f["partner_id"].apply(lambda x: x[1] if isinstance(x, list) else "")
df_f["maand"] = pd.to_datetime(df_f["invoice_date"]).dt.to_period("M").astype(str)

df_inv = pd.DataFrame(open_inv)
df_inv["vervallen"] = pd.to_datetime(df_inv["invoice_date_due"]) < pd.Timestamp(today)

df60 = pd.DataFrame(lines_60)
df70 = pd.DataFrame(lines_70)
df60["maand"] = pd.to_datetime(df60["date"]).dt.to_period("M").astype(str)
df70["maand"] = pd.to_datetime(df70["date"]).dt.to_period("M").astype(str)

kosten_ytd = df60["debit"].sum() - df60["credit"].sum()
omzet_70_ytd = df70["credit"].sum() - df70["debit"].sum()
marge_ytd = (omzet_70_ytd - kosten_ytd) / omzet_70_ytd * 100 if omzet_70_ytd else 0

# Brutomarge deze maand
df60_m = df60[df60["maand"] == today.strftime("%Y-%m")]
df70_m = df70[df70["maand"] == today.strftime("%Y-%m")]
kosten_m = df60_m["debit"].sum() - df60_m["credit"].sum()
omzet_70_m = df70_m["credit"].sum() - df70_m["debit"].sum()
marge_m = (omzet_70_m - kosten_m) / omzet_70_m * 100 if omzet_70_m else 0

# --- KPI rij 1: YTD ---
st.subheader(f"YTD — 1 januari t/m {today.strftime('%d %B %Y')}")
k1, k2, k3, k4, k5 = st.columns(5)
k1.metric("Omzet YTD", f"€ {omzet_70_ytd:,.0f}", delta="70-rekeningen excl. BTW")
k2.metric("Brutomarge YTD", f"€ {omzet_70_ytd - kosten_ytd:,.0f}", delta=f"{marge_ytd:.1f}%")
k3.metric("Brutomarge % YTD", f"{marge_ytd:.1f}%")
k4.metric("Openstaande facturen", f"€ {df_inv['amount_residual'].sum():,.0f}",
          delta=f"{len(df_inv)} facturen")
k5.metric("Waarvan vervallen ⚠️", f"€ {df_inv[df_inv['vervallen']]['amount_residual'].sum():,.0f}",
          delta=f"{df_inv['vervallen'].sum()} facturen", delta_color="inverse")

st.divider()

# --- KPI rij 2: deze maand ---
st.subheader(f"Deze maand — {maand_naam.capitalize()} {today.year}")
m1, m2, m3, m4 = st.columns(4)
m1.metric("Omzet", f"€ {omzet_70_m:,.0f}", delta="70-rekeningen excl. BTW")
m2.metric("Brutomarge", f"€ {omzet_70_m - kosten_m:,.0f}", delta=f"{marge_m:.1f}%")
m3.metric("Brutomarge %", f"{marge_m:.1f}%")
m4.metric("Open pijplijn", f"€ {df_p['amount_total'].sum():,.0f}",
          delta=f"{len(df_p)} open offertes")

st.divider()

# --- Maanddata voorbereiden ---
g60 = df60.groupby("maand").apply(lambda x: (x["debit"]-x["credit"]).sum()).reset_index()
g60.columns = ["maand","kosten"]
g70 = df70.groupby("maand").apply(lambda x: (x["credit"]-x["debit"]).sum()).reset_index()
g70.columns = ["maand","omzet"]
mg = g70.merge(g60, on="maand", how="outer").fillna(0).sort_values("maand")
mg["marge_pct"] = ((mg["omzet"] - mg["kosten"]) / mg["omzet"] * 100).where(mg["omzet"] > 0).round(1)

# --- Grafiek 1: Omzet + Marge% gecombineerd ---
st.subheader("Omzet & Brutomarge per maand")
fig1 = go.Figure()
fig1.add_bar(
    x=mg["maand"], y=mg["omzet"],
    name="Omzet (€)", marker_color="#1E88E5",
    hovertemplate="<b>%{x}</b><br>Omzet: € %{y:,.0f}<extra></extra>",
)
fig1.add_bar(
    x=mg["maand"], y=mg["kosten"],
    name="Kosten 60 (€)", marker_color="#EF5350",
    hovertemplate="<b>%{x}</b><br>Kosten: € %{y:,.0f}<extra></extra>",
)
fig1.add_scatter(
    x=mg["maand"], y=mg["marge_pct"],
    name="Marge %", mode="lines+markers+text",
    line=dict(color="#43A047", width=3),
    marker=dict(size=9, color="#43A047", line=dict(color="white", width=2)),
    text=mg["marge_pct"].apply(lambda x: f"{x:.0f}%" if pd.notna(x) else ""),
    textposition="top center", textfont=dict(size=11, color="#43A047"),
    hovertemplate="<b>%{x}</b><br>Marge: %{y:.1f}%<extra></extra>",
    yaxis="y2",
)
fig1.add_hline(
    y=marge_ytd, yref="y2", line_dash="dot", line_color="#FB8C00", line_width=2,
    annotation_text=f"Gem. {marge_ytd:.1f}%", annotation_font_color="#FB8C00",
    annotation_position="top left",
)
fig1.update_layout(
    barmode="group",
    height=380,
    margin=dict(t=30, b=20, l=10, r=60),
    legend=dict(orientation="h", yanchor="bottom", y=1.02, x=0),
    yaxis=dict(title="Bedrag (€)", tickformat=",.0f", gridcolor="#f0f0f0"),
    yaxis2=dict(title="Marge %", overlaying="y", side="right", ticksuffix="%",
                range=[0, max(mg["marge_pct"].dropna().max() * 1.3, 60)], showgrid=False),
    plot_bgcolor="white", paper_bgcolor="white",
    xaxis=dict(showgrid=False),
)
st.plotly_chart(fig1, use_container_width=True)

st.divider()

# --- Grafiek 2: Verkoper + Top klanten ---
col_v, col_k = st.columns(2)

with col_v:
    st.subheader("Omzet per verkoper (YTD)")
    verk = df_o.groupby("verkoper")["amount_total"].sum().sort_values(ascending=True).reset_index()
    kleuren = ["#90CAF9","#64B5F6","#42A5F5","#2196F3","#1E88E5",
               "#1976D2","#1565C0","#0D47A1","#0A2A6E"][:len(verk)]
    fig2 = go.Figure()
    fig2.add_bar(
        x=verk["amount_total"], y=verk["verkoper"],
        orientation="h",
        marker_color=kleuren,
        text=verk["amount_total"].apply(lambda x: f"€ {x:,.0f}"),
        textposition="outside",
        textfont=dict(size=11),
        hovertemplate="<b>%{y}</b><br>€ %{x:,.0f}<extra></extra>",
    )
    fig2.update_layout(
        height=360, margin=dict(t=20, b=20, l=10, r=120),
        xaxis=dict(tickformat=",.0f", showgrid=True, gridcolor="#f0f0f0", title=""),
        yaxis=dict(showgrid=False),
        plot_bgcolor="white", paper_bgcolor="white",
        showlegend=False,
    )
    st.plotly_chart(fig2, use_container_width=True)

with col_k:
    st.subheader("Top 10 klanten op factuuromzet (YTD)")
    top_k = df_f.groupby("klant")["amount_untaxed"].sum().sort_values(ascending=True).tail(10).reset_index()
    top_k["klant_kort"] = top_k["klant"].str[:40]
    fig3 = go.Figure()
    fig3.add_bar(
        x=top_k["amount_untaxed"], y=top_k["klant_kort"],
        orientation="h",
        marker=dict(color=top_k["amount_untaxed"], colorscale="Blues", showscale=False),
        text=top_k["amount_untaxed"].apply(lambda x: f"€ {x:,.0f}"),
        textposition="outside",
        textfont=dict(size=11),
        hovertemplate="<b>%{y}</b><br>€ %{x:,.0f}<extra></extra>",
    )
    fig3.update_layout(
        height=360, margin=dict(t=20, b=20, l=10, r=120),
        xaxis=dict(tickformat=",.0f", showgrid=True, gridcolor="#f0f0f0", title=""),
        yaxis=dict(showgrid=False),
        plot_bgcolor="white", paper_bgcolor="white",
        showlegend=False,
    )
    st.plotly_chart(fig3, use_container_width=True)
