"use client";

import Image from "next/image";
import Link from "next/link";
import { usePathname } from "next/navigation";
import { ThemeToggle } from "@/components/theme-toggle";

interface Props {
  children: React.ReactNode;
}

/**
 * Top-level layout shell. English-only — language switcher removed in
 * feat/polish-v1 follow-up (was premature; bring back when we re-localize).
 * Slim top header (logo only) + full-width main.
 *
 * ChatDock used to mount here for any /results/* route, but that meant the
 * "Ask about your results" CTA appeared while the report was still being
 * scanned. ChatDock is now mounted from the results page itself, gated on
 * a successful analysis — so the CTA never shows until there are actual
 * results to ask about.
 */
export function AppShell({ children }: Props) {
  const pathname = usePathname();

  // Reserve a little bottom space on results routes for the floating chat
  // button so it never overlaps the last paragraph.
  const onResults = pathname?.startsWith("/results/") ?? false;
  const bottomPad = onResults ? "pb-20" : "pb-4";

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
            {/* Logo includes the LabLens wordmark + tagline. Transparent
                bg so it sits cleanly on light + dark surfaces. next/image
                serves WebP/AVIF at the actual render size. */}
            <Image
              src="/logo1.png"
              alt="LabLens"
              width={1600}
              height={394}
              priority
              sizes="(max-width: 640px) 144px, 176px"
              className="h-9 w-auto sm:h-10"
            />
          </Link>

          <ThemeToggle />
        </div>
      </header>

      <main className={`flex-1 min-w-0 ${bottomPad}`}>
        {children}
      </main>
    </div>
  );
}
