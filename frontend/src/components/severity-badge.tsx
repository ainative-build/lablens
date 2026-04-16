import type { Language } from "@/lib/i18n";
import { t } from "@/lib/i18n";

interface Props {
  severity: string;
  language?: Language;
}

// WCAG AA contrast — verified ≥4.5:1 against the chip background.
const SEVERITY_STYLES: Record<string, string> = {
  normal: "bg-emerald-100 text-emerald-900 ring-1 ring-emerald-300",
  mild: "bg-amber-100 text-amber-900 ring-1 ring-amber-300",
  moderate: "bg-orange-100 text-orange-900 ring-1 ring-orange-400",
  critical: "bg-rose-100 text-rose-900 ring-1 ring-rose-400",
};

export function SeverityBadge({ severity, language = "en" }: Props) {
  const cls = SEVERITY_STYLES[severity] ?? SEVERITY_STYLES.normal;
  const key = `results.${severity}`;
  return (
    <span
      className={`inline-block px-2 py-0.5 rounded text-xs font-medium ${cls}`}
    >
      {t(key, language)}
    </span>
  );
}
