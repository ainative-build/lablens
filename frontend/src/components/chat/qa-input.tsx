"use client";

import { useState } from "react";
import type { Language } from "@/lib/i18n";
import { t } from "@/lib/i18n";

interface Props {
  disabled: boolean;
  /** When true, render an inline spinner + "Sending..." label on the send button.
   * `disabled` should usually also be true while pending. */
  pending?: boolean;
  language: Language;
  onSubmit: (question: string) => void;
  initialValue?: string;
}

const MAX_LEN = 500;

export function QaInput({
  disabled,
  pending = false,
  language,
  onSubmit,
  initialValue = "",
}: Props) {
  const [value, setValue] = useState(initialValue);

  const submit = () => {
    const q = value.trim();
    if (!q || disabled) return;
    onSubmit(q);
    setValue("");
  };

  // Use Intl.Segmenter for grapheme-correct length on multi-byte scripts.
  const count = (() => {
    if (typeof Intl !== "undefined" && "Segmenter" in Intl) {
      try {
        const seg = new (Intl as unknown as {
          Segmenter: new (l: string, o: Record<string, unknown>) => {
            segment(s: string): Iterable<unknown>;
          };
        }).Segmenter(language, { granularity: "grapheme" });
        return Array.from(seg.segment(value)).length;
      } catch {
        return value.length;
      }
    }
    return value.length;
  })();

  // Counter color shifts to brand-green as user nears the limit, so it acts
  // as a positive progress indicator rather than just a static label.
  const nearLimit = count > MAX_LEN * 0.8;
  const atLimit = count >= MAX_LEN;
  const counterClass = atLimit
    ? "text-rose-600 dark:text-rose-400 font-medium"
    : nearLimit
      ? "text-[var(--color-brand-700)] dark:text-[var(--color-brand-500)]"
      : "text-[var(--foreground-muted)]";

  const canSubmit = !disabled && value.trim().length > 0;

  return (
    <div className="border-t border-[var(--color-border)] p-3 bg-[var(--color-surface-muted)]">
      <label className="sr-only" htmlFor="qa-input">
        {t("chat.placeholder", language)}
      </label>
      {/* Composer wrapper — single rounded card containing textarea + actions
          row. Outer ring shifts to brand-green on focus-within so the whole
          surface (not just the textarea) lights up. */}
      <div className="rounded-[var(--radius-card)] border border-[var(--color-border-strong)] bg-[var(--color-surface)] shadow-[var(--shadow-card)] focus-within:border-[var(--color-brand-500)] focus-within:ring-2 focus-within:ring-[var(--color-brand-500)]/20 transition-colors">
        <textarea
          id="qa-input"
          value={value}
          onChange={(e) => setValue(e.target.value.slice(0, MAX_LEN))}
          onKeyDown={(e) => {
            if (e.key === "Enter" && !e.shiftKey) {
              e.preventDefault();
              submit();
            }
          }}
          disabled={disabled}
          placeholder={t("chat.placeholder", language)}
          rows={2}
          className="block w-full resize-none bg-transparent border-0 text-sm leading-relaxed text-[var(--foreground)] placeholder:text-[var(--foreground-muted)] px-3 pt-3 pb-1 focus:outline-none disabled:opacity-60"
        />
        <div className="flex items-center justify-between gap-2 px-3 pb-2">
          <span className={`text-xs tabular-nums ${counterClass}`}>
            {t("chat.character_limit", language, { count })}
          </span>
          <button
            type="button"
            disabled={!canSubmit}
            onClick={submit}
            className="rounded-md bg-[var(--color-brand-500)] hover:bg-[var(--color-brand-600)] text-white text-sm font-medium px-4 py-2 min-h-[44px] md:min-h-0 md:py-1.5 disabled:opacity-50 disabled:cursor-not-allowed inline-flex items-center justify-center gap-1.5 transition-colors focus-visible:outline focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-[var(--color-brand-500)]"
          >
            {pending && (
              <svg
                aria-hidden="true"
                viewBox="0 0 24 24"
                fill="none"
                stroke="currentColor"
                strokeWidth="3"
                className="inline-block h-3.5 w-3.5 animate-spin"
              >
                <path d="M12 3a9 9 0 1 0 9 9" strokeLinecap="round" />
              </svg>
            )}
            {pending ? t("chat.sending", language) : t("chat.send", language)}
          </button>
        </div>
      </div>
    </div>
  );
}
