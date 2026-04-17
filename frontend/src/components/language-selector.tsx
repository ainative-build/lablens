"use client";

import { type Language, LANGUAGE_LABELS, SUPPORTED_LANGUAGES } from "@/lib/i18n";

interface Props {
  value: Language;
  onChange: (lang: Language) => void;
}

/**
 * Native <select> styled with brand tokens. Lives in the top header.
 * Uses tokens so light + dark themes both look right with no extra code.
 */
export function LanguageSelector({ value, onChange }: Props) {
  return (
    <select
      value={value}
      onChange={(e) => onChange(e.target.value as Language)}
      aria-label="Language"
      className="rounded-md border border-[var(--color-border-strong)] bg-[var(--color-surface)] text-[var(--foreground)] px-3 py-1.5 text-sm font-medium hover:border-[var(--color-brand-500)] focus-visible:outline focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-[var(--color-brand-500)] cursor-pointer"
    >
      {SUPPORTED_LANGUAGES.map((lang) => (
        <option key={lang} value={lang}>
          {LANGUAGE_LABELS[lang]}
        </option>
      ))}
    </select>
  );
}
