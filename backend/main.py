from pathlib import Path
from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse

from backend.database.database import Base, engine
from backend.database import models

from backend.api.auth import router as auth_router
from backend.api.dashboard import router as dashboard_router
from backend.api.monitoring import router as monitoring_router
from backend.api.enrollment import router as enrollment_router

Base.metadata.create_all(bind=engine)


app = FastAPI(
    title="SentinelAI API",
    description="AI-based continuous behavioral risk assessment system",
    version="1.0.0"
)


app.include_router(auth_router)
app.include_router(dashboard_router)
app.include_router(monitoring_router)
app.include_router(enrollment_router)

STATIC_DIR = Path(__file__).resolve().parent / "frontend" / "static"
INDEX_FILE = STATIC_DIR / "index.html"

if STATIC_DIR.exists():
    app.mount("/static", StaticFiles(directory=str(STATIC_DIR)), name="static")


@app.get("/")
def root():
    if INDEX_FILE.exists():
        return FileResponse(str(INDEX_FILE))
    return {
        "message": "SentinelAI Backend is running",
        "status": "active"
    }


@app.get("/health")
def health():
    return {
        "status": "healthy"
    }

