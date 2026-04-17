import type { ReportSummary, Status, TopFinding } from "@/lib/api-client";
import type { Language } from "@/lib/i18n";
import { t } from "@/lib/i18n";
import { SeverityDot } from "./severity-dot";

interface Props {
  summary: ReportSummary;
  language: Language;
}

// Stronger frame intensity per status — leans on colored bg for visual hierarchy
// (orange/red feel different at a glance from green/yellow).
const STATUS_FRAME: Record<Status, string> = {
  green: "border-emerald-300 bg-emerald-50 dark:bg-emerald-950/30",
  yellow: "border-amber-300 bg-amber-50 dark:bg-amber-950/30",
  orange: "border-orange-400 bg-orange-50/80 dark:bg-orange-950/40",
  red: "border-rose-500 bg-rose-50/90 dark:bg-rose-950/50 ring-2 ring-rose-500/20",
};

const DIRECTION_ICON: Record<TopFinding["direction"], string> = {
  high: "▲",
  low: "▼",
  indeterminate: "ⓘ",
};

const DIRECTION_COLOR: Record<TopFinding["direction"], string> = {
  high: "text-rose-600 dark:text-rose-400",
  low: "text-blue-600 dark:text-blue-400",
  indeterminate: "text-gray-500 dark:text-gray-400",
};

/**
 * L1 — Executive briefing card. Always visible at top of report.
 *
 * Calibrated v6 (clinical briefing format):
 *   1. Status pill (Optimal / Mostly normal / Worth follow-up / Important)
 *   2. Bold one-line takeaway (LLM headline OR deterministic fallback)
 *   3. "Main items to discuss" — 3 bullets (name + direction icon + topic)
 *   4. "Suggested next step" — labeled action line
 *   5. Optional uncertainty footnote
 */
export function SummaryCard({ summary, language }: Props) {
  const status = summary.overall_status;
  const isGreen = status === "green" && summary.top_findings.length === 0;

  return (
    <section
      aria-label="Report summary"
      className={`rounded-[var(--radius-card)] border-2 p-5 sm:p-6 shadow-[var(--shadow-card)] ${STATUS_FRAME[status]}`}
    >
      {/* 1. Status pill */}
      <header className="flex items-center gap-2 mb-3">
        <SeverityDot status={status} size="md" />
        <span className="text-xs font-semibold uppercase tracking-wider text-[var(--foreground)]">
          {t(`summary.status.${status}`, language)}
        </span>
      </header>

      {/* 2. Bold one-line takeaway */}
      <p className="text-lg sm:text-xl font-semibold text-[var(--foreground)] leading-snug">
        {summary.headline}
      </p>

      {!isGreen && summary.top_findings.length > 0 && (
        <>
          {/* 3. Main items to discuss — tight bullet list */}
          <div className="mt-5">
            <h3 className="text-xs font-semibold uppercase tracking-wider text-gray-700 dark:text-gray-300 mb-2">
              {t("summary.main_items", language)}
            </h3>
            <ul className="space-y-1.5">
              {summary.top_findings.map((f, i) => (
                <li
                  key={`${f.test_name}-${i}`}
                  className="flex items-baseline gap-2 text-sm"
                >
                  <span aria-hidden className={`font-mono text-base ${DIRECTION_COLOR[f.direction]}`}>
                    {DIRECTION_ICON[f.direction]}
                  </span>
                  <span className="font-semibold text-[var(--foreground)]">
                    {f.test_name}
                  </span>
                  <span className="text-gray-600 dark:text-gray-400 text-xs">
                    · {t(`topic.${f.health_topic}`, language)}
                  </span>
                </li>
              ))}
            </ul>
          </div>
        </>
      )}

      {/* 4. Suggested next step — labeled, more prominent */}
      <div className="mt-5">
        <h3 className="text-xs font-semibold uppercase tracking-wider text-gray-700 dark:text-gray-300 mb-1">
          {t("summary.next_step_label", language)}
        </h3>
        <p className="text-sm text-[var(--foreground)] leading-relaxed">
          {t(`summary.next_steps.${summary.next_steps_key}`, language)}
        </p>
      </div>

      {/* 5. Uncertainty footnote — smallest, separated */}
      {summary.uncertainty_note_key && (
        <p className="mt-4 pt-3 border-t border-black/[0.06] dark:border-white/[0.06] text-xs text-gray-600 dark:text-gray-400">
          {t(summary.uncertainty_note_key, language, {
            count: summary.indeterminate_count,
          })}
        </p>
      )}
    </section>
  );
}
