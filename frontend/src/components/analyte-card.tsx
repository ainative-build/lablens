import type { Explanation, InterpretedValue } from "@/lib/api-client";
import type { Language } from "@/lib/i18n";
import { t } from "@/lib/i18n";
import { AuditPanel } from "./audit-panel";
import { RangeBar } from "./range-bar";
import { SeverityBadge } from "./severity-badge";

interface Props {
  value: InterpretedValue;
  explanation?: Explanation;
  language: Language;
  cardId?: string;
}

/**
 * Derive a one-line friendly helper for indeterminate rows.
 * Calm tone, concrete reason — so users see uncertainty as an intentional
 * state, not a missing feature. Matches backend signals already exposed.
 */
function unclearHelper(value: InterpretedValue, language: Language): string {
  const flag = (value.evidence_trace?.source_flag as string | undefined) ?? "";
  const directionHint =
    flag === "H"
      ? t("direction.high", language)
      : flag === "L"
        ? t("direction.low", language)
        : "";

  if (value.range_source === "no-range") {
    return t("unclear.no_range", language);
  }
  if (value.range_source === "ocr-flag-fallback" && directionHint) {
    return t("unclear.ocr_flag_with_direction", language, {
      direction: directionHint,
    });
  }
  if (value.range_source === "ocr-flag-fallback") {
    return t("unclear.ocr_flag", language);
  }
  if (value.unit_confidence === "low") {
    return t("unclear.unit_low_confidence", language);
  }
  return t("unclear.generic", language);
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

      <div className="mt-2 flex items-baseline gap-2 text-sm">
        <strong className="text-2xl font-semibold text-[var(--foreground)] tabular-nums">
          {String(value.value)}
        </strong>
        {value.unit && (
          <span className="text-gray-600 dark:text-gray-400">
            {value.unit}
          </span>
        )}
      </div>

      {/* Range bar — Phase 3: replaces the text "Reference Range: low – high" */}
      {value.reference_range_low !== null && value.reference_range_high !== null && (
        <div className="mt-3">
          <RangeBar
            value={typeof value.value === "number" ? value.value : Number(value.value) || 0}
            low={value.reference_range_low}
            high={value.reference_range_high}
            unit={value.unit}
          />
        </div>
      )}

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

      {/* Indeterminate rows rarely have an LLM explanation — show a calm
          helper line so users see uncertainty as intentional, not missing. */}
      {isIndet && !(explanation && (explanation.summary || explanation.what_it_means)) && (
        <p className="mt-3 text-xs text-gray-600 dark:text-gray-400 italic border-l-2 border-gray-300 dark:border-gray-600 pl-2">
          {unclearHelper(value, language)}
        </p>
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
