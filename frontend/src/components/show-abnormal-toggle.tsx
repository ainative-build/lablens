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
 *
 * Implementation notes:
 *   The whole control (label text + pill) is a single `<button role="switch">`
 *   so a click anywhere fires exactly one toggle. The earlier version wrapped
 *   the button in a `<label>` — that pattern double-fires on click in most
 *   browsers (label re-dispatches click on its first interactive descendant)
 *   so the toggle appeared to do nothing.
 */
export function ShowAbnormalToggle({ value, onChange, language }: Props) {
  return (
    <button
      type="button"
      role="switch"
      aria-checked={value}
      onClick={() => onChange(!value)}
      className="inline-flex items-center gap-2 text-sm text-[var(--foreground)] select-none rounded-md px-1 -mx-1 focus-visible:outline focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-[var(--color-brand-500)] cursor-pointer"
    >
      <span>{t("filter.show_abnormal_only", language)}</span>
      <span
        aria-hidden
        className={`relative inline-flex h-5 w-9 items-center rounded-full transition-colors ${
          value
            ? "bg-[var(--color-brand-500)]"
            : "bg-[var(--color-surface-sunken)] border border-[var(--color-border-strong)]"
        }`}
      >
        <span
          className={`inline-block h-4 w-4 transform rounded-full bg-white shadow transition-transform ${
            value ? "translate-x-4" : "translate-x-0.5"
          }`}
        />
      </span>
    </button>
  );
}
