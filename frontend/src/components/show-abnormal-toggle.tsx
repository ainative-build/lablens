"use client";

import type { Language } from "@/lib/i18n";
import { t } from "@/lib/i18n";

interface Props {
  value: boolean;
  onChange: (next: boolean) => void;
  language: Language;
}

/**
 * Page-level "Show abnormal only" iOS-style switch.
 * a11y: <button role="switch" aria-checked>.
 */
export function ShowAbnormalToggle({ value, onChange, language }: Props) {
  return (
    <label className="inline-flex items-center gap-2 text-sm text-[var(--foreground)] cursor-pointer select-none">
      <span>{t("filter.show_abnormal_only", language)}</span>
      <button
        type="button"
        role="switch"
        aria-checked={value}
        onClick={() => onChange(!value)}
        className={`relative inline-flex h-5 w-9 items-center rounded-full transition-colors focus-visible:outline focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-[var(--color-brand-500)] ${
          value
            ? "bg-[var(--color-brand-500)]"
            : "bg-[var(--color-surface-sunken)]"
        }`}
      >
        <span
          aria-hidden
          className={`inline-block h-4 w-4 transform rounded-full bg-white shadow transition-transform ${
            value ? "translate-x-4" : "translate-x-0.5"
          }`}
        />
      </button>
    </label>
  );
}
