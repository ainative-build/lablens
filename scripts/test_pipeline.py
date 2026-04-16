"""Manual pipeline test — run against PDF and export CSV.

Outputs section-aware data (Phase 2-6): HPLC blocks, screening results,
verification verdicts, and section_type per value.
"""
import asyncio
import csv
import json
import os
import sys
from pathlib import Path

# Ensure working directory is project root
PROJECT_ROOT = Path(__file__).resolve().parent.parent
os.chdir(PROJECT_ROOT)

# Add src to path
sys.path.insert(0, str(PROJECT_ROOT / "src"))

from lablens.config import Settings  # noqa: E402
from lablens.orchestration.pipeline import PlainPipeline  # noqa: E402


async def main():
    pdf_path = Path(__file__).parent.parent / "resources" / "DiaG feb 2026.pdf"
    if not pdf_path.exists():
        print(f"PDF not found: {pdf_path}")
        return

    settings = Settings()
    pipeline = PlainPipeline(settings)

    print(f"Analyzing {pdf_path.name}...")
    pdf_bytes = pdf_path.read_bytes()
    result = await pipeline.analyze(pdf_bytes, language="en")

    values = result["values"]
    screening = result.get("screening_results", [])
    audit = result.get("audit", {})
    hplc_blocks = audit.get("hplc_blocks", [])
    verdicts = audit.get("verification_verdicts", [])

    print(f"\nValues: {len(values)}")
    print(f"Screening results: {len(screening)}")
    print(f"HPLC blocks: {len(hplc_blocks)}")
    print(f"Verification verdicts: {len(verdicts)}")

    # Summary stats
    dirs = {}
    sevs = {}
    sections = {}
    verif = {}
    for v in values:
        d = v.get("direction", "?")
        s = v.get("severity", "?")
        sec = v.get("section_type", "standard_lab_table")
        vv = v.get("verification_verdict", "?")
        dirs[d] = dirs.get(d, 0) + 1
        sevs[s] = sevs.get(s, 0) + 1
        sections[sec] = sections.get(sec, 0) + 1
        verif[vv] = verif.get(vv, 0) + 1
    print(f"Directions: {dirs}")
    print(f"Severities: {sevs}")
    print(f"Section types: {sections}")
    print(f"Verification: {verif}")

    # HPLC blocks detail
    if hplc_blocks:
        print("\n--- HPLC Blocks ---")
        for i, hb in enumerate(hplc_blocks):
            print(f"  Block {i}: NGSP={hb.get('ngsp_value')} "
                  f"IFCC={hb.get('ifcc_value')} eAG={hb.get('eag_value')} "
                  f"cat={hb.get('diabetes_category')} "
                  f"cross_check={hb.get('cross_check_passed')} "
                  f"flags={hb.get('consistency_flags')}")

    # Screening detail
    if screening:
        print("\n--- Screening Results ---")
        for sr in screening:
            print(f"  {sr.get('test_type')}: {sr.get('result_status')} "
                  f"(origin={sr.get('signal_origin')}, "
                  f"conf={sr.get('confidence')})")
            if sr.get("organs_screened"):
                print(f"    Organs: {sr.get('organs_screened')}")
            if sr.get("limitations"):
                print(f"    Limitations: {sr.get('limitations')}")
            if sr.get("followup_recommendation"):
                print(f"    Follow-up: {sr.get('followup_recommendation')}")

    # Show key values
    targets = ["MCHC", "Calcium", "Free T", "Testosterone", "HDL", "LDL",
               "HbA1c", "eAG"]
    print("\nKey values:")
    for v in values:
        name = v.get("test_name", "")
        if any(t.lower() in name.lower() for t in targets):
            print(
                f"  {name:50s} val={str(v.get('value', '?')):>10s} "
                f"dir={v.get('direction', '?'):>14s} "
                f"sev={v.get('severity', '?'):>10s} "
                f"sec={v.get('section_type', '?'):>22s} "
                f"range=[{v.get('reference_range_low', 'None')}-"
                f"{v.get('reference_range_high', 'None')}] "
                f"src={v.get('range_source', '?')}"
            )

    # Show all abnormal
    print("\nAbnormal values:")
    for v in values:
        if v.get("direction") in ("high", "low"):
            name = v.get("test_name", "")
            print(
                f"  {name:50s} val={str(v.get('value', '?')):>10s} "
                f"dir={v.get('direction', '?'):>6s} "
                f"sev={v.get('severity', '?'):>10s} "
                f"range=[{v.get('reference_range_low', 'None')}-"
                f"{v.get('reference_range_high', 'None')}] "
                f"src={v.get('range_source', '?')}"
            )

    # Show indeterminate
    print("\nIndeterminate values:")
    for v in values:
        if v.get("direction") == "indeterminate":
            name = v.get("test_name", "")
            print(f"  {name:50s} val={str(v.get('value', '?')):>10s} "
                  f"sec={v.get('section_type', '?')}")

    # Export CSV with new fields
    csv_path = (Path(__file__).parent.parent / "resources"
                / "manual-test-output.csv")
    with open(csv_path, "w", newline="") as f:
        writer = csv.writer(f)
        writer.writerow([
            "test_name", "value", "unit", "direction", "severity",
            "is_panic", "actionability", "confidence",
            "reference_range_low", "reference_range_high",
            "range_source", "range_trust", "loinc_code",
            "section_type", "verification_verdict", "unit_confidence",
        ])
        for v in values:
            writer.writerow([
                v.get("test_name", ""),
                v.get("value", ""),
                v.get("unit", ""),
                v.get("direction", ""),
                v.get("severity", ""),
                v.get("is_panic", ""),
                v.get("actionability", ""),
                v.get("confidence", ""),
                v.get("reference_range_low", ""),
                v.get("reference_range_high", ""),
                v.get("range_source", ""),
                v.get("range_trust", ""),
                v.get("loinc_code", ""),
                v.get("section_type", ""),
                v.get("verification_verdict", ""),
                v.get("unit_confidence", ""),
            ])
    print(f"\nCSV exported to: {csv_path}")

    # Export full JSON for evaluation harness
    json_path = (Path(__file__).parent.parent / "resources"
                 / "manual-test-output.json")
    with open(json_path, "w") as f:
        json.dump(result, f, indent=2, default=str)
    print(f"JSON exported to: {json_path}")


if __name__ == "__main__":
    asyncio.run(main())
