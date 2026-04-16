import type { ReportSummary, Status, TopFinding } from "@/lib/api-client";
import type { Language } from "@/lib/i18n";
import { t } from "@/lib/i18n";
import { SeverityDot } from "./severity-dot";

interface Props {
  summary: ReportSummary;
  language: Language;
}

const STATUS_BORDER: Record<Status, string> = {
  green: "border-emerald-300 bg-emerald-50 dark:bg-emerald-950/30",
  yellow: "border-amber-300 bg-amber-50 dark:bg-amber-950/30",
  orange: "border-orange-400 bg-orange-50 dark:bg-orange-950/30",
  red: "border-rose-500 bg-rose-50 dark:bg-rose-950/30",
};

const DIRECTION_ICON: Record<TopFinding["direction"], string> = {
  high: "▲",
  low: "▼",
  indeterminate: "ⓘ",
};

const TOPIC_BG: Record<string, string> = {
  blood_sugar: "bg-purple-100 text-purple-800",
  heart_lipids: "bg-rose-100 text-rose-800",
  kidney: "bg-blue-100 text-blue-800",
  liver: "bg-amber-100 text-amber-800",
  blood_count: "bg-red-100 text-red-800",
  thyroid_hormones: "bg-pink-100 text-pink-800",
  vitamins_minerals: "bg-green-100 text-green-800",
  electrolytes: "bg-cyan-100 text-cyan-800",
  inflammation: "bg-orange-100 text-orange-800",
  urinalysis_other: "bg-yellow-100 text-yellow-800",
  other: "bg-gray-100 text-gray-800",
};

/** L1 — Executive summary card. Always visible at top of report. */
export function SummaryCard({ summary, language }: Props) {
  const status = summary.overall_status;
  const isGreen = status === "green" && summary.top_findings.length === 0;

  return (
    <section
      aria-label="Report summary"
      className={`rounded-lg border-2 p-5 ${STATUS_BORDER[status]}`}
    >
      <header className="flex items-baseline gap-3 flex-wrap">
        <SeverityDot status={status} size="lg" />
        <h2 className="text-sm font-semibold uppercase tracking-wide text-gray-700 dark:text-gray-300">
          {t(`summary.status.${status}`, language)}
        </h2>
      </header>

      <p className="mt-2 text-lg sm:text-xl font-medium text-gray-900 dark:text-gray-50 leading-snug">
        {summary.headline}
      </p>

      {!isGreen && summary.top_findings.length > 0 && (
        <>
          <h3 className="mt-4 text-xs font-semibold uppercase tracking-wide text-gray-600 dark:text-gray-400">
            {t("summary.top_findings", language)}
          </h3>
          <ul className="mt-1 space-y-1">
            {summary.top_findings.map((f, i) => (
              <li
                key={`${f.test_name}-${i}`}
                className="flex items-baseline gap-2 text-sm"
              >
                <span aria-hidden className="font-mono text-gray-500">
                  {DIRECTION_ICON[f.direction]}
                </span>
                <span className="font-medium text-gray-900 dark:text-gray-100">
                  {f.test_name}
                </span>
                <span className="text-gray-700 dark:text-gray-300">
                  {String(f.value)}
                  {f.unit ? ` ${f.unit}` : ""}
                </span>
                <span className="text-gray-500 text-xs">
                  · {t(f.plain_language_key, language)}
                </span>
                <span
                  className={`ml-auto text-xs px-1.5 py-0.5 rounded ${TOPIC_BG[f.health_topic] ?? TOPIC_BG.other}`}
                >
                  {t(`topic.${f.health_topic}`, language)}
                </span>
              </li>
            ))}
          </ul>
        </>
      )}

      <p className="mt-4 text-sm text-gray-700 dark:text-gray-300">
        {t(`summary.next_steps.${summary.next_steps_key}`, language)}
      </p>

      {summary.uncertainty_note_key && (
        <p className="mt-2 text-xs text-gray-600 dark:text-gray-400">
          {t(summary.uncertainty_note_key, language, {
            count: summary.indeterminate_count,
          })}
        </p>
      )}
    </section>
  );
}
