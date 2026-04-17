# Backend production image — single-worker uvicorn (in-memory job_store
# constraint locked in for v1; document this in deployment-guide.md).
#
# Build context: repo root  →  `docker compose -f docker/docker-compose.prod.yml build backend`

FROM python:3.11-slim AS runtime

# poppler-utils → pdftoppm for PDF page rendering during OCR
# curl          → HEALTHCHECK probe
RUN apt-get update && apt-get install -y --no-install-recommends \
    poppler-utils curl \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

# pyproject.toml uses setuptools `packages.find where=["src"]`, so src/ must
# exist at install time. Copy everything needed for the install in one layer
# (mild caching loss vs. pyproject-only is fine — pyproject + src change
# together in practice).
COPY pyproject.toml ./
COPY src/ src/
COPY data/ data/
RUN pip install --no-cache-dir .

ENV LABLENS_APP_ENV=production
ENV LABLENS_LOG_LEVEL=INFO
ENV PYTHONUNBUFFERED=1

EXPOSE 8000

# /api/health is the canonical health route (see plans/260417-1341-…/phase-01)
HEALTHCHECK --interval=30s --timeout=5s --start-period=20s --retries=3 \
    CMD curl -f http://localhost:8000/api/health || exit 1

# --workers 1 is intentional: in-memory job_store can't be shared across workers.
# When that becomes a bottleneck, swap job_store for Redis and bump workers.
CMD ["uvicorn", "lablens.main:app", "--host", "0.0.0.0", "--port", "8000", "--workers", "1"]
