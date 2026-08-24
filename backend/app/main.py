"""DAS D.I.A.L API entrypoint. Run: uvicorn app.main:app --reload"""
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from app.core.config import settings
from app.routers import (auth, learners, profiles, activities,
                         assessments, reviews, share, dashboard)

# Fail at boot, not per request. The embedding provider and the vector column it ranks
# against must agree, and a mismatch is invisible at every other layer — see Settings.verify.
settings.verify()

app = FastAPI(title=settings.app_name)

app.add_middleware(
    CORSMiddleware,
    # strip() so "a, b" in .env works — an origin with a stray space silently fails
    # to match, and a blocked origin looks like a network error, not a config error.
    allow_origins=[o.strip() for o in settings.cors_origins.split(",") if o.strip()],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

for r in (auth, learners, profiles, activities, assessments, reviews, share, dashboard):
    app.include_router(r.router)


@app.get("/health")
def health():
    return {"status": "ok", "app": settings.app_name}
