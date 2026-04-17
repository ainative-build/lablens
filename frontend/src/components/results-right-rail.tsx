import type { AnalysisResult } from "@/lib/api-client";
import type { Language } from "@/lib/i18n";
import { t } from "@/lib/i18n";

interface Props {
  result: NonNullable<AnalysisResult["result"]>;
  language: Language;
}

/**
 * Phase 5 — compact counts strip (replaces the old right-rail donut panels).
 *
 * Renders a single readable line under the SummaryCard:
 *   "3 main items to discuss · 5 minor findings · 1 unclear"
 *   "Most other results are within expected range."
 *
 * Framing is deliberately human: no "8/74" denominators on the default view,
 * no donut charts competing with the summary card. The full normal-vs-
 * abnormal breakdown is still available by toggling "Show all results" —
 * this strip just answers "am I okay overall?" at a glance.
 */
export function ResultsRightRail({ result, language }: Props) {
  const total = result.values?.length ?? 0;
  const groups = result.topic_groups ?? [];
  const summary = result.summary;

  const abnormal = groups.reduce((s, g) => s + g.abnormal_count, 0);
  const minor = groups.reduce((s, g) => s + (g.minor_count ?? 0), 0);
  const unclear = groups.reduce((s, g) => s + g.indeterminate_count, 0);

  // "Main items" mirrors the hero: the top-findings list (capped 3) are the
  // focus. "Minor findings" is everything else in the abnormal + minor buckets
  // that didn't make the hero. Clamp ≥0 to survive count mismatches.
  const mainCount = summary?.top_findings.length ?? Math.min(3, abnormal);
  const minorRemaining = Math.max(0, abnormal + minor - mainCount);

  const allNormal = total > 0 && abnormal === 0 && minor === 0 && unclear === 0;

  const parts: string[] = [];
  if (mainCount > 0) {
    parts.push(
      mainCount === 1
        ? t("strip.main_item_single", language)
        : t("strip.main_items", language, { count: mainCount }),
    );
  }
  if (minorRemaining > 0) {
    parts.push(
      minorRemaining === 1
        ? t("strip.minor_single", language)
        : t("strip.minor", language, { count: minorRemaining }),
    );
  }
  if (unclear > 0) {
    parts.push(
      unclear === 1
        ? t("strip.unclear_single", language)
        : t("strip.unclear", language, { count: unclear }),
    );
  }

  return (
    <div
      role="status"
      aria-label="Results breakdown"
      className="rounded-[var(--radius-card)] border border-[var(--color-border)] bg-[var(--color-surface)] px-4 py-3 text-sm text-[var(--foreground)] flex flex-wrap items-baseline gap-x-2 gap-y-1"
    >
      {parts.length > 0 ? (
        <span className="font-medium">{parts.join(" · ")}</span>
      ) : null}
      <span className="text-[var(--foreground-muted)]">
        {allNormal || parts.length === 0
          ? t("strip.all_normal", language)
          : t("strip.rest_normal", language)}
      </span>
    </div>
  );
}
