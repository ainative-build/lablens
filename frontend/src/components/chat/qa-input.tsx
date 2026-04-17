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

  return (
    <div className="border-t border-gray-200 dark:border-gray-700 p-3 space-y-2">
      <label className="sr-only" htmlFor="qa-input">
        {t("chat.placeholder", language)}
      </label>
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
        className="w-full text-sm rounded border border-gray-300 dark:border-gray-600 bg-white dark:bg-gray-800 text-gray-900 dark:text-gray-100 p-2 focus-visible:outline focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-blue-500 disabled:opacity-60"
      />
      <div className="flex items-center justify-between">
        <span className="text-xs text-gray-500 dark:text-gray-400">
          {t("chat.character_limit", language, { count })}
        </span>
        <button
          type="button"
          disabled={disabled || value.trim().length === 0}
          onClick={submit}
          className="rounded bg-blue-600 hover:bg-blue-700 text-white text-sm px-4 py-2 min-h-[44px] md:min-h-0 md:py-1.5 disabled:opacity-60 inline-flex items-center justify-center gap-1.5 focus-visible:outline focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-blue-500"
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
  );
}
