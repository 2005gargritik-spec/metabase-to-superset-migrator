import json
import uuid


class DashboardLayoutBuilder:

    def build(self, dashboard_title, charts, parameters=None):

        position = {
            "DASHBOARD_VERSION_KEY": "v2",
            "ROOT_ID": {
                "children": ["GRID_ID"],
                "id": "ROOT_ID",
                "type": "ROOT",
            },
            "GRID_ID": {
                "children": [],
                "id": "GRID_ID",
                "parents": ["ROOT_ID"],
                "type": "GRID",
            },
            "HEADER_ID": {
                "id": "HEADER_ID",
                "meta": {
                    "text": dashboard_title,
                },
                "type": "HEADER",
            },
        }

        metadata = {
            "color_scheme_domain": [],
            "shared_label_colors": [],
            "map_label_colors": {},
            "label_colors": {},
            "chart_configuration": {},
            "global_chart_configuration": {
                "scope": {
                    "rootPath": ["ROOT_ID"],
                    "excluded": [],
                },
                "chartsInScope": [],
            },
            "color_scheme": "",
            "refresh_frequency": 0,
            "expanded_slices": {},
            "timed_refresh_immune_slices": [],
            "cross_filters_enabled": True,
            "default_filters": "{}",
            "native_filter_configuration": [],
        }

        mappings = {}
        for chart in charts:
            for item in chart.get("dashboard_filters", []):
                mappings.setdefault(item.get("parameter_id"), []).append(item)
        for parameter in parameters or []:
            targets = mappings.get(parameter.get("id"), [])
            if not targets:
                continue
            parameter_type = str(parameter.get("type") or "").lower()
            is_time = "date" in parameter_type or "time" in parameter_type
            default = parameter.get("default")
            metadata["native_filter_configuration"].append({
                "id": f"NATIVE_FILTER-{uuid.uuid4().hex[:12]}",
                "name": parameter.get("name") or parameter.get("slug") or "Filter",
                "filterType": "filter_time" if is_time else "filter_select",
                "targets": [
                    {"datasetId": item["dataset_id"], "column": {"name": item["column"]}}
                    for item in targets
                ],
                "defaultDataMask": {
                    "extraFormData": {},
                    "filterState": {"value": default} if default is not None else {},
                },
                "controlValues": {"enableEmptyFilter": False},
                "cascadeParentIds": [],
                "scope": {"rootPath": ["ROOT_ID"], "excluded": []},
                "type": "NATIVE_FILTER",
                "description": parameter.get("name") or "",
            })

        source_width = max(
            (int(c.get("layout", {}).get("col") or 0) + int(c.get("layout", {}).get("size_x") or 1) for c in charts),
            default=12,
        )
        rows = {}
        for chart in sorted(charts, key=lambda c: (
            c.get("layout", {}).get("row") or 0,
            c.get("layout", {}).get("col") or 0,
        )):
            source_row = chart.get("layout", {}).get("row") or 0
            if source_row not in rows:
                row_id = f"ROW-{uuid.uuid4().hex[:12]}"
                rows[source_row] = row_id
                position["GRID_ID"]["children"].append(row_id)
                position[row_id] = {
                "children": [],
                "id": row_id,
                "parents": ["ROOT_ID", "GRID_ID"],
                "meta": {
                    "background": "BACKGROUND_TRANSPARENT",
                },
                "type": "ROW",
            }
            row_id = rows[source_row]
            chart_node = f"CHART-{uuid.uuid4().hex[:12]}"
            position[row_id]["children"].append(chart_node)

            position[chart_node] = {
                "children": [],
                "id": chart_node,
                "parents": [
                    "ROOT_ID",
                    "GRID_ID",
                    row_id,
                ],
                "meta": {
                    "chartId": chart["id"],
                    "height": max(10, int(chart.get("layout", {}).get("size_y") or 4) * 8),
                    "width": max(1, min(12, round(int(chart.get("layout", {}).get("size_x") or 4) * 12 / source_width))),
                    "sliceName": chart["name"],
                    "uuid": chart["uuid"],
                },
                "type": "CHART",
            }

            metadata["global_chart_configuration"]["chartsInScope"].append(
                chart["id"]
            )

        return {
            "position_json": json.dumps(position),
            "json_metadata": json.dumps(metadata),
        }
