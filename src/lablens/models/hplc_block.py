"""Structured HPLC block schema for HbA1c/IFCC/eAG.

IMPORTANT: HPLCBlock is audit metadata, NOT a second truth object.
The canonical analyte truth is always the LabValue in values[].
HPLCBlock governs interpretation routing (diabetes_category,
cross_check_passed) but does not replace or duplicate LabValues.
"""

from dataclasses import dataclass, field
from enum import Enum


class DiabetesCategory(str, Enum):
    NORMAL = "normal"
    PREDIABETES = "prediabetes"
    DIABETES = "diabetes"
    INDETERMINATE = "indeterminate"


@dataclass
class HPLCAnalyte:
    """Single analyte within the HPLC block."""

    test_name: str
    value: float | None
    unit: str | None
    reference_range_low: float | None = None
    reference_range_high: float | None = None
    source: str = "ocr"  # ocr | re-extracted


@dataclass
class HPLCBlock:
    """Coherent HPLC diabetes block with cross-validation."""

    ngsp: HPLCAnalyte | None = None
    ifcc: HPLCAnalyte | None = None
    eag: HPLCAnalyte | None = None
    eag_unit: str = "mg/dL"

    diabetes_category: DiabetesCategory = DiabetesCategory.INDETERMINATE
    consistency_flags: list[str] = field(default_factory=list)
    cross_check_passed: bool = False
    completeness: int = 0  # 0-3: how many analytes found
