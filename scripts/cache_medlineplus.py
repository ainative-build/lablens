"""Fetch MedlinePlus content for LOINC codes, cache locally.

Usage: python scripts/cache_medlineplus.py --codes data/loinc/target-codes.txt
Rate limit: 0.7s delay between requests.

MedlinePlus Connect only supports en/es. FR/AR/VN are machine-translated via Qwen.
"""

import argparse
import json
import os
import time
from pathlib import Path

import httpx

CACHE_DIR = Path("data/medlineplus-cache")
BASE_URL = "https://connect.medlineplus.gov/service"
SUPPORTED_LANGS = {"en", "es"}
TRANSLATE_TARGETS = ["fr", "ar", "vn"]


def query_medlineplus(loinc_code: str, language: str = "en") -> dict | None:
    """Fetch MedlinePlus content for a LOINC code."""
    if language not in SUPPORTED_LANGS:
        raise ValueError(f"MedlinePlus does not support '{language}'. Use en or es.")
    url = (
        f"{BASE_URL}?mainSearchCriteria.v.c={loinc_code}"
        f"&mainSearchCriteria.v.cs=2.16.840.1.113883.6.1"
        f"&knowledgeResponseType=application/json"
        f"&informationRecipient.languageCode.c={language}"
    )
    resp = httpx.get(url, timeout=30)
    if resp.status_code == 200:
        return resp.json()
    return None


def translate_via_qwen(text: str, target_lang: str) -> str:
    """Machine-translate EN text to target language using Qwen."""
    from dashscope import Generation

    lang_names = {"fr": "French", "ar": "Arabic", "vn": "Vietnamese"}
    resp = Generation.call(
        model="qwen-plus",
        messages=[
            {
                "role": "system",
                "content": (
                    f"Translate the following medical education text to {lang_names[target_lang]}. "
                    "Preserve medical terms accurately."
                ),
            },
            {"role": "user", "content": text},
        ],
        api_key=os.getenv("LABLENS_DASHSCOPE_API_KEY"),
        result_format="message",
    )
    return resp.output.choices[0].message.content


def cache_responses(codes: list[str], skip_translate: bool = False):
    """Cache MedlinePlus responses and optionally translate."""
    CACHE_DIR.mkdir(parents=True, exist_ok=True)

    for code in codes:
        cache_file = CACHE_DIR / f"{code}-en.json"
        if not cache_file.exists():
            print(f"Fetching MedlinePlus for {code}...")
            result = query_medlineplus(code, language="en")
            if result:
                cache_file.write_text(json.dumps(result, indent=2))
                print(f"  Cached {cache_file.name}")
            else:
                print(f"  No results for {code}")
            time.sleep(0.7)

        if skip_translate or not cache_file.exists():
            continue

        en_data = json.loads(cache_file.read_text())
        entries = en_data.get("feed", {}).get("entry", [])
        if not entries:
            continue

        for lang in TRANSLATE_TARGETS:
            trans_file = CACHE_DIR / f"{code}-{lang}.json"
            if trans_file.exists():
                continue
            print(f"  Translating {code} → {lang}...")
            translated_entries = []
            for entry in entries:
                summary = entry.get("summary", {}).get("_value", "")
                if not summary:
                    continue
                translated = translate_via_qwen(summary, lang)
                entry_copy = dict(entry)
                entry_copy["summary"] = {"_value": translated}
                entry_copy["_provenance"] = "machine-translated"
                entry_copy["_source_language"] = "en"
                translated_entries.append(entry_copy)
                time.sleep(0.3)
            trans_data = dict(en_data)
            trans_data["feed"] = dict(en_data.get("feed", {}))
            trans_data["feed"]["entry"] = translated_entries
            trans_data["_language"] = lang
            trans_file.write_text(json.dumps(trans_data, indent=2))


def main():
    parser = argparse.ArgumentParser(description="Cache MedlinePlus content")
    parser.add_argument("--codes", required=True, help="File with LOINC codes (one per line)")
    parser.add_argument("--skip-translate", action="store_true", help="Skip machine translation")
    args = parser.parse_args()

    with open(args.codes) as f:
        codes = [line.strip() for line in f if line.strip() and not line.startswith("#")]

    print(f"Processing {len(codes)} LOINC codes...")
    cache_responses(codes, skip_translate=args.skip_translate)
    print("Done.")


if __name__ == "__main__":
    main()
