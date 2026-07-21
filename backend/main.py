"""Surveyor Job Dashboard — FastAPI application entry point."""

import os
import sys
from contextlib import asynccontextmanager
from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles
from fastapi.middleware.cors import CORSMiddleware

# Add parent to path for imports
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from backend.database import init_db
from backend.routes import jobs, applications, cv, companies, analytics, pipeline, graduate_schemes, health


@asynccontextmanager
async def lifespan(app: FastAPI):
    init_db()
    yield


app = FastAPI(
    title="Surveyor Job Dashboard",
    description="Personal job-hunting dashboard for junior surveyor in Hong Kong",
    version="1.0.0",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

# API routes
app.include_router(jobs.router)
app.include_router(applications.router)
app.include_router(cv.router)
app.include_router(companies.router)
app.include_router(analytics.router)
app.include_router(pipeline.router)
app.include_router(graduate_schemes.router)
app.include_router(health.router)

# Serve frontend
frontend_dir = os.path.join(os.path.dirname(os.path.dirname(__file__)), "frontend")
if os.path.exists(frontend_dir):
    app.mount("/", StaticFiles(directory=frontend_dir, html=True), name="frontend")


if __name__ == "__main__":
    import uvicorn
    uvicorn.run("main:app", host="0.0.0.0", port=8765, reload=True)
