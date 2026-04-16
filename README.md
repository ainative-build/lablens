# LabLens — AI Lab Report Interpreter

Deterministic lab-interpretation pipeline with multilingual OCR extraction, curated clinical rules, and AI-generated explanations.

## Architecture

```
PDF → Qwen-VL-OCR → Noise Filter → Range Preprocessor → HPLC Validator
    → LOINC Mapper → Unit Normalizer → Range Plausibility Checker
    → Deterministic Engine (8-step) → Qwen Explainer → UI + Evidence Panel
```

**Core principle**: Deterministic engine owns clinical logic (direction, severity, panic); LLM owns only OCR extraction and explanation phrasing.

### Extraction Pipeline

| Stage | Module | Purpose |
|-------|--------|---------|
| PDF → Images | `pdf_processor` | Convert pages to base64 PNG |
| OCR | `ocr_extractor` | Qwen-VL-OCR primary, Qwen3-VL reparse for suspicious pages |
| Noise Filter | `response_parser` | Remove non-test rows (headers, metadata, schema leaks) |
| Range Fix | `ocr_range_preprocessor` | Parse range strings, detect threshold-style ranges |
| HPLC Validator | `hplc_semantic_validator` | Validate HbA1c/IFCC/eAG unit-value consistency |
| Terminology | `terminology_mapper` | Map test names → LOINC codes via exact/alias/normalized/fuzzy cascade |
| Unit Normalization | `unit_normalizer` | Convert to canonical units for curated range comparison |
| Plausibility | `range_plausibility_checker` | Curated cross-check + analyte-family validation for range trust scoring |

### Interpretation Engine

8-step deterministic pipeline (zero LLM, zero network):

1. **Range selection** — lab-provided → curated fallback → text extraction → OCR flag
2. **Direction** — in-range / high / low / indeterminate
3. **Severity** — normal / mild / moderate / critical (curated bands or heuristic deviation)
4. **Panic check** — curated thresholds only
5. **Actionability** — routine / follow-up / urgent
6. **Confidence scoring** — match quality × range source × unit confidence
7. **Evidence trace** — full audit trail for every decision
8. **Panel analysis** — CBC, CMP, lipid, thyroid panel completeness

### Safety Guards

- **Range trust scoring**: lab ranges cross-checked against curated midpoints; unit-system differences detected
- **Decision-threshold gating**: HbA1c, LDL, HDL use clinical cut-points, not reference intervals
- **Unit misreport detection**: flags OCR unit errors (e.g., mmol/L reported as mg/dL)
- **Severity caps**: never critical without curated bands; low-trust ranges capped at mild
- **Restricted flag categories**: hormones, tumor markers, infectious tests can't use OCR flags for direction
- **Row-level merge**: suspicious page reparse only patches incomplete rows, preserves known-good rows

## Tech Stack

| Layer | Technology |
|-------|-----------|
| Backend | Python 3.11+, FastAPI |
| OCR | Qwen-VL-OCR (DashScope international endpoint) |
| Reparse | Qwen3-VL (`qwen-vl-max-latest`) for suspicious pages |
| Explanation | Qwen-Plus (DashScope) |
| Knowledge | 7 curated rule sets (YAML), LOINC terminology, 200+ test aliases |
| Frontend | Next.js + TypeScript |
| Optional | Alibaba GDB (graph), DashVector (embeddings) |

## Quick Start

```bash
# Create venv and install
python -m venv .venv
source .venv/bin/activate
pip install -e ".[dev]"

# Copy env and configure
cp .env.example .env
# Edit .env — required: LABLENS_DASHSCOPE_API_KEY

# Run tests
pytest

# Start backend
uvicorn lablens.main:app --reload

# Start frontend (separate terminal)
cd frontend && pnpm install && pnpm dev
```

## Docker

```bash
cd docker
docker compose up --build
```

## Project Structure

```
src/lablens/
├── main.py                  # FastAPI entry
├── config.py                # Pydantic Settings (.env)
├── api/                     # HTTP endpoints (analyze, health)
├── models/                  # Data schemas (LabReport, LabValue)
├── extraction/              # PDF → structured lab data
│   ├── ocr_extractor.py         # Primary OCR + suspicious page retry
│   ├── pdf_processor.py         # PDF → base64 images
│   ├── response_parser.py       # Noise filter + deduplication
│   ├── ocr_range_preprocessor.py # Range parsing + threshold detection
│   ├── hplc_semantic_validator.py # HbA1c/IFCC/eAG consistency
│   ├── terminology_mapper.py    # Test name → LOINC mapping
│   ├── unit_normalizer.py       # Unit conversion (μmol/L → mg/dL)
│   ├── range_plausibility_checker.py # Range trust scoring
│   └── alias_registry.py       # 200+ test name aliases
├── interpretation/          # Deterministic clinical engine
│   ├── engine.py                # 8-step decision pipeline
│   ├── range_selection.py       # Range source + direction
│   ├── severity.py              # Severity bands + heuristics
│   ├── confidence.py            # Confidence scoring
│   ├── evidence.py              # Audit trail builder
│   └── qualitative.py          # Positive/Negative interpretation
├── knowledge/               # Curated clinical rules
│   └── rules_loader.py         # YAML rule loading
├── retrieval/               # Explanation generation
│   ├── explanation_generator.py # Qwen-powered explanations
│   └── context_assembler.py    # Context for explainer
└── orchestration/           # Pipeline coordination
    └── pipeline.py              # Extract → Map → Interpret → Explain

data/
├── rules/                   # 7 curated rule sets (CBC, CMP, lipid, etc.)
├── aliases/
│   ├── common-aliases.yaml      # 200+ test name aliases
│   ├── analyte-families.yaml    # Family ranges + categories
│   └── unit-conversions.yaml    # Unit conversion factors
└── loinc/                   # LOINC reference data

frontend/                    # Next.js app (upload, results, evidence)
```

## API

| Endpoint | Method | Description |
|----------|--------|-------------|
| `/health` | GET | Health check |
| `/api/analyze` | POST | Upload PDF, returns interpreted results |

## Languages

Extraction validated on English, French, Arabic, and Vietnamese with language-specific OCR prompts.

## Configuration

Key environment variables (prefix `LABLENS_`):

| Variable | Required | Default | Description |
|----------|----------|---------|-------------|
| `DASHSCOPE_API_KEY` | Yes | — | Alibaba Cloud DashScope API key |
| `DASHSCOPE_API_BASE` | No | `https://dashscope-intl.aliyuncs.com/api/v1` | DashScope endpoint |
| `DASHSCOPE_OCR_MODEL` | No | `qwen-vl-ocr` | Primary OCR model |
| `DASHSCOPE_CHAT_MODEL` | No | `qwen-plus` | Explanation model |
| `GDB_HOST` | No | — | Alibaba GDB host (optional graph enrichment) |
| `DASHVECTOR_ENDPOINT` | No | — | DashVector endpoint (optional embeddings) |
