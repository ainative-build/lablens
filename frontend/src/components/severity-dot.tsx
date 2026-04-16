import type { Status } from "@/lib/api-client";

interface Props {
  status: Status;
  size?: "sm" | "md" | "lg";
}

const STATUS_BG: Record<Status, string> = {
  green: "bg-emerald-500",
  yellow: "bg-amber-400",
  orange: "bg-orange-500",
  red: "bg-rose-600",
};

const SIZE: Record<NonNullable<Props["size"]>, string> = {
  sm: "h-2 w-2",
  md: "h-3 w-3",
  lg: "h-4 w-4",
};

/** Small status dot used in summary card and topic group headers. */
export function SeverityDot({ status, size = "md" }: Props) {
  return (
    <span
      aria-hidden
      className={`inline-block rounded-full ${SIZE[size]} ${STATUS_BG[status]}`}
    />
  );
}
