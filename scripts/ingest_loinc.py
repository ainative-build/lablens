"""Parse loinc.csv and load top common lab tests into GDB.

Usage: python scripts/ingest_loinc.py --csv data/loinc/loinc.csv --gdb-endpoint ws://host:8182/gremlin
Without --gdb-endpoint, prints parsed tests to stdout (dry run).
"""

import argparse
import csv
import json
import sys

TARGET_CLASSES = {"CHEM", "HEM/BC", "UA", "SERO"}


def parse_loinc_csv(csv_path: str, target_codes: set[str] | None = None) -> list[dict]:
    """Parse loinc.csv, return dicts for target lab tests."""
    results = []
    with open(csv_path, encoding="utf-8") as f:
        reader = csv.DictReader(f)
        for row in reader:
            if row.get("STATUS") != "ACTIVE":
                continue
            if row.get("CLASSTYPE") != "1":
                continue
            loinc_num = row.get("LOINC_NUM", "")
            if target_codes and loinc_num not in target_codes:
                if row.get("CLASS", "") not in TARGET_CLASSES:
                    continue
            results.append({
                "loinc_code": loinc_num,
                "component": row.get("COMPONENT", ""),
                "long_common_name": row.get("LONG_COMMON_NAME", ""),
                "short_name": row.get("SHORTNAME", ""),
                "property": row.get("PROPERTY", ""),
                "system": row.get("SYSTEM", ""),
                "scale_type": row.get("SCALE_TYP", ""),
                "class_field": row.get("CLASS", ""),
                "consumer_name": row.get("CONSUMER_NAME", ""),
            })
    return results


def load_to_gdb(tests: list[dict], gdb_endpoint: str):
    """Upsert LabTest nodes into GDB (idempotent)."""
    from gremlin_python.driver.driver_remote_connection import DriverRemoteConnection
    from gremlin_python.process.anonymous_traversal import traversal

    conn = DriverRemoteConnection(gdb_endpoint, "g")
    g = traversal().with_remote(conn)
    for test in tests:
        g.V().has("LabTest", "loinc_code", test["loinc_code"]).drop().iterate()
        t = g.addV("LabTest")
        for key, val in test.items():
            t = t.property(key, val)
        t.iterate()
    conn.close()
    print(f"Loaded {len(tests)} LabTest nodes into GDB")


def main():
    parser = argparse.ArgumentParser(description="Ingest LOINC CSV into GDB")
    parser.add_argument("--csv", required=True, help="Path to loinc.csv")
    parser.add_argument("--gdb-endpoint", help="GDB Gremlin endpoint (ws://host:port/gremlin)")
    parser.add_argument("--codes-file", help="File with target LOINC codes (one per line)")
    args = parser.parse_args()

    target_codes = None
    if args.codes_file:
        with open(args.codes_file) as f:
            target_codes = {line.strip() for line in f if line.strip()}

    tests = parse_loinc_csv(args.csv, target_codes)
    print(f"Parsed {len(tests)} lab tests from LOINC CSV")

    if args.gdb_endpoint:
        load_to_gdb(tests, args.gdb_endpoint)
    else:
        print("Dry run (no --gdb-endpoint). Sample output:")
        for t in tests[:5]:
            print(json.dumps(t, indent=2))


if __name__ == "__main__":
    main()
