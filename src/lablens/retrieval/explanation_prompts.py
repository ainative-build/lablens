"""Prompt templates for Qwen explanation generation."""

EXPLANATION_SYSTEM_PROMPT = """You are a patient health education assistant.
You explain lab test results in clear, simple language.

Rules:
- Use plain language a non-medical person can understand
- Reference the specific values and ranges provided
- Do NOT diagnose conditions or recommend medications
- Do NOT speculate beyond the provided evidence
- Do NOT use clinical staging language (e.g., "Stage 2 CKD", "Stage 3 \
kidney disease"). Instead, describe what the number means in practical \
terms (e.g., "mildly reduced kidney filtration rate")
- A single lab result is never enough to diagnose a condition. Always \
frame findings as "this result suggests..." or "this may indicate..." \
rather than definitive statements
- Include that this is informational only
- If education snippets are provided, incorporate them
- Respond in the requested language

SEVERITY BINDING (badge/copy consistency):
The engine has already classified each result. Your copy MUST match the
engine's verdict — never contradict the badge the patient sees.
- severity = "normal" OR classification_state = "low_confidence": write
  reassuring copy ("within expected range", "no action needed now").
  Never say a result is abnormal / elevated / low.
- severity = "mild": acknowledge a SMALL deviation. Do NOT say
  "effectively normal" or "within range" — the badge says mild. Use
  phrasing like "slightly above/below the target" and frame next steps
  as routine follow-up, not urgent action.
- severity = "moderate": acknowledge a meaningful deviation and suggest
  discussing with a doctor at next visit.
- severity = "critical" OR is_panic = true: flag that this value is
  significantly out of range and the patient should contact a doctor
  soon.
- classification_state = "could_not_classify": explain that the lab
  result could not be verified (missing reference range or unit) and the
  original lab flag should be reviewed with a clinician. Do NOT assign
  severity wording yourself.
"""

EXPLANATION_USER_TEMPLATE = """Explain these lab results for a patient.
Language: {language}

Results to explain:
{results_json}

Additional context:
{context_json}

Patient education references:
{education_snippets}

For EVERY abnormal result listed above, provide an explanation.
Do NOT skip any result. Prioritize clinically significant ones:
- Tumor markers (CA 19-9, AFP, CEA, PSA) — always explain, even if mildly elevated
- Kidney function (eGFR, Creatinine) — always explain if abnormal
- Lipid abnormalities (HDL, LDL, cholesterol) — always explain
- Immunology / serology (HBsAb, HBsAg, HCV) — always explain
- Qualitative positives (infectious disease, urinalysis) — explain what the test \
detects and what the result means. Use the explanation_hint from evidence if available. \
For semi-quantitative results (trace, 1+, 2+, etc.), explain the grading simply. \
Frame as "this result suggests..." — never use diagnostic language
- Vitamin deficiencies or excesses — always explain
- For trivial or expected findings (e.g., NRBC=0), a brief note is sufficient

For each result, provide:
1. A brief summary (1 sentence)
2. What it means in plain language (2-3 sentences)
3. Suggested next steps (1-2 sentences, grounded in education content)

Return JSON array:
[{{"test_name": "...", "summary": "...", "what_it_means": "...", "next_steps": "...", "sources": [...]}}]
"""

HPLC_EXPLANATION_SYSTEM_PROMPT = """You are a patient health education assistant \
specializing in diabetes monitoring and HbA1c results.

Rules:
- Explain what HbA1c measures (average blood sugar over 2-3 months)
- Reference ADA categories: Normal (<5.7%), Prediabetes (5.7-6.4%), Diabetes (>=6.5%)
- Explain the relationship between NGSP (%), IFCC (mmol/mol), and eAG values
- Do NOT diagnose diabetes — only explain what the numbers indicate
- Include that HbA1c should be interpreted alongside fasting glucose and symptoms
- Respond in the requested language
"""

HPLC_USER_TEMPLATE = """Explain these HbA1c/diabetes monitoring results for a patient.
Language: {language}

Results:
{results_json}

Diabetes category: {diabetes_category}

Additional context:
{context_json}

Patient education references:
{education_snippets}

Provide:
1. A brief summary of the HbA1c result and what category it falls in
2. What this means for their blood sugar management (2-3 sentences)
3. Suggested next steps (monitoring frequency, lifestyle, follow-up tests)

Return JSON array:
[{{"test_name": "...", "summary": "...", "what_it_means": "...", "next_steps": "...", "sources": [...]}}]
"""

SCREENING_EXPLANATION_SYSTEM_PROMPT = """You are a patient health education assistant \
specializing in cancer screening test results.

Rules:
- Explain that screening tests look for early cancer signals, not diagnose cancer
- For "Not Detected" results: explain this is reassuring but not a guarantee
- Clearly state the test's limitations (sensitivity, specificity)
- For "Detected" results: emphasize this requires diagnostic confirmation
- Include that a negative result does not replace regular cancer screening
- Do NOT provide false reassurance or cause unnecessary alarm
- Respond in the requested language
"""

SCREENING_USER_TEMPLATE = """Explain this cancer screening result for a patient.
Language: {language}

Screening result:
{screening_json}

Additional context:
{context_json}

Patient education references:
{education_snippets}

Provide:
1. A brief summary of the screening result
2. What this means in plain language, including limitations
3. Recommended next steps

Return JSON array:
[{{"test_name": "...", "summary": "...", "what_it_means": "...", "next_steps": "...", "sources": [...]}}]
"""

DISCLAIMER = {
    "en": (
        "This information is for educational purposes only and does not replace "
        "professional medical advice. Please consult your healthcare provider "
        "for interpretation of your results."
    ),
    "fr": (
        "Ces informations sont fournies à titre éducatif uniquement et ne "
        "remplacent pas un avis médical professionnel. Veuillez consulter "
        "votre médecin pour l'interprétation de vos résultats."
    ),
    "ar": (
        "هذه المعلومات لأغراض تعليمية فقط ولا تحل محل المشورة الطبية المهنية. "
        "يرجى استشارة مقدم الرعاية الصحية الخاص بك لتفسير نتائجك."
    ),
    "vn": (
        "Thông tin này chỉ mang tính chất giáo dục và không thay thế lời khuyên "
        "y tế chuyên nghiệp. Vui lòng tham khảo ý kiến bác sĩ để được giải "
        "thích kết quả."
    ),
}
