"""
QueryContextBuilder — Superset 6.0.0 compatible.

Builds both `query_context` (used by /api/v1/chart/data and stored on the
Chart model) and `form_data` / `params` (stored on Chart.params) in the
exact shape Superset's frontend controls expect PER VIZ TYPE.

This is the #1 fix point for:
  - "Empty Query" screens
  - Pie / Big Number needing a manually re-selected metric
  - Metrics silently dropped
  - Missing/garbled groupby, columns, filters, datasource
"""

from typing import Any, Dict, List, Optional


# ---------------------------------------------------------------------------
# Viz-type classification (Superset 6.0.0 viz_type keys)
# ---------------------------------------------------------------------------
PIE_TYPES = {"pie", "echarts_pie"}
BIG_NUMBER_TYPES = {"big_number_total", "big_number"}
TIMESERIES_TYPES = {
    "echarts_timeseries_line",
    "echarts_timeseries_bar",
    "echarts_timeseries_smooth",
    "echarts_timeseries_area",
    "echarts_timeseries",
    "line",
    "bar",
    "dist_bar",
    "area",
}
TABLE_TYPES = {"table"}

DEFAULT_COUNT_METRIC = {
    "expressionType": "SQL",
    "sqlExpression": "COUNT(*)",
    "label": "COUNT(*)",
    "optionName": "metric_count_star",
}


class QueryContextBuilder:
    """
    Expects `chart` (the intermediate representation produced by
    ChartConverter) to contain, at minimum:
        - viz_type            : str   (Superset viz_type, already mapped)
        - metrics              : list  (raw Metabase-derived metrics, may be
                                         partially normalized)
        - groupby / x_axis / columns : optional dimension fields
        - temporal_column       : optional str, name of the datetime column
        - time_grain             : optional str (Superset time_grain_sqla value)
        - time_range             : optional str
        - adhoc_filters          : optional list, UI/client adhoc-filter shape
        - row_limit, order_desc  : optional

    NOTE: `metrics` here should ideally already be normalized adhoc-metric
    dicts produced by `superset_field_mapper.py`. This builder still
    defensively re-normalizes them (see `_normalize_metric`) so that a
    malformed upstream metric never silently produces an empty chart —
    but the upstream mapper should be fixed too (see accompanying notes).
    """

    def build(self, chart: Dict[str, Any], dataset_id: int) -> Dict[str, Any]:
        viz_type = chart.get("viz_type", "table")

        metrics = self._normalize_metrics(chart.get("metrics", []))
        filters_adhoc = chart.get("adhoc_filters", []) or []
        simple_filters = self._adhoc_to_simple_filters(filters_adhoc)

        temporal_column = chart.get("temporal_column")
        time_grain = chart.get("time_grain") or "P1D"
        time_range = chart.get("time_range", "No filter")
        row_limit = chart.get("row_limit", 10000)
        order_desc = chart.get("order_desc", True)

        # ------------------------------------------------------------
        # Per-viz-type dimension/metric resolution
        # ------------------------------------------------------------
        if viz_type in PIE_TYPES:
            metrics = metrics or [DEFAULT_COUNT_METRIC]
            groupby = chart.get("groupby") or (
                [chart["x_axis"]] if chart.get("x_axis") else []
            )
            columns: List[Any] = []
            query_mode = None
            is_timeseries = False

        elif viz_type in BIG_NUMBER_TYPES:
            # Big Number never groups by a dimension. Exactly one metric.
            metrics = [metrics[0]] if metrics else [DEFAULT_COUNT_METRIC]
            groupby = []
            columns = []
            query_mode = None
            is_timeseries = viz_type == "big_number"  # trend line variant

        elif viz_type in TIMESERIES_TYPES:
            metrics = metrics or [DEFAULT_COUNT_METRIC]
            dimensions = chart.get("groupby", [])
            axis = temporal_column or chart.get("x_axis") or (dimensions[0] if dimensions else None)
            columns = [axis] if axis else []
            groupby = [d for d in dimensions if d != axis]
            query_mode = None
            is_timeseries = bool(temporal_column)

        elif viz_type in TABLE_TYPES:
            # Aggregate mode if metrics exist, else raw record mode.
            if metrics:
                query_mode = "aggregate"
                groupby = chart.get("groupby") or chart.get("columns", [])
                columns = []
            else:
                query_mode = "raw"
                groupby = []
                columns = chart.get("columns") or chart.get("groupby", [])
            is_timeseries = False

        else:
            # Fallback: behave like a generic aggregate chart.
            metrics = metrics or [DEFAULT_COUNT_METRIC]
            groupby = chart.get("groupby", [])
            columns = []
            query_mode = None
            is_timeseries = False

        # ------------------------------------------------------------
        # Build the QueryObject (queries[0])
        # ------------------------------------------------------------
        query_object: Dict[str, Any] = {
            "filters": simple_filters,
            "extras": {
                "time_grain_sqla": time_grain,
                "having": "",
                "where": "",
            },
            "applied_time_extras": {},
            "columns": columns,
            "groupby": groupby,
            "metrics": metrics,
            "orderby": self._build_orderby(metrics, order_desc, is_timeseries),
            "annotation_layers": [],
            "row_limit": row_limit,
            "series_columns": groupby if is_timeseries else [],
            "series_limit": 0,
            "group_others": False,
            "group_others_when_limit_reached": False,
            "order_desc": order_desc,
            "url_params": {},
            "custom_params": {},
            "custom_form_data": {},
            "time_offsets": [],
            "post_processing": [],
            "time_range": time_range,
            "is_timeseries": is_timeseries,
        }

        if temporal_column:
            query_object["granularity"] = temporal_column
            if is_timeseries:
                query_object["x_axis"] = temporal_column

        if query_mode:
            query_object["query_mode"] = query_mode

        # ------------------------------------------------------------
        # Build form_data / params
        # ------------------------------------------------------------
        form_data: Dict[str, Any] = {
            **chart,
            "viz_type": viz_type,
            "datasource": f"{dataset_id}__table",
            "datasource_id": dataset_id,
            "datasource_type": "table",
            "adhoc_filters": filters_adhoc,
            "row_limit": row_limit,
            "time_range": time_range,
        }

        if temporal_column:
            form_data["granularity_sqla"] = temporal_column
            if is_timeseries:
                form_data["x_axis"] = temporal_column
                form_data["time_grain_sqla"] = time_grain

        if viz_type in PIE_TYPES:
            form_data["metric"] = metrics[0]
            form_data["groupby"] = groupby
            form_data.pop("metrics", None)
            form_data.pop("columns", None)

        elif viz_type in BIG_NUMBER_TYPES:
            form_data["metric"] = metrics[0]
            form_data.pop("metrics", None)
            form_data.pop("groupby", None)
            form_data.pop("columns", None)

        elif viz_type in TIMESERIES_TYPES:
            form_data["metrics"] = metrics
            form_data["groupby"] = groupby
            if columns:
                form_data["x_axis"] = columns[0]
            form_data.pop("columns", None)
            form_data.pop("metric", None)

        elif viz_type in TABLE_TYPES:
            form_data["query_mode"] = query_mode
            if query_mode == "aggregate":
                form_data["metrics"] = metrics
                form_data["groupby"] = groupby
                form_data.pop("all_columns", None)
            else:
                form_data["all_columns"] = columns
                form_data.pop("metrics", None)
                form_data.pop("groupby", None)
            form_data.pop("metric", None)

        else:
            form_data["metrics"] = metrics
            form_data["groupby"] = groupby

        return {
            "datasource": {
                "id": dataset_id,
                "type": "table",
            },
            "force": False,
            "queries": [query_object],
            "form_data": form_data,
            "result_format": "json",
            "result_type": "full",
        }

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------
    def _normalize_metrics(self, metrics: Optional[List[Any]]) -> List[Any]:
        if not metrics:
            return []
        return [self._normalize_metric(m) for m in metrics]

    def _normalize_metric(self, metric: Any) -> Any:
        """
        Accepts:
          - a string -> treated as a saved-metric reference, passed through.
          - a fully-formed Superset adhoc metric dict (has 'expressionType')
            -> passed through unchanged.
          - a loosely-shaped dict e.g. {"column": "id", "aggregate": "COUNT"}
            (typical FieldMapper/ChartConverter intermediate shape)
            -> converted into a proper SIMPLE adhoc metric.
        Anything that can't be resolved to a column falls back to COUNT(*),
        since Superset will refuse to run/save a metric with no expression
        at all — this is the #1 cause of "silently missing metric".
        """
        if isinstance(metric, str):
            return metric

        if isinstance(metric, dict):
            if "expressionType" in metric:
                return metric

            column = metric.get("column") or metric.get("column_name")
            aggregate = (metric.get("aggregate") or "COUNT").upper()
            label = metric.get("label")

            if column:
                label = label or f"{aggregate}({column})"
                return {
                    "expressionType": "SIMPLE",
                    "column": {"column_name": column},
                    "aggregate": aggregate,
                    "label": label,
                    "optionName": f"metric_{column}_{aggregate}".lower(),
                }

            sql_expression = metric.get("sqlExpression") or "COUNT(*)"
            label = label or sql_expression
            return {
                "expressionType": "SQL",
                "sqlExpression": sql_expression,
                "label": label,
                "optionName": f"metric_sql_{abs(hash(sql_expression))}",
            }

        # Unknown shape — do not let this silently drop the metric.
        return DEFAULT_COUNT_METRIC

    def _adhoc_to_simple_filters(
        self, adhoc_filters: List[Dict[str, Any]]
    ) -> List[Dict[str, Any]]:
        """
        Converts client-shape adhoc filters (expressionType/clause/subject/
        operator/comparator) into the server-shape `filters` list Superset's
        QueryObject expects (col/op/val). Sending the client shape directly
        into `queries[].filters` causes Superset to ignore the filter
        entirely (or, for SQL-clause filters, to be dropped since they
        belong in `extras.where`, not `filters`).
        """
        simple: List[Dict[str, Any]] = []
        for f in adhoc_filters:
            if f.get("expressionType") == "SIMPLE":
                simple.append(
                    {
                        "col": f.get("subject"),
                        "op": f.get("operator"),
                        "val": f.get("comparator"),
                    }
                )
            elif f.get("expressionType") == "SQL":
                # SQL-clause adhoc filters must go through extras.where, not
                # `filters`. We surface these via a well-known key so
                # `build()`'s caller (ChartConverter) can merge them into
                # extras.where if needed. We do not silently drop them.
                simple.append(
                    {
                        "col": None,
                        "op": "SQL",
                        "val": f.get("sqlExpression"),
                    }
                )
            elif "col" in f and "op" in f:
                # Already server-shape (e.g. re-migration / idempotent run).
                simple.append(f)
        return simple

    def _build_orderby(
        self, metrics: List[Any], order_desc: bool, is_timeseries: bool
    ) -> List[List[Any]]:
        if is_timeseries or not metrics:
            return []
        return [[metrics[0], not order_desc]]
