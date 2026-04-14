"use client";

import { useCallback, useRef, useState } from "react";
import type { Language } from "@/lib/i18n";
import { t } from "@/lib/i18n";

interface Props {
  onUpload: (file: File) => void;
  isLoading: boolean;
  language: Language;
}

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
      onDragOver={(e) => { e.preventDefault(); setDragActive(true); }}
      onDragLeave={() => setDragActive(false)}
      onDrop={handleDrop}
      onClick={handleClick}
      className={`border-2 border-dashed rounded-lg p-12 text-center cursor-pointer transition-colors
        ${dragActive ? "border-blue-500 bg-blue-50" : "border-gray-300 hover:border-gray-400"}
        ${isLoading ? "opacity-50 pointer-events-none" : ""}`}
    >
      <svg className="mx-auto h-12 w-12 text-gray-400 mb-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
        <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={1.5} d="M9 13h6m-3-3v6m5 5H7a2 2 0 01-2-2V5a2 2 0 012-2h5.586a1 1 0 01.707.293l5.414 5.414a1 1 0 01.293.707V19a2 2 0 01-2 2z" />
      </svg>
      <p className="text-lg font-medium text-gray-700">{t("upload.dropzone", language)}</p>
      <p className="text-sm text-gray-500 mt-2">{t("upload.browse", language)}</p>
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
