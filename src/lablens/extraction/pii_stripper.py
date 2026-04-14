"""Strip patient identifiers before external API calls.

Regex-based PII redaction (Finding #2). Clears patient_id and raw_text
before data reaches DashScope explanation API.
"""

import logging
import re

from lablens.models.lab_report import LabReport

logger = logging.getLogger(__name__)

_PII_PATTERNS = [
    (re.compile(r"\b\d{3}[-.\s]?\d{2}[-.\s]?\d{4}\b"), "[SSN]"),
    (re.compile(r"\b[A-Z][a-z]+,?\s+[A-Z][a-z]+\b"), "[NAME]"),
    (re.compile(r"\b\d{10,}\b"), "[ID]"),
    (re.compile(r"\b[\w.+-]+@[\w-]+\.[a-z]{2,}\b"), "[EMAIL]"),
    (re.compile(r"\b\d{3}[-.\s]\d{3}[-.\s]\d{4}\b"), "[PHONE]"),
]


def strip_pii_from_text(text: str) -> str:
    """Apply regex PII patterns to a text string."""
    for pattern, replacement in _PII_PATTERNS:
        text = pattern.sub(replacement, text)
    return text


def strip_pii_from_report(report: LabReport) -> LabReport:
    """Return a copy of LabReport with PII fields cleared."""
    stripped = report.model_copy(deep=True)
    stripped.patient_id = None
    stripped.raw_text = None
    logger.info("PII stripped from report before external API call")
    return stripped
