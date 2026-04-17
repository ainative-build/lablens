"use client";

import type { Language } from "@/lib/i18n";
import { t } from "@/lib/i18n";

export type ProvenanceVariant =
  | "high"
  | "lab_flagged"
  | "missing_range"
  | "rule_based";

interface Props {
  confidence?: string;
  range_source?: string;
  classification_state?: "classified" | "low_confidence" | "could_not_classify";
  language: Language;
}

/**
 * Phase 4 — confidence/provenance badge. Picks at most one of four variants
 * based on range provenance + classification state. Returns null when no
 * variant fires (e.g. normal row with curated range) to avoid visual noise.
 *
 * Dispatch priority (first match wins):
 *   missing_range — no range AND row could not classify
 *   lab_flagged   — classified only via the lab's own H/L flag (no numeric range)
 *   high          — confident curated or validated lab range
 *   rule_based    — built-in clinical rule used as a fallback for an unvalidated range
 */
export function ConfidenceBadge({
  confidence,
  range_source,
  classification_state,
  language,
}: Props) {
  const variant = pickVariant({
    confidence,
    range_source,
    classification_state,
  });
  if (!variant) return null;

  const styles: Record<ProvenanceVariant, string> = {
    high: "bg-sky-50 text-sky-800 border-sky-200 dark:bg-sky-950/40 dark:text-sky-200 dark:border-sky-800",
    lab_flagged:
      "bg-stone-100 text-stone-800 border-stone-300 dark:bg-stone-800 dark:text-stone-200 dark:border-stone-700",
    missing_range:
      "bg-amber-50 text-amber-900 border-amber-200 dark:bg-amber-950/40 dark:text-amber-200 dark:border-amber-800",
    rule_based:
      "bg-neutral-100 text-neutral-800 border-neutral-300 dark:bg-neutral-800 dark:text-neutral-200 dark:border-neutral-700",
  };

  return (
    <span
      title={t(`badge.${variant}.tip`, language)}
      className={`inline-flex items-center whitespace-nowrap rounded-full border px-2 py-0.5 text-[11px] font-medium ${styles[variant]}`}
    >
      {t(`badge.${variant}`, language)}
    </span>
  );
}

function pickVariant({
  confidence,
  range_source,
  classification_state,
}: {
  confidence?: string;
  range_source?: string;
  classification_state?: string;
}): ProvenanceVariant | null {
  const src = (range_source || "").toLowerCase();
  const state = (classification_state || "").toLowerCase();

  if (state === "could_not_classify" && (src === "no-range" || !src)) {
    return "missing_range";
  }
  if (src === "ocr-flag-fallback" || src === "range-text") {
    return "lab_flagged";
  }
  if (src === "curated-fallback" && confidence === "high") {
    return "rule_based";
  }
  if (
    confidence === "high" &&
    (src === "lab-provided-validated" || src === "curated-fallback")
  ) {
    return "high";
  }
  return null;
}
