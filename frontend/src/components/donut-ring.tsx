import type { ReactNode } from "react";

interface Props {
  /** 0–100 percent fill */
  percent: number;
  /** Outer pixel size of the SVG (default 88) */
  size?: number;
  /** Stroke width in pixels (default 8) */
  thickness?: number;
  /** Track (background ring) Tailwind stroke class */
  trackClass?: string;
  /** Filled arc Tailwind stroke class */
  valueClass?: string;
  /** Center content; defaults to "{percent}%" */
  label?: ReactNode;
}

/**
 * Pure-SVG donut/progress ring. No chart-library dependency.
 * Accessible: role="img" + aria-label with percent.
 */
export function DonutRing({
  percent,
  size = 88,
  thickness = 8,
  trackClass = "stroke-[var(--color-surface-sunken)]",
  valueClass = "stroke-[var(--color-brand-500)]",
  label,
}: Props) {
  const clamped = Math.max(0, Math.min(100, percent));
  const r = (size - thickness) / 2;
  const c = 2 * Math.PI * r;
  const offset = c * (1 - clamped / 100);

  return (
    <svg
      width={size}
      height={size}
      viewBox={`0 0 ${size} ${size}`}
      role="img"
      aria-label={`${Math.round(clamped)} percent`}
    >
      <circle
        cx={size / 2}
        cy={size / 2}
        r={r}
        strokeWidth={thickness}
        fill="none"
        className={trackClass}
      />
      <circle
        cx={size / 2}
        cy={size / 2}
        r={r}
        strokeWidth={thickness}
        fill="none"
        strokeDasharray={c}
        strokeDashoffset={offset}
        strokeLinecap="round"
        transform={`rotate(-90 ${size / 2} ${size / 2})`}
        className={valueClass}
      />
      <text
        x="50%"
        y="50%"
        textAnchor="middle"
        dominantBaseline="central"
        className="font-semibold fill-[var(--foreground)]"
        fontSize={size * 0.22}
      >
        {label ?? `${Math.round(clamped)}%`}
      </text>
    </svg>
  );
}
