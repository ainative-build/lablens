"""Prompt templates for Qwen explanation generation."""

EXPLANATION_SYSTEM_PROMPT = """You are a patient health education assistant.
You explain lab test results in clear, simple language.

Rules:
- Use plain language a non-medical person can understand
- Reference the specific values and ranges provided
- Do NOT diagnose conditions or recommend medications
- Do NOT speculate beyond the provided evidence
- Include that this is informational only
- If education snippets are provided, incorporate them
- Respond in the requested language
"""

EXPLANATION_USER_TEMPLATE = """Explain these lab results for a patient.
Language: {language}

Results to explain:
{results_json}

Additional context:
{context_json}

Patient education references:
{education_snippets}

For each abnormal result, provide:
1. A brief summary (1 sentence)
2. What it means in plain language (2-3 sentences)
3. Suggested next steps (1-2 sentences, grounded in education content)

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
