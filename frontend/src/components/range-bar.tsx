interface Props {
  value: number;
  low: number | null;
  high: number | null;
  unit?: string | null;
  /** Compact mode for L3 cards: thinner bar, no axis labels */
  compact?: boolean;
}

/**
 * 3-zone reference-range bar with marker (BloodGPT-style).
 * Zones: under-range (rose) | in-range (emerald) | over-range (rose)
 *
 * Pure CSS / Tailwind — no chart library, no SVG. Marker is a small dot
 * positioned via percent. Tail margin (20% of width on each side) lets the
 * marker sit visually outside the in-range zone when value is out of range.
 *
 * Degrades gracefully: if low or high is null, renders just a value pill
 * with an "—" placeholder (caller's surrounding text already shows value).
 */
export function RangeBar({ value, low, high, unit, compact }: Props) {
  // No range → render nothing; the AnalyteCard's value display still shows.
  if (low === null || high === null || high <= low) return null;

  const pad = (high - low) * 0.2;
  const min = low - pad;
  const max = high + pad;
  const span = max - min;

  // Position marker; clamp so it stays inside the bar.
  const rawPct = ((value - min) / span) * 100;
  const markerPct = Math.max(2, Math.min(98, rawPct));

  // Zone widths as percent of total bar width
  const underPct = ((low - min) / span) * 100; // == 16.67% with 20% pad
  const inRangePct = ((high - low) / span) * 100;
  const overPct = ((max - high) / span) * 100;

  const barHeight = compact ? "h-2" : "h-2.5";

  return (
    <div className="w-full" aria-hidden>
      <div className={`relative flex ${barHeight} rounded-full overflow-hidden`}>
        <div
          className="bg-rose-300 dark:bg-rose-500/60"
          style={{ width: `${underPct}%` }}
        />
        <div
          className="bg-emerald-400 dark:bg-emerald-500/80"
          style={{ width: `${inRangePct}%` }}
        />
        <div
          className="bg-rose-300 dark:bg-rose-500/60"
          style={{ width: `${overPct}%` }}
        />
        {/* Marker (vertical line + dot) */}
        <div
          className="absolute top-1/2 -translate-y-1/2 -translate-x-1/2 pointer-events-none"
          style={{ left: `${markerPct}%` }}
        >
          <div className="h-3.5 w-1 rounded-full bg-[var(--foreground)] shadow ring-2 ring-[var(--color-surface)]" />
        </div>
      </div>
      {!compact && (
        <div className="flex justify-between mt-1 text-[11px] text-gray-500 dark:text-gray-400 tabular-nums">
          <span>{low}</span>
          <span>{high}{unit ? ` ${unit}` : ""}</span>
        </div>
      )}
    </div>
  );
}
