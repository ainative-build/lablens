"""FastAPI application entry point."""

from fastapi import FastAPI

from lablens.api.health import router as health_router

app = FastAPI(title="LabLens", version="0.1.0")
app.include_router(health_router)
