import type { Language } from "@/lib/i18n";
import { t } from "@/lib/i18n";

type Variant =
  | "normal"
  | "minor"
  | "mild"
  | "moderate"
  | "critical"
  | "unclear";

interface Props {
  /** Pass `direction` if the row is indeterminate, OR `severity` otherwise.
   *  AnalyteCard handles the routing — this component just renders. */
  variant?: Variant;
  /** Legacy: pass severity string directly (backwards-compat). */
  severity?: string;
  language?: Language;
}

// WCAG AA contrast — verified ≥4.5:1 against the chip background.
const STYLES: Record<Variant, string> = {
  normal: "bg-emerald-100 text-emerald-900 ring-1 ring-emerald-300",
  minor: "bg-slate-100 text-slate-800 ring-1 ring-slate-300",
  mild: "bg-amber-100 text-amber-900 ring-1 ring-amber-300",
  moderate: "bg-orange-100 text-orange-900 ring-1 ring-orange-400",
  critical: "bg-rose-100 text-rose-900 ring-1 ring-rose-400",
  unclear: "bg-gray-100 text-gray-700 ring-1 ring-gray-400 ring-dashed",
};

const LABEL_KEY: Record<Variant, string> = {
  normal: "results.normal",
  minor: "results.minor",
  mild: "results.mild",
  moderate: "results.moderate",
  critical: "results.critical",
  unclear: "results.unclear",
};

export function SeverityBadge({ variant, severity, language = "en" }: Props) {
  const v: Variant =
    variant ??
    (severity && (severity as Variant) in STYLES
      ? (severity as Variant)
      : "normal");
  return (
    <span
      className={`inline-block px-2 py-0.5 rounded text-xs font-medium ${STYLES[v]}`}
    >
      {t(LABEL_KEY[v], language)}
    </span>
  );
}
