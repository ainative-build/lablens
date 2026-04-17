"use client";

import { useEffect, useRef, useState } from "react";
import { useParams, useSearchParams } from "next/navigation";
import Link from "next/link";
import { DisclaimerBanner } from "@/components/disclaimer-banner";
import { PanicStickyBanner } from "@/components/panic-sticky-banner";
import { ResultsRightRail } from "@/components/results-right-rail";
import { SummaryCard } from "@/components/summary-card";
import { TopicGroup } from "@/components/topic-group";
import type { AnalysisResult } from "@/lib/api-client";
import { getExportUrl, pollResult } from "@/lib/api-client";
import type { Language } from "@/lib/i18n";
import { t } from "@/lib/i18n";

const MAX_POLL_ATTEMPTS = 60; // ~ 10 min wall time

function nextDelay(attempt: number): number {
  // 2s, 4s, 8s, 16s, 16s, ...
  return Math.min(2000 * 2 ** Math.min(attempt, 3), 16000);
}

export default function ResultsPage() {
  const params = useParams();
  const searchParams = useSearchParams();
  const jobId = params.jobId as string;
  // Language is owned by AppShell; we read ?lang= for poll initialization
  // and rendering. AppShell's selector updates the URL via push.
  const language = (searchParams.get("lang") as Language) || "en";
  const [result, setResult] = useState<AnalysisResult | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [stillWorking, setStillWorking] = useState(false);
  const attemptRef = useRef(0);

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
    <div className="px-4 py-5">
      <PanicStickyBanner values={data.values} language={language} />

      {/* Mobile/tablet: right-rail content collapses into a horizontal scroll
          strip ABOVE the main content. Desktop ≥lg: hidden here, shown as
          a true side panel below. */}
      <div className="lg:hidden mb-4 -mx-4 px-4 overflow-x-auto snap-x">
        <div className="flex gap-3 min-w-max pb-1">
          <div className="w-72 shrink-0 snap-start">
            <ResultsRightRail result={data} language={language} />
          </div>
        </div>
      </div>

      {/* Two-column layout on lg+; main fixed-width centered, right rail fixed */}
      <div className="lg:grid lg:grid-cols-[minmax(0,1fr)_320px] lg:gap-6 max-w-[1180px] mx-auto">
        <div className="space-y-5 min-w-0">
          {/* Toolbar — page-level actions */}
          <div className="flex justify-between items-center flex-wrap gap-2">
            <h1 className="text-2xl font-bold text-[var(--foreground)]">
              {t("results.title", language)}
            </h1>
            <a
              href={getExportUrl(jobId)}
              download
              className="px-3 py-1.5 text-sm bg-[var(--color-surface)] border border-[var(--color-border)] rounded-md hover:bg-[var(--color-surface-muted)] text-[var(--foreground)] focus-visible:outline focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-[var(--color-brand-500)]"
            >
              {t("results.export_csv", language)}
            </a>
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

          <div className="pt-4 border-t border-[var(--color-border)] text-center">
            <Link
              href="/"
              className="text-[var(--color-brand-600)] hover:underline text-sm focus-visible:outline focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-[var(--color-brand-500)] rounded"
            >
              {t("results.back", language)}
            </Link>
          </div>
        </div>

        {/* Right rail — desktop only (mobile shows it above as scroll strip) */}
        <aside className="hidden lg:block">
          <div className="sticky top-4">
            <ResultsRightRail result={data} language={language} />
          </div>
        </aside>
      </div>
      {/* Sticky chat bar lives in AppShell — auto-shown for /results/* routes. */}
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
