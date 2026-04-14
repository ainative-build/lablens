"use client";

import { useEffect, useState } from "react";
import { useParams, useSearchParams } from "next/navigation";
import Link from "next/link";
import { DisclaimerBanner } from "@/components/disclaimer-banner";
import { EvidencePanel } from "@/components/evidence-panel";
import { LanguageSelector } from "@/components/language-selector";
import { ResultsSummary } from "@/components/results-summary";
import type { AnalysisResult } from "@/lib/api-client";
import { pollResult } from "@/lib/api-client";
import type { Language } from "@/lib/i18n";
import { t } from "@/lib/i18n";

export default function ResultsPage() {
  const params = useParams();
  const searchParams = useSearchParams();
  const jobId = params.jobId as string;
  const [language, setLanguage] = useState<Language>(
    (searchParams.get("lang") as Language) || "en"
  );
  const [result, setResult] = useState<AnalysisResult | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    if (!jobId) return;
    let cancelled = false;

    const poll = async () => {
      try {
        const data = await pollResult(jobId);
        if (cancelled) return;
        setResult(data);
        if (data.status === "queued" || data.status === "processing") {
          setTimeout(poll, 2000);
        }
      } catch (e) {
        if (!cancelled) {
          setError(e instanceof Error ? e.message : "Polling failed");
        }
      }
    };

    poll();
    return () => { cancelled = true; };
  }, [jobId]);

  const dir = language === "ar" ? "rtl" : "ltr";

  if (error) {
    return (
      <div dir={dir} className="flex-1 flex items-center justify-center p-4">
        <div className="w-full max-w-2xl space-y-4">
          <div className="bg-red-50 border border-red-200 text-red-700 rounded-md p-4">
            {t("error.analysis", language)}: {error}
          </div>
          <Link href="/" className="text-blue-600 hover:underline text-sm">
            {t("results.back", language)}
          </Link>
        </div>
      </div>
    );
  }

  if (!result || result.status === "queued" || result.status === "processing") {
    return (
      <div dir={dir} className="flex-1 flex items-center justify-center p-4">
        <div className="text-center space-y-4">
          <div className="inline-block h-10 w-10 animate-spin rounded-full border-4 border-gray-300 border-t-blue-600" />
          <p className="text-gray-600 text-lg">{t("upload.analyzing", language)}</p>
          <p className="text-sm text-gray-400">Job: {jobId}</p>
        </div>
      </div>
    );
  }

  if (result.status === "failed") {
    return (
      <div dir={dir} className="flex-1 flex items-center justify-center p-4">
        <div className="w-full max-w-2xl space-y-4">
          <div className="bg-red-50 border border-red-200 text-red-700 rounded-md p-4">
            {t("error.analysis", language)}: {result.error}
          </div>
          <Link href="/" className="text-blue-600 hover:underline text-sm">
            {t("results.back", language)}
          </Link>
        </div>
      </div>
    );
  }

  const data = result.result!;

  return (
    <div dir={dir} className="flex-1 p-4 max-w-4xl mx-auto space-y-6">
      <div className="flex justify-between items-center">
        <h1 className="text-2xl font-bold text-gray-900">
          {t("results.title", language)}
        </h1>
        <LanguageSelector value={language} onChange={setLanguage} />
      </div>

      <DisclaimerBanner type="results" language={language} />

      <ResultsSummary result={data} language={language} />

      <div className="space-y-4">
        {data.values.map((val, i) => {
          const explanation = data.explanations.find(
            (e) => e.test_name === val.test_name
          );
          return (
            <EvidencePanel
              key={`${val.test_name}-${i}`}
              result={val}
              explanation={explanation}
              language={language}
            />
          );
        })}
      </div>

      <div className="pt-4 border-t text-center">
        <Link
          href="/"
          className="text-blue-600 hover:underline text-sm"
        >
          {t("results.back", language)}
        </Link>
      </div>
    </div>
  );
}
