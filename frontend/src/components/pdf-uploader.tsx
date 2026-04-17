"use client";

import { useCallback, useRef, useState } from "react";
import type { Language } from "@/lib/i18n";
import { t } from "@/lib/i18n";

interface Props {
  onUpload: (file: File) => void;
  isLoading: boolean;
  language: Language;
}

/**
 * PDF dropzone — brand-token styled. Larger touch surface, clear hover/drag
 * affordance via brand-green border + tinted bg. Icon is an inline SVG so it
 * inherits theme color on light/dark.
 */
export function PDFUploader({ onUpload, isLoading, language }: Props) {
  const [dragActive, setDragActive] = useState(false);
  const inputRef = useRef<HTMLInputElement>(null);

  const handleDrop = useCallback(
    (e: React.DragEvent) => {
      e.preventDefault();
      setDragActive(false);
      const file = e.dataTransfer.files[0];
      if (file?.type === "application/pdf") onUpload(file);
    },
    [onUpload]
  );

  const handleClick = () => inputRef.current?.click();

  return (
    <div
      role="button"
      tabIndex={0}
      onDragOver={(e) => {
        e.preventDefault();
        setDragActive(true);
      }}
      onDragLeave={() => setDragActive(false)}
      onDrop={handleDrop}
      onClick={handleClick}
      onKeyDown={(e) => {
        if (e.key === "Enter" || e.key === " ") {
          e.preventDefault();
          handleClick();
        }
      }}
      aria-label={t("upload.dropzone", language)}
      aria-busy={isLoading}
      className={`group relative w-full rounded-[var(--radius-card)] border-2 border-dashed cursor-pointer transition-all duration-200 px-6 py-12 sm:py-16 text-center min-h-[44px] focus-visible:outline-none focus-visible:ring-4 focus-visible:ring-[var(--color-brand-500)]/30
        ${
          dragActive
            ? "border-[var(--color-brand-500)] bg-[var(--color-brand-50)] shadow-[var(--shadow-hero)]"
            : "border-[var(--color-border-strong)] bg-[var(--color-surface)] hover:border-[var(--color-brand-500)] hover:bg-[var(--color-brand-50)]/50"
        }
        ${isLoading ? "opacity-50 pointer-events-none" : ""}`}
    >
      {/* Document upload icon — brand tinted on hover/drag */}
      <svg
        aria-hidden="true"
        viewBox="0 0 48 48"
        fill="none"
        stroke="currentColor"
        strokeWidth={1.5}
        strokeLinecap="round"
        strokeLinejoin="round"
        className={`mx-auto h-12 w-12 mb-4 transition-colors ${
          dragActive
            ? "text-[var(--color-brand-600)]"
            : "text-[var(--foreground-muted)] group-hover:text-[var(--color-brand-600)]"
        }`}
      >
        <path d="M30 6H12a3 3 0 0 0-3 3v30a3 3 0 0 0 3 3h24a3 3 0 0 0 3-3V15z" />
        <path d="M30 6v9h9" />
        <path d="M24 33V21" />
        <path d="m18 27 6-6 6 6" />
      </svg>

      <p className="text-base sm:text-lg font-semibold text-[var(--foreground)]">
        {t("upload.dropzone", language)}
      </p>
      <p className="mt-1.5 text-sm text-[var(--foreground-muted)]">
        {t("upload.browse", language)}
      </p>

      <input
        ref={inputRef}
        type="file"
        accept=".pdf"
        className="hidden"
        onChange={(e) => e.target.files?.[0] && onUpload(e.target.files[0])}
      />
    </div>
  );
}
