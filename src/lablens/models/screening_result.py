"""Structured schema for ctDNA/MCED screening results.

Screening results are fundamentally different from standard lab analytes:
- No numeric value / reference range / unit pattern
- Result is qualitative: Detected / Not Detected / Indeterminate
- Includes free-text fields: signal origin, limitations, follow-up
- Bypasses interpretation engine entirely (Contract D)
"""

from dataclasses import dataclass, field
from enum import Enum


class ScreeningStatus(str, Enum):
    DETECTED = "detected"
    NOT_DETECTED = "not_detected"
    INDETERMINATE = "indeterminate"


@dataclass
class ScreeningResult:
    """Single screening test result from an attachment page."""

    test_type: str  # e.g., "SPOT-MAS", "Galleri"
    result_status: ScreeningStatus = ScreeningStatus.INDETERMINATE
    signal_origin: str | None = None  # e.g., "Colorectal" if detected
    organs_screened: list[str] = field(default_factory=list)
    limitations: str | None = None  # Sensitivity/specificity caveats
    followup_recommendation: str | None = None
    raw_text: str | None = None  # Original extracted text for audit
    confidence: float = 0.0  # 0.0-1.0
