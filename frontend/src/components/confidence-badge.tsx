const CONFIDENCE_STYLES: Record<string, string> = {
  high: "bg-blue-100 text-blue-800",
  medium: "bg-gray-100 text-gray-700",
  low: "bg-amber-100 text-amber-800",
};

export function ConfidenceBadge({ confidence }: { confidence: string }) {
  return (
    <span className={`px-2 py-0.5 rounded text-xs font-medium ${CONFIDENCE_STYLES[confidence] || "bg-gray-100 text-gray-700"}`}>
      {confidence}
    </span>
  );
}
