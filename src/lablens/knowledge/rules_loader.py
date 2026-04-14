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
            for rule in panel_rules:
                loinc_code = rule.get("loinc_code")
                if loinc_code:
                    rules[loinc_code] = rule
                    logger.debug("Loaded rule for %s (%s)", loinc_code, rule.get("test_name", ""))

    logger.info("Loaded %d interpretation rules from %s", len(rules), directory)
    return rules


def get_rule(loinc_code: str, rules: dict[str, dict]) -> dict | None:
    """Look up a single rule by LOINC code."""
    return rules.get(loinc_code)
