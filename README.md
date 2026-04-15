# LabLens — AI Lab Report Interpreter

Deterministic lab-interpretation pipeline with graph-backed retrieval and multilingual AI explanations.

## Architecture

```
PDF → Qwen-OCR → Noise Filter → LOINC Mapper → Unit Normalizer → Deterministic Engine
  → Qwen Explainer → UI + Evidence Panel
```

**Core principle**: Deterministic engine owns clinical logic; LLM owns explanation phrasing.

> **Note**: Graph retrieval (GDB) and vector enrichment (DashVector) are optional add-ons
> not active in the default pipeline. The core path runs without them. Set `GDB_HOST` and
> `DASHVECTOR_ENDPOINT` in `.env` to enable enrichment.

## Tech Stack

- **Backend**: Python 3.11+, FastAPI, AgentScope
- **AI**: Qwen (DashScope) — OCR, chat, embeddings
- **Knowledge**: Alibaba GDB (Gremlin), DashVector, LOINC, MedlinePlus
- **Frontend**: Next.js + TypeScript

## Quick Start

```bash
# Create venv and install
python -m venv .venv
source .venv/bin/activate
pip install -e ".[dev]"

# Copy env and configure
cp .env.example .env
# Edit .env with your DashScope API key

# Run tests
pytest

# Start dev server
uvicorn lablens.main:app --reload
```

## Docker

```bash
cd docker
docker compose up --build
```

## Project Structure

```
src/lablens/
├── main.py              # FastAPI entry point
├── config.py            # Pydantic Settings
├── api/                 # HTTP endpoints
├── models/              # Data schemas (pipeline contracts)
├── extraction/          # PDF → Canonical Lab JSON
├── knowledge/           # LOINC, rules, MedlinePlus
├── interpretation/      # Deterministic severity engine
├── retrieval/           # Graph + vector enrichment
└── orchestration/       # AgentScope pipeline
```

## API

- `GET /health` — Health check

## Languages

Extraction validated on EN, FR, AR, VN with language-specific prompts.
