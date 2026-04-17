"use client";

import { useEffect, useState } from "react";
import type { InterpretedValue } from "@/lib/api-client";
import type { Language } from "@/lib/i18n";
import { t } from "@/lib/i18n";

interface Props {
  values: InterpretedValue[];
  language: Language;
}

/**
 * Sticky banner that appears when any value is panic OR severity=critical.
 * Mobile: full banner for 3s, then auto-shrinks to a small pill at top-right;
 *         tap to re-expand.
 */
export function PanicStickyBanner({ values, language }: Props) {
  const panicValues = values.filter(
    (v) => v.is_panic || v.severity === "critical"
  );
  const [collapsed, setCollapsed] = useState(false);

  // Mobile-only: auto-shrink after 3s.  Desktop stays full.
  useEffect(() => {
    if (typeof window === "undefined") return;
    const isMobile = window.matchMedia("(max-width: 767px)").matches;
    if (!isMobile) return;
    const id = setTimeout(() => setCollapsed(true), 3000);
    return () => clearTimeout(id);
  }, []);

  if (panicValues.length === 0) return null;

  const first = panicValues[0];
  const targetId = `card-${first.health_topic ?? "other"}-${first.test_name}-0`;

  if (collapsed) {
    return (
      <button
        type="button"
        onClick={() => setCollapsed(false)}
        className="fixed top-2 right-2 md:hidden z-50 rounded-full bg-rose-600 text-white px-3 py-1 text-xs font-medium shadow-lg focus-visible:outline focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-white"
        aria-label={t("panic.banner", language)}
      >
        ⚠ {panicValues.length}
      </button>
    );
  }

  return (
    <div
      role="alert"
      className="sticky top-0 z-40 -mx-4 sm:mx-0 px-4 py-2 bg-rose-600 text-white flex items-center gap-3 shadow"
    >
      <span aria-hidden className="text-lg">⚠</span>
      <p className="text-sm font-medium flex-1">
        {t("panic.banner", language)}
      </p>
      <a
        href={`#${targetId}`}
        className="text-xs underline underline-offset-2 hover:no-underline"
      >
        {t("panic.view", language)}
      </a>
    </div>
  );
}
