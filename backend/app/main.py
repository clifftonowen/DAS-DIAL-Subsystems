"""DAS D.I.A.L API entrypoint. Run: uvicorn app.main:app --reload"""
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from app.core.config import settings
from app.routers import (auth, learners, profiles, activities,
                         assessments, reviews, share, dashboard)

app = FastAPI(title=settings.app_name)

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins.split(","),
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

for r in (auth, learners, profiles, activities, assessments, reviews, share, dashboard):
    app.include_router(r.router)


@app.get("/health")
def health():
    return {"status": "ok", "app": settings.app_name}
