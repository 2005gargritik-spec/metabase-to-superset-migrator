"""Translate Metabase MBQL into a dataset-independent chart description."""

AGGREGATES = {
    "sum": "SUM", "avg": "AVG", "average": "AVG", "min": "MIN",
    "max": "MAX", "count": "COUNT", "distinct": "COUNT_DISTINCT",
    "count-distinct": "COUNT_DISTINCT", "cum-sum": "SUM",
}
GRAINS = {
    "minute": "PT1M", "hour": "PT1H", "day": "P1D", "week": "P1W",
    "month": "P1M", "quarter": "P3M", "year": "P1Y",
}


class QueryParser:
    def __init__(self, field_mapper):
        self.fields = field_mapper

    @staticmethod
    def _stage(dataset_query):
        stages = dataset_query.get("stages") or []
        return stages[-1] if stages else dataset_query.get("query", dataset_query)

    @staticmethod
    def _options(ref):
        return ref[-1] if isinstance(ref, list) and ref and isinstance(ref[-1], dict) else {}

    def _name(self, ref):
        if isinstance(ref, str):
            return ref
        return self.fields.get_name(ref)

    def _metric(self, agg):
        if isinstance(agg, dict):
            operator = agg.get("aggregation") or agg.get("operator") or "count"
            ref = agg.get("field")
            label = agg.get("name")
        else:
            operator = agg[0] if agg else "count"
            ref = agg[1] if len(agg) > 1 else None
            # legacy forms sometimes wrap the field after an options dict
            if isinstance(ref, dict) and len(agg) > 2:
                ref = agg[2]
            label = None
        operator = AGGREGATES.get(str(operator).lower(), str(operator).upper())
        column = self._name(ref) if ref is not None else None
        return {"aggregate": operator, "column": column, "label": label or (f"{operator}({column})" if column else "COUNT(*)")}

    def _filter(self, expression):
        if not isinstance(expression, list) or not expression:
            return []
        op = str(expression[0]).lower()
        if op in ("and", "or"):
            result = []
            for child in expression[1:]:
                result.extend(self._filter(child))
            return result
        if len(expression) < 2:
            return []
        operator_map = {"=": "==", "!=": "!=", ">": ">", "<": "<", ">=": ">=", "<=": "<=", "in": "IN", "not-in": "NOT IN", "contains": "LIKE", "is-null": "IS NULL", "not-null": "IS NOT NULL", "between": "BETWEEN"}
        try:
            subject = self._name(expression[1])
        except ValueError:
            return []
        values = expression[2:]
        comparator = values[0] if len(values) == 1 else values
        return [{"clause": "WHERE", "subject": subject, "operator": operator_map.get(op, op.upper()), "comparator": comparator, "expressionType": "SIMPLE"}]

    def parse(self, card):
        dataset_query = card.get("dataset_query") or {}
        if dataset_query.get("type") == "native":
            settings = card.get("visualization_settings") or {}
            dimensions = settings.get("graph.dimensions") or []
            metric_names = settings.get("graph.metrics") or []
            return {
                "native_sql": dataset_query.get("native", {}).get("query", ""),
                "metrics": [{"aggregate": "SUM", "column": name, "label": name} for name in metric_names],
                "groupby": list(dimensions),
                "columns": [f.get("name") for f in card.get("result_metadata", []) if f.get("name")],
                "filters": [],
            }

        stage = self._stage(dataset_query)
        aggregations = stage.get("aggregation") or stage.get("aggregations") or []
        breakouts = stage.get("breakout") or stage.get("breakouts") or []
        groupby, temporal_column, time_grain = [], None, None
        for ref in breakouts:
            name = self._name(ref)
            groupby.append(name)
            options = self._options(ref)
            unit = options.get("temporal-unit") or options.get("temporal_unit")
            if unit or self.fields.is_temporal(ref):
                temporal_column = temporal_column or name
                time_grain = GRAINS.get(unit, "P1D")

        order_by = stage.get("order-by") or stage.get("order_by") or []
        sort_by, descending = None, False
        if order_by:
            descending = str(order_by[0][0]).lower() == "desc"
            try:
                sort_by = self._name(order_by[0][1])
            except (ValueError, IndexError):
                pass

        return {
            "metrics": [self._metric(a) for a in aggregations],
            "groupby": groupby,
            "columns": self.fields.all_names() if not aggregations and card.get("display") == "table" else groupby,
            "filters": self._filter(stage.get("filter", [])),
            "sort_by": sort_by,
            "descending": descending,
            "row_limit": stage.get("limit", 10000),
            "temporal_column": temporal_column,
            "time_grain": time_grain,
        }
