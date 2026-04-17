"use client";

import { useState } from "react";
import type { InterpretedValue } from "@/lib/api-client";
import type { Language } from "@/lib/i18n";
import { t } from "@/lib/i18n";
import { Disclosure } from "./disclosure";

interface Props {
  value: InterpretedValue;
  language: Language;
}

/** L4 — technical audit panel, hidden by default behind a disclosure. */
export function AuditPanel({ value, language }: Props) {
  const [open, setOpen] = useState(false);
  return (
    <Disclosure
      isOpen={open}
      onToggle={() => setOpen((v) => !v)}
      triggerClassName="text-xs text-gray-500 hover:text-gray-700 mt-2 underline-offset-2 hover:underline"
      bodyClassName="mt-2 text-xs text-gray-600 space-y-1 bg-gray-50 dark:bg-gray-800 dark:text-gray-300 p-2 rounded border border-gray-200 dark:border-gray-700"
      trigger={open ? t("audit.hide", language) : t("audit.show", language)}
    >
      {/* Confidence is per-value extraction confidence; moved here so the
          card header carries one badge (severity), not two competing dimensions. */}
      <Row label={t("audit.confidence", language)} value={value.confidence} />
      <Row label={t("audit.range_source", language)} value={value.range_source} />
      {value.range_trust && (
        <Row label={t("audit.range_trust", language)} value={value.range_trust} />
      )}
      {value.verification_verdict && (
        <Row label={t("audit.verifier", language)} value={value.verification_verdict} />
      )}
      {value.unit_confidence && (
        <Row
          label={t("audit.unit_confidence", language)}
          value={value.unit_confidence}
        />
      )}
      {value.section_type && (
        <Row label={t("audit.section_type", language)} value={value.section_type} />
      )}
      {value.loinc_code && (
        <Row label={t("audit.loinc", language)} value={value.loinc_code} />
      )}
      {Object.keys(value.evidence_trace || {}).length > 0 && (
        <details className="mt-1">
          <summary className="cursor-pointer">evidence_trace</summary>
          <pre className="mt-1 overflow-x-auto whitespace-pre-wrap break-all">
            {JSON.stringify(value.evidence_trace, null, 2)}
          </pre>
        </details>
      )}
    </Disclosure>
  );
}

function Row({ label, value }: { label: string; value: string }) {
  return (
    <div className="flex gap-2">
      <span className="font-medium">{label}:</span>
      <span className="font-mono">{value}</span>
    </div>
  );
}
