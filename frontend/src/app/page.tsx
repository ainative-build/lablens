"use client";

import { useCallback, useState } from "react";
import { useRouter } from "next/navigation";
import { DisclaimerBanner } from "@/components/disclaimer-banner";
import { PDFUploader } from "@/components/pdf-uploader";
import { uploadReport } from "@/lib/api-client";
import { t } from "@/lib/i18n";

/**
 * Landing — single-column hero, prominent dropzone, three trust signals,
 * quiet disclaimer footer. Designed against the "Accessible & Ethical"
 * style + healthcare type pairing (Figtree headline / Geist body).
 *
 * English-only for now; `language` is hardcoded so the i18n surface stays
 * intact for future re-localization.
 */
export default function HomePage() {
  const router = useRouter();
  const language = "en" as const;

  const [isLoading, setIsLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const handleUpload = useCallback(
    async (file: File) => {
      setIsLoading(true);
      setError(null);
      try {
        const jobId = await uploadReport(file, language);
        router.push(`/results/${jobId}`);
      } catch (e) {
        setError(e instanceof Error ? e.message : t("error.upload", language));
        setIsLoading(false);
      }
    },
    [router]
  );

  return (
    <div className="mx-auto max-w-[var(--container-max)] px-4 sm:px-6">
      {/* Hero — eyebrow + display headline + sub */}
      <section className="pt-10 sm:pt-16 pb-6 sm:pb-8 text-center max-w-[720px] mx-auto">
        <p className="inline-flex items-center gap-2 text-xs font-medium uppercase tracking-wider text-[var(--color-brand-700)] bg-[var(--color-brand-50)] border border-[var(--color-brand-100)] rounded-full px-3 py-1">
          <span
            aria-hidden
            className="inline-block h-1.5 w-1.5 rounded-full bg-[var(--color-brand-500)]"
          />
          {t("hero.eyebrow", language)}
        </p>
        <h1 className="font-display mt-5 text-3xl sm:text-5xl font-bold text-[var(--foreground)] leading-tight tracking-tight">
          {t("hero.headline", language)}
        </h1>
        <p className="mt-4 text-base sm:text-lg text-[var(--foreground-muted)] leading-relaxed max-w-[600px] mx-auto">
          {t("hero.sub", language)}
        </p>
      </section>

      {/* Dropzone — primary CTA */}
      <section className="max-w-[640px] mx-auto">
        <PDFUploader
          onUpload={handleUpload}
          isLoading={isLoading}
          language={language}
        />
        <p className="mt-3 text-center text-xs text-[var(--foreground-muted)]">
          {t("hero.cta_hint", language)}
        </p>

        {isLoading && (
          <div
            role="status"
            aria-busy="true"
            aria-live="polite"
            className="mt-6 text-center space-y-1.5"
          >
            <div className="inline-flex items-center gap-2 text-[var(--foreground)] font-semibold text-base">
              <svg
                aria-hidden="true"
                viewBox="0 0 24 24"
                fill="none"
                stroke="currentColor"
                strokeWidth="2.5"
                className="h-5 w-5 animate-spin text-[var(--color-brand-600)]"
              >
                <path d="M12 3a9 9 0 1 0 9 9" strokeLinecap="round" />
              </svg>
              <span>{t("upload.analyzing", language)}</span>
            </div>
            <p className="text-sm text-[var(--foreground-muted)]">
              {t("upload.timing_hint", language)}
            </p>
          </div>
        )}

        {error && (
          <div
            role="alert"
            className="mt-6 bg-[var(--color-surface-sunken)] border border-[var(--color-border)] rounded-[var(--radius-card)] p-3 text-sm text-[var(--foreground)] flex items-start gap-2"
          >
            <svg
              aria-hidden="true"
              viewBox="0 0 20 20"
              fill="currentColor"
              className="h-5 w-5 shrink-0 text-rose-600 dark:text-rose-400"
            >
              <path
                fillRule="evenodd"
                d="M10 18a8 8 0 100-16 8 8 0 000 16zM8.94 6.94a1.5 1.5 0 112.12 2.12L10 10.12V12a1 1 0 11-2 0V9.5c0-.4.16-.78.44-1.06l.5-.5zM10 16a1 1 0 100-2 1 1 0 000 2z"
                clipRule="evenodd"
              />
            </svg>
            <span>{error}</span>
          </div>
        )}
      </section>

      {/* Trust signals — three pills, single row on md+, stacked on mobile */}
      <section
        className="mt-14 sm:mt-20 max-w-[920px] mx-auto grid grid-cols-1 md:grid-cols-3 gap-4"
        aria-label="Trust signals"
      >
        <TrustCard
          icon={
            <path d="M12 2 4 6v6c0 5 3.5 9 8 10 4.5-1 8-5 8-10V6l-8-4z" />
          }
          title={t("trust.private.title", language)}
          body={t("trust.private.body", language)}
        />
        <TrustCard
          icon={
            <>
              <circle cx="12" cy="12" r="9" />
              <path d="M12 7v5l3 2" strokeLinecap="round" />
            </>
          }
          title={t("trust.fast.title", language)}
          body={t("trust.fast.body", language)}
        />
        <TrustCard
          icon={
            <>
              <circle cx="12" cy="12" r="9" />
              <path d="M3 12h18M12 3a14 14 0 0 1 0 18M12 3a14 14 0 0 0 0 18" />
            </>
          }
          title={t("trust.languages.title", language)}
          body={t("trust.languages.body", language)}
        />
      </section>

      {/* Quiet disclaimer — bottom, low visual weight, full legal text */}
      <footer className="mt-16 sm:mt-24 pb-10 border-t border-[var(--color-border)] pt-8">
        <DisclaimerBanner type="upload" language={language} variant="compact" />
      </footer>
    </div>
  );
}

/**
 * Trust signal card. Inline SVG icon (children rendered inside <svg>) so each
 * card stays one tight node — no per-icon wrapper component proliferation.
 */
function TrustCard({
  icon,
  title,
  body,
}: {
  icon: React.ReactNode;
  title: string;
  body: string;
}) {
  return (
    <div className="rounded-[var(--radius-card)] border border-[var(--color-border)] bg-[var(--color-surface)] p-5 shadow-[var(--shadow-card)]">
      <div className="flex items-start gap-3">
        <span
          aria-hidden
          className="inline-flex items-center justify-center h-9 w-9 shrink-0 rounded-lg bg-[var(--color-brand-50)] text-[var(--color-brand-600)]"
        >
          <svg
            viewBox="0 0 24 24"
            fill="none"
            stroke="currentColor"
            strokeWidth="2"
            strokeLinejoin="round"
            className="h-5 w-5"
          >
            {icon}
          </svg>
        </span>
        <div className="min-w-0">
          <h3 className="font-display font-semibold text-[var(--foreground)] text-sm">
            {title}
          </h3>
          <p className="mt-1 text-sm text-[var(--foreground-muted)] leading-relaxed">
            {body}
          </p>
        </div>
      </div>
    </div>
  );
}
