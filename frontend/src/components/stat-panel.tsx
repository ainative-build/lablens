import type { ReactNode } from "react";
import { DonutRing } from "./donut-ring";

type Variant = "normal" | "warn" | "unclear";

interface Props {
  title: string;
  percent: number;
  caption: string;
  variant?: Variant;
  /** Optional CTA / link rendered at the bottom of the card */
  action?: ReactNode;
}

const VARIANT_RING: Record<Variant, string> = {
  normal: "stroke-[var(--color-brand-500)]",
  warn: "stroke-amber-500",
  unclear: "stroke-gray-400 dark:stroke-gray-500",
};

const VARIANT_DOT: Record<Variant, string> = {
  normal: "bg-[var(--color-brand-500)]",
  warn: "bg-amber-500",
  unclear: "bg-gray-400 dark:bg-gray-500",
};

/**
 * Right-rail card composing donut + title + 2-line caption.
 * BloodGPT pattern.
 */
export function StatPanel({
  title,
  percent,
  caption,
  variant = "normal",
  action,
}: Props) {
  return (
    <section
      className="rounded-[var(--radius-card)] border border-[var(--color-border)] bg-[var(--color-surface)] p-4 shadow-[var(--shadow-card)]"
      aria-label={title}
    >
      <div className="flex items-start gap-3">
        <div className="flex-1 min-w-0">
          <div className="flex items-center gap-2 mb-1">
            <span
              aria-hidden
              className={`inline-block h-2 w-2 rounded-full ${VARIANT_DOT[variant]}`}
            />
            <h3 className="font-semibold text-sm text-[var(--foreground)] truncate">
              {title}
            </h3>
          </div>
          <p className="text-xs text-gray-600 dark:text-gray-400 leading-snug">
            {caption}
          </p>
          {action && <div className="mt-2">{action}</div>}
        </div>
        <div className="shrink-0">
          <DonutRing percent={percent} valueClass={VARIANT_RING[variant]} />
        </div>
      </div>
    </section>
  );
}
