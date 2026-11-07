import streamlit as st
from auth import require_password
from odoo_client import OdooClient

require_password()

st.set_page_config(
    page_title="Goossaert Dashboard",
    page_icon="📊",
    layout="wide",
)

st.title("Goossaert Dashboard")

# --- Verbindingsstatus ---
st.header("Odoo Verbinding")

@st.cache_resource
def get_client() -> OdooClient:
    return OdooClient()

client = get_client()

col1, col2 = st.columns([2, 1])

with col1:
    if st.button("Test verbinding", type="primary"):
        with st.spinner("Verbinden met Odoo..."):
            success, message = client.authenticate()
        if success:
            st.success(f"✅ {message}")
            version = client.get_server_version()
            if version:
                st.info(
                    f"Odoo versie: **{version.get('server_version', 'onbekend')}** "
                    f"| Serie: {version.get('server_serie', '')}"
                )
        else:
            st.error(f"❌ {message}")

with col2:
    with st.expander("Huidige configuratie"):
        st.code(
            f"URL:      {client.url or '(niet ingesteld)'}\n"
            f"Database: {client.db or '(niet ingesteld)'}\n"
            f"Gebruiker:{client.username or '(niet ingesteld)'}\n"
            f"API key:  {'***' if client.api_key else '(niet ingesteld)'}",
            language=None,
        )

st.divider()

# --- Navigatie overzicht ---
st.header("Pagina's")
st.info(
    "Voeg nieuwe pagina's toe als `.py` bestanden in de `pages/` map. "
    "Streamlit toont ze automatisch in de zijbalk."
)

pages = {
    "📈 Verkoop": "Omzet, orders en klanten uit `sale.order`",
    "🧾 Facturatie": "Facturen en betalingen uit `account.move`",
    "📦 Voorraad": "Producten en bewegingen uit `stock`",
    "👥 Klanten": "Klantenlijst uit `res.partner`",
}

for title, description in pages.items():
    with st.container(border=True):
        st.markdown(f"**{title}** — {description}")
        st.caption("Nog niet gebouwd")