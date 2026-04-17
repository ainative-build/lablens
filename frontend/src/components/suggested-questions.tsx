"use client";

import type { Language } from "@/lib/i18n";
import { t } from "@/lib/i18n";

/**
 * Custom DOM event the ChatDock listens for. SuggestedQuestions dispatches
 * it on click; ChatDock opens its dialog with the question pre-filled and
 * auto-submits.
 *
 * Why a DOM event instead of prop-drilling: AppShell owns ChatDock and is
 * separate from the results page tree. A typed CustomEvent keeps wiring lean.
 */
export const ASK_EVENT = "lablens:ask";

export interface AskEventDetail {
  question: string;
}

/**
 * Pinned "Questions you can ask" panel — appears on the results page so
 * the Q&A feels like part of the report UX, not an extra tool.
 */
export function SuggestedQuestions({ language }: { language: Language }) {
  const questions = [
    t("suggested.q.focus", language),
    t("suggested.q.urgent", language),
    t("suggested.q.questions_for_doctor", language),
    t("suggested.q.improve_vitamin_d", language),
    t("suggested.q.what_is_egfr", language),
  ];

  const ask = (q: string) => {
    if (typeof window === "undefined") return;
    window.dispatchEvent(
      new CustomEvent<AskEventDetail>(ASK_EVENT, { detail: { question: q } })
    );
  };

  return (
    <section
      aria-label={t("suggested.title", language)}
      className="rounded-[var(--radius-card)] border border-[var(--color-border)] bg-[var(--color-surface)] p-4 shadow-[var(--shadow-card)]"
    >
      <header className="flex items-center gap-2 mb-3">
        <span aria-hidden className="text-[var(--color-brand-500)]">💬</span>
        <h3 className="font-semibold text-sm text-[var(--foreground)]">
          {t("suggested.title", language)}
        </h3>
      </header>
      <ul className="space-y-1.5">
        {questions.map((q) => (
          <li key={q}>
            <button
              type="button"
              onClick={() => ask(q)}
              className="text-left w-full text-sm text-[var(--foreground)] hover:text-[var(--color-brand-700)] dark:hover:text-[var(--color-brand-500)] hover:bg-[var(--color-surface-muted)] rounded px-2 py-1.5 transition-colors focus-visible:outline focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-[var(--color-brand-500)]"
            >
              <span className="text-[var(--color-brand-600)] mr-1.5" aria-hidden>›</span>
              {q}
            </button>
          </li>
        ))}
      </ul>
    </section>
  );
}
