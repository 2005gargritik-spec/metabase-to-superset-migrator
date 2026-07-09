"""Map Metabase visualisations to a clean Superset chart configuration."""

from .query_parser import QueryParser


DISPLAY_MAP = {
    "bar": "echarts_timeseries_bar",
    "row": "echarts_timeseries_bar",
    "line": "echarts_timeseries_line",
    "area": "echarts_timeseries_line",
    "pie": "pie",
    "scalar": "big_number_total",
    "smartscalar": "big_number_total",
    "table": "table",
}


class ChartConverter:
    def __init__(self, field_mapper):
        self.parser = QueryParser(field_mapper)

    def convert(self, card):
        parsed = self.parser.parse(card)
        viz_type = DISPLAY_MAP.get(card.get("display"), "table")
        settings = card.get("visualization_settings") or {}
        config = {
            "viz_type": viz_type,
            "metrics": parsed.get("metrics", []),
            "groupby": parsed.get("groupby", []),
            "columns": parsed.get("columns", []),
            "adhoc_filters": parsed.get("filters", []),
            "temporal_column": parsed.get("temporal_column"),
            "time_grain": parsed.get("time_grain"),
            "row_limit": parsed.get("row_limit", 10000),
            "order_desc": parsed.get("descending", False),
        }
        # Metabase line charts without a temporal breakout are categorical;
        # preserve the real first breakout instead of inventing a date column.
        if parsed.get("groupby"):
            config["x_axis"] = parsed["groupby"][0]
        if settings.get("graph.show_values") is not None:
            config["show_value"] = bool(settings["graph.show_values"])
        return config
