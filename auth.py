import os
import streamlit as st
from dotenv import load_dotenv

load_dotenv()


def _get_password() -> str:
    try:
        return st.secrets.get("APP_PASSWORD", os.getenv("APP_PASSWORD", ""))
    except Exception:
        return os.getenv("APP_PASSWORD", "")


def require_password() -> None:
    if st.session_state.get("authenticated"):
        return

    st.set_page_config(page_title="Goossaert Dashboard", page_icon="🔒", layout="centered")
    st.title("🔒 Goossaert Dashboard")
    st.caption("Voer het wachtwoord in om toegang te krijgen.")

    password = st.text_input("Wachtwoord", type="password", label_visibility="collapsed")
    if st.button("Inloggen", type="primary", use_container_width=True):
        expected = _get_password()
        if not expected:
            st.error("APP_PASSWORD is niet ingesteld in secrets.")
        elif password == expected:
            st.session_state["authenticated"] = True
            st.rerun()
        else:
            st.error("Onjuist wachtwoord.")

    st.stop()
