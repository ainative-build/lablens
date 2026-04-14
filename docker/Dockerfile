FROM python:3.11-slim

RUN apt-get update && apt-get install -y --no-install-recommends \
    poppler-utils \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app
COPY pyproject.toml .
RUN pip install --no-cache-dir .
COPY src/ src/

EXPOSE 8000
CMD ["uvicorn", "lablens.main:app", "--host", "0.0.0.0", "--port", "8000"]
