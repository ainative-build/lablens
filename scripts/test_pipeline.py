"""Manual pipeline test — run against PDF and export CSV."""
import asyncio
import csv
import sys
from pathlib import Path

# Add src to path
sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

from lablens.config import Settings
from lablens.orchestration.pipeline import PlainPipeline


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
    print(f"\nValues: {len(values)}")

    # Summary stats
    dirs = {}
    sevs = {}
    for v in values:
        d = v.get("direction", "?")
        s = v.get("severity", "?")
        dirs[d] = dirs.get(d, 0) + 1
        sevs[s] = sevs.get(s, 0) + 1
    print(f"Directions: {dirs}")
    print(f"Severities: {sevs}")

    # Show key values
    targets = ["MCHC", "Calcium", "Free T", "Testosterone", "HDL", "LDL"]
    print("\nKey values:")
    for v in values:
        name = v.get("test_name", "")
        if any(t.lower() in name.lower() for t in targets):
            print(
                f"  {name:50s} val={str(v.get('value', '?')):>10s} "
                f"dir={v.get('direction', '?'):>14s} "
                f"sev={v.get('severity', '?'):>10s} "
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
            print(f"  {name:50s} val={str(v.get('value', '?')):>10s}")

    # Export CSV
    csv_path = Path(__file__).parent.parent / "resources" / "pipeline-test-round4.csv"
    with open(csv_path, "w", newline="") as f:
        writer = csv.writer(f)
        writer.writerow([
            "test_name", "value", "unit", "direction", "severity",
            "is_panic", "actionability", "confidence",
            "reference_range_low", "reference_range_high",
            "range_source", "range_trust", "loinc_code",
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
            ])
    print(f"\nCSV exported to: {csv_path}")


if __name__ == "__main__":
    asyncio.run(main())
