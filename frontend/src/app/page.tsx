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
          <div className="text-center text-gray-600">
            <div className="inline-block h-6 w-6 animate-spin rounded-full border-2 border-gray-300 border-t-blue-600 mr-2" />
            {t("upload.analyzing", language)}
          </div>
        )}

        {error && (
          <div className="bg-red-50 border border-red-200 text-red-700 rounded-md p-3 text-sm">
            {error}
          </div>
        )}
      </div>
    </div>
  );
}
