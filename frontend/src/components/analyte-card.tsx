"use client";

import { useState } from "react";
import type { Explanation, InterpretedValue } from "@/lib/api-client";
import type { Language } from "@/lib/i18n";
import { t } from "@/lib/i18n";
import { AuditPanel } from "./audit-panel";
import { ConfidenceBadge } from "./confidence-badge";
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

  // Low-confidence rows must never wear a severity tier badge — the engine
  // has already flagged the classification as weak, so surfacing "Mild" or
  // "Minor" would contradict the low_confidence state pill and the Qwen
  // copy (which correctly reasons the value is within range).
  const isWeakClassification =
    value.classification_state === "low_confidence" ||
    value.classification_state === "could_not_classify";

  // Phase 3 state pill — only render when not fully classified. We hide it
  // on `could_not_classify` rows whose severity badge already says "Unclear"
  // so we don't double-up on the same signal.
  const state = value.classification_state;
  const showStatePill =
    state === "low_confidence" ||
    (state === "could_not_classify" && !isIndet);
  const stateLabel =
    state === "low_confidence"
      ? t("state.low_confidence", language)
      : state === "could_not_classify"
        ? t("state.could_not_classify", language)
        : "";
  const stateTip =
    state === "low_confidence"
      ? t("state.low_confidence_tip", language)
      : state === "could_not_classify"
        ? t("state.could_not_classify_tip", language)
        : "";

  const borderClass = value.is_panic
    ? "border-rose-500 border-2"
    : isAbnormal
      ? "border-amber-200 dark:border-amber-700"
      : isIndet
        ? "border-gray-300 dark:border-gray-600"
        : "border-gray-200 dark:border-gray-700";

  // PR #6 v6 calibration: tighten card to 4 essentials, hide rest.
  // Card surfaces (in order):
  //   1. test name + direction icon
  //   2. value + unit + severity badge
  //   3. range bar (visual)
  //   4. ONE "why it matters" line (explanation.summary OR first sentence of what_it_means)
  //   5. ONE "what to do" line (explanation.next_steps)
  //   ⤷ "Learn more" expand: full what_it_means body + technical audit
  const whyItMatters = explanation?.summary ||
    (explanation?.what_it_means
      ? firstSentence(explanation.what_it_means)
      : null);
  const fullExplanation = explanation?.what_it_means || null;
  // Show "Learn more" only when there's MORE to reveal beyond the 1-line summary.
  const hasMore =
    fullExplanation &&
    fullExplanation.trim() !== (whyItMatters || "").trim();

  const [learnMoreOpen, setLearnMoreOpen] = useState(false);

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
        <div className="flex items-center gap-2 flex-wrap max-w-full">
          {showStatePill && (
            <span
              title={stateTip}
              className="inline-flex items-center rounded-full border border-gray-300 dark:border-gray-600 bg-gray-50 dark:bg-gray-800 px-2 py-0.5 text-[11px] font-medium text-gray-700 dark:text-gray-300"
            >
              {stateLabel}
            </span>
          )}
          {/* Phase 4 — provenance badge. Only rendered for rows that are NOT
              fully classified OR where the range provenance is worth flagging
              (lab-only, rule-based). Pure function; returns null otherwise. */}
          {(isAbnormal || isIndet || isWeakClassification) && (
            <ConfidenceBadge
              confidence={value.confidence}
              range_source={value.range_source}
              classification_state={value.classification_state}
              language={language}
            />
          )}
          <SeverityBadge
            variant={
              isIndet || isWeakClassification
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

      {/* Range bar */}
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

      {/* Lab-flagged but no curated range — surface the limitation so users
          understand why we trusted the lab's H/L without showing a range bar. */}
      {value.range_source === "ocr-flag-fallback" &&
        (value.direction === "high" || value.direction === "low") && (
          <p className="mt-2 text-xs text-[var(--foreground-muted)] italic border-l-2 border-[var(--color-border-strong)] pl-2">
            {unclearHelper(value, language)}
          </p>
        )}

      {/* PR #6 v6: tightened "why it matters" + "what to do" lines */}
      {whyItMatters && (
        <p className="mt-3 text-sm text-gray-800 dark:text-gray-200 leading-relaxed">
          {whyItMatters}
        </p>
      )}
      {explanation?.next_steps && (
        <p className="mt-1.5 text-sm text-[var(--color-brand-700)] dark:text-[var(--color-brand-500)] leading-relaxed">
          <span className="font-medium">{t("card.next_step", language)}:</span>{" "}
          {explanation.next_steps}
        </p>
      )}

      {/* Indeterminate rows rarely have an LLM explanation — calm helper line */}
      {isIndet && !whyItMatters && (
        <p className="mt-3 text-xs text-gray-600 dark:text-gray-400 italic border-l-2 border-gray-300 dark:border-gray-600 pl-2">
          {unclearHelper(value, language)}
        </p>
      )}

      {value.is_panic && (
        <div className="mt-2 bg-rose-50 dark:bg-rose-950 text-rose-800 dark:text-rose-200 p-2 rounded text-sm font-medium">
          {t("results.panic", language)}
        </div>
      )}

      {/* Learn more — full LLM explanation behind a disclosure */}
      {hasMore && (
        <div className="mt-3">
          <button
            type="button"
            onClick={() => setLearnMoreOpen((v) => !v)}
            aria-expanded={learnMoreOpen}
            className="text-xs text-[var(--color-brand-700)] dark:text-[var(--color-brand-500)] hover:underline focus-visible:outline focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-[var(--color-brand-500)] rounded"
          >
            {learnMoreOpen
              ? t("card.learn_less", language)
              : t("card.learn_more", language)}
          </button>
          {learnMoreOpen && fullExplanation && (
            <p className="mt-2 text-sm text-gray-700 dark:text-gray-300 bg-gray-50 dark:bg-gray-800 rounded p-3 leading-relaxed">
              {fullExplanation}
            </p>
          )}
        </div>
      )}

      <AuditPanel value={value} language={language} />
    </div>
  );
}

/** Best-effort "first sentence" — handles common end punctuation. */
function firstSentence(text: string): string {
  const trimmed = text.trim();
  // Match through the first . ! ? followed by space or end.
  const m = trimmed.match(/^.+?[.!?](?=\s|$)/);
  return m ? m[0] : trimmed;
}
