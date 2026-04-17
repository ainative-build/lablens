"use client";

import Image from "next/image";
import Link from "next/link";
import { usePathname } from "next/navigation";
import { ChatDock } from "@/components/chat-dock";

interface Props {
  children: React.ReactNode;
}

/**
 * Top-level layout shell. English-only — language switcher removed in
 * feat/polish-v1 follow-up (was premature; bring back when we re-localize).
 * Slim top header (logo only) + full-width main + floating chat dock on
 * `/results/[jobId]`. Header uses translucent surface so content scrolls
 * under calmly.
 *
 * The `language` prop pipeline on downstream components is intentionally
 * preserved (cheap to keep, expensive to thread back). All callers pass "en".
 */
export function AppShell({ children }: Props) {
  const pathname = usePathname();
  const language = "en" as const;

  // Extract jobId from /results/[jobId] for chat bar.
  const jobIdMatch = pathname?.match(/^\/results\/([^/]+)/);
  const jobId = jobIdMatch?.[1];

  // Chat dock floats; reserve a touch of bottom space on results screens
  // so its 56-px floating button never overlaps the last paragraph.
  const bottomPad = jobId ? "pb-20" : "pb-4";

  return (
    <div className="min-h-dvh flex flex-col bg-radial-brand">
      {/* Sticky top header — logo only. Language switcher removed; restore
          here when re-localizing (multi-lang select goes on the right side). */}
      <header
        className="sticky top-0 z-40 backdrop-blur-md bg-[var(--color-surface)]/85 border-b border-[var(--color-border)]"
        style={{ height: "var(--header-height)" }}
      >
        <div className="mx-auto h-full flex items-center justify-between gap-3 px-4 sm:px-6 max-w-[var(--container-max)]">
          <Link
            href="/"
            className="flex items-center rounded-md px-1 -mx-1 focus-visible:outline focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-[var(--color-brand-500)]"
            aria-label="LabLens home"
          >
            {/* Logo includes the LabLens wordmark + tagline. White bg
                stripped via ImageMagick floodfill so it sits cleanly on
                light + dark page surfaces. next/image serves WebP/AVIF
                at the actual render size. */}
            <Image
              src="/logo.png"
              alt="LabLens"
              width={1400}
              height={764}
              priority
              sizes="(max-width: 640px) 80px, 96px"
              className="h-10 w-auto sm:h-11"
            />
          </Link>
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
