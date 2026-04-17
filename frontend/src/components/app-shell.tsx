"use client";

import { usePathname, useSearchParams } from "next/navigation";
import { useEffect, useState } from "react";
import { ChatDock } from "@/components/chat-dock";
import { Sidebar } from "@/components/sidebar";
import { type Language } from "@/lib/i18n";

interface Props {
  children: React.ReactNode;
}

/**
 * Top-level layout shell (BloodGPT-inspired).
 * - Persistent left sidebar (logo + upload + language)
 * - Main column (children)
 * - Right rail slot (filled by results page when present — handled by children)
 * - Sticky bottom chat bar (only on /results/[jobId] routes)
 * - Mobile (<md): sidebar off-canvas drawer behind hamburger
 */
export function AppShell({ children }: Props) {
  const pathname = usePathname();
  const searchParams = useSearchParams();
  const [drawerOpen, setDrawerOpen] = useState(false);

  // Language is shared between sidebar + chat. We initialise from ?lang=,
  // fall back to "en". The results page also reads ?lang= so they stay in sync.
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

  // Esc closes mobile drawer.
  useEffect(() => {
    if (!drawerOpen) return;
    const onKey = (e: KeyboardEvent) => {
      if (e.key === "Escape") setDrawerOpen(false);
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [drawerOpen]);

  // Extract jobId from /results/[jobId] for chat bar.
  const jobIdMatch = pathname?.match(/^\/results\/([^/]+)/);
  const jobId = jobIdMatch?.[1];

  // ChatDock is a floating button (bottom-right) — not a full-width bar — so
  // we no longer need to reserve bottom padding for it. Reserve a little
  // for safe-area + breathing room.
  const bottomPad = jobId ? "pb-20" : "pb-4";

  return (
    <div className="min-h-dvh flex flex-col">
      {/* Mobile top bar with hamburger */}
      <div className="md:hidden flex items-center justify-between border-b border-[var(--color-border)] bg-[var(--color-surface)] px-3 py-2">
        <button
          type="button"
          onClick={() => setDrawerOpen(true)}
          aria-label="Open menu"
          className="inline-flex items-center justify-center h-9 w-9 rounded hover:bg-[var(--color-surface-muted)] focus-visible:outline focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-[var(--color-brand-500)]"
        >
          ☰
        </button>
        <span className="font-semibold text-[var(--foreground)]">LabLens</span>
        <span className="w-9" /> {/* spacer */}
      </div>

      <div className="flex-1 flex">
        {/* Sidebar — inline on md+, off-canvas drawer on mobile */}
        <div className="hidden md:block w-[var(--sidebar-width)] shrink-0">
          <Sidebar language={language} onLanguageChange={setLanguage} />
        </div>
        {drawerOpen && (
          <>
            <div
              className="fixed inset-0 bg-black/40 z-50 md:hidden"
              onClick={() => setDrawerOpen(false)}
              aria-hidden
            />
            <div className="fixed inset-y-0 left-0 w-[280px] z-50 md:hidden">
              <Sidebar language={language} onLanguageChange={setLanguage} />
            </div>
          </>
        )}

        {/* Main column */}
        <main className={`flex-1 min-w-0 ${bottomPad}`}>
          {children}
        </main>
      </div>

      {/* Floating chat button + dialog — only on results pages */}
      {jobId && <ChatDock jobId={jobId} language={language} />}
    </div>
  );
}
