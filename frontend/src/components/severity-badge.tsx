const SEVERITY_STYLES: Record<string, string> = {
  normal: "bg-green-100 text-green-800",
  mild: "bg-yellow-100 text-yellow-800",
  moderate: "bg-orange-100 text-orange-800",
  critical: "bg-red-100 text-red-800",
};

export function SeverityBadge({ severity }: { severity: string }) {
  return (
    <span className={`px-2 py-0.5 rounded text-xs font-medium ${SEVERITY_STYLES[severity] || "bg-gray-100 text-gray-800"}`}>
      {severity}
    </span>
  );
}
