# LOINC Data

LOINC (Logical Observation Identifiers Names and Codes) CSV files go here.

## Download Instructions

1. Register at https://loinc.org/get-loinc/
2. Download the "LOINC Table File" (CSV format)
3. Extract `loinc.csv` into this directory
4. Optionally download "LOINC Linguistic Variants" for multilingual synonyms

## Files (gitignored)

- `loinc.csv` — Main LOINC table (~280K codes)
- `LinguisticVariants/` — Multilingual synonym CSVs
- `target-codes.txt` — Curated list of ~200 target LOINC codes for LabLens

## Target Codes

Create `target-codes.txt` with one LOINC code per line for the ingestion scripts:

```
2345-7
6690-2
718-7
...
```
