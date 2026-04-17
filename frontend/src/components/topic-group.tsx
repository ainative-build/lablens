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

// Unclear-only treatment (PR #6 calibration): when a group has zero abnormals
// but does have indeterminates, give it a distinct gray-dashed border so it
// doesn't read as "all-normal but hidden". The bucket is unresolved, not safe.
const UNCLEAR_BORDER_LEFT = "border-l-gray-400 border-l-dashed";

/** L2 — Health-topic accordion group. */
export function TopicGroup({
  group,
  explanations,
  language,
  defaultOpen,
}: Props) {
  const minorCount = group.minor_count ?? 0;

  // Default open if any abnormal/indeterminate; collapsed if all normal+minor.
  // (Minor-only groups stay collapsed by default — they're low-impact.)
  const hasAttention =
    group.abnormal_count + group.indeterminate_count > 0;
  const initial = defaultOpen ?? hasAttention;
  const [open, setOpen] = useState(initial);

  // PR #6 calibration v2: distinguish 3 states beyond "all normal":
  //   - unclear-only: 0 abnormal AND 0 minor AND >0 indeterminate → gray dashed
  //   - has follow-up: ≥1 abnormal → status color
  //   - minor-only: 0 abnormal, ≥1 minor (no follow-up needed)
  const isUnclearOnly =
    group.abnormal_count === 0 &&
    minorCount === 0 &&
    group.indeterminate_count > 0;
  const isMinorOnly =
    group.abnormal_count === 0 && minorCount > 0;

  // Compose header summary from non-zero parts (locked order:
  // follow-up → minor → unclear). Localized via i18n.
  const headerParts: string[] = [];
  if (group.abnormal_count > 0) {
    headerParts.push(
      t("group.abnormal_count_inline", language, {
        abnormal: group.abnormal_count,
        total: group.total_count,
      })
    );
  }
  if (minorCount > 0) {
    headerParts.push(t("group.minor_count", language, { minor: minorCount }));
  }
  if (group.indeterminate_count > 0) {
    headerParts.push(
      t("group.unclear_count", language, {
        indeterminate: group.indeterminate_count,
      })
    );
  }
  const headerSummary =
    headerParts.length === 0
      ? t("group.all_normal", language, { total: group.total_count })
      : headerParts.join(" · ");

  const borderClass = isUnclearOnly || isMinorOnly
    ? UNCLEAR_BORDER_LEFT
    : STATUS_BORDER_LEFT[group.status];

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
      className={`rounded-lg border bg-white dark:bg-gray-900 border-gray-200 dark:border-gray-700 border-l-4 ${borderClass}`}
    >
      <button
        type="button"
        aria-expanded={open}
        onClick={() => setOpen((v) => !v)}
        className="w-full flex items-center gap-3 px-4 py-3 text-left hover:bg-gray-50 dark:hover:bg-gray-800 focus-visible:outline focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-blue-500 rounded-lg"
      >
        {isUnclearOnly || isMinorOnly ? (
          <span
            aria-hidden
            className="inline-block h-3 w-3 rounded-full border-2 border-dashed border-gray-400"
          />
        ) : (
          <SeverityDot status={group.status} size="md" />
        )}
        <span
          className={`font-semibold text-gray-900 dark:text-gray-100 ${isUnclearOnly || isMinorOnly ? "italic" : ""}`}
        >
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
