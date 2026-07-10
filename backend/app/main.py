from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from .routes import router

app = FastAPI(
    title="MigrAI API",
    version="1.0.0",
    description="API-only Metabase to Apache Superset dashboard migration service.",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "http://localhost:5173",
        "http://localhost:5174",
        "http://127.0.0.1:5173",
        "http://127.0.0.1:5174",
        "https://metabase-to-superset-migrator.vercel.app",
        "https://metabase-to-superset-migrator-i84fssm69-migr-ai.vercel.app",
    ],
    allow_origin_regex=r"https://metabase-to-superset-migrator-[a-z0-9-]+\.vercel\.app",
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(router, prefix="/api")


@app.get("/health")
def health():
    return {"status": "ok", "service": "MigrAI API"}
