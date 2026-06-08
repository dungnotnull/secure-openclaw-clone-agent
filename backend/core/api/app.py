from __future__ import annotations

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from backend.core.api.routes import auth, revert, tasks
from backend.core.middleware.security import audit_logger
from backend.core.background.runner import get_background_runner
from backend.core.knowledge.scheduler import get_scheduler, weekly_crawl_job

app = FastAPI(
    title="SecureClawAgent API",
    version="0.1.0",
    docs_url="/docs",
    redoc_url="/redoc",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "http://localhost:5173",
        "http://localhost:3000",
        "http://127.0.0.1:5173",
        "http://127.0.0.1:3000",
    ],
    allow_credentials=True,
    allow_methods=["GET", "POST", "PUT", "DELETE", "OPTIONS"],
    allow_headers=["Authorization", "Content-Type", "X-Request-ID"],
    expose_headers=["X-Request-ID"],
    max_age=600,
)

app.middleware("http")(audit_logger)

app.include_router(auth.router, prefix="/api/v1")
app.include_router(tasks.router, prefix="/api/v1")
app.include_router(revert.router, prefix="/api/v1")


@app.get("/health")
async def health():
    from backend.core.db.database import get_db
    from backend.core.llm.provider import get_fallback_chain

    db_ok = False
    try:
        get_db().execute("SELECT 1")
        db_ok = True
    except Exception:
        pass

    llm_health = {}
    try:
        chain = get_fallback_chain()
        llm_health = await chain.health_check()
    except Exception:
        llm_health = {"error": "health check failed"}

    return {
        "status": "ok",
        "version": "0.1.0",
        "database": "connected" if db_ok else "disconnected",
        "llm_providers": llm_health,
    }


@app.on_event("startup")
async def startup():
    runner = get_background_runner()
    await runner.start()

    scheduler = get_scheduler()
    scheduler.add_job(weekly_crawl_job, interval_seconds=604800, name="weekly-knowledge-crawl")
    await scheduler.start()

    from backend.core.db.database import get_db
    get_db()


@app.on_event("shutdown")
async def shutdown():
    await get_background_runner().stop()
    await get_scheduler().stop()
