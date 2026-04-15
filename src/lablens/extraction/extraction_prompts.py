"""Language-specific extraction prompts for Qwen-OCR.

Each language has tailored hints for script direction, common test names, and units.
"""

_BASE_RULES = """
- Extract ONLY actual lab test results (analytes with measured values)
- Preserve original test names (do not translate or normalize)
- Preserve original units exactly as printed
- ALWAYS extract reference ranges from the report — look for columns labeled "Normal Range", "Ref Range", "Giá trị tham chiếu", "Valeurs normales", or similar
- If range is "3.5 - 5.0", split into reference_range_low=3.5 and reference_range_high=5.0
- If range is "< 200" or "<= 39", set reference_range_low=null and reference_range_high=200 (or 39)
- If range is "> 60" or ">= 90", set reference_range_low=60 (or 90) and reference_range_high=null
- If range has categories (e.g., "Desirable: < 5.18"), extract the numeric bound
- If value is non-numeric (e.g., "Positive", "Reactive"), keep as string
- If a field is unreadable, set to null
- Do NOT infer or calculate values not present in the report

IMPORTANT - DO NOT extract any of the following:
- Section headers or category labels (e.g., "GENETICS", "Lipid Panel")
- Patient metadata (name, ID, date of birth, doctor, sample date, collection site)
- Lab methodology or analysis descriptions (how tests are performed)
- Marketing text, lab certifications, statistics, or promotional content
- Organ names from screening charts without individual test values
- Sample processing information (reagents, equipment, procedures)
- Free-text paragraphs explaining results or procedures
- JSON schema examples or template placeholders
Only extract rows that have a test_name AND a measured value (numeric or qualitative like Positive/Negative).
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
