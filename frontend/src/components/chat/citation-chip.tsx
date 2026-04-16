"use client";

import type { ChatCitation } from "@/lib/api-client";
import type { Language } from "@/lib/i18n";
import { t } from "@/lib/i18n";

interface Props {
  citation: ChatCitation;
  language: Language;
}

/**
 * Clickable chip that jumps to the analyte card in the report.
 * Target IDs follow the pattern from Phase 2: `card-{topic}-{test_name}-{index}`.
 * We scroll to the first match and briefly ring-highlight it.
 */
export function CitationChip({ citation, language }: Props) {
  const topic = citation.health_topic || "other";
  const topicLabel = t(`topic.${topic}`, language);

  const handleClick = () => {
    // Find the first matching card: id starts with `card-{topic}-{name}-`.
    const name = citation.test_name;
    if (typeof document === "undefined") return;
    const match = Array.from(
      document.querySelectorAll<HTMLElement>("[id^='card-']")
    ).find((el) => el.id.includes(`-${name}-`));
    if (!match) return;
    match.scrollIntoView({ behavior: "smooth", block: "center" });
    match.classList.add("ring-2", "ring-blue-500", "ring-offset-2");
    setTimeout(() => {
      match.classList.remove("ring-2", "ring-blue-500", "ring-offset-2");
    }, 1500);
    // Move focus (a11y).
    match.setAttribute("tabindex", "-1");
    match.focus();
  };

  return (
    <button
      type="button"
      onClick={handleClick}
      className="inline-flex items-center gap-1 rounded bg-white dark:bg-gray-700 text-blue-700 dark:text-blue-200 text-xs px-2 py-0.5 border border-blue-200 dark:border-blue-800 hover:bg-blue-50 dark:hover:bg-blue-900 focus-visible:outline focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-blue-500"
      title={topicLabel}
    >
      <span className="font-medium">{citation.test_name}</span>
      {citation.value !== null && citation.value !== undefined && (
        <span className="opacity-80">
          {String(citation.value)}
          {citation.unit ? ` ${citation.unit}` : ""}
        </span>
      )}
    </button>
  );
}
