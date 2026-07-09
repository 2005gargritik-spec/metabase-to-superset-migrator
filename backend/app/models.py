from typing import Any, Literal

from pydantic import BaseModel, Field, HttpUrl


class MetabaseCredentials(BaseModel):
    metabase_url: HttpUrl
    metabase_email: str
    metabase_password: str


class SupersetCredentials(BaseModel):
    superset_url: HttpUrl
    superset_username: str
    superset_password: str


class DashboardSummary(BaseModel):
    id: int
    name: str
    description: str | None = None
    archived: bool = False
    updated_at: str | None = None


class SupersetDatabaseSummary(BaseModel):
    id: int
    name: str
    backend: str | None = None


class MigrationStartRequest(MetabaseCredentials, SupersetCredentials):
    dashboard_ids: list[int] = Field(min_length=1)
    superset_database_id: int | None = None


class MigrationStage(BaseModel):
    percent: int
    stage: str
    detail: str | None = None


class MigrationJob(BaseModel):
    id: str
    status: Literal["queued", "running", "completed", "failed"]
    progress: MigrationStage
    requested_dashboards: int
    results: list[dict[str, Any]] = Field(default_factory=list)
    summary: dict[str, Any] | None = None
    error: str | None = None
    created_at: str
    updated_at: str
