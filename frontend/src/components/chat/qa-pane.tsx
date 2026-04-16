"use client";

/**
 * Q&A pane stub — Phase 4 implementation.
 *
 * This component is dynamically imported via `next/dynamic({ ssr: false })`
 * from the results page to keep it out of the initial bundle.  The full
 * chat UI (input, thread, citations, doctor-routing, refusal) lands in
 * Phase 4.  Until then, this renders a minimal "coming soon" panel so
 * the lazy import resolves successfully.
 */

import type { Language } from "@/lib/i18n";
import { t } from "@/lib/i18n";

interface Props {
  jobId: string;
  language: Language;
  onClose: () => void;
}

export function QaPane({ jobId, language, onClose }: Props) {
  return (
    <aside
      role="complementary"
      aria-label={t("chat.title", language)}
      className="fixed bottom-0 right-0 left-0 md:left-auto md:bottom-4 md:right-4 md:w-96 z-40 bg-white dark:bg-gray-900 border border-gray-200 dark:border-gray-700 rounded-t-lg md:rounded-lg shadow-2xl"
    >
      <div className="flex items-center justify-between px-4 py-3 border-b border-gray-200 dark:border-gray-700">
        <h2 className="font-semibold text-gray-900 dark:text-gray-100">
          {t("chat.title", language)}
        </h2>
        <button
          type="button"
          onClick={onClose}
          aria-label="Close"
          className="text-gray-500 hover:text-gray-800 dark:hover:text-gray-200 focus-visible:outline focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-blue-500 rounded"
        >
          ✕
        </button>
      </div>
      <div className="p-4 space-y-3 text-sm text-gray-700 dark:text-gray-300">
        <p>Q&amp;A coming in Phase 4. Job: <span className="font-mono text-xs">{jobId}</span></p>
        <p className="text-gray-500 dark:text-gray-400">
          You will be able to ask questions about this report and get answers grounded in
          your specific results.
        </p>
      </div>
    </aside>
  );
}
