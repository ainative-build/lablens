"use client";

import { useEffect, useRef, useState } from "react";
import { useParams, useSearchParams } from "next/navigation";
import Link from "next/link";
import { DisclaimerBanner } from "@/components/disclaimer-banner";
import { PanicStickyBanner } from "@/components/panic-sticky-banner";
import { ResultsRightRail } from "@/components/results-right-rail";
import { ShowAbnormalToggle } from "@/components/show-abnormal-toggle";
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
  const [abnormalOnly, setAbnormalOnly] = useState(false);
  const attemptRef = useRef(0);

  // Restore abnormal-only preference from localStorage on mount.
  useEffect(() => {
    if (typeof window === "undefined") return;
    const v = window.localStorage.getItem("lablens.filter.abnormalOnly");
    if (v === "1") setAbnormalOnly(true);
  }, []);

  const setAbnormalOnlyPersisted = (next: boolean) => {
    setAbnormalOnly(next);
    if (typeof window !== "undefined") {
      window.localStorage.setItem(
        "lablens.filter.abnormalOnly",
        next ? "1" : "0"
      );
    }
  };

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
    // Centered loader: spinner + bold caption + timing hint + job id. No
    // skeleton blocks — they read as empty/error cards more than "loading".
    return (
      <div className="flex-1 flex items-center justify-center p-4">
        <div
          role="status"
          aria-busy="true"
          aria-live="polite"
          className="text-center space-y-2"
        >
          <div className="inline-flex items-center gap-2 text-[var(--foreground)] font-semibold text-xl">
            <svg
              aria-hidden="true"
              viewBox="0 0 24 24"
              fill="none"
              stroke="currentColor"
              strokeWidth="2.5"
              className="h-6 w-6 animate-spin text-[var(--color-brand-600)]"
            >
              <path d="M12 3a9 9 0 1 0 9 9" strokeLinecap="round" />
            </svg>
            <span>{t("upload.analyzing", language)}</span>
          </div>
          <p className="text-sm text-[var(--foreground)] opacity-70">
            {t("upload.timing_hint", language)}
          </p>
          {stillWorking && (
            <p className="text-sm text-[var(--color-brand-600)] font-medium">
              {t("upload.still_working", language)}
            </p>
          )}
          <p className="text-[11px] text-[var(--foreground)] opacity-40">
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
          <div className="flex justify-between items-center flex-wrap gap-3">
            <h1 className="text-2xl font-bold text-[var(--foreground)]">
              {t("results.title", language)}
            </h1>
            <div className="flex items-center gap-3">
              <ShowAbnormalToggle
                value={abnormalOnly}
                onChange={setAbnormalOnlyPersisted}
                language={language}
              />
              <a
                href={getExportUrl(jobId)}
                download
                className="px-3 py-1.5 text-sm bg-[var(--color-surface)] border border-[var(--color-border)] rounded-md hover:bg-[var(--color-surface-muted)] text-[var(--foreground)] focus-visible:outline focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-[var(--color-brand-500)]"
              >
                {t("results.export_csv", language)}
              </a>
            </div>
          </div>

          <DisclaimerBanner type="results" language={language} />

          {summary && <SummaryCard summary={summary} language={language} />}

          <div className="space-y-3">
            {(() => {
              const visible = abnormalOnly
                ? groups.filter(
                    (g) =>
                      g.abnormal_count + g.indeterminate_count + (g.minor_count ?? 0) > 0
                  )
                : groups;
              if (visible.length === 0) {
                return (
                  <div
                    role="status"
                    className="bg-[var(--color-surface)] border border-[var(--color-border)] rounded-[var(--radius-card)] p-6 text-center flex flex-col items-center gap-2"
                  >
                    <svg
                      aria-hidden="true"
                      viewBox="0 0 20 20"
                      fill="currentColor"
                      className="h-6 w-6 text-emerald-600 dark:text-emerald-400"
                    >
                      <path
                        fillRule="evenodd"
                        d="M10 18a8 8 0 100-16 8 8 0 000 16zm3.707-9.293a1 1 0 00-1.414-1.414L9 10.586 7.707 9.293a1 1 0 00-1.414 1.414l2 2a1 1 0 001.414 0l4-4z"
                        clipRule="evenodd"
                      />
                    </svg>
                    <p className="text-[var(--foreground)] font-medium">
                      {t("results.empty.all_normal_title", language)}
                    </p>
                    <p className="text-sm text-[var(--foreground)] opacity-70">
                      {t("filter.empty_state", language)}
                    </p>
                  </div>
                );
              }
              return visible.map((g) => (
                <TopicGroup
                  key={g.topic}
                  group={g}
                  explanations={data.explanations}
                  language={language}
                  abnormalOnly={abnormalOnly}
                />
              ));
            })()}
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
  // Token-aligned: surface-sunken + border tokens match SummaryCard tone.
  // Error tone is conveyed by the icon, not by tinting the whole panel.
  return (
    <div className="flex-1 flex items-center justify-center p-4">
      <div className="w-full max-w-2xl space-y-4">
        <div
          role="alert"
          className="bg-[var(--color-surface-sunken)] border border-[var(--color-border)] rounded-[var(--radius-card)] p-4 flex items-start gap-3"
        >
          <svg
            aria-hidden="true"
            viewBox="0 0 20 20"
            fill="currentColor"
            className="h-5 w-5 mt-0.5 shrink-0 text-rose-600 dark:text-rose-400"
          >
            <path
              fillRule="evenodd"
              d="M8.485 2.495c.673-1.167 2.357-1.167 3.03 0l6.28 10.875c.673 1.167-.17 2.625-1.516 2.625H3.72c-1.347 0-2.189-1.458-1.515-2.625L8.485 2.495zM10 6a1 1 0 011 1v3a1 1 0 11-2 0V7a1 1 0 011-1zm0 8a1 1 0 100-2 1 1 0 000 2z"
              clipRule="evenodd"
            />
          </svg>
          <p className="text-[var(--foreground)] text-sm">{message}</p>
        </div>
        <Link
          href="/"
          className="text-[var(--color-brand-600)] hover:underline text-sm focus-visible:outline focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-[var(--color-brand-500)] rounded"
        >
          {t("results.back", language)}
        </Link>
      </div>
    </div>
  );
}
