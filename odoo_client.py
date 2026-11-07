import xmlrpc.client
import os
from functools import cached_property
from dotenv import load_dotenv

load_dotenv()


def _secret(key: str) -> str:
    """Reads from st.secrets (Streamlit Cloud) with fallback to os.getenv (.env locally)."""
    try:
        import streamlit as st
        return st.secrets.get(key, os.getenv(key, ""))
    except Exception:
        return os.getenv(key, "")


class OdooClient:
    def __init__(self):
        self.url = _secret("ODOO_URL").rstrip("/")
        self.db = _secret("ODOO_DB")
        self.username = _secret("ODOO_USERNAME")
        self.api_key = _secret("ODOO_API_KEY")
        self._uid = None

    @cached_property
    def _common(self):
        return xmlrpc.client.ServerProxy(f"{self.url}/xmlrpc/2/common")

    @cached_property
    def _models(self):
        return xmlrpc.client.ServerProxy(f"{self.url}/xmlrpc/2/object")

    def authenticate(self) -> tuple[bool, str]:
        if not all([self.url, self.db, self.username, self.api_key]):
            return False, "Ontbrekende configuratie: controleer .env bestand"
        try:
            uid = self._common.authenticate(self.db, self.username, self.api_key, {})
            if uid:
                self._uid = uid
                return True, f"Verbonden als gebruiker ID {uid}"
            return False, "Authenticatie mislukt: controleer gebruikersnaam en API key"
        except Exception as e:
            return False, f"Verbindingsfout: {e}"

    def get_server_version(self) -> dict:
        try:
            return self._common.version()
        except Exception:
            return {}

    @property
    def uid(self) -> int:
        if self._uid is None:
            success, _ = self.authenticate()
            if not success:
                raise RuntimeError("Niet geauthenticeerd bij Odoo")
        return self._uid

    def search_read(
        self,
        model: str,
        domain: list = None,
        fields: list = None,
        limit: int = 100,
        order: str = None,
        context: dict = None,
    ) -> list[dict]:
        kwargs = {"limit": limit, "context": context or {"lang": "nl_BE"}}
        if fields:
            kwargs["fields"] = fields
        if order:
            kwargs["order"] = order
        return self._models.execute_kw(
            self.db, self.uid, self.api_key,
            model, "search_read",
            [domain or []],
            kwargs,
        )

    def search_count(self, model: str, domain: list = None) -> int:
        return self._models.execute_kw(
            self.db, self.uid, self.api_key,
            model, "search_count",
            [domain or []],
        )

    def read(self, model: str, ids: list[int], fields: list = None) -> list[dict]:
        kwargs = {}
        if fields:
            kwargs["fields"] = fields
        return self._models.execute_kw(
            self.db, self.uid, self.api_key,
            model, "read",
            [ids],
            kwargs,
        )