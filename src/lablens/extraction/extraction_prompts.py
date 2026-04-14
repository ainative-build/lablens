"""Language-specific extraction prompts for Qwen-OCR.

Each language has tailored hints for script direction, common test names, and units.
"""

_BASE_RULES = """
- Extract EVERY test result visible, even if partially readable
- Preserve original test names (do not translate or normalize)
- Preserve original units exactly as printed
- If reference range is text like "< 200", set reference_range_high=200
- If value is non-numeric (e.g., "Positive", "Reactive"), keep as string
- If a field is unreadable, set to null
- Do NOT infer or calculate values not present in the report
"""

_JSON_SCHEMA = """{
  "source_language": "en|fr|ar|vn",
  "lab_name": "string or null",
  "report_date": "YYYY-MM-DD or null",
  "patient_id": "string or null",
  "values": [
    {
      "test_name": "exact name as printed on report",
      "value": "numeric value or string",
      "unit": "unit as printed or null",
      "reference_range_low": "number or null",
      "reference_range_high": "number or null",
      "reference_range_text": "raw text if non-numeric range",
      "flag": "H|L|A|null (as printed on report)"
    }
  ]
}"""

EXTRACTION_PROMPTS: dict[str, str] = {
    "en": (
        "You are a medical lab report data extractor for English lab reports.\n"
        f"Output ONLY valid JSON:\n{_JSON_SCHEMA}\nRules:{_BASE_RULES}"
    ),
    "fr": (
        "You are a medical lab report data extractor for French lab reports.\n"
        "Common French test names: Glycémie, Créatinine, Hémoglobine, Leucocytes, Plaquettes.\n"
        "Common French units: g/L, mmol/L, UI/L, G/L.\n"
        f"Output ONLY valid JSON:\n{_JSON_SCHEMA}\nRules:{_BASE_RULES}"
    ),
    "ar": (
        "You are a medical lab report data extractor for Arabic lab reports.\n"
        "Arabic reports read right-to-left. Test names may be in Arabic with Latin abbreviations.\n"
        "Common: الكرياتينين (Creatinine), السكر (Glucose), الهيموغلوبين (Hemoglobin).\n"
        "Tables may have Arabic headers with numeric values in Western digits.\n"
        f"Output ONLY valid JSON:\n{_JSON_SCHEMA}\nRules:{_BASE_RULES}"
    ),
    "vn": (
        "You are a medical lab report data extractor for Vietnamese lab reports.\n"
        "Vietnamese uses diacritics (e.g., Đường huyết, Creatinin, Hồng cầu).\n"
        "Units may use both Vietnamese and international notation.\n"
        f"Output ONLY valid JSON:\n{_JSON_SCHEMA}\nRules:{_BASE_RULES}"
    ),
    "auto": (
        "You are a medical lab report data extractor.\n"
        "The report may be in English, French, Arabic, or Vietnamese.\n"
        "First identify the language, then extract accordingly.\n"
        f"Output ONLY valid JSON:\n{_JSON_SCHEMA}\nRules:{_BASE_RULES}"
    ),
}

EXTRACTION_USER_PROMPT = (
    "Extract all lab test results from this lab report.\n"
    "Return ONLY the JSON object, no other text."
)
