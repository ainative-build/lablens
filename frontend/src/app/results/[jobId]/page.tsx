"use client";

import { useEffect, useRef, useState } from "react";
import { useParams, useSearchParams } from "next/navigation";
import Link from "next/link";
import dynamic from "next/dynamic";
import { DisclaimerBanner } from "@/components/disclaimer-banner";
import { LanguageSelector } from "@/components/language-selector";
import { PanicStickyBanner } from "@/components/panic-sticky-banner";
import { SummaryCard } from "@/components/summary-card";
import { TopicGroup } from "@/components/topic-group";
import type { AnalysisResult } from "@/lib/api-client";
import { getExportUrl, pollResult } from "@/lib/api-client";
import type { Language } from "@/lib/i18n";
import { t } from "@/lib/i18n";

// Phase 4 (lazy): Q&A pane is loaded only when the user opens it.
const ChatPane = dynamic(
  () => import("@/components/chat/qa-pane").then((m) => m.QaPane),
  { ssr: false }
);

const MAX_POLL_ATTEMPTS = 60; // ~ 10 min wall time

function nextDelay(attempt: number): number {
  // 2s, 4s, 8s, 16s, 16s, ...
  return Math.min(2000 * 2 ** Math.min(attempt, 3), 16000);
}

export default function ResultsPage() {
  const params = useParams();
  const searchParams = useSearchParams();
  const jobId = params.jobId as string;
  const [language, setLanguage] = useState<Language>(
    (searchParams.get("lang") as Language) || "en"
  );
  const [result, setResult] = useState<AnalysisResult | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [stillWorking, setStillWorking] = useState(false);
  const [chatOpen, setChatOpen] = useState(false);
  const attemptRef = useRef(0);

  // Sync <html lang/dir> with selected language for a11y + RTL.
  useEffect(() => {
    if (typeof document !== "undefined") {
      document.documentElement.lang = language;
      document.documentElement.dir = language === "ar" ? "rtl" : "ltr";
    }
  }, [language]);

  useEffect(() => {
    if (!jobId) return;
    let cancelled = false;
    let timer: ReturnType<typeof setTimeout> | null = null;

    const poll = async () => {
      attemptRef.current += 1;
      if (attemptRef.current > MAX_POLL_ATTEMPTS) {
        if (!cancelled) setError("timeout");
        return;
      }
      if (attemptRef.current === 30) setStillWorking(true);
      try {
        const data = await pollResult(jobId);
        if (cancelled) return;
        setResult(data);
        if (data.status === "queued" || data.status === "processing") {
          timer = setTimeout(poll, nextDelay(attemptRef.current));
        }
      } catch (e) {
        if (cancelled) return;
        // Network error → exponential backoff retry
        timer = setTimeout(poll, nextDelay(attemptRef.current));
      }
    };

    poll();
    return () => {
      cancelled = true;
      if (timer) clearTimeout(timer);
    };
  }, [jobId]);

  // ── Loading / error states ──
  if (error === "timeout") {
    return (
      <ErrorBox
        message="Analysis is taking too long. Please try uploading again."
        language={language}
      />
    );
  }
  if (error) {
    return <ErrorBox message={`${t("error.analysis", language)}: ${error}`} language={language} />;
  }
  if (!result || result.status === "queued" || result.status === "processing") {
    return (
      <div className="flex-1 flex items-center justify-center p-4">
        <div className="text-center space-y-4">
          <div
            role="status"
            aria-live="polite"
            className="inline-block h-10 w-10 animate-spin rounded-full border-4 border-gray-300 border-t-blue-600"
          />
          <p className="text-gray-700 dark:text-gray-300 text-lg">
            {t("upload.analyzing", language)}
          </p>
          {stillWorking && (
            <p className="text-sm text-gray-500 dark:text-gray-400">
              Still working...
            </p>
          )}
          <p className="text-xs text-gray-500 dark:text-gray-400">
            Job: {jobId}
          </p>
        </div>
      </div>
    );
  }
  if (result.status === "failed") {
    return <ErrorBox message={`${t("error.analysis", language)}: ${result.error ?? ""}`} language={language} />;
  }

  // ── Success: render summary + grouped layout ──
  const data = result.result!;
  const summary = data.summary;
  const groups = data.topic_groups ?? [];

  return (
    <div className="flex-1 p-4 max-w-5xl mx-auto space-y-6">
      <PanicStickyBanner values={data.values} language={language} />

      <div className="flex justify-between items-center flex-wrap gap-2">
        <h1 className="text-2xl font-bold text-gray-900 dark:text-gray-50">
          {t("results.title", language)}
        </h1>
        <div className="flex items-center gap-3">
          <a
            href={getExportUrl(jobId)}
            download
            className="px-3 py-1.5 text-sm bg-white dark:bg-gray-800 border border-gray-300 dark:border-gray-600 rounded-md hover:bg-gray-50 dark:hover:bg-gray-700 text-gray-700 dark:text-gray-200 focus-visible:outline focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-blue-500"
          >
            {t("results.export_csv", language)}
          </a>
          <LanguageSelector value={language} onChange={setLanguage} />
        </div>
      </div>

      <DisclaimerBanner type="results" language={language} />

      {summary && <SummaryCard summary={summary} language={language} />}

      <div className="space-y-3">
        {groups.map((g) => (
          <TopicGroup
            key={g.topic}
            group={g}
            explanations={data.explanations}
            language={language}
          />
        ))}
      </div>

      <div className="pt-4 border-t border-gray-200 dark:border-gray-700 text-center">
        <Link
          href="/"
          className="text-blue-600 dark:text-blue-400 hover:underline text-sm focus-visible:outline focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-blue-500 rounded"
        >
          {t("results.back", language)}
        </Link>
      </div>

      {/* Phase 4: Q&A floating CTA + lazy-loaded chat pane */}
      {!chatOpen && (
        <button
          type="button"
          onClick={() => setChatOpen(true)}
          className="fixed bottom-4 right-4 z-30 rounded-full bg-blue-600 hover:bg-blue-700 text-white px-5 py-3 text-sm font-medium shadow-lg focus-visible:outline focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-blue-500"
        >
          💬 {t("chat.cta_open", language)}
        </button>
      )}
      {chatOpen && (
        <ChatPane
          jobId={jobId}
          language={language}
          onClose={() => setChatOpen(false)}
        />
      )}
    </div>
  );
}

function ErrorBox({ message, language }: { message: string; language: Language }) {
  return (
    <div className="flex-1 flex items-center justify-center p-4">
      <div className="w-full max-w-2xl space-y-4">
        <div className="bg-rose-50 dark:bg-rose-950 border border-rose-200 dark:border-rose-800 text-rose-800 dark:text-rose-200 rounded-md p-4">
          {message}
        </div>
        <Link
          href="/"
          className="text-blue-600 dark:text-blue-400 hover:underline text-sm"
        >
          {t("results.back", language)}
        </Link>
      </div>
    </div>
  );
}
