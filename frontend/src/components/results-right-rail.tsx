import type { AnalysisResult } from "@/lib/api-client";
import type { Language } from "@/lib/i18n";
import { t } from "@/lib/i18n";
import { StatPanel } from "./stat-panel";
import { SuggestedQuestions } from "./suggested-questions";

// Discriminated union: when `isLoading` is true, no `result` is required —
// the rail renders skeleton placeholders. Default branch keeps the existing
// callsite signature ({ result, language }) unchanged.
type Props =
  | {
      isLoading: true;
      language: Language;
      result?: undefined;
    }
  | {
      isLoading?: false;
      result: NonNullable<AnalysisResult["result"]>;
      language: Language;
    };

/**
 * Right-rail composition of 3 stat cards derived from the existing
 * `summary` + `topic_groups` payload (no API changes).
 *
 * Counts (from topic groups, source of truth):
 *   abnormal_count = "worth follow-up" findings
 *   minor_count    = low-clinical-impact abnormals (not in worth-follow-up)
 *   indeterminate_count = unclear
 *   normal = total - abnormal - minor - unclear
 */
export function ResultsRightRail(props: Props) {
  const { language } = props;

  if (props.isLoading) {
    // 3 stat-panel-shaped skeletons match the loaded height (~h-28) so swap-in
    // causes minimal layout shift. Use shimmer so they read as "loading", not
    // "empty cards".
    return (
      <div
        role="status"
        aria-label={t("upload.skeleton.label", language)}
        className="space-y-3"
      >
        <div className="h-28 rounded-[var(--radius-card)] border border-[var(--color-border)] skeleton-shimmer" aria-hidden="true" />
        <div className="h-28 rounded-[var(--radius-card)] border border-[var(--color-border)] skeleton-shimmer" aria-hidden="true" />
        <div className="h-28 rounded-[var(--radius-card)] border border-[var(--color-border)] skeleton-shimmer" aria-hidden="true" />
      </div>
    );
  }

  const result = props.result;
  const total = result.values?.length ?? 0;
  const groups = result.topic_groups ?? [];

  const abnormal = groups.reduce((s, g) => s + g.abnormal_count, 0);
  const minor = groups.reduce((s, g) => s + (g.minor_count ?? 0), 0);
  const unclear = groups.reduce((s, g) => s + g.indeterminate_count, 0);
  const normal = Math.max(0, total - abnormal - minor - unclear);

  const pct = (n: number) => (total === 0 ? 0 : Math.round((n / total) * 100));

  // PR #6 v6 calibration: human counts in donut center ("12 of 75") instead
  // of percentages. Captions get one-line action context.
  return (
    <div className="space-y-3">
      <StatPanel
        title={t("stats.normal", language)}
        percent={pct(normal)}
        countLabel={`${normal}/${total}`}
        caption={t("stats.normal_caption", language, {
          count: normal,
          total,
        })}
        variant="normal"
      />
      <StatPanel
        title={t("stats.worth_followup", language)}
        percent={pct(abnormal + minor)}
        countLabel={`${abnormal + minor}/${total}`}
        caption={t("stats.followup_caption", language, {
          count: abnormal,
          minor,
        })}
        variant="warn"
      />
      {unclear > 0 && (
        <StatPanel
          title={t("stats.unclear", language)}
          percent={pct(unclear)}
          countLabel={`${unclear}/${total}`}
          caption={t("stats.unclear_caption", language, { count: unclear })}
          variant="unclear"
        />
      )}

      {/* PR #6 v6: pinned Q&A starter panel — makes Q&A feel native to UX */}
      <SuggestedQuestions language={language} />
    </div>
  );
}
