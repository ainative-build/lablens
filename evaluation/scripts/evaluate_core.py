"""Core evaluation — imports pipeline modules directly, no API required.

Tests interpretation engine at analyte level against ground truth.
Usage: python evaluation/scripts/evaluate_core.py --ground-truth evaluation/ground-truth/
"""

import argparse
import json
import sys
from pathlib import Path

# Add project root to path
sys.path.insert(0, str(Path(__file__).parent.parent.parent / "src"))

from lablens.interpretation.engine import InterpretationEngine
from metrics import AnalyteResult, compute_aggregate, evaluate_analyte


def evaluate_engine_against_ground_truth(gt_path: str) -> dict:
    """Evaluate interpretation engine against ground truth JSON."""
    gt = json.loads(Path(gt_path).read_text())
    engine = InterpretationEngine()

    # Build input values from ground truth (simulating perfect extraction)
    values = []
    match_confidences = {}
    for i, v in enumerate(gt["values"]):
        values.append({
            "test_name": v["test_name"],
            "value": v["value"],
            "unit": v["unit"],
            "loinc_code": v["loinc_code"],
            "ref_range_low": v.get("reference_range_low"),
            "ref_range_high": v.get("reference_range_high"),
        })
        match_confidences[i] = "high"  # Perfect extraction = high confidence

    report = engine.interpret_report(values, match_confidences)

    # Evaluate each analyte
    results = []
    for i, (interpreted, gt_val) in enumerate(zip(report.values, gt["values"])):
        predicted = {
            "value": interpreted.value,
            "unit": interpreted.unit,
            "loinc_code": interpreted.loinc_code,
            "direction": interpreted.direction,
            "severity": interpreted.severity,
            "confidence": interpreted.confidence,
        }
        result = evaluate_analyte(predicted, gt_val, gt.get("variant_type", "clean"))
        results.append(result)

    aggregate = compute_aggregate(results)

    return {
        "report_id": gt["report_id"],
        "variant_type": gt.get("variant_type", "clean"),
        "analyte_results": [vars(r) for r in results],
        "aggregate": aggregate,
    }


def main():
    parser = argparse.ArgumentParser(description="Core evaluation")
    parser.add_argument("--ground-truth", required=True, help="Ground truth directory")
    args = parser.parse_args()

    gt_dir = Path(args.ground_truth)
    all_results = []

    for gt_file in sorted(gt_dir.glob("*.json")):
        if gt_file.name == "schema.json":
            continue
        print(f"\nEvaluating: {gt_file.name}")
        result = evaluate_engine_against_ground_truth(str(gt_file))
        all_results.append(result)
        print(json.dumps(result["aggregate"], indent=2))

    # Print scenario table
    print("\n| Report | Variant | Direction Acc | Severity Acc | Status |")
    print("|--------|---------|---------------|--------------|--------|")
    for r in all_results:
        agg = r.get("aggregate", {})
        direction = agg.get("direction_accuracy", 0)
        severity = agg.get("severity_accuracy", 0)
        status = "PASS" if direction >= 0.9 and severity >= 0.85 else "FAIL"
        print(
            f"| {r['report_id']} | {r['variant_type']} | "
            f"{direction:.0%} | {severity:.0%} | {status} |"
        )


if __name__ == "__main__":
    main()
