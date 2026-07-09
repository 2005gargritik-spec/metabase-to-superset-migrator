"""Small, version-tolerant Metabase API client used by the migration engine."""

from urllib.parse import urljoin
import time

import requests


class MetabaseClient:
    def __init__(self, base_url, username, password, timeout=30):
        self.url = base_url.rstrip("/")
        self.timeout = timeout
        self.session = requests.Session()
        response = self._request("POST", "api/session", json={"username": username, "password": password})
        response.raise_for_status()
        self.session.headers.update({"X-Metabase-Session": response.json()["id"]})

    def _request(self, method, path, **kwargs):
        kwargs.setdefault("timeout", self.timeout)
        response = None
        for attempt in range(3):
            response = self.session.request(method, urljoin(f"{self.url}/", path.lstrip("/")), **kwargs)
            if response.status_code not in {408, 429, 500, 502, 503, 504}:
                break
            time.sleep(0.4 * (attempt + 1))
        return response

    def _get(self, path):
        response = self._request("GET", path)
        response.raise_for_status()
        return response.json()

    def get_dashboards(self):
        return self._get("api/dashboard")

    def get_dashboard(self, dashboard_id):
        return self._get(f"api/dashboard/{dashboard_id}")

    def get_card(self, card_id):
        return self._get(f"api/card/{card_id}")

    def get_table(self, table_id):
        return self._get(f"api/table/{table_id}/query_metadata")

    def get_fields(self, table_id):
        return self.get_table(table_id)

    def get_database(self, database_id):
        return self._get(f"api/database/{database_id}")

    def resolve_card(self, dashcard):
        """Dashboards differ by Metabase version: cards may be embedded."""
        card = dashcard.get("card")
        if card and card.get("dataset_query"):
            return card
        card_id = dashcard.get("card_id") or (card or {}).get("id")
        if not card_id:
            return None  # heading/text/action dashboard component
        return self.get_card(card_id)
