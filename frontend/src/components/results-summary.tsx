import type { AnalysisResult } from "@/lib/api-client";
import type { Language } from "@/lib/i18n";
import { t } from "@/lib/i18n";

interface Props {
  result: NonNullable<AnalysisResult["result"]>;
  language: Language;
}

export function ResultsSummary({ result, language }: Props) {
  const abnormal = result.values.filter((v) => v.direction !== "in-range");
  const critical = result.values.filter((v) => v.severity === "critical");

  return (
    <div className="grid grid-cols-2 sm:grid-cols-4 gap-4">
      <div className="bg-white rounded-lg border p-4 text-center">
        <div className="text-2xl font-bold">{result.values.length}</div>
        <div className="text-sm text-gray-500">Total Tests</div>
      </div>
      <div className="bg-white rounded-lg border p-4 text-center">
        <div className="text-2xl font-bold text-orange-600">{abnormal.length}</div>
        <div className="text-sm text-gray-500">Abnormal</div>
      </div>
      <div className="bg-white rounded-lg border p-4 text-center">
        <div className="text-2xl font-bold text-red-600">{critical.length}</div>
        <div className="text-sm text-gray-500">{t("results.critical", language)}</div>
      </div>
      <div className="bg-white rounded-lg border p-4 text-center">
        <div className="text-sm font-mono">{result.coverage_score}</div>
        <div className="text-sm text-gray-500">{t("results.coverage", language)}</div>
      </div>
    </div>
  );
}
