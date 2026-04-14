"""Panel completeness checker.

Identifies which common panels are partially represented in a report
and flags missing tests.
"""

from lablens.interpretation.models import PanelCompleteness

PANELS: dict[str, dict] = {
    "CBC": {
        "expected": ["6690-2", "789-8", "718-7", "4544-3", "777-3"],
    },
    "BMP": {
        "expected": [
            "2345-7", "3094-0", "2160-0", "2951-2",
            "2823-3", "2075-0", "2028-9", "17861-6",
        ],
    },
    "Lipid Panel": {
        "expected": ["2093-3", "2085-9", "13457-7", "2571-8"],
    },
    "Thyroid Panel": {
        "expected": ["3016-3", "3024-7"],
    },
}


def check_panels(
    present_codes: list[str], rules: dict
) -> list[PanelCompleteness]:
    """Check which panels are partially represented and what's missing."""
    results = []
    present_set = set(present_codes)

    for panel_name, panel in PANELS.items():
        expected = set(panel["expected"])
        found = expected & present_set
        if len(found) >= 2:  # At least 2 tests from panel present
            missing = expected - found
            results.append(
                PanelCompleteness(
                    panel_name=panel_name,
                    expected=sorted(expected),
                    present=sorted(found),
                    missing=sorted(missing),
                )
            )

    return results
