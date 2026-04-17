"""In-memory lookup tables for test name → LOINC code mapping.

Built at startup from common-aliases.yaml. Supports exact match and alias match
across EN/FR/AR/VN.
"""

import logging
from dataclasses import dataclass
from pathlib import Path

import yaml

from lablens._data_paths import data_path

logger = logging.getLogger(__name__)

ALIASES_PATH = data_path("aliases")


@dataclass
class TestIdentity:
    loinc_code: str
    canonical_name: str
    match_type: str  # "exact" | "alias"


class AliasRegistry:
    """In-memory lookup for test name → LOINC mapping."""

    def __init__(self, aliases_dir: Path | None = None):
        self._exact: dict[str, TestIdentity] = {}
        self._aliases: dict[str, TestIdentity] = {}
        self._load(aliases_dir or ALIASES_PATH)

    def _load(self, aliases_dir: Path):
        path = aliases_dir / "common-aliases.yaml"
        if not path.exists():
            logger.warning("Aliases file not found: %s", path)
            return

        data = yaml.safe_load(path.read_text())
        for entry in data.get("aliases", []):
            loinc = entry["loinc"]
            canonical = entry["canonical"]
            identity = TestIdentity(loinc, canonical, "exact")
            self._exact[canonical.lower()] = identity
            for _lang, names in entry.get("aliases", {}).items():
                for name in names:
                    key = name.lower().strip()
                    self._aliases[key] = TestIdentity(loinc, canonical, "alias")

        logger.info(
            "Loaded %d exact + %d alias entries",
            len(self._exact),
            len(self._aliases),
        )

    def lookup(self, test_name: str) -> TestIdentity | None:
        """Exact → alias → None."""
        key = test_name.lower().strip()
        if key in self._exact:
            return self._exact[key]
        if key in self._aliases:
            return self._aliases[key]
        return None

    @property
    def all_entries(self) -> list[tuple[str, str]]:
        """All known (name, loinc_code) pairs for fuzzy matching."""
        entries = []
        for key, identity in self._exact.items():
            entries.append((key, identity.loinc_code))
        for key, identity in self._aliases.items():
            entries.append((key, identity.loinc_code))
        return entries
