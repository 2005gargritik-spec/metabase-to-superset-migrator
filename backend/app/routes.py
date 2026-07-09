from __future__ import annotations

from datetime import datetime, timezone
from threading import Thread
from time import perf_counter
from typing import Any

import requests
from fastapi import APIRouter, HTTPException

from .job_store import jobs
from .metabase_client import MetabaseClient
from .migrate_dashboard import migrate_dashboard
from .models import (
    DashboardSummary,
    MetabaseCredentials,
    MigrationJob,
    MigrationStage,
    MigrationStartRequest,
    SupersetCredentials,
    SupersetDatabaseSummary,
)
from .superset_client import SupersetClient

router = APIRouter()


def _http_error_message(source: str, exc: requests.HTTPError) -> str:
    response = exc.response
    if response is None:
        return f"{source} request failed"
    if response.status_code in {401, 403}:
        return f"{source} authentication failed. Check the URL and credentials."
    detail = response.text[:500] if response.text else response.reason
    return f"{source} API returned {response.status_code}: {detail}"


def _normalize_dashboards(payload: Any) -> list[DashboardSummary]:
    if isinstance(payload, list):
        raw_dashboards = payload
    elif isinstance(payload, dict):
        raw_dashboards = payload.get("data") or payload.get("dashboards") or payload.get("items") or []
    else:
        raw_dashboards = []

    dashboards = []
    for dashboard in raw_dashboards:
        if not isinstance(dashboard, dict) or dashboard.get("id") is None:
            continue
        dashboards.append(
            DashboardSummary(
                id=dashboard["id"],
                name=dashboard.get("name") or dashboard.get("display_name") or f"Dashboard {dashboard['id']}",
                description=dashboard.get("description"),
                archived=bool(dashboard.get("archived", False)),
                updated_at=dashboard.get("updated_at"),
            )
        )
    return sorted(dashboards, key=lambda item: item.name.lower())


@router.post("/metabase/dashboards", response_model=list[DashboardSummary])
def metabase_dashboards(request: MetabaseCredentials):
    try:
        metabase = MetabaseClient(
            str(request.metabase_url),
            request.metabase_email,
            request.metabase_password,
        )
        return _normalize_dashboards(metabase.get_dashboards())
    except requests.HTTPError as exc:
        raise HTTPException(status_code=401, detail=_http_error_message("Metabase", exc)) from exc
    except requests.RequestException as exc:
        raise HTTPException(status_code=502, detail=f"Could not reach Metabase: {exc}") from exc


@router.post("/superset/databases", response_model=list[SupersetDatabaseSummary])
def superset_databases(request: SupersetCredentials):
    try:
        superset = SupersetClient(
            str(request.superset_url),
            request.superset_username,
            request.superset_password,
        )
        superset.login()
        databases = []
        for database in superset._all("database"):
            if database.get("id") is None:
                continue
            databases.append(
                SupersetDatabaseSummary(
                    id=database["id"],
                    name=database.get("database_name") or f"Database {database['id']}",
                    backend=database.get("backend"),
                )
            )
        return sorted(databases, key=lambda item: item.name.lower())
    except requests.HTTPError as exc:
        raise HTTPException(status_code=401, detail=_http_error_message("Superset", exc)) from exc
    except requests.RequestException as exc:
        raise HTTPException(status_code=502, detail=f"Could not reach Superset: {exc}") from exc


def _run_migration(job_id: str, request: MigrationStartRequest) -> None:
    started = perf_counter()
    total = len(request.dashboard_ids)
    results: list[dict[str, Any]] = []
    base_stage_weight = {
        "connecting to Metabase": 5,
        "connecting to Superset": 10,
        "reading dashboard metadata": 18,
        "reading charts": 30,
        "reading filters": 40,
        "matching datasets": 50,
        "creating charts": 66,
        "creating dashboards": 78,
        "recreating layouts": 86,
        "verifying migration": 94,
        "completing migration": 100,
    }

    def update_progress(index: int, stage: str, detail: str | None = None) -> None:
        dashboard_span = 100 / max(total, 1)
        local_percent = base_stage_weight.get(stage, 50)
        percent = min(99, int(index * dashboard_span + (local_percent / 100) * dashboard_span))
        jobs.update(
            job_id,
            status="running",
            progress=MigrationStage(percent=percent, stage=stage, detail=detail),
            results=results,
        )

    try:
        jobs.update(job_id, status="running", progress=MigrationStage(percent=1, stage="connecting to Metabase"))
        for index, dashboard_id in enumerate(request.dashboard_ids):
            result = migrate_dashboard(
                dashboard_id,
                str(request.metabase_url),
                request.metabase_email,
                request.metabase_password,
                str(request.superset_url),
                request.superset_username,
                request.superset_password,
                request.superset_database_id,
                progress=lambda stage, detail, index=index: update_progress(index, stage, detail),
            )
            results.append(result)
            update_progress(index, "completing migration", result.get("dashboard_name"))

        failed_dashboards = [result for result in results if not result.get("success")]
        duration = round(perf_counter() - started, 2)
        summary = {
            "overall_status": "completed_with_warnings" if failed_dashboards else "completed",
            "dashboard_names": [result.get("dashboard_name") for result in results],
            "dashboards_requested": total,
            "dashboards_migrated": len(results),
            "charts_migrated": sum(result.get("charts_imported", 0) for result in results),
            "failed_charts": sum(result.get("failed", 0) for result in results),
            "skipped_charts": sum(max(result.get("charts_found", 0) - result.get("charts_imported", 0) - result.get("failed", 0), 0) for result in results),
            "warnings": [failure for result in results for failure in result.get("failed_cards", [])],
            "superset_dashboard_ids": [result.get("superset_dashboard_id") for result in results if result.get("superset_dashboard_id")],
            "duration_seconds": duration,
            "completed_at": datetime.now(timezone.utc).isoformat(),
        }
        jobs.update(
            job_id,
            status="completed",
            progress=MigrationStage(percent=100, stage="completed", detail="Migration report ready"),
            results=results,
            summary=summary,
        )
    except Exception as exc:
        jobs.update(
            job_id,
            status="failed",
            progress=MigrationStage(percent=100, stage="failed", detail=str(exc)),
            results=results,
            error=str(exc),
        )


@router.post("/migrations", response_model=MigrationJob, status_code=202)
def start_migration(request: MigrationStartRequest):
    job = jobs.create(len(request.dashboard_ids))
    Thread(target=_run_migration, args=(job.id, request), daemon=True).start()
    return job


@router.get("/migrations/{job_id}", response_model=MigrationJob)
def migration_status(job_id: str):
    job = jobs.get(job_id)
    if job is None:
        raise HTTPException(status_code=404, detail="Migration job was not found")
    return job
