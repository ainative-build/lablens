"""Composite confidence scoring for interpretation results.

Confidence = min(match, range, unit) with lab-provided range boost.
Lab-provided ranges are the most trustworthy source (from the lab's own report),
so they compensate for weak LOINC match confidence.
"""


def calculate_confidence(
    match_confidence: str,
    range_source: str,
    unit_confidence: str = "high",
) -> str:
    """Composite confidence from three dimensions.

    When lab-provided ranges exist, match confidence is boosted to at least
    medium — the lab's own ranges don't need LOINC matching to be trustworthy.
    """
    scores = {"high": 3, "medium": 2, "low": 1}
    range_conf_map = {
        "lab-provided": "high",
        "curated-fallback": "medium",
        "none": "low",
    }

    match_score = scores.get(match_confidence, 1)
    range_score = scores.get(range_conf_map.get(range_source, "low"), 1)
    unit_score = scores.get(unit_confidence, 1)

    # Lab-provided ranges are self-sufficient — match quality matters less
    if range_source == "lab-provided":
        match_score = max(match_score, 2)

    minimum = min(match_score, range_score, unit_score)
    if minimum >= 3:
        return "high"
    if minimum >= 2:
        return "medium"
    return "low"
