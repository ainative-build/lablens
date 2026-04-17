import type { AnalysisResult } from "@/lib/api-client";
import type { Language } from "@/lib/i18n";
import { t } from "@/lib/i18n";
import { StatPanel } from "./stat-panel";
import { SuggestedQuestions } from "./suggested-questions";

interface Props {
  result: NonNullable<AnalysisResult["result"]>;
  language: Language;
}

/**
 * Right-rail composition — donut StatPanels + Q&A starters.
 *
 * Counts (from topic groups, source of truth):
 *   abnormal_count = "worth follow-up" findings
 *   minor_count    = low-clinical-impact abnormals (folded into follow-up donut)
 *   indeterminate_count = unclear (panel only rendered when > 0)
 *   normal = total - abnormal - minor - unclear
 */
export function ResultsRightRail({ result, language }: Props) {
  const total = result.values?.length ?? 0;
  const groups = result.topic_groups ?? [];

  const abnormal = groups.reduce((s, g) => s + g.abnormal_count, 0);
  const minor = groups.reduce((s, g) => s + (g.minor_count ?? 0), 0);
  const unclear = groups.reduce((s, g) => s + g.indeterminate_count, 0);
  const normal = Math.max(0, total - abnormal - minor - unclear);

  const pct = (n: number) => (total === 0 ? 0 : Math.round((n / total) * 100));

  // lg:pb-24 keeps the floating chat FAB from visually overlapping the last
  // panel on viewports where rail + FAB share screen space (~1024-1400px).
  return (
    <div className="space-y-3 lg:pb-24">
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

      <SuggestedQuestions language={language} />
    </div>
  );
}
