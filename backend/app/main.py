from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.config import get_settings
from app.routers import choices, colleges, courses, plans, programs, scenarios, terms

settings = get_settings()

app = FastAPI(title="Academic Degree Optimization Engine API")

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins,
    allow_origin_regex=settings.cors_allow_origin_regex or None,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(colleges.router)
app.include_router(programs.router)
app.include_router(courses.router)
app.include_router(choices.router)
app.include_router(scenarios.router)
app.include_router(plans.router)
app.include_router(terms.router)


@app.get("/health")
def health() -> dict[str, str]:
    """Liveness check used by Docker healthchecks and local smoke tests."""
    return {"status": "ok"}
