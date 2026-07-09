# MigrAI

MigrAI is a metadata-driven web application for migrating dashboards from Metabase to Apache Superset through their REST APIs.

## What It Does

- Authenticates against Metabase and lists every dashboard visible to the user.
- Lets the user select one dashboard, multiple dashboards, or all dashboards.
- Authenticates against Superset and dynamically discovers configured databases.
- Migrates dashboard metadata, cards, layout, filters, datasets, charts, metrics, dimensions, native SQL questions where supported, and Superset query context.
- Continues past chart-level failures and returns a detailed migration report.
- Shows migration progress from 0% to 100% with named stages.

## Structure

- `backend/app/main.py` - FastAPI application entrypoint.
- `backend/app/routes.py` - API routes for discovery, migration jobs, and polling.
- `backend/app/metabase_client.py` - Metabase REST client.
- `backend/app/superset_client.py` - Superset REST client.
- `backend/app/migrate_dashboard.py` - end-to-end migration engine.
- `backend/app/query_parser.py` - MBQL/native metadata parser.
- `backend/app/chart_converter.py` - Metabase to Superset visualization conversion.
- `backend/app/query_context_builder.py` - Superset query context generator.
- `frontend/src/main.tsx` - React application.

## Run Locally

Backend:

```bash
cd backend
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
uvicorn app.main:app --reload --port 8000
```

Frontend:

```bash
cd frontend
npm install
npm run dev
```

Open `http://localhost:5173`.

## Important Superset Requirement

Metabase does not expose stored database passwords through its API. MigrAI can dynamically discover, match, and create Superset datasets, but the target database connection must already exist in Superset or be selected from the discovered Superset database list.

## API

- `POST /api/metabase/dashboards`
- `POST /api/superset/databases`
- `POST /api/migrations`
- `GET /api/migrations/{job_id}`
- `GET /health`
