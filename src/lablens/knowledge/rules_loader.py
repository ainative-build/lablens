"""Load interpretation rules from YAML files.

Rules are organized by panel (cbc.yaml, bmp.yaml, etc.) and indexed by LOINC code.
Each rule contains reference ranges, severity bands, and actionability mappings.
"""

import logging
from pathlib import Path

import yaml

logger = logging.getLogger(__name__)

RULES_DIR = Path(__file__).parent.parent.parent.parent / "data" / "rules"


def load_all_rules(rules_dir: Path | None = None) -> dict[str, dict]:
    """Load all YAML rule files into {loinc_code: rule_dict}.

    Args:
        rules_dir: Override directory for rules. Defaults to data/rules/.

    Returns:
        Dict mapping LOINC codes to their interpretation rules.
    """
    directory = rules_dir or RULES_DIR
    rules: dict[str, dict] = {}

    if not directory.exists():
        logger.warning("Rules directory not found: %s", directory)
        return rules

    for yaml_file in sorted(directory.glob("*.yaml")):
        with open(yaml_file) as f:
            panel_rules = yaml.safe_load(f)
            if not panel_rules:
                continue
            if not isinstance(panel_rules, list):
                continue
            for rule in panel_rules:
                loinc_code = rule.get("loinc_code")
                if loinc_code:
                    rules[loinc_code] = rule
                    logger.debug("Loaded rule for %s (%s)", loinc_code, rule.get("test_name", ""))

    logger.info("Loaded %d interpretation rules from %s", len(rules), directory)
    return rules


_qualitative_rules: dict | None = None


def load_qualitative_rules(rules_dir: Path | None = None) -> dict:
    """Load qualitative test rules from YAML (separate from panel rules).

    Returns: {"tests": {loinc: rule_dict}, "value_aliases": {str: str}}
    """
    global _qualitative_rules
    if _qualitative_rules is not None:
        return _qualitative_rules
    directory = rules_dir or RULES_DIR
    path = directory / "qualitative.yaml"
    if not path.exists():
        logger.warning("Qualitative rules not found: %s", path)
        return {"tests": {}, "value_aliases": {}}
    data = yaml.safe_load(path.read_text())
    _qualitative_rules = data or {"tests": {}, "value_aliases": {}}
    logger.info("Loaded %d qualitative rules", len(_qualitative_rules.get("tests", {})))
    return _qualitative_rules


def get_rule(loinc_code: str, rules: dict[str, dict]) -> dict | None:
    """Look up a single rule by LOINC code."""
    return rules.get(loinc_code)
