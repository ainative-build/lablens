import type { ChatCitation } from "@/lib/api-client";
import type { Language } from "@/lib/i18n";
import { t } from "@/lib/i18n";
import { CitationChip } from "./citation-chip";

type Role = "user" | "assistant";

interface Props {
  role: Role;
  content: string;
  citations?: ChatCitation[];
  doctorRouting?: boolean;
  refused?: boolean;
  language: Language;
}

export function MessageBubble({
  role,
  content,
  citations = [],
  doctorRouting = false,
  refused = false,
  language,
}: Props) {
  const isUser = role === "user";
  const bubbleBase =
    "max-w-[85%] rounded-lg px-3 py-2 text-sm whitespace-pre-wrap";
  const bubbleColor = isUser
    ? "bg-blue-600 text-white"
    : refused
      ? "bg-gray-100 dark:bg-gray-800 text-gray-700 dark:text-gray-200 border border-gray-300 dark:border-gray-600"
      : "bg-gray-50 dark:bg-gray-900 text-gray-900 dark:text-gray-50 border border-gray-200 dark:border-gray-700";

  return (
    <div className={`flex ${isUser ? "justify-end" : "justify-start"}`}>
      <div className={`${bubbleBase} ${bubbleColor}`}>
        <p>{content}</p>
        {citations.length > 0 && (
          <div className="mt-2 flex flex-wrap gap-1">
            {citations.map((c, i) => (
              <CitationChip
                key={`${c.test_name}-${i}`}
                citation={c}
                language={language}
              />
            ))}
          </div>
        )}
        {doctorRouting && (
          <div
            role="note"
            className="mt-2 border-l-4 border-amber-500 bg-amber-50 dark:bg-amber-950/60 text-amber-900 dark:text-amber-100 px-2 py-1 text-xs"
          >
            ⚕️ {t("chat.doctor_routing", language)}
          </div>
        )}
      </div>
    </div>
  );
}
