"""FastAPI application entry point."""

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from lablens.api.analyze import router as analyze_router
from lablens.api.chat import router as chat_router
from lablens.api.health import router as health_router
from lablens.config import settings

app = FastAPI(title="LabLens", version="0.1.0")

app.add_middleware(
    CORSMiddleware,
    # Production: comma-separated origins via LABLENS_ALLOWED_ORIGINS env.
    # Dev default: ["*"] (any origin) for local development.
    allow_origins=settings.allowed_origins,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Mount health under /api prefix so HEALTHCHECK + Nginx probe + smoke-test
# all hit the same canonical URL: /api/health
app.include_router(health_router, prefix="/api")
app.include_router(analyze_router)
app.include_router(chat_router)
