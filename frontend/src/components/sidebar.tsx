"use client";

import Link from "next/link";
import { useRouter } from "next/navigation";
import { useState } from "react";
import { LanguageSelector } from "@/components/language-selector";
import { PDFUploader } from "@/components/pdf-uploader";
import { uploadReport } from "@/lib/api-client";
import type { Language } from "@/lib/i18n";
import { t } from "@/lib/i18n";

interface Props {
  language: Language;
  onLanguageChange: (lang: Language) => void;
}

/**
 * Persistent left rail (BloodGPT-style minimal sidebar).
 * Logo at top, mini "New Test" upload card in the middle, language selector at bottom.
 * Renders inline at ≥md breakpoint; off-canvas drawer below md (toggled by AppShell).
 */
export function Sidebar({ language, onLanguageChange }: Props) {
  const router = useRouter();
  const [uploadingFile, setUploadingFile] = useState<string | null>(null);
  const [uploadError, setUploadError] = useState<string | null>(null);

  const handleUpload = async (file: File) => {
    setUploadingFile(file.name);
    setUploadError(null);
    try {
      const jobId = await uploadReport(file, language);
      router.push(`/results/${jobId}?lang=${language}`);
    } catch (err) {
      setUploadError(err instanceof Error ? err.message : "Upload failed");
      setUploadingFile(null);
    }
  };

  return (
    <aside
      aria-label="App navigation"
      className="flex flex-col h-full p-4 gap-4 bg-[var(--color-surface)] border-r border-[var(--color-border)]"
    >
      {/* Logo / wordmark */}
      <Link
        href="/"
        className="flex items-center gap-2 px-2 py-1 rounded-md hover:bg-[var(--color-surface-muted)] focus-visible:outline focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-[var(--color-brand-500)]"
      >
        <span
          aria-hidden
          className="inline-flex items-center justify-center h-7 w-7 rounded-full bg-[var(--color-brand-500)] text-white font-bold text-sm"
        >
          L
        </span>
        <span className="font-semibold text-base text-[var(--foreground)]">
          LabLens
        </span>
      </Link>

      {/* Mini upload card */}
      <div className="rounded-[var(--radius-card)] border border-[var(--color-border)] bg-[var(--color-surface-muted)] p-3 mt-2">
        <p className="text-xs font-medium text-[var(--foreground)] mb-2">
          {t("upload.title", language)}
        </p>
        <CompactUpload onUpload={handleUpload} language={language} />
        {uploadingFile && (
          <div
            role="status"
            className="mt-2 inline-flex items-center gap-1.5 text-xs text-[var(--foreground)] font-medium"
            title={uploadingFile}
          >
            <svg
              aria-hidden="true"
              viewBox="0 0 24 24"
              fill="none"
              stroke="currentColor"
              strokeWidth="2.5"
              className="h-3 w-3 animate-spin text-[var(--color-brand-600)] shrink-0"
            >
              <path d="M12 3a9 9 0 1 0 9 9" strokeLinecap="round" />
            </svg>
            <span className="truncate">
              {t("upload.analyzing", language)}
            </span>
          </div>
        )}
        {uploadError && (
          <p className="mt-2 text-xs text-rose-600 dark:text-rose-400">
            {t("error.upload", language)}
          </p>
        )}
      </div>

      {/* Spacer pushes language selector to the bottom */}
      <div className="flex-1" />

      {/* Language at bottom */}
      <LanguageSelector value={language} onChange={onLanguageChange} />
    </aside>
  );
}

/**
 * Compact upload trigger for the sidebar slot. Reuses the full `<PDFUploader>`
 * primitive — just sized down for the rail.
 */
function CompactUpload({
  onUpload,
  language,
}: {
  onUpload: (file: File) => void;
  language: Language;
}) {
  return (
    <div className="text-xs">
      <PDFUploader onUpload={onUpload} isLoading={false} language={language} />
    </div>
  );
}
