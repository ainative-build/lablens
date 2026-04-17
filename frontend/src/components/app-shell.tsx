"use client";

import Link from "next/link";
import { usePathname, useSearchParams } from "next/navigation";
import { useEffect, useState } from "react";
import { ChatDock } from "@/components/chat-dock";
import { LanguageSelector } from "@/components/language-selector";
import type { Language } from "@/lib/i18n";

interface Props {
  children: React.ReactNode;
}

/**
 * Top-level layout shell. Sidebar removed in feat/polish-v1 (redundant once
 * the homepage owns the upload flow). Now: slim top header (logo + lang) +
 * full-width main + floating chat dock on `/results/[jobId]`.
 *
 * The header is sticky + uses translucent surface so content underneath
 * scrolls calmly. Language is owned here so chat + results stay in sync
 * with the URL `?lang=` param.
 */
export function AppShell({ children }: Props) {
  const pathname = usePathname();
  const searchParams = useSearchParams();

  const initialLang = (searchParams.get("lang") as Language) || "en";
  const [language, setLanguage] = useState<Language>(initialLang);

  // Re-sync if the user navigates with a different ?lang.
  useEffect(() => {
    const next = (searchParams.get("lang") as Language) || "en";
    setLanguage(next);
  }, [searchParams]);

  // Sync <html lang/dir> for a11y + RTL.
  useEffect(() => {
    if (typeof document === "undefined") return;
    document.documentElement.lang = language;
    document.documentElement.dir = language === "ar" ? "rtl" : "ltr";
  }, [language]);

  // Extract jobId from /results/[jobId] for chat bar.
  const jobIdMatch = pathname?.match(/^\/results\/([^/]+)/);
  const jobId = jobIdMatch?.[1];

  // Chat dock floats; reserve a touch of bottom space on results screens
  // so its 56-px floating button never overlaps the last paragraph.
  const bottomPad = jobId ? "pb-20" : "pb-4";

  return (
    <div className="min-h-dvh flex flex-col bg-radial-brand">
      {/* Sticky top header — logo (left), language (right). Same on all sizes. */}
      <header
        className="sticky top-0 z-40 backdrop-blur-md bg-[var(--color-surface)]/85 border-b border-[var(--color-border)]"
        style={{ height: "var(--header-height)" }}
      >
        <div className="mx-auto h-full flex items-center justify-between gap-3 px-4 sm:px-6 max-w-[var(--container-max)]">
          <Link
            href="/"
            className="flex items-center gap-2 rounded-md px-1 -mx-1 focus-visible:outline focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-[var(--color-brand-500)]"
            aria-label="LabLens home"
          >
            {/* Compact mark — solid green dot with a stylized "drop" cutout.
                Pure SVG so it scales + theme-tints cleanly. */}
            <span
              aria-hidden
              className="inline-flex items-center justify-center h-8 w-8 rounded-xl bg-[var(--color-brand-500)] shadow-[var(--shadow-card)]"
            >
              <svg
                viewBox="0 0 24 24"
                fill="none"
                stroke="white"
                strokeWidth="2.5"
                strokeLinecap="round"
                strokeLinejoin="round"
                className="h-4 w-4"
              >
                <path d="M12 3c3 4 5 7 5 10a5 5 0 0 1-10 0c0-3 2-6 5-10z" fill="white" stroke="none" />
              </svg>
            </span>
            <span className="font-display font-semibold text-[15px] sm:text-base text-[var(--foreground)]">
              LabLens
            </span>
          </Link>

          <LanguageSelector value={language} onChange={setLanguage} />
        </div>
      </header>

      <main className={`flex-1 min-w-0 ${bottomPad}`}>
        {children}
      </main>

      {/* Floating chat button + dialog — only on results pages */}
      {jobId && <ChatDock jobId={jobId} language={language} />}
    </div>
  );
}
