"""Superset REST client with dynamic database, dataset and chart creation."""

import json
import re
import time
from urllib.parse import quote

import requests

from .dashboard_layout_builder import DashboardLayoutBuilder
from .query_context_builder import QueryContextBuilder
from .superset_field_mapper import SupersetFieldMapper


class SupersetClient:
    def __init__(self, base_url, username, password, timeout=30):
        self.base_url = base_url.rstrip("/")
        self.username = username
        self.password = password
        self.timeout = timeout
        self.session = requests.Session()
        self.access_token = None
        self.csrf_token = None
        self.query_context_builder = QueryContextBuilder()
        self.field_mapper = SupersetFieldMapper(self)
        self.dashboard_layout_builder = DashboardLayoutBuilder()

    def login(self):
        response = self.session.post(
            f"{self.base_url}/api/v1/security/login",
            json={"username": self.username, "password": self.password, "provider": "db", "refresh": True},
            timeout=self.timeout,
        )
        response.raise_for_status()
        self.access_token = response.json()["access_token"]
        response = self.session.get(
            f"{self.base_url}/api/v1/security/csrf_token/",
            headers={"Authorization": f"Bearer {self.access_token}"},
            timeout=self.timeout,
        )
        response.raise_for_status()
        self.csrf_token = response.json()["result"]

    def get_headers(self):
        if not self.access_token:
            self.login()
        return {"Authorization": f"Bearer {self.access_token}", "X-CSRFToken": self.csrf_token, "Referer": self.base_url, "Content-Type": "application/json"}

    def _request(self, method, path, **kwargs):
        kwargs.setdefault("headers", self.get_headers())
        kwargs.setdefault("timeout", self.timeout)
        response = None
        for attempt in range(3):
            response = self.session.request(method, f"{self.base_url}{path}", **kwargs)
            if response.status_code not in {408, 429, 500, 502, 503, 504}:
                break
            time.sleep(0.4 * (attempt + 1))
        if not response.ok:
            raise RuntimeError(f"Superset {method} {path} failed ({response.status_code}): {response.text[:1000]}")
        return response.json() if response.content else {}

    def _all(self, resource):
        page, items = 0, []
        while True:
            query = quote(json.dumps({"page": page, "page_size": 100}), safe="")
            payload = self._request("GET", f"/api/v1/{resource}/?q={query}")
            batch = payload.get("result", [])
            items.extend(batch)
            if len(items) >= payload.get("count", len(items)) or not batch:
                return items
            page += 1

    @staticmethod
    def _norm(value):
        return re.sub(r"[^a-z0-9]", "", str(value or "").lower())

    def resolve_database(self, metabase_database, preferred_id=None):
        """Match a Metabase DB to an already configured Superset DB.

        Metabase intentionally does not return stored database passwords, so a
        generic tool cannot safely recreate the connection from Metabase login
        credentials alone. The connection must exist in Superset; users may
        disambiguate same-named databases with ``superset_database_id``.
        """
        databases = self._all("database")
        if preferred_id is not None:
            match = next((d for d in databases if d.get("id") == preferred_id), None)
            if not match:
                raise ValueError(f"Superset database ID {preferred_id} does not exist or is inaccessible")
            return match
        name = metabase_database.get("name") or metabase_database.get("display_name")
        exact = [d for d in databases if self._norm(d.get("database_name")) == self._norm(name)]
        if len(exact) == 1:
            return exact[0]
        if not exact and len(databases) == 1:
            return databases[0]
        non_demo = [
            database for database in databases
            if self._norm(database.get("database_name")) not in {"examples", "example", "sample", "samples"}
        ]
        plain_postgres = [
            database for database in non_demo
            if self._norm(database.get("database_name")) in {"postgresql", "postgres"}
        ]
        if not exact and len(plain_postgres) == 1:
            return plain_postgres[0]
        if not exact and len(non_demo) == 1:
            return non_demo[0]
        available = [f"{d.get('id')}:{d.get('database_name')}" for d in databases]
        raise ValueError(f"Cannot uniquely map Metabase database {name!r} to Superset. Configure that database in Superset or pass superset_database_id. Available: {available}")

    def ensure_dataset(self, database_id, table_name=None, schema=None, sql=None, dataset_name=None):
        datasets = self._all("dataset")
        for dataset in datasets:
            same_db = (dataset.get("database") or {}).get("id") == database_id or dataset.get("database_id") == database_id
            if same_db and self._norm(dataset.get("table_name")) == self._norm(dataset_name or table_name) and (not schema or dataset.get("schema") == schema):
                return dataset["id"]
        payload = {"database": database_id, "table_name": dataset_name or table_name, "schema": schema or None}
        if sql:
            payload["sql"] = sql
        result = self._request("POST", "/api/v1/dataset/", json=payload)
        dataset_id = result.get("id") or result.get("result", {}).get("id")
        if not dataset_id:
            raise RuntimeError(f"Superset created a dataset without returning an ID: {result}")
        self.field_mapper.invalidate(dataset_id)
        return dataset_id

    def create_chart(self, chart_name, chart_config, dataset_id):
        config = dict(chart_config)
        config["metrics"] = self.field_mapper.build_metrics(dataset_id, config.get("metrics", []))
        for key in ("groupby", "columns"):
            config[key] = self.field_mapper.resolve_groupby(dataset_id, config.get(key, []))
        if config.get("temporal_column"):
            config["temporal_column"] = self.field_mapper.resolve_column_name(dataset_id, config["temporal_column"])
        config["adhoc_filters"] = self.field_mapper.resolve_filters(dataset_id, config.get("adhoc_filters", []))
        query_context = self.query_context_builder.build(config, dataset_id)
        payload = {
            "slice_name": chart_name,
            "viz_type": config["viz_type"],
            "datasource_id": dataset_id,
            "datasource_type": "table",
            "params": json.dumps(query_context["form_data"]),
            "query_context": json.dumps(query_context),
        }
        result = self._request("POST", "/api/v1/chart/", json=payload)
        chart_id = result.get("id") or result.get("result", {}).get("id")
        chart = self._request("GET", f"/api/v1/chart/{chart_id}").get("result", {})
        return {"id": chart_id, "uuid": chart.get("uuid"), "name": chart_name}

    def create_dashboard(self, name):
        result = self._request("POST", "/api/v1/dashboard/", json={"dashboard_title": name, "published": True})
        return result.get("id") or result.get("result", {}).get("id")

    def attach_chart_to_dashboard(self, chart_id, dashboard_id):
        chart = self._request("GET", f"/api/v1/chart/{chart_id}")["result"]
        payload = {k: chart[k] for k in ("slice_name", "viz_type", "datasource_id", "datasource_type", "params", "query_context") if k in chart}
        payload["dashboards"] = [dashboard_id]
        self._request("PUT", f"/api/v1/chart/{chart_id}", json=payload)

    def add_chart_to_dashboard(self, dashboard_id, charts, dashboard_title, parameters=None):
        layout = self.dashboard_layout_builder.build(dashboard_title, charts, parameters)
        return self._request("PUT", f"/api/v1/dashboard/{dashboard_id}", json={"published": True, **layout})
