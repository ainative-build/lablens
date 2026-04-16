"use client";

import { useState } from "react";
import type { Explanation, Status, TopicGroup } from "@/lib/api-client";
import type { Language } from "@/lib/i18n";
import { t } from "@/lib/i18n";
import { AnalyteCard } from "./analyte-card";
import { NormalCollapsedRow } from "./normal-collapsed-row";
import { SeverityDot } from "./severity-dot";

interface Props {
  group: TopicGroup;
  explanations: Explanation[];
  language: Language;
  /** Default-collapsed override (mobile defaults to collapsed). */
  defaultOpen?: boolean;
}

const STATUS_BORDER_LEFT: Record<Status, string> = {
  green: "border-l-emerald-400",
  yellow: "border-l-amber-400",
  orange: "border-l-orange-500",
  red: "border-l-rose-600",
};

/** L2 — Health-topic accordion group. */
export function TopicGroup({
  group,
  explanations,
  language,
  defaultOpen,
}: Props) {
  // Default open if any abnormal/indeterminate; collapsed if all normal.
  const hasAttention =
    group.abnormal_count + group.indeterminate_count > 0;
  const initial = defaultOpen ?? hasAttention;
  const [open, setOpen] = useState(initial);

  const headerSummary =
    group.abnormal_count === 0 && group.indeterminate_count === 0
      ? t("group.all_normal", language, { total: group.total_count })
      : group.indeterminate_count > 0
        ? t("group.indeterminate_count", language, {
            abnormal: group.abnormal_count,
            total: group.total_count,
            indeterminate: group.indeterminate_count,
          })
        : t("group.abnormal_count", language, {
            abnormal: group.abnormal_count,
            total: group.total_count,
          });

  // Split into needs-attention vs normal
  const attention = group.results.filter(
    (r) =>
      r.direction === "high" ||
      r.direction === "low" ||
      r.direction === "indeterminate" ||
      r.is_panic
  );
  const normal = group.results.filter(
    (r) => r.direction === "in-range" && !r.is_panic
  );

  return (
    <section
      className={`rounded-lg border bg-white dark:bg-gray-900 border-gray-200 dark:border-gray-700 border-l-4 ${STATUS_BORDER_LEFT[group.status]}`}
    >
      <button
        type="button"
        aria-expanded={open}
        onClick={() => setOpen((v) => !v)}
        className="w-full flex items-center gap-3 px-4 py-3 text-left hover:bg-gray-50 dark:hover:bg-gray-800 focus-visible:outline focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-blue-500 rounded-lg"
      >
        <SeverityDot status={group.status} size="md" />
        <span className="font-semibold text-gray-900 dark:text-gray-100">
          {t(group.topic_label_key, language)}
        </span>
        <span className="text-sm text-gray-600 dark:text-gray-400 ml-2">
          {headerSummary}
        </span>
        <span aria-hidden className="ml-auto text-gray-500">
          {open ? "▾" : "▸"}
        </span>
      </button>

      {open && (
        <div className="px-4 pb-4 space-y-3">
          {attention.map((v, i) => {
            const exp = explanations.find((e) => e.test_name === v.test_name);
            return (
              <AnalyteCard
                key={`${group.topic}-${v.test_name}-${i}`}
                cardId={`card-${group.topic}-${v.test_name}-${i}`}
                value={v}
                explanation={exp}
                language={language}
              />
            );
          })}
          {normal.length > 0 && (
            <NormalCollapsedRow
              values={normal}
              explanations={explanations}
              language={language}
            />
          )}
        </div>
      )}
    </section>
  );
}
