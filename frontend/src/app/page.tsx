"use client";

import { useCallback, useState } from "react";
import { useRouter } from "next/navigation";
import { DisclaimerBanner } from "@/components/disclaimer-banner";
import { LanguageSelector } from "@/components/language-selector";
import { PDFUploader } from "@/components/pdf-uploader";
import { uploadReport } from "@/lib/api-client";
import type { Language } from "@/lib/i18n";
import { t } from "@/lib/i18n";

export default function HomePage() {
  const router = useRouter();
  const [language, setLanguage] = useState<Language>("en");
  const [isLoading, setIsLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const handleUpload = useCallback(
    async (file: File) => {
      setIsLoading(true);
      setError(null);
      try {
        const jobId = await uploadReport(file, language);
        router.push(`/results/${jobId}?lang=${language}`);
      } catch (e) {
        setError(e instanceof Error ? e.message : t("error.upload", language));
        setIsLoading(false);
      }
    },
    [language, router]
  );

  const dir = language === "ar" ? "rtl" : "ltr";

  return (
    <div dir={dir} className="flex-1 flex items-center justify-center p-4">
      <div className="w-full max-w-xl space-y-6">
        <div className="flex justify-between items-center">
          <h1 className="text-2xl font-bold text-gray-900">
            {t("upload.title", language)}
          </h1>
          <LanguageSelector value={language} onChange={setLanguage} />
        </div>

        <DisclaimerBanner type="upload" language={language} />

        <PDFUploader
          onUpload={handleUpload}
          isLoading={isLoading}
          language={language}
        />

        {isLoading && (
          <div
            role="status"
            aria-busy="true"
            aria-live="polite"
            className="space-y-3"
          >
            {/* Skeleton mirrors the results layout: 1 summary card + 2 topic groups.
                Same radius/border tokens as real components → minimal CLS on swap. */}
            <div className="h-32 rounded-[var(--radius-card)] border-2 border-[var(--color-border)] bg-[var(--color-surface-sunken)] animate-pulse" />
            <div className="h-20 rounded-[var(--radius-card)] border border-[var(--color-border)] bg-[var(--color-surface-sunken)] animate-pulse" />
            <div className="h-20 rounded-[var(--radius-card)] border border-[var(--color-border)] bg-[var(--color-surface-sunken)] animate-pulse" />
            <p className="text-center text-sm text-[var(--foreground)] opacity-70">
              {t("upload.skeleton.label", language)}
            </p>
            <span className="sr-only">{t("upload.analyzing", language)}</span>
          </div>
        )}

        {error && (
          <div
            role="alert"
            className="bg-[var(--color-surface-sunken)] border border-[var(--color-border)] rounded-[var(--radius-card)] p-3 text-sm text-[var(--foreground)] flex items-start gap-2"
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
      </div>
    </div>
  );
}
