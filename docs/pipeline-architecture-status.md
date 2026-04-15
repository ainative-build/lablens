# LabLens Pipeline Architecture & Current Status

## The Pipeline

```
PDF → [OCR] → [Noise Filter] → [Terminology Mapper] → [Unit Normalizer] → [Interpretation Engine] → [Explanation] → UI
       ↓              ↓                ↓                       ↓                    ↓
   Qwen VL      response_parser   alias_registry        unit_normalizer         engine.py
   per page      heuristic         LOINC fuzzy match     data/aliases/           data/rules/*.yaml
                                   common-aliases.yaml   unit-conversions.yaml   severity bands
```

## What each stage does

### Stage 1 — OCR Extraction
**Files:** `src/lablens/extraction/ocr_extractor.py`, `extraction_prompts.py`

- Converts PDF pages to images, sends each to Qwen-VL-OCR
- OCR returns JSON per page: `test_name`, `value`, `unit`, `reference_range_low`, `reference_range_high`, `flag`
- `_fix_range_fields()` handles when OCR puts range string like `"4 - 10"` into the low field
- **Status: Working.** Extracts ~75 values. But OCR sometimes puts wrong column data into range fields (root of remaining false abnormals)

### Stage 2 — Noise Filter
**File:** `src/lablens/extraction/response_parser.py`

- Removes non-test entries (metadata, methodology text, marketing)
- Uses heuristic approach: "does this have a valid measurement value?"
- **Status: Working.** Filters ~35 noise entries per run

### Stage 3 — Terminology Mapping
**Files:** `src/lablens/extraction/terminology_mapper.py`, `alias_registry.py`

- Tries to match extracted test names to LOINC codes
- Uses exact match → alias lookup → fuzzy match (threshold 0.85)
- Aliases defined in `data/aliases/common-aliases.yaml` (50 tests × 4 languages)
- **Status: Weak.** Most tests don't match — fuzzy scores are 0.4-0.8, below threshold. No LOINC code → no curated rules → no severity bands

### Stage 4 — Unit Normalization
**File:** `src/lablens/extraction/unit_normalizer.py`

- Converts values to canonical units per LOINC code (e.g., mmol/L → mg/dL)
- Conversion factors in `data/aliases/unit-conversions.yaml`
- **Status: Partially fixed.** We now skip conversion when lab-provided ranges exist (to avoid value/range unit mismatch). When ranges are missing and we DO convert, it works correctly

### Stage 5 — Interpretation Engine
**File:** `src/lablens/interpretation/engine.py`

- Pure deterministic, zero API calls
- 8-step pipeline per value:
  1. Select range (lab-provided preferred, curated fallback)
  2. Determine direction (low/in-range/high)
  3. Apply severity band (normal/mild/moderate/critical) — only if LOINC-matched rule exists
  4. Check panic threshold
  5. Assign actionability (routine/monitor/consult/urgent)
  6. Calculate confidence (composite of match + range + unit)
  7. Build evidence trace
- **Status: Logic is correct.** But it's only as good as its inputs

### Stage 6 — Explanation
**File:** `src/lablens/retrieval/explanation_generator.py`

- Sends abnormal values to Qwen LLM for natural language explanations
- Falls back to templates if LLM fails
- **Status: Working** for the values that reach it

## The 3 remaining problems and WHY they happen

### Problem 1: OCR extracts wrong ranges (~8 false abnormals)

```
PDF table layout:
Test Name    | Value  | Unit     | Ref Range
Platelets    | 163    | 10³/μL  | 150 - 400
MPV          | 11.7   | fL       | 7.5 - 11.5

What OCR sometimes returns:
Platelets: value=163, range_low=9.04, range_high=12.79  ← WRONG! Grabbed MPV's range
```

The OCR model confuses adjacent columns/rows in complex table layouts. This is a **model quality issue**.

**Possible solutions:**
- Better OCR prompt with table structure hints
- Post-extraction sanity check: if value is wildly outside range, flag as suspicious
- Use a different/newer vision model for complex tables
- Pre-process PDF with table extraction library (pdfplumber/camelot) before OCR

### Problem 2: 21 values still indeterminate (no ranges at all)

These are tests where:
1. OCR returned null ranges (hormones, immunology, tumor markers — ranges printed in footnotes or separate sections)
2. No LOINC match → no curated fallback ranges

```
Example: Testosterone [Serum] = 642.56
- OCR: reference_range_low=null, reference_range_high=null
- LOINC match: failed (fuzzy=0.41, below 0.85 threshold)
- Curated fallback: can't look up without LOINC code
- Result: direction=indeterminate, severity=normal
```

**Possible solutions:**
- **Expand alias registry** — add more test name aliases for common tests (safest approach)
- **Lower fuzzy threshold** from 0.85 → could cause false matches
- **Use OCR-extracted flag field** — if OCR returns `flag: "H"` or `flag: "L"`, use as fallback direction
- **Reference range text parsing** — some values have `reference_range_text` populated but not parsed

### Problem 3: Severity always "normal" for non-LOINC-matched tests

Even when direction is correctly detected (low/high), severity stays "normal" because:

```python
# engine.py _apply_severity():
if not rule or "severity_bands" not in rule:
    return "normal"  # ← No LOINC match → no rule → always normal
```

**Possible solutions:**
- Expand alias registry to get more LOINC matches (same fix as Problem 2)
- Add heuristic: if direction is "high"/"low" and no rule exists, set severity to at least "mild"
- Use magnitude of deviation from range to estimate severity

## Current data files

```
data/
├── aliases/
│   ├── common-aliases.yaml    # 50 test name → LOINC mappings (4 languages)
│   └── unit-conversions.yaml  # LOINC-keyed unit conversion factors
└── rules/
    ├── bmp.yaml    # Basic Metabolic Panel (7 tests)
    ├── cbc.yaml    # Complete Blood Count (10 tests)
    ├── cmp.yaml    # Comprehensive Metabolic Panel
    ├── kidney.yaml # Kidney function
    ├── lipid.yaml  # Lipid panel
    ├── liver.yaml  # Liver function
    └── thyroid.yaml # Thyroid panel
```

Rules cover ~50 common tests. But the alias registry doesn't map enough real-world test name variants to LOINC codes, so the engine can't find rules even when they exist.

## The core insight

The pipeline architecture is sound. The bottleneck is the **terminology mapping layer** — it's the bridge between OCR output and the interpretation engine. When it fails to match a test name to a LOINC code, everything downstream falls back to defaults (no severity bands, no curated ranges, no actionability tiers).

The highest-impact fix would be **expanding `common-aliases.yaml`** with more test name variants that real PDFs use.
