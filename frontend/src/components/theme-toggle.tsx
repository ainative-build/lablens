"use client";

import { useEffect, useState } from "react";

const STORAGE_KEY = "lablens.theme";
type Theme = "light" | "dark";

/**
 * Sun/moon toggle that flips `[data-theme]` on <html>. Persists to
 * localStorage so the choice survives reloads. The actual initial theme is
 * applied by the inline `<script>` in `app/layout.tsx` (pre-paint, no FOUC);
 * this component just syncs its UI state from the DOM after mount.
 *
 * Renders a placeholder during SSR/pre-mount so the icon doesn't flash an
 * incorrect state on first paint.
 */
export function ThemeToggle() {
  const [theme, setTheme] = useState<Theme | null>(null);

  // Read the theme that the inline script already applied.
  useEffect(() => {
    const current = document.documentElement.dataset.theme;
    setTheme(current === "dark" ? "dark" : "light");
  }, []);

  const toggle = () => {
    const next: Theme = theme === "dark" ? "light" : "dark";
    setTheme(next);
    document.documentElement.dataset.theme = next;
    try {
      localStorage.setItem(STORAGE_KEY, next);
    } catch {
      /* private mode etc — toggle still works for the session */
    }
  };

  // Pre-mount: render an opaque placeholder of the same size to avoid layout
  // shift and to keep server + client markup identical.
  if (theme === null) {
    return (
      <span
        aria-hidden
        className="inline-block h-9 w-9 rounded-md border border-transparent"
      />
    );
  }

  const isDark = theme === "dark";
  return (
    <button
      type="button"
      onClick={toggle}
      aria-label={isDark ? "Switch to light theme" : "Switch to dark theme"}
      title={isDark ? "Switch to light theme" : "Switch to dark theme"}
      className="inline-flex items-center justify-center h-9 w-9 rounded-md border border-[var(--color-border)] bg-[var(--color-surface)] text-[var(--foreground-muted)] hover:text-[var(--foreground)] hover:border-[var(--color-border-strong)] transition-colors focus-visible:outline focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-[var(--color-brand-500)]"
    >
      {isDark ? (
        // Sun icon (we are in dark, click switches to light)
        <svg
          aria-hidden="true"
          viewBox="0 0 24 24"
          fill="none"
          stroke="currentColor"
          strokeWidth="2"
          strokeLinecap="round"
          strokeLinejoin="round"
          className="h-4 w-4"
        >
          <circle cx="12" cy="12" r="4" />
          <path d="M12 2v2M12 20v2M4.93 4.93l1.41 1.41M17.66 17.66l1.41 1.41M2 12h2M20 12h2M4.93 19.07l1.41-1.41M17.66 6.34l1.41-1.41" />
        </svg>
      ) : (
        // Moon icon (we are in light, click switches to dark)
        <svg
          aria-hidden="true"
          viewBox="0 0 24 24"
          fill="none"
          stroke="currentColor"
          strokeWidth="2"
          strokeLinecap="round"
          strokeLinejoin="round"
          className="h-4 w-4"
        >
          <path d="M21 12.79A9 9 0 1 1 11.21 3a7 7 0 0 0 9.79 9.79z" />
        </svg>
      )}
    </button>
  );
}
