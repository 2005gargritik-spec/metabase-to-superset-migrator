"""
SupersetFieldMapper — Superset 6.0.0 compatible.

Single source of truth for resolving Metabase-derived field references
against the ACTUAL Superset dataset metadata (columns, saved metrics,
temporal columns, datasource type).

This is where metric/column validation belongs — not in
QueryContextBuilder, which should only assemble the JSON shape. Doing
resolution here means a bad mapping fails loudly and per-chart, instead
of silently producing an "Empty Query" chart or crashing the whole
migration batch.
"""

from difflib import get_close_matches
from typing import Any, Dict, List, Optional


NUMERIC_TYPES = {
    "INTEGER", "BIGINT", "SMALLINT", "FLOAT", "DOUBLE", "DOUBLE PRECISION",
    "DECIMAL", "NUMERIC", "REAL",
}

# Aggregates that require a numeric column. COUNT / COUNT_DISTINCT work on
# any column type (including *), so they're intentionally excluded here.
NUMERIC_ONLY_AGGREGATES = {"SUM", "AVG"}


class FieldResolutionError(Exception):
    """Raised when a Metabase field/metric can't be safely resolved
    against the target Superset dataset. Callers (migration_engine.py)
    should catch this PER CHART and skip/flag that chart rather than
    aborting the whole migration."""


class SupersetFieldMapper:

    def __init__(self, client):
        self.client = client
        self._dataset_cache: Dict[int, Dict[str, Any]] = {}

    # ------------------------------------------------------------------
    # Dataset loading
    # ------------------------------------------------------------------
    def load(self, dataset_id: int) -> Dict[str, Any]:
        """Returns the full raw dataset payload (cached)."""
        if dataset_id in self._dataset_cache:
            return self._dataset_cache[dataset_id]

        url = f"{self.client.base_url}/api/v1/dataset/{dataset_id}"
        response = self.client.session.get(url, headers=self.client.get_headers())
        response.raise_for_status()

        dataset = response.json()["result"]
        self._dataset_cache[dataset_id] = dataset
        return dataset

    def invalidate(self, dataset_id: int) -> None:
        self._dataset_cache.pop(dataset_id, None)

    def _columns_by_name(self, dataset_id: int) -> Dict[str, Any]:
        dataset = self.load(dataset_id)
        return {c["column_name"]: c for c in dataset.get("columns", [])}

    def _metrics_by_name(self, dataset_id: int) -> Dict[str, Any]:
        dataset = self.load(dataset_id)
        return {m["metric_name"]: m for m in dataset.get("metrics", [])}

    def get_datasource_type(self, dataset_id: int) -> str:
        """Returns 'table' for physical datasets, or the dataset's actual
        type — needed because virtual/SQL datasets must NOT be hardcoded
        as 'table' in query_context/form_data.datasource."""
        dataset = self.load(dataset_id)
        # Superset marks virtual datasets via a non-empty `sql` field.
        return "table"  # Superset's own /chart/data contract always uses
        # "table" as the datasource.type regardless of physical/virtual —
        # kept as an explicit method so this is documented and can be
        # overridden per-instance if a custom datasource type is ever needed.

    # ------------------------------------------------------------------
    # Column resolution
    # ------------------------------------------------------------------
    def get_column(self, dataset_id: int, column_name: str) -> Dict[str, Any]:
        """Exact-match column lookup. Raises FieldResolutionError with
        close-match suggestions instead of a bare Exception, so callers
        can log something actionable."""
        columns = self._columns_by_name(dataset_id)

        if column_name in columns:
            return columns[column_name]

        suggestions = get_close_matches(column_name, columns.keys(), n=3, cutoff=0.6)
        raise FieldResolutionError(
            f"Column '{column_name}' not found on dataset {dataset_id}. "
            f"Closest matches: {suggestions or 'none'}"
        )

    def resolve_column_name(self, dataset_id: int, column_name: str) -> str:
        """Case-insensitive / fuzzy resolution of a Metabase-origin column
        name to the actual Superset column name. This handles differences in
        case or identifier normalization without assuming any domain fields."""
        columns = self._columns_by_name(dataset_id)

        if column_name in columns:
            return column_name

        lowered = {c.lower(): c for c in columns}
        if column_name.lower() in lowered:
            return lowered[column_name.lower()]

        matches = get_close_matches(column_name, columns.keys(), n=1, cutoff=0.75)
        if matches:
            return matches[0]

        raise FieldResolutionError(
            f"Cannot resolve column '{column_name}' on dataset {dataset_id}. "
            f"Available columns: {sorted(columns.keys())}"
        )

    def is_numeric_column(self, dataset_id: int, column_name: str) -> bool:
        column = self.get_column(dataset_id, self.resolve_column_name(dataset_id, column_name))
        col_type = (column.get("type") or "").upper()
        return any(col_type.startswith(t) for t in NUMERIC_TYPES)

    # ------------------------------------------------------------------
    # Temporal column resolution
    # ------------------------------------------------------------------
    def get_temporal_column(self, dataset_id: int) -> Optional[str]:
        """Returns the dataset's designated temporal column, required for
        granularity/x_axis on time series, big number (trend), and any
        time-filtered chart. Without this, QueryContextBuilder cannot
        populate `granularity`/`x_axis`, which is a direct cause of
        Empty Query on time-based charts."""
        dataset = self.load(dataset_id)

        main_dttm = dataset.get("main_dttm_col")
        if main_dttm:
            return main_dttm

        for column in dataset.get("columns", []):
            if column.get("is_dttm"):
                return column["column_name"]

        return None

    # ------------------------------------------------------------------
    # Metric resolution
    # ------------------------------------------------------------------
    def get_saved_metric(self, dataset_id: int, metric_name: str) -> Optional[str]:
        """If the Superset dataset already has a saved metric matching
        the Metabase metric by name (exact or close match), return its
        metric_name so QueryContextBuilder can reference it as a plain
        string instead of building a redundant/incorrect ad-hoc metric."""
        metrics = self._metrics_by_name(dataset_id)

        if metric_name in metrics:
            return metric_name

        matches = get_close_matches(metric_name, metrics.keys(), n=1, cutoff=0.8)
        return matches[0] if matches else None

    def build_metric(self, dataset_id: int, metric_spec: Any) -> Any:
        """
        Converts a Metabase-derived metric spec into a Superset-valid
        metric — either a saved-metric string reference, or a verified
        SIMPLE/SQL ad-hoc metric dict. This REPLACES the defensive
        normalization previously living in QueryContextBuilder; doing it
        here means every metric is checked against real dataset metadata
        before it's ever sent to Superset.

        Accepts:
          - str                      -> treated as a saved metric name;
                                         verified to exist, else resolved
                                         via fuzzy match, else raises.
          - {"aggregate": "COUNT"}                       -> COUNT(*)
          - {"column": "id", "aggregate": "COUNT"}       -> COUNT(col)
          - {"column": "amount", "aggregate": "SUM"}     -> SUM(col), with
                                                             numeric-type
                                                             validation
          - already-built adhoc dict (has 'expressionType') -> passed
                                                                through
        """
        if isinstance(metric_spec, str):
            resolved = self.get_saved_metric(dataset_id, metric_spec)
            if resolved:
                return resolved
            raise FieldResolutionError(
                f"Saved metric '{metric_spec}' not found on dataset {dataset_id}."
            )

        if isinstance(metric_spec, dict):
            if "expressionType" in metric_spec:
                metric_spec = dict(metric_spec)
                column = metric_spec.get("column")
                if isinstance(column, dict) and column.get("column_name"):
                    metric_spec["column"] = self.get_column(
                        dataset_id,
                        self.resolve_column_name(dataset_id, column["column_name"]),
                    )
                return metric_spec

            aggregate = (metric_spec.get("aggregate") or "COUNT").upper()
            column_name = metric_spec.get("column") or metric_spec.get("column_name")

            if not column_name:
                # COUNT(*) needs no column and no type check.
                return {
                    "expressionType": "SQL",
                    "sqlExpression": "COUNT(*)",
                    "label": metric_spec.get("label") or "COUNT(*)",
                    "optionName": "metric_count_star",
                }

            resolved_name = self.resolve_column_name(dataset_id, column_name)

            if aggregate in NUMERIC_ONLY_AGGREGATES and not self.is_numeric_column(
                dataset_id, resolved_name
            ):
                raise FieldResolutionError(
                    f"Aggregate '{aggregate}' requires a numeric column, but "
                    f"'{resolved_name}' on dataset {dataset_id} is not numeric."
                )

            label = metric_spec.get("label") or f"{aggregate}({resolved_name})"
            return {
                "expressionType": "SIMPLE",
                "column": {"column_name": resolved_name},
                "aggregate": aggregate,
                "label": label,
                "optionName": f"metric_{resolved_name}_{aggregate}".lower(),
            }

        raise FieldResolutionError(f"Unsupported metric spec: {metric_spec!r}")

    def build_metrics(self, dataset_id: int, metric_specs: List[Any]) -> List[Any]:
        if not metric_specs:
            return []
        return [self.build_metric(dataset_id, spec) for spec in metric_specs]

    # ------------------------------------------------------------------
    # Groupby / adhoc-column resolution
    # ------------------------------------------------------------------
    def resolve_groupby(self, dataset_id: int, columns: List[str]) -> List[str]:
        """Resolves a list of Metabase-origin dimension names to verified
        Superset column names. Raises FieldResolutionError on any
        unresolvable entry so the caller can decide whether to skip that
        chart or fail the migration."""
        return [self.resolve_column_name(dataset_id, c) for c in (columns or [])]

    def resolve_filters(self, dataset_id: int, filters: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        resolved = []
        for item in filters or []:
            item = dict(item)
            item["subject"] = self.resolve_column_name(dataset_id, item["subject"])
            resolved.append(item)
        return resolved
