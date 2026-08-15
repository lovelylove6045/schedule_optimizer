from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.config import get_settings
from app.routers import courses, programs

settings = get_settings()

app = FastAPI(title="Academic Degree Optimization Engine API")

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(programs.router)
app.include_router(courses.router)


@app.get("/health")
def health() -> dict[str, str]:
    """Liveness check used by Docker healthchecks and local smoke tests."""
    return {"status": "ok"}
