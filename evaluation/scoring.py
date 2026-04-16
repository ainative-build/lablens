"""Offline evaluation scoring for LabLens extraction quality.

Usage:
    python evaluation/scoring.py --ground-truth evaluation/ground_truth/ \
        --extracted evaluation/outputs/ [--golden evaluation/golden/]

Reads ground truth annotations and extracted outputs, computes field-level
metrics, prints summary table, exits non-zero if regressions detected.
"""

import argparse
import json
import re
import sys
from dataclasses import dataclass, field
from pathlib import Path


# ---------------------------------------------------------------------------
# Data classes
# ---------------------------------------------------------------------------

@dataclass
class ValueMetrics:
    """Field-level metrics for a single value comparison."""

    test_name_match: bool = False
    value_match: bool = False
    unit_match: bool = False
    range_match: bool = False
    flag_match: bool = False
    section_match: bool = False


@dataclass
class ArchetypeScore:
    """Aggregate score for one archetype."""

    archetype: str
    total_expected: int = 0
    total_extracted: int = 0
    matched: int = 0
    value_metrics: list[ValueMetrics] = field(default_factory=list)

    # --- screening / HPLC sub-scores ---
    screening_expected: int = 0
    screening_matched: int = 0
    hplc_expected: int = 0
    hplc_category_matched: int = 0

    @property
    def recall(self) -> float:
        return self.matched / self.total_expected if self.total_expected else 0

    @property
    def precision(self) -> float:
        return self.matched / self.total_extracted if self.total_extracted else 0

    @property
    def section_accuracy(self) -> float:
        if not self.value_metrics:
            return 0
        return (
            sum(1 for m in self.value_metrics if m.section_match)
            / len(self.value_metrics)
        )

    @property
    def value_accuracy(self) -> float:
        if not self.value_metrics:
            return 0
        return (
            sum(1 for m in self.value_metrics if m.value_match)
            / len(self.value_metrics)
        )

    @property
    def unit_accuracy(self) -> float:
        if not self.value_metrics:
            return 0
        return (
            sum(1 for m in self.value_metrics if m.unit_match)
            / len(self.value_metrics)
        )


# ---------------------------------------------------------------------------
# Normalization helpers
# ---------------------------------------------------------------------------

def normalize_test_name(name: str) -> str:
    """Normalize test name for fuzzy matching."""
    name = name.lower().strip()
    name = re.sub(r"\s*\[.*?\]", "", name)  # [Serum], [Whole blood]
    name = re.sub(r"\s*\(.*?\)", "", name)  # (NGSP), (IFCC)
    name = re.sub(r"[*#\u2020\u2021]", "", name)  # footnote markers
    name = re.sub(r"\s+", " ", name).strip()
    return name


# ---------------------------------------------------------------------------
# Comparison functions
# ---------------------------------------------------------------------------

def match_value(
    expected: dict, extracted: dict, tolerance: float = 0.05
) -> ValueMetrics:
    """Compare a single expected value against its extracted counterpart."""
    metrics = ValueMetrics()

    # Test name (fuzzy)
    metrics.test_name_match = normalize_test_name(
        expected["test_name"]
    ) == normalize_test_name(extracted.get("test_name", ""))

    # Value: numeric tolerance or case-insensitive string
    ev, xv = expected["value"], extracted.get("value")
    if isinstance(ev, (int, float)) and isinstance(xv, (int, float)):
        if ev == 0:
            metrics.value_match = xv == 0
        else:
            metrics.value_match = abs(ev - xv) / abs(ev) <= tolerance
    else:
        metrics.value_match = (
            str(ev).lower().strip() == str(xv).lower().strip()
        )

    # Unit (exact after lower + strip)
    eu = (expected.get("unit") or "").lower().strip()
    xu = (extracted.get("unit") or "").lower().strip()
    metrics.unit_match = eu == xu or (not eu and not xu)

    # Range bounds (within tolerance)
    range_ok = True
    for bound in ("reference_range_low", "reference_range_high"):
        eb = expected.get(bound)
        xb = extracted.get(bound)
        if eb is not None and xb is not None:
            if eb == 0:
                if xb != 0:
                    range_ok = False
            elif abs(eb - xb) / abs(eb) > tolerance:
                range_ok = False
    metrics.range_match = range_ok

    # Flag (exact, upper)
    ef = (expected.get("flag") or "").upper()
    xf = (extracted.get("flag") or "").upper()
    metrics.flag_match = ef == xf

    # Section type
    metrics.section_match = expected.get("section_type") == extracted.get(
        "section_type", "standard_lab_table"
    )

    return metrics


def score_archetype(gt_path: Path, output_path: Path) -> ArchetypeScore:
    """Score one archetype: compare ground truth vs extracted output."""
    gt = json.loads(gt_path.read_text())
    output = json.loads(output_path.read_text())

    score = ArchetypeScore(archetype=gt["archetype"])
    expected = gt["expected_values"]
    extracted = output.get("values", [])

    score.total_expected = len(expected)
    score.total_extracted = len(extracted)

    # Build lookup by normalized test name
    extracted_map: dict[str, list[dict]] = {}
    for x in extracted:
        key = normalize_test_name(x.get("test_name", ""))
        extracted_map.setdefault(key, []).append(x)

    for ev in expected:
        key = normalize_test_name(ev["test_name"])
        candidates = extracted_map.get(key, [])
        if candidates:
            xv = candidates.pop(0)
            metrics = match_value(ev, xv)
            score.value_metrics.append(metrics)
            if metrics.test_name_match:
                score.matched += 1

    # Screening sub-score
    gt_screening = gt.get("expected_screening", [])
    out_screening = output.get("screening_results", [])
    score.screening_expected = len(gt_screening)
    out_screen_map = {
        s.get("test_type", "").lower(): s for s in out_screening
    }
    for gs in gt_screening:
        key = gs["test_type"].lower()
        if key in out_screen_map:
            xs = out_screen_map[key]
            if gs["result_status"] == xs.get("result_status"):
                score.screening_matched += 1

    # HPLC sub-score
    gt_hplc = gt.get("expected_hplc", [])
    out_hplc = output.get("audit", {}).get("hplc_blocks", [])
    score.hplc_expected = len(gt_hplc)
    for i, gh in enumerate(gt_hplc):
        if i < len(out_hplc):
            xh = out_hplc[i]
            if gh["diabetes_category"] == xh.get("diabetes_category"):
                score.hplc_category_matched += 1

    return score


def check_regression(current: dict, golden_path: Path) -> list[str]:
    """Compare current output against golden output, return diff descriptions."""
    if not golden_path.exists():
        return []
    golden = json.loads(golden_path.read_text())
    diffs: list[str] = []

    golden_values = {
        normalize_test_name(v.get("test_name", "")): v
        for v in golden.get("values", [])
    }
    current_values = {
        normalize_test_name(v.get("test_name", "")): v
        for v in current.get("values", [])
    }

    # Missing values
    for key in golden_values:
        if key not in current_values:
            diffs.append(
                f"REGRESSION: '{key}' present in golden but missing in current"
            )

    # Value changes
    for key in golden_values:
        if key in current_values:
            gv = golden_values[key]
            cv = current_values[key]
            if gv.get("value") != cv.get("value"):
                diffs.append(
                    f"VALUE CHANGE: '{key}' "
                    f"golden={gv.get('value')} current={cv.get('value')}"
                )

    return diffs


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def print_summary(scores: list[ArchetypeScore]) -> None:
    """Print human-readable summary table."""
    print()
    print("=" * 88)
    print(
        f"{'Archetype':<28} {'Recall':>8} {'Precision':>10} "
        f"{'Value':>8} {'Unit':>8} {'Section':>9} {'Screen':>8} {'HPLC':>7}"
    )
    print("-" * 88)
    for s in scores:
        scr = (
            f"{s.screening_matched}/{s.screening_expected}"
            if s.screening_expected
            else "-"
        )
        hplc = (
            f"{s.hplc_category_matched}/{s.hplc_expected}"
            if s.hplc_expected
            else "-"
        )
        print(
            f"{s.archetype:<28} {s.recall:>7.1%} {s.precision:>9.1%} "
            f"{s.value_accuracy:>7.1%} {s.unit_accuracy:>7.1%} "
            f"{s.section_accuracy:>8.1%} {scr:>8} {hplc:>7}"
        )
    print("=" * 88)


def main() -> None:
    parser = argparse.ArgumentParser(description="LabLens evaluation scoring")
    parser.add_argument(
        "--ground-truth", required=True, help="Ground truth directory"
    )
    parser.add_argument(
        "--extracted", required=True, help="Extracted outputs directory"
    )
    parser.add_argument(
        "--golden", default=None, help="Golden outputs for regression"
    )
    args = parser.parse_args()

    gt_dir = Path(args.ground_truth)
    out_dir = Path(args.extracted)
    golden_dir = Path(args.golden) if args.golden else None

    scores: list[ArchetypeScore] = []
    regressions: list[str] = []

    for gt_file in sorted(gt_dir.glob("*.json")):
        archetype = gt_file.stem
        out_file = out_dir / f"{archetype}.json"
        if not out_file.exists():
            print(f"SKIP: {archetype} (no extracted output)")
            continue

        score = score_archetype(gt_file, out_file)
        scores.append(score)

        if golden_dir:
            golden_file = golden_dir / f"{archetype}.json"
            output_data = json.loads(out_file.read_text())
            diffs = check_regression(output_data, golden_file)
            regressions.extend(diffs)

    print_summary(scores)

    if regressions:
        print(f"\n{'!' * 60}")
        print(f"REGRESSIONS DETECTED: {len(regressions)}")
        for r in regressions:
            print(f"  - {r}")
        print(f"{'!' * 60}")
        sys.exit(1)

    print("\nAll checks passed.")
    sys.exit(0)


if __name__ == "__main__":
    main()
