# LabLens — AI Lab Report Interpreter

Deterministic lab-interpretation pipeline with document-aware OCR extraction, curated clinical rules, semantic verification, and AI-generated patient explanations.

## Architecture

```
PDF → Page Classification → Qwen-VL-OCR → Noise Filter → Range Preprocessor
    → Section Classifier → HPLC Parser → Screening Parser
    → LOINC Mapper → Unit Normalizer → Range Plausibility Checker
    → Semantic Verifier (5-verdict) → Unit Misreport Correction
    → Deterministic Engine (8-step) → Pre-Explanation Consistency Check
    → Qwen Explainer (section-aware) → Canonical Dedup → UI + Evidence Panel
```

**Core principle**: Deterministic engine owns clinical logic (direction, severity, panic); LLM owns only OCR extraction and explanation phrasing. Semantic verifier bridges both with deterministic checks + optional model fallback.

### Extraction Pipeline

| Stage | Module | Purpose |
|-------|--------|---------|
| PDF → Images | `pdf_processor` | Convert pages to base64 PNG |
| OCR | `ocr_extractor` | Qwen-VL-OCR primary, Qwen3-VL reparse for suspicious pages |
| Noise Filter | `response_parser` | Remove non-test rows (headers, metadata, schema leaks) |
| Range Fix | `ocr_range_preprocessor` | Parse range strings, detect threshold-style ranges |
| **Section Classifier** | `section_classifier` | Detect page sections: standard table, HPLC block, screening attachment |
| **HPLC Parser** | `hplc_block_parser` | Dedicated HbA1c/IFCC/eAG parser with NGSP.org cross-validation |
| **Screening Parser** | `screening_parser` | ctDNA multi-cancer screening attachment parser + canonicalization |
| **Semantic Verifier** | `semantic_verifier` | 8 deterministic checks + optional model verification (5-verdict) |
| Terminology | `terminology_mapper` | Map test names → LOINC codes via exact/alias/normalized/fuzzy cascade |
| Unit Normalization | `unit_normalizer` | Convert to canonical units for curated range comparison |
| **Unit Misreport Correction** | `pipeline` (stage 2.5) | Detect and correct OCR unit errors (e.g., mmol/L reported as mg/dL) |
| Plausibility | `range_plausibility_checker` | Curated cross-check + analyte-family validation for range trust scoring |

### Section-Aware Processing

The pipeline classifies each page into section types before extraction:

- **`standard_lab_table`** — Conventional lab results with test/value/unit/range columns
- **`hplc_diabetes_block`** — HbA1c (NGSP%), IFCC (mmol/mol), eAG with ADA diabetes categorization
- **`screening_attachment`** — ctDNA multi-cancer screening results (SPOT-MAS, Galleri, etc.)

Each section type routes to a specialized parser and explanation prompt.

### HPLC Cross-Validation

HbA1c results use NGSP.org conversion formulas for unit consistency:
- **IFCC**: `10.93 × NGSP - 23.5` (±1.5 mmol/mol tolerance)
- **eAG**: `28.7 × NGSP - 46.7` (±0.3 mmol/L tolerance)
- **ADA categories**: Normal (<5.7%), Prediabetes (5.7–6.4%), Diabetes (≥6.5%)
- Bypasses standard range-selection; direction/severity derived from clinical cutpoints

### Semantic Verifier

5-verdict decision framework with 8 deterministic checks:

| Verdict | Meaning |
|---------|---------|
| `ACCEPT` | All checks pass, high confidence |
| `ACCEPT_WITH_WARNING` | Passes but has caution signals (suspicious range, low confidence) |
| `DOWNGRADE` | 1 check failed — lower confidence, keep result |
| `MARK_INDETERMINATE` | Unreliable data — direction set to indeterminate |
| `RETRY` | 2+ failures — trigger re-extraction if possible |

Checks cover: missing fields, unit-value plausibility, flag-range consistency (audit-only), extraction quality signals (unit_confidence, range_source), and double-low escalation.

### Interpretation Engine

8-step deterministic pipeline (zero LLM, zero network):

1. **Range selection** — lab-provided → curated fallback → text extraction → OCR flag
2. **Direction** — in-range / high / low / indeterminate
3. **Severity** — normal / mild / moderate / critical (curated bands or heuristic deviation)
4. **Panic check** — curated thresholds only
5. **Actionability** — routine / follow-up / urgent
6. **Confidence scoring** — match quality × range source × unit confidence
7. **Evidence trace** — full audit trail for every decision
8. **Panel analysis** — CBC, CMP, BMP, lipid, thyroid, liver, kidney panel completeness

### Safety Guards

- **Range trust scoring**: lab ranges cross-checked against curated midpoints; unit-system differences detected
- **Decision-threshold gating**: HbA1c, LDL, HDL use clinical cut-points, not reference intervals
- **Unit misreport correction**: detects AND corrects OCR unit errors (e.g., 0.41 mmol/L→6.89 mg/dL for Uric Acid)
- **Severity caps**: never critical without curated bands; low-trust ranges capped at mild
- **Restricted flag categories**: hormones, tumor markers, infectious tests can't use OCR flags for direction
- **Row-level merge**: suspicious page reparse only patches incomplete rows, preserves known-good rows
- **Flag sanitization**: raw OCR flags allowlisted to {H, L, A}; bogus grabs ("UNIT", "%") discarded
- **Pre-explanation consistency**: OCR-flag-only directions without numeric ranges downgraded to indeterminate before explanation
- **3-tier canonical dedup**: confidence → range-source trust (5 levels) → unit_confidence; HPLC values exempt
- **Explanation guardrails**: no clinical staging language; hedged framing ("suggests", "may indicate")

### Output Design

- **`source_flag`**: Raw OCR flag moved to `evidence_trace` (audit-only), not in top-level output
- **`verification_verdict`**: Per-row verdict string from semantic verifier
- **`range_source`**: Provenance of reference range used for interpretation
- **`evidence_trace`**: Full decision audit trail including severity source, match confidence, range trust

## Tech Stack

| Layer | Technology |
|-------|-----------|
| Backend | Python 3.11+, FastAPI |
| OCR | Qwen-VL-OCR (DashScope international endpoint) |
| Reparse | Qwen3-VL (`qwen-vl-max-latest`) for suspicious pages |
| Explanation | Qwen-Plus (DashScope), section-aware prompts (standard, HPLC, screening) |
| Knowledge | 8 curated rule sets (YAML), LOINC terminology, 200+ test aliases |
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
├── models/                  # Data schemas (LabReport, ScreeningResult, HplcBlock)
│   ├── schemas.py               # API request/response models
│   ├── lab_report.py            # Core lab value model
│   ├── hplc_block.py            # HPLC block data model
│   ├── screening_result.py      # Screening result model
│   └── section_types.py         # Section type enum
├── extraction/              # PDF → structured lab data
│   ├── ocr_extractor.py         # Primary OCR + suspicious page retry
│   ├── pdf_processor.py         # PDF → base64 images
│   ├── response_parser.py       # Noise filter + deduplication
│   ├── ocr_range_preprocessor.py # Range parsing + threshold detection
│   ├── section_classifier.py    # Page section detection (table/HPLC/screening)
│   ├── hplc_block_parser.py     # Dedicated HPLC parser + cross-validation
│   ├── screening_parser.py      # ctDNA screening parser + canonicalization
│   ├── semantic_verifier.py     # 5-verdict verification (8 deterministic checks)
│   ├── hplc_semantic_validator.py # HbA1c/IFCC/eAG consistency check
│   ├── terminology_mapper.py    # Test name → LOINC mapping
│   ├── unit_normalizer.py       # Unit conversion (μmol/L → mg/dL)
│   ├── range_plausibility_checker.py # Range trust scoring
│   ├── plausibility_validator.py # Value-range plausibility validation
│   ├── alias_registry.py        # 200+ test name aliases
│   └── pii_stripper.py         # PII removal from OCR output
├── interpretation/          # Deterministic clinical engine
│   ├── engine.py                # 8-step decision pipeline
│   ├── range_selection.py       # Range source + direction
│   ├── severity.py              # Severity bands + heuristic deviation
│   ├── confidence.py            # Confidence scoring
│   ├── evidence.py              # Audit trail builder
│   ├── band_validator.py        # Severity band contiguity validation
│   ├── panel_checker.py         # Panel completeness analysis
│   └── qualitative.py          # Positive/Negative interpretation
├── knowledge/               # Curated clinical rules
│   └── rules_loader.py         # YAML rule loading
├── retrieval/               # Explanation generation
│   ├── explanation_generator.py # Qwen-powered explanations (section-aware dispatch)
│   ├── explanation_prompts.py   # Prompt templates (standard, HPLC, screening)
│   ├── context_assembler.py     # Context for explainer
│   └── models.py               # ExplanationResult, FinalReport
└── orchestration/           # Pipeline coordination
    ├── pipeline.py              # Extract → Verify → Interpret → Explain → Canonicalize
    └── job_store.py             # Async job tracking

data/
├── rules/                   # 8 curated rule sets
│   ├── cbc.yaml                 # Complete blood count
│   ├── bmp.yaml                 # Basic metabolic panel
│   ├── cmp.yaml                 # Comprehensive metabolic panel
│   ├── lipid.yaml               # Lipid panel
│   ├── thyroid.yaml             # Thyroid function
│   ├── liver.yaml               # Liver function
│   ├── kidney.yaml              # Kidney function (eGFR, creatinine, BUN)
│   └── vitamins.yaml            # Vitamin D, B12, Folate, Iron, Ferritin
├── aliases/
│   ├── common-aliases.yaml      # 200+ test name aliases
│   ├── analyte-families.yaml    # Family ranges + categories
│   └── unit-conversions.yaml    # Unit conversion factors (incl. Vitamin D, B12, Uric Acid)
└── loinc/                   # LOINC reference data

tests/                       # 25 test modules
frontend/                    # Next.js app (upload, results, evidence)
```

## Evaluation

Offline evaluation harness for pipeline accuracy scoring:

```bash
# Run evaluation against ground-truth annotations
python -m lablens.evaluation.harness --input results.json --truth ground_truth.csv
```

Tracks: direction accuracy, severity calibration, indeterminate rate, false abnormal rate, explanation coverage.

## API

| Endpoint | Method | Description |
|----------|--------|-------------|
| `/health` | GET | Health check |
| `/api/analyze` | POST | Upload PDF, returns interpreted results with evidence traces |

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
