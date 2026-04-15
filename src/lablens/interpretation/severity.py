"""Severity assessment, panic thresholds, and actionability mapping.

Handles Steps 3-5 of the 8-step interpretation pipeline:
severity bands, panic check, and actionability assignment.
"""

# Maps YAML severity band names to severity tiers
SEVERITY_TIERS = {
    "normal": "normal",
    "mild_low": "mild",
    "mild_high": "mild",
    "moderate_low": "moderate",
    "moderate_high": "moderate",
    "critical_low": "critical",
    "critical_high": "critical",
}

# Maps severity tiers to default actionability
DEFAULT_ACTIONABILITY = {
    "normal": "routine",
    "mild": "monitor",
    "moderate": "consult",
    "critical": "urgent",
}


def apply_severity(value: float, rule: dict | None) -> str:
    """Step 3: Map value to severity band.

    If value falls in a band gap, return based on whether
    it's outside the normal range (not silently 'normal').
    """
    if not rule or "severity_bands" not in rule:
        return "normal"

    bands = rule["severity_bands"]
    # Check bands in priority order (most severe first)
    for band_name in [
        "critical_low", "critical_high",
        "moderate_low", "moderate_high",
        "mild_low", "mild_high",
        "normal",
    ]:
        band = bands.get(band_name)
        if band and band["low"] <= value <= band["high"]:
            return SEVERITY_TIERS.get(band_name, "normal")

    # Band gap fallback
    normal_band = bands.get("normal")
    if normal_band and not (normal_band["low"] <= value <= normal_band["high"]):
        return "moderate"  # Outside normal, no band matched
    return "normal"


def check_panic(value: float, rule: dict | None) -> bool:
    """Step 4: Check panic thresholds."""
    if not rule or "panic_thresholds" not in rule:
        return False
    panic = rule["panic_thresholds"]
    return (
        value <= panic.get("low", float("-inf"))
        or value >= panic.get("high", float("inf"))
    )


def heuristic_severity(value: float, ref_low: float, ref_high: float) -> str:
    """Estimate severity from deviation % when no curated severity bands exist."""
    range_span = ref_high - ref_low
    if range_span <= 0:
        return "mild"
    if value < ref_low:
        deviation = (ref_low - value) / range_span
    else:
        deviation = (value - ref_high) / range_span
    if deviation <= 0.1:
        return "mild"
    return "moderate"
