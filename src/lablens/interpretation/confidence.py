"""Composite confidence scoring for interpretation results.

Confidence = min(match_confidence, range_confidence, unit_confidence).
"""


def calculate_confidence(
    match_confidence: str,
    range_source: str,
    unit_confidence: str = "high",
) -> str:
    """Composite confidence: lowest of three dimensions.

    high = all three high. medium = at least one medium, none low. low = any low.
    """
    scores = {"high": 3, "medium": 2, "low": 1}
    range_conf_map = {
        "lab-provided": "high",
        "curated-fallback": "medium",
        "none": "low",
    }
    dimensions = [
        scores.get(match_confidence, 1),
        scores.get(range_conf_map.get(range_source, "low"), 1),
        scores.get(unit_confidence, 1),
    ]
    minimum = min(dimensions)
    if minimum >= 3:
        return "high"
    if minimum >= 2:
        return "medium"
    return "low"
