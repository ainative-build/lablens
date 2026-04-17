interface Props {
  value: number;
  low: number | null;
  high: number | null;
  unit?: string | null;
  /** Compact mode for L3 cards: thinner bar, no axis labels */
  compact?: boolean;
}

/**
 * 3-zone reference-range bar with a marker that's actually visible.
 *
 * Zones: under-range (rose) | in-range (emerald) | over-range (rose).
 * Marker:
 *   - A pill-shaped chip above the bar showing the exact value
 *   - A small downward triangle from the chip pointing onto the bar
 *   - A full-height vertical line through the bar at the marker position
 *   - Color coded by direction: rose if out of range, slate if in range
 *
 * Pure CSS / Tailwind — no chart library, no SVG bar primitives. Tail
 * margin (20% of width on each side) lets out-of-range markers sit
 * visually outside the in-range zone.
 *
 * Degrades gracefully: if low or high is null, renders nothing.
 */
export function RangeBar({ value, low, high, unit, compact }: Props) {
  if (low === null || high === null || high <= low) return null;

  const pad = (high - low) * 0.2;
  const min = low - pad;
  const max = high + pad;
  const span = max - min;

  // Position marker; clamp so it stays inside the bar.
  const rawPct = ((value - min) / span) * 100;
  const markerPct = Math.max(2, Math.min(98, rawPct));

  // Out-of-range gets a stronger color treatment on the marker chip.
  const outOfRange = value < low || value > high;
  const chipColors = outOfRange
    ? "bg-rose-600 text-white border-rose-700 dark:bg-rose-500 dark:border-rose-400"
    : "bg-emerald-600 text-white border-emerald-700 dark:bg-emerald-500 dark:border-emerald-400";
  const tickColor = outOfRange
    ? "bg-rose-600 dark:bg-rose-400"
    : "bg-emerald-600 dark:bg-emerald-400";

  // Zone widths as percent of total bar width
  const underPct = ((low - min) / span) * 100; // == 16.67% with 20% pad
  const inRangePct = ((high - low) / span) * 100;
  const overPct = ((max - high) / span) * 100;

  const barHeight = compact ? "h-2" : "h-2.5";

  // Decide which side the chip "tail" points / chip aligns to. When the
  // marker is hugging an edge, anchor the chip differently so it doesn't
  // clip out of the bar's parent container.
  const chipAlign =
    markerPct < 12
      ? "left-0 -translate-x-0"
      : markerPct > 88
        ? "right-0 translate-x-0"
        : "left-1/2 -translate-x-1/2";

  // Rounded value for the chip — keep up to 2 decimals to avoid floats like 121.0371.
  const chipValue = Number.isInteger(value) ? value : Math.round(value * 100) / 100;

  return (
    <div className="w-full" aria-hidden>
      {/* Marker chip + tick (positioned via the bar's relative parent) */}
      <div className="relative pt-7">
        <div
          className="absolute top-0 -translate-x-1/2 pointer-events-none flex flex-col items-center"
          style={{ left: `${markerPct}%` }}
        >
          {/* Value chip */}
          <span
            className={`relative inline-flex items-center rounded-md px-1.5 py-0.5 text-[11px] font-semibold tabular-nums leading-none border ${chipColors} shadow-sm whitespace-nowrap ${chipAlign}`}
          >
            {chipValue}
          </span>
          {/* Downward arrow under the chip — small triangle in chip color */}
          <span
            aria-hidden
            className={`-mt-px h-1.5 w-1.5 rotate-45 border-r border-b ${chipColors}`}
          />
        </div>

        {/* Bar */}
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
          {/* Vertical tick — full bar height, sits over the zones */}
          <div
            className={`absolute top-0 bottom-0 w-[3px] -translate-x-1/2 rounded-full ${tickColor} ring-2 ring-white dark:ring-[var(--color-surface)]`}
            style={{ left: `${markerPct}%` }}
          />
        </div>
      </div>

      {!compact && (
        <div className="flex justify-between mt-1 text-[11px] text-gray-500 dark:text-gray-400 tabular-nums">
          <span>{low}</span>
          <span>
            {high}
            {unit ? ` ${unit}` : ""}
          </span>
        </div>
      )}
    </div>
  );
}
