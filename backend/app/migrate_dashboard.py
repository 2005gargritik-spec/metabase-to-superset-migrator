"""End-to-end, metadata-driven Metabase dashboard migration."""

import re
from datetime import datetime, timezone

from collections.abc import Callable

from .chart_converter import ChartConverter
from .field_mapper import FieldMapper
from .metabase_client import MetabaseClient
from .superset_client import SupersetClient


def _slug(value):
    return re.sub(r"[^a-zA-Z0-9_]+", "_", value or "card").strip("_")[:180]


def _query_parts(card):
    dataset_query = card.get("dataset_query") or {}
    stages = dataset_query.get("stages") or []
    stage = stages[0] if stages else dataset_query.get("query", {})
    source = stage.get("source-table") or stage.get("source_table") or dataset_query.get("source-table")
    return dataset_query, stage, source


def _source_context(metabase, card, seen=None):
    """Resolve physical tables, native cards, and saved-question sources."""
    seen = seen or set()
    if card.get("id") in seen:
        raise ValueError("Circular saved-question dependency in Metabase card")
    seen.add(card.get("id"))
    dataset_query, stage, source = _query_parts(card)

    if isinstance(source, str) and source.startswith("card__"):
        parent = metabase.get_card(int(source.split("__", 1)[1]))
        return _source_context(metabase, parent, seen)

    if dataset_query.get("type") == "native" or dataset_query.get("native"):
        sql = dataset_query.get("native", {}).get("query")
        database_id = dataset_query.get("database")
        if not sql or not database_id:
            raise ValueError(f"Native card {card.get('id')} is missing SQL or database ID")
        return {"kind": "virtual", "database_id": database_id, "sql": sql, "name": f"mb_{card.get('id', 'card')}_{_slug(card.get('name'))}"}

    if not isinstance(source, int):
        source_query = stage.get("source-query") or stage.get("source_query")
        if source_query:
            sql = source_query.get("native", {}).get("query")
            if sql:
                return {"kind": "virtual", "database_id": dataset_query.get("database"), "sql": sql, "name": f"mb_{card.get('id', 'card')}_{_slug(card.get('name'))}"}
        raise ValueError(f"Card {card.get('id')} has no resolvable physical or native source")

    table = metabase.get_table(source)
    database_id = table.get("db_id") or table.get("database_id") or dataset_query.get("database")
    return {"kind": "physical", "database_id": database_id, "table_id": source, "table_name": table.get("name"), "schema": table.get("schema"), "metadata": table}


def migrate_dashboard(
    dashboard_id,
    metabase_url,
    metabase_email,
    metabase_password,
    superset_url,
    superset_username,
    superset_password,
    superset_database_id=None,
    progress: Callable[[str, str | None], None] | None = None,
):
    def emit(stage, detail=None):
        if progress:
            progress(stage, detail)

    emit("connecting to Metabase", f"Authenticating and opening dashboard {dashboard_id}")
    metabase = MetabaseClient(metabase_url, metabase_email, metabase_password)
    emit("connecting to Superset", "Authenticating with Apache Superset")
    superset = SupersetClient(superset_url, superset_username, superset_password)
    superset.login()
    emit("reading dashboard metadata", f"Loading Metabase dashboard {dashboard_id}")
    dashboard = metabase.get_dashboard(dashboard_id)
    if not dashboard:
        raise ValueError(f"Metabase dashboard {dashboard_id} was not found")

    database_cache, dataset_cache, charts, failures = {}, {}, [], []
    dashcards = dashboard.get("dashcards") or dashboard.get("ordered_cards") or []
    for dashcard in dashcards:
        emit("reading charts", f"Reading dashboard card {dashcard.get('card_id') or (dashcard.get('card') or {}).get('id')}")
        card = metabase.resolve_card(dashcard)
        if not card:
            continue
        try:
            emit("matching datasets", card.get("name"))
            source = _source_context(metabase, card)
            mb_database_id = source["database_id"]
            if mb_database_id not in database_cache:
                mb_database = metabase.get_database(mb_database_id)
                database_cache[mb_database_id] = superset.resolve_database(mb_database, superset_database_id)
            target_database_id = database_cache[mb_database_id]["id"]
            dataset_key = (target_database_id, source.get("schema"), source.get("table_name"), source.get("sql"))
            if dataset_key not in dataset_cache:
                dataset_cache[dataset_key] = superset.ensure_dataset(
                    target_database_id,
                    table_name=source.get("table_name"),
                    schema=source.get("schema"),
                    sql=source.get("sql"),
                    dataset_name=source.get("name"),
                )
            dataset_id = dataset_cache[dataset_key]
            metadata = source.get("metadata")
            if metadata is None:
                # Native query result columns are reflected by Superset after
                # dataset creation, so parsing only needs names from result metadata.
                metadata = {"fields": card.get("result_metadata") or []}
            emit("creating charts", card.get("name"))
            chart_config = ChartConverter(FieldMapper(metadata)).convert(card)
            chart = superset.create_chart(card.get("name") or f"Card {card.get('id')}", chart_config, dataset_id)
            chart["layout"] = {k: dashcard.get(k) for k in ("row", "col", "size_x", "size_y")}
            chart["dashboard_filters"] = []
            source_fields = FieldMapper(metadata)
            for mapping in dashcard.get("parameter_mappings", []) or []:
                target = mapping.get("target") or []
                try:
                    field_ref = target[1] if len(target) > 1 else None
                    chart["dashboard_filters"].append({
                        "parameter_id": mapping.get("parameter_id"),
                        "dataset_id": dataset_id,
                        "column": source_fields.get_name(field_ref),
                    })
                except (ValueError, TypeError, IndexError):
                    # Variable/template-tag targets do not always map to one
                    # physical column and cannot become a Superset native filter.
                    pass
            charts.append(chart)
        except Exception as exc:
            failures.append({"card_id": card.get("id"), "card_name": card.get("name"), "error": str(exc)})

    if not charts:
        raise RuntimeError(f"No charts could be migrated: {failures}")
    emit("creating dashboards", dashboard.get("name"))
    target_dashboard_id = superset.create_dashboard(dashboard.get("name") or "Migrated Dashboard")
    for chart in charts:
        superset.attach_chart_to_dashboard(chart["id"], target_dashboard_id)
    emit("recreating layouts", dashboard.get("name"))
    superset.add_chart_to_dashboard(
        target_dashboard_id, charts, dashboard.get("name") or "Migrated Dashboard",
        dashboard.get("parameters") or [],
    )
    emit("verifying migration", f"Created Superset dashboard {target_dashboard_id}")
    return {
        "success": not failures,
        "message": "Migration completed" if not failures else "Migration completed with chart failures",
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "dashboard_name": dashboard.get("name"),
        "charts_found": len([d for d in dashcards if d.get("card_id") or d.get("card")]),
        "charts_imported": len(charts),
        "failed": len(failures),
        "failed_cards": failures,
        "superset_dashboard_id": target_dashboard_id,
        "datasets": sorted(set(dataset_cache.values())),
    }
