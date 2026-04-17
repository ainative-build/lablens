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

## Qwen Integration

Three Qwen models are used, each with a narrow, audited responsibility. Clinical decisions never depend on model output — the deterministic engine always has the final say.

| Stage | Qwen Model | Role | Why this model |
|-------|-----------|------|----------------|
| **Primary OCR** | `qwen-vl-ocr` | Extract test name / value / unit / range / H‑L flag from each PDF page | Document‑specialized VL model tuned for tabular/form OCR; returns structured key‑value rows |
| **Suspicious‑page reparse** | `qwen-vl-max-latest` (Qwen3‑VL) | Re‑extract when page fails plausibility or has incomplete rows | Stronger reasoning + better handling of ambiguous layouts (HPLC blocks, scanned charts) |
| **Explanation** | `qwen-plus` | Write patient‑facing `what_it_means` + `next_steps` prose from already‑interpreted values | Chat‑tier model; fast, cheap, hedged‑tone when guarded by prompt |

### How each call is wired

- **Transport**: Alibaba DashScope Python SDK (`dashscope.MultiModalConversation.call` for VL; `dashscope.Generation.call` for chat). Default endpoint is the international edge (`dashscope-intl.aliyuncs.com`), overridable via `LABLENS_DASHSCOPE_API_BASE` for Mainland deployments.
- **Auth**: `LABLENS_DASHSCOPE_API_KEY` from `.env` (pydantic‑settings). No key = hard fail at startup.
- **Async bridge**: all calls run in a thread pool (`loop.run_in_executor`) so the FastAPI event loop stays unblocked during OCR batches.
- **Error surfacing**: `_call_dashscope_ocr` inspects `resp.status_code` + `resp.output` and raises `RuntimeError` with the SDK's `code` / `message` / `request_id` instead of letting a `NoneType` crash leak through — real DashScope errors (auth, quota, throttle) surface cleanly in the UI as `extraction_empty`.

### Guardrails around Qwen output

Nothing Qwen returns is trusted without verification:

1. **Schema enforcement** — OCR responses pass through `response_parser` (noise filter, dedup, flag allowlist `{H, L, A}`).
2. **Plausibility bounds** — values are rejected or unit‑corrected against two‑tier physiological ceilings before interpretation.
3. **Reparse trigger** — `semantic_verifier` flags low‑quality pages; the pipeline re‑OCRs them with `qwen-vl-max-latest` and merges row‑level, preserving known‑good rows.
4. **Explanation prompt contract** — section‑aware prompts (standard / HPLC / screening) forbid clinical staging language, enforce hedged framing ("suggests", "may indicate"), and never hand Qwen the authority to change direction/severity — only to phrase what the deterministic engine already decided.
5. **Mathematical fallback** — HPLC fields (NGSP / IFCC / eAG) derive missing values from NGSP.org formulas when OCR drops them, so a single bad extraction doesn't lose the panel.

### Language coverage

OCR prompts are language‑specific (English, French, Arabic, Vietnamese). The same three models handle all four; explanation prose is generated in the requested output language. UI surface is currently English‑only; the `i18n.ts` key map retains French / Arabic / Vietnamese for re‑localization.

### Extraction Pipeline

| Stage | Module | Purpose |
|-------|--------|---------|
| PDF → Images | `pdf_processor` | Convert pages to base64 PNG |
| OCR | `ocr_extractor` | Qwen-VL-OCR primary, Qwen3-VL reparse for suspicious pages |
| Noise Filter | `response_parser` | Remove non-test rows (headers, metadata, schema leaks) |
| Range Fix | `ocr_range_preprocessor` | Parse range strings (incl. comma-decimal), detect threshold-style ranges |
| **Section Classifier** | `section_classifier` | Detect page sections: standard table, HPLC block, screening attachment |
| **HPLC Parser** | `hplc_block_parser` | Dedicated HbA1c/IFCC/eAG parser with NGSP.org cross-validation |
| **Screening Parser** | `screening_parser` | ctDNA multi-cancer screening attachment parser + canonicalization |
| **Semantic Verifier** | `semantic_verifier` | 8 deterministic checks + optional model verification (5-verdict) |
| Terminology | `terminology_mapper` | Map test names → LOINC codes via exact/alias/normalized/fuzzy cascade |
| Unit Normalization | `unit_normalizer` | Convert to canonical units (case-insensitive aliases) + post-conversion plausibility guard |
| **Unit Misreport Correction** | `pipeline` (stage 2.5) | Detect and correct OCR unit errors (e.g., mmol/L reported as mg/dL) |
| Plausibility | `range_plausibility_checker` | Curated cross-check + analyte-family validation for range trust scoring |
| **Qualitative Interpreter** | `qualitative` | LOINC-aware qualitative dispatch (4 categories, 22 assays) |

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

### Classification State

Every interpreted value carries a `classification_state` that drives the UI badge and CSV export:

| State | When stamped | UI treatment |
|-------|--------------|--------------|
| `classified` | Curated rule supports direction + severity | Normal severity badge |
| `low_confidence` | Direction supported but evidence is weak (OCR‑extracted range with no curated rule, or lab H/L flag with no verifiable range) | "Low confidence" pill, severity suppressed to normal |
| `could_not_classify` | Indeterminate — no range, unclear unit, or unreconcilable evidence | "Unclear" badge, no direction arrow |

The state is enforced at two layers: the engine (`uncertainty gate` — suppresses severity when no curated bands exist) and the orchestration pipeline (Stage 3.5 — aligns `ocr-flag-fallback` rows without a curated rule to `low_confidence`). This keeps UI semantics consistent with CSV export and prevents contradictions like "lab flagged as high" displayed alongside "mildly reduced".

### Severity Cap

Low‑clinical‑impact analytes (Basophils, NRBC, NRBC%, PDW, MPV, Plateletcrit) have a canonical severity ceiling defined in `retrieval/clinical_priority.py::get_severity_cap`. Even if bands would produce `moderate` or `critical`, these analytes cap at `mild` — prevents alarming users about findings that are not clinically actionable in isolation. The raw pre‑cap severity is preserved in `evidence_trace.severity_source_raw` for audit.

### Safety Guards

- **Two-tier plausibility bounds**: unit-level hard-impossible ceilings (30 units) + analyte-specific LOINC-keyed physiological limits (31 LOINCs); LOINC bounds override generic when available
- **Range trust scoring**: lab ranges cross-checked against curated midpoints; unit-system differences detected
- **Cross-unit mismatch detection**: value/range ratio >20x clears range and flags low trust (catches value in mmol/L with range in mg/dL)
- **Post-conversion plausibility guard**: converted values re-checked against bounds; reverted if conversion produces implausible result
- **Decision-threshold gating**: HbA1c, LDL, HDL use clinical cut-points, not reference intervals
- **Unit misreport correction**: detects AND corrects OCR unit errors (e.g., 0.41 mmol/L→6.89 mg/dL for Uric Acid)
- **Severity caps**: never critical without curated bands; low-trust ranges capped at mild
- **Restricted flag categories**: hormones, tumor markers, infectious tests can't use OCR flags for direction
- **Row-level merge**: suspicious page reparse only patches incomplete rows, preserves known-good rows
- **Flag sanitization**: raw OCR flags allowlisted to {H, L, A}; bogus grabs ("UNIT", "%") discarded
- **Zero-width range guard**: `[0,0]` and equal-bound ranges caught and cleared with type coercion
- **Pre-explanation consistency**: OCR-flag-only directions without numeric ranges downgraded to indeterminate before explanation
- **3-tier canonical dedup**: confidence → range-source trust (5 levels) → unit_confidence; HPLC values exempt
- **Explanation guardrails**: no clinical staging language; hedged framing ("suggests", "may indicate")
- **Qualitative assay semantics**: LOINC-keyed dispatch with 4 categories (expected-negative, expected-positive, categorical, semi-quantitative); HBsAb inversion handled; blood type/Rh categorical bypass; urobilinogen trace/1+ normal

### Output Design

- **`classification_state`**: `classified` / `low_confidence` / `could_not_classify` — drives UI state pills + CSV semantics
- **`source_flag`**: Raw OCR flag moved to `evidence_trace` (audit-only), not in top-level output
- **`verification_verdict`**: Per-row verdict string from semantic verifier
- **`range_source`**: Provenance of reference range (`lab-provided-validated`, `curated-fallback`, `range-text`, `lab-provided-suspicious`, `ocr-flag-fallback`, `no-range`)
- **`evidence_trace`**: Full decision audit trail including severity source, match confidence, range trust, severity cap raw value when applied

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
│   ├── vitamins.yaml            # Vitamin D, B12, Folate, Iron, Ferritin
│   └── qualitative.yaml             # Qualitative test rules (22 assays, 4 categories)
├── aliases/
│   ├── common-aliases.yaml      # 200+ test name aliases
│   ├── analyte-families.yaml    # 20 analyte families (split CBC/thyroid, iron, inflammatory)
│   └── unit-conversions.yaml    # Unit conversion factors + case-insensitive aliases
└── loinc/                   # LOINC reference data

tests/                       # 26 test modules, 500+ tests
frontend/                    # Next.js app (upload, results, evidence)
```

## Known Refinements

Captured from expert review for follow-up work (non-blockers — safe to defer):

1. **Tumor marker semantics (CA 19-9, etc.)** — currently flagged via numeric range only. Need assay-native interpretation (clinical decision points, "elevated above reference" framing instead of just `high`), and proper context that tumor markers are non-diagnostic in isolation.

2. **Chemistry long-tail curated coverage** — `Calcium [Serum]`, `Non-HDL Cholesterol`, `Free Testosterone Index` still lack curated bands so resolve to `low_confidence` or `could_not_classify`. `Plateletcrit (PCT)`, `PDW`, `NRBC %` now correctly surface as `low_confidence` via the severity cap + uncertainty gate; expanding `data/rules/*.yaml` would upgrade them to `classified` where clinical consensus exists.

3. **Qualitative assay-native semantics** — minimal `interpret_qualitative()` covers positive/negative keywords. Need full assay-native semantics for HBsAg (negative=expected normal), urinalysis grades (`Trace`, `1+`, `2+`), titer routing for HCV/HIV, and proper direction/severity for categorical assays. Plan stub at `plans/260416-1958-qualitative-semantics`.

4. **OCR non-determinism** — Qwen-VL-OCR conflates HPLC fields (~75% of runs). Currently mitigated by mathematical derivation in `_derive_missing_values()` (NGSP↔IFCC↔eAG via NGSP.org formulas) and plausibility reclassification. Root cause is upstream — could benefit from extraction-level prompt hardening or multi-pass voting.

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

OCR + explanation generation validated on English, French, Arabic, and Vietnamese with language‑specific Qwen prompts. UI surface is currently English‑only — the `frontend/src/lib/i18n.ts` key map retains the other three languages for re‑localization.

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
