import type { Explanation, InterpretedValue } from "@/lib/api-client";
import type { Language } from "@/lib/i18n";
import { t } from "@/lib/i18n";
import { ConfidenceBadge } from "./confidence-badge";
import { SeverityBadge } from "./severity-badge";

interface Props {
  result: InterpretedValue;
  explanation?: Explanation;
  language: Language;
}

export function EvidencePanel({ result, explanation, language }: Props) {
  return (
    <div className={`rounded-lg p-4 border ${result.is_panic ? "border-red-500 border-2" : "border-gray-200"}`}>
      <div className="flex justify-between items-start flex-wrap gap-2">
        <h3 className="font-semibold text-lg">{result.test_name}</h3>
        <div className="flex gap-2">
          <SeverityBadge severity={result.severity} />
          <ConfidenceBadge confidence={result.confidence} />
        </div>
      </div>

      <div className="mt-2 grid grid-cols-1 sm:grid-cols-2 gap-2 text-sm">
        <div>
          Value: <strong>{result.value} {result.unit}</strong>
        </div>
        <div>
          Direction: <strong>{result.direction}</strong>
        </div>
        <div>
          {t("results.range", language)}: {result.reference_range_low}&ndash;{result.reference_range_high}
        </div>
        <div>
          {t("results.source", language)}: <span className="text-gray-600">{result.range_source}</span>
        </div>
      </div>

      {explanation && (
        <div className="mt-3 bg-gray-50 rounded p-3 text-sm space-y-1">
          <p className="font-medium">{explanation.summary}</p>
          <p className="text-gray-700">{explanation.what_it_means}</p>
          <p className="text-blue-700">{explanation.next_steps}</p>
        </div>
      )}

      {result.is_panic && (
        <div className="mt-2 bg-red-50 text-red-700 p-2 rounded text-sm font-medium">
          {t("results.panic", language)}
        </div>
      )}
    </div>
  );
}
