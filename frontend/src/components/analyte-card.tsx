import type { Explanation, InterpretedValue } from "@/lib/api-client";
import type { Language } from "@/lib/i18n";
import { t } from "@/lib/i18n";
import { AuditPanel } from "./audit-panel";
import { SeverityBadge } from "./severity-badge";

interface Props {
  value: InterpretedValue;
  explanation?: Explanation;
  language: Language;
  cardId?: string;
}

/** L3 — single analyte card with value, range, plain explanation, and L4 audit. */
export function AnalyteCard({ value, explanation, language, cardId }: Props) {
  const isAbnormal = value.direction === "high" || value.direction === "low";
  const isIndet = value.direction === "indeterminate";
  const dirArrow = value.direction === "high" ? "▲" : value.direction === "low" ? "▼" : "·";

  const borderClass = value.is_panic
    ? "border-rose-500 border-2"
    : isAbnormal
      ? "border-amber-200 dark:border-amber-700"
      : isIndet
        ? "border-gray-300 dark:border-gray-600"
        : "border-gray-200 dark:border-gray-700";

  return (
    <div
      id={cardId}
      className={`rounded-lg p-4 border bg-white dark:bg-gray-900 ${borderClass}`}
    >
      <div className="flex justify-between items-start flex-wrap gap-2">
        <h3 className="font-semibold text-base text-gray-900 dark:text-gray-50">
          <span className="mr-2 text-gray-500">{dirArrow}</span>
          {value.test_name}
        </h3>
        <div className="flex gap-2 items-center">
          {/* PR #6 calibration v2: badge variant routes by direction first
              (indeterminate → "unclear"), then by display_severity (capped
              for low-clinical-impact tests), then by raw severity. This
              matches the explanation tone instead of the engine's raw math. */}
          <SeverityBadge
            variant={
              isIndet
                ? "unclear"
                : value.is_minor
                  ? "minor"
                  : (value.display_severity as
                      | "normal"
                      | "mild"
                      | "moderate"
                      | "critical"
                      | undefined) ??
                    (value.severity as
                      | "normal"
                      | "mild"
                      | "moderate"
                      | "critical")
            }
            language={language}
          />
        </div>
      </div>

      <div className="mt-2 grid grid-cols-1 sm:grid-cols-2 gap-x-4 gap-y-1 text-sm">
        <div className="text-gray-700 dark:text-gray-200">
          <strong className="text-gray-900 dark:text-gray-50">
            {String(value.value)}
            {value.unit ? ` ${value.unit}` : ""}
          </strong>
        </div>
        {(value.reference_range_low !== null ||
          value.reference_range_high !== null) && (
          <div className="text-gray-600 dark:text-gray-400 text-xs">
            {t("results.range", language)}:{" "}
            {value.reference_range_low ?? "—"} – {value.reference_range_high ?? "—"}
          </div>
        )}
      </div>

      {explanation && (explanation.summary || explanation.what_it_means) && (
        <div className="mt-3 bg-gray-50 dark:bg-gray-800 rounded p-3 text-sm space-y-1">
          {explanation.summary && (
            <p className="font-medium text-gray-900 dark:text-gray-100">
              {explanation.summary}
            </p>
          )}
          {explanation.what_it_means && (
            <p className="text-gray-700 dark:text-gray-300">
              {explanation.what_it_means}
            </p>
          )}
          {explanation.next_steps && (
            <p className="text-blue-700 dark:text-blue-300">
              {explanation.next_steps}
            </p>
          )}
        </div>
      )}

      {value.is_panic && (
        <div className="mt-2 bg-rose-50 dark:bg-rose-950 text-rose-800 dark:text-rose-200 p-2 rounded text-sm font-medium">
          {t("results.panic", language)}
        </div>
      )}

      <AuditPanel value={value} language={language} />
    </div>
  );
}
