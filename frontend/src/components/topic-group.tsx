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
  /** Hide normal in-range rows when true (page-level filter). */
  abnormalOnly?: boolean;
}

// Status-pill style (BloodGPT-inspired framing per Phase 3).
// Wraps the section in a soft colored frame, with a status pill at the top.
const STATUS_FRAME: Record<Status, string> = {
  green: "border-emerald-300 bg-emerald-50/50 dark:border-emerald-800/50 dark:bg-emerald-950/20",
  yellow: "border-amber-300 bg-amber-50/50 dark:border-amber-800/50 dark:bg-amber-950/20",
  orange: "border-orange-400 bg-orange-50/50 dark:border-orange-800/50 dark:bg-orange-950/20",
  red: "border-rose-500 bg-rose-50/50 dark:border-rose-800/50 dark:bg-rose-950/20",
};

const STATUS_PILL: Record<Status, string> = {
  green: "bg-emerald-500 text-white",
  yellow: "bg-amber-500 text-white",
  orange: "bg-orange-500 text-white",
  red: "bg-rose-600 text-white",
};

const STATUS_LABEL_KEY: Record<Status, string> = {
  green: "group.pill.optimal",
  yellow: "group.pill.mostly_normal",
  orange: "group.pill.worth_followup",
  red: "group.pill.important",
};

const UNCLEAR_FRAME = "border-gray-300 dark:border-gray-700 bg-[var(--color-surface)] border-dashed";
const UNCLEAR_PILL = "bg-gray-300 text-gray-800 dark:bg-gray-700 dark:text-gray-200";

/** L2 — Health-topic accordion group. */
export function TopicGroup({
  group,
  explanations,
  language,
  defaultOpen,
  abnormalOnly = false,
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

  const frameClass = isUnclearOnly || isMinorOnly
    ? UNCLEAR_FRAME
    : STATUS_FRAME[group.status];
  const pillClass = isUnclearOnly || isMinorOnly
    ? UNCLEAR_PILL
    : STATUS_PILL[group.status];
  const pillLabel = isUnclearOnly
    ? t("group.pill.unclear", language)
    : isMinorOnly
      ? t("group.pill.minor", language)
      : t(STATUS_LABEL_KEY[group.status], language);

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
      className={`rounded-[var(--radius-card)] border-2 shadow-[var(--shadow-card)] ${frameClass}`}
    >
      <button
        type="button"
        aria-expanded={open}
        onClick={() => setOpen((v) => !v)}
        className="w-full flex items-center gap-3 px-4 pt-3 pb-2 text-left hover:bg-black/[0.02] dark:hover:bg-white/[0.02] focus-visible:outline focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-[var(--color-brand-500)] rounded-t-[var(--radius-card)]"
      >
        <span
          className={`inline-flex items-center gap-1 rounded-full px-2 py-0.5 text-xs font-medium ${pillClass}`}
        >
          {isUnclearOnly || isMinorOnly ? (
            <span aria-hidden>○</span>
          ) : (
            <SeverityDot status={group.status} size="sm" />
          )}
          {pillLabel}
        </span>
        <span
          className={`font-semibold text-[var(--foreground)] ${isUnclearOnly || isMinorOnly ? "italic" : ""}`}
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
          {normal.length > 0 && !abnormalOnly && (
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
