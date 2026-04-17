"use client";

import { useEffect, useRef, useState } from "react";
import { useParams } from "next/navigation";
import Link from "next/link";
import { ChatDock } from "@/components/chat-dock";
import { DisclaimerBanner } from "@/components/disclaimer-banner";
import { PanicStickyBanner } from "@/components/panic-sticky-banner";
import { ResultsRightRail } from "@/components/results-right-rail";
import { ShowAbnormalToggle } from "@/components/show-abnormal-toggle";
import { SummaryCard } from "@/components/summary-card";
import { TopicGroup } from "@/components/topic-group";
import type { AnalysisResult } from "@/lib/api-client";
import { getExportUrl, JobNotFoundError, pollResult } from "@/lib/api-client";
import { t } from "@/lib/i18n";

const MAX_POLL_ATTEMPTS = 60; // ~ 10 min wall time

function nextDelay(attempt: number): number {
  // 2s, 4s, 8s, 16s, 16s, ...
  return Math.min(2000 * 2 ** Math.min(attempt, 3), 16000);
}

export default function ResultsPage() {
  const params = useParams();
  const jobId = params.jobId as string;
  // English-only for now; switcher removed in feat/polish-v1. Restore by
  // reading ?lang= from URL when re-localizing.
  const language = "en" as const;
  const [result, setResult] = useState<AnalysisResult | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [stillWorking, setStillWorking] = useState(false);
  // Phase 5 — default ON: the page should open with only abnormal + unclear
  // rows visible so users see "the few things that matter" without scanning
  // past dozens of normal rows. Overridden by persisted preference if any.
  const [abnormalOnly, setAbnormalOnly] = useState(true);
  const [tipIndex, setTipIndex] = useState(0);
  const [exportError, setExportError] = useState<string | null>(null);
  const [exporting, setExporting] = useState(false);
  const attemptRef = useRef(0);

  // Fetch the CSV via JS so we can detect non-200 responses (e.g. 404
  // when the in-memory job_store has been wiped by a backend restart)
  // and surface a clear error instead of silently downloading the JSON
  // error body the way `<a download>` does.
  const handleExport = async () => {
    if (exporting) return;
    setExportError(null);
    setExporting(true);
    try {
      const resp = await fetch(getExportUrl(jobId));
      if (!resp.ok) {
        setExportError(t("results.export_failed", language));
        return;
      }
      const blob = await resp.blob();
      // Filename comes from Content-Disposition; fall back to a sensible default.
      const dispositionHeader = resp.headers.get("content-disposition") || "";
      const filenameMatch = dispositionHeader.match(/filename="?([^"]+)"?/);
      const filename = filenameMatch?.[1] ?? `lablens-${jobId.slice(0, 8)}.csv`;
      const url = URL.createObjectURL(blob);
      const a = document.createElement("a");
      a.href = url;
      a.download = filename;
      document.body.appendChild(a);
      a.click();
      document.body.removeChild(a);
      URL.revokeObjectURL(url);
    } catch {
      setExportError(t("results.export_failed", language));
    } finally {
      setExporting(false);
    }
  };

  // Rotate through friendly progress hints during the wait. 7 tips total,
  // each visible ~4.5 s. Mounted only while we're still polling — cleanup
  // clears the interval when results land or the page unmounts.
  const isProcessing =
    !result || result.status === "queued" || result.status === "processing";
  useEffect(() => {
    if (!isProcessing) return;
    const id = setInterval(() => {
      setTipIndex((i) => (i + 1) % 7);
    }, 4500);
    return () => clearInterval(id);
  }, [isProcessing]);

  // Restore abnormal-only preference from localStorage on mount.
  // Default is ON (Phase 5). Only flip to OFF when the user has explicitly
  // opted out before — that way first-time users get the calm default view.
  useEffect(() => {
    if (typeof window === "undefined") return;
    const v = window.localStorage.getItem("lablens.filter.abnormalOnly");
    if (v === "0") setAbnormalOnly(false);
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
        // Job ID not on the server (backend restart or stale URL) — stop
        // polling and surface a clear error so the user can re-upload.
        if (e instanceof JobNotFoundError) {
          setError("not_found");
          return;
        }
        // Otherwise treat as transient network error and back off.
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
      <ErrorBox message="Analysis is taking too long. Please try uploading again." />
    );
  }
  if (error === "not_found") {
    return (
      <ErrorBox message="This analysis has expired. Please upload the report again to continue." />
    );
  }
  if (error) {
    return <ErrorBox message={`${t("error.analysis", language)}: ${error}`} />;
  }
  if (isProcessing) {
    // Centered loader, fills remaining height under the header via flex-1
    // (AppShell now makes <main> a flex column).
    const tipKey = `upload.tip.${tipIndex + 1}`;
    return (
      <div className="flex-1 flex items-center justify-center p-4">
        <div
          role="status"
          aria-busy="true"
          aria-live="polite"
          className="text-center space-y-4 max-w-md"
        >
          {/* Spinner + subtle pulse ring around it for depth */}
          <div className="relative inline-flex items-center justify-center h-16 w-16">
            <span
              aria-hidden
              className="absolute inset-0 rounded-full bg-[var(--color-brand-500)]/10 animate-ping"
            />
            <span
              aria-hidden
              className="absolute inset-2 rounded-full bg-[var(--color-brand-500)]/15"
            />
            <svg
              aria-hidden="true"
              viewBox="0 0 24 24"
              fill="none"
              stroke="currentColor"
              strokeWidth="2.5"
              className="relative h-8 w-8 animate-spin text-[var(--color-brand-600)]"
            >
              <path d="M12 3a9 9 0 1 0 9 9" strokeLinecap="round" />
            </svg>
          </div>

          <h1 className="text-xl font-semibold text-[var(--foreground)]">
            {t("upload.analyzing", language)}
          </h1>

          <p className="text-sm text-[var(--foreground)] opacity-70">
            {t("upload.timing_hint", language)}
          </p>

          {/* Rotating tip — fades in/out on change via `key` re-mount. */}
          <p
            key={tipIndex}
            className="text-sm text-[var(--color-brand-700)] dark:text-[var(--color-brand-500)] font-medium min-h-[1.5rem] animate-fade-in"
          >
            {t(tipKey, language)}
          </p>

          {stillWorking && (
            <p className="text-sm text-[var(--foreground-muted)] italic">
              {t("upload.still_working", language)}
            </p>
          )}

          <p className="text-[11px] text-[var(--foreground)] opacity-30 pt-2">
            Job: {jobId}
          </p>
        </div>
      </div>
    );
  }
  if (result.status === "failed") {
    return <ErrorBox message={`${t("error.analysis", language)}: ${result.error ?? ""}`} />;
  }

  // ── Success: render summary + grouped layout ──
  const data = result.result!;
  const summary = data.summary;
  const groups = data.topic_groups ?? [];

  return (
    <div className="px-4 py-5">
      <PanicStickyBanner values={data.values} language={language} />

      {/* Phase 5 — single-column calm layout. The old right-rail aside is
          gone; its role is now served by the compact counts strip directly
          under the SummaryCard. Keeps L1 focused on "am I okay · what
          matters · what to do" without competing panels. */}
      <div className="max-w-[760px] mx-auto">
        <div className="space-y-5 min-w-0">
          {/* SR-only page heading — visible affordance is the back link below. */}
          <h1 className="sr-only">{t("results.title", language)}</h1>

          {/* Toolbar — page-level actions. Left side carries the
              "Analyze another report" affordance so users always see how
              to start over. Right side: filter + export. */}
          <div className="flex justify-between items-center flex-wrap gap-3">
            <Link
              href="/"
              className="inline-flex items-center gap-1.5 text-sm font-medium text-[var(--color-brand-700)] hover:text-[var(--color-brand-600)] focus-visible:outline focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-[var(--color-brand-500)] rounded-md px-2 py-1 -mx-2"
            >
              <svg
                aria-hidden="true"
                viewBox="0 0 24 24"
                fill="none"
                stroke="currentColor"
                strokeWidth="2"
                strokeLinecap="round"
                strokeLinejoin="round"
                className="h-4 w-4"
              >
                <path d="M19 12H5M12 19l-7-7 7-7" />
              </svg>
              {t("results.back", language)}
            </Link>
            <div className="flex items-center gap-3">
              <ShowAbnormalToggle
                value={abnormalOnly}
                onChange={setAbnormalOnlyPersisted}
                language={language}
              />
              <button
                type="button"
                onClick={handleExport}
                disabled={exporting}
                className="px-3 py-1.5 text-sm bg-[var(--color-surface)] border border-[var(--color-border)] rounded-md hover:bg-[var(--color-surface-muted)] text-[var(--foreground)] focus-visible:outline focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-[var(--color-brand-500)] disabled:opacity-50 disabled:cursor-not-allowed"
              >
                {t("results.export_csv", language)}
              </button>
            </div>
          </div>

          {/* Inline export-error banner — shows when the export endpoint
              returns non-200 (most commonly 404 after a backend restart). */}
          {exportError && (
            <div
              role="alert"
              className="bg-[var(--color-surface-sunken)] border border-[var(--color-border)] rounded-[var(--radius-card)] p-3 text-sm text-[var(--foreground)] flex items-start gap-2"
            >
              <svg
                aria-hidden="true"
                viewBox="0 0 20 20"
                fill="currentColor"
                className="h-5 w-5 shrink-0 text-rose-600"
              >
                <path
                  fillRule="evenodd"
                  d="M10 18a8 8 0 100-16 8 8 0 000 16zM8.94 6.94a1.5 1.5 0 112.12 2.12L10 10.12V12a1 1 0 11-2 0V9.5c0-.4.16-.78.44-1.06l.5-.5zM10 16a1 1 0 100-2 1 1 0 000 2z"
                  clipRule="evenodd"
                />
              </svg>
              <span className="flex-1">{exportError}</span>
              <button
                type="button"
                onClick={() => setExportError(null)}
                aria-label="Dismiss"
                className="text-[var(--foreground-muted)] hover:text-[var(--foreground)] -mt-0.5"
              >
                ×
              </button>
            </div>
          )}

          <DisclaimerBanner type="results" language={language} />

          {summary && <SummaryCard summary={summary} language={language} />}

          {/* Phase 5 — compact counts strip (single line). Replaces the
              old right-rail donut panels so L1 is calmer. */}
          <ResultsRightRail result={data} language={language} />

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
      </div>
      {/* Floating chat dock — only mounted now that results are confirmed
          ready. While scanning, the CTA is intentionally hidden. */}
      <ChatDock jobId={jobId} language={language} />
    </div>
  );
}

function ErrorBox({ message }: { message: string }) {
  // Token-aligned: surface-sunken + border tokens match SummaryCard tone.
  // Error tone is conveyed by the icon, not by tinting the whole panel.
  // Hardcoded "en" since the app is English-only for now.
  const language = "en" as const;
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
