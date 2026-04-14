"use client";

import { type Language, LANGUAGE_LABELS, SUPPORTED_LANGUAGES } from "@/lib/i18n";

interface Props {
  value: Language;
  onChange: (lang: Language) => void;
}

export function LanguageSelector({ value, onChange }: Props) {
  return (
    <select
      value={value}
      onChange={(e) => onChange(e.target.value as Language)}
      className="rounded border border-gray-300 px-3 py-1.5 text-sm bg-white"
    >
      {SUPPORTED_LANGUAGES.map((lang) => (
        <option key={lang} value={lang}>
          {LANGUAGE_LABELS[lang]}
        </option>
      ))}
    </select>
  );
}
