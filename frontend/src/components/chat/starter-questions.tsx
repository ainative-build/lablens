import type { Language } from "@/lib/i18n";
import { t } from "@/lib/i18n";

interface Props {
  language: Language;
  onPick: (question: string) => void;
}

const STARTER_KEYS = [
  "chat.starter.focus",
  "chat.starter.out_of_range",
  "chat.starter.see_doctor",
  "chat.starter.questions_for_doctor",
  "chat.starter.retest",
] as const;

export function StarterQuestions({ language, onPick }: Props) {
  return (
    <div className="flex flex-wrap gap-1">
      {STARTER_KEYS.map((k) => {
        const text = t(k, language);
        return (
          <button
            key={k}
            type="button"
            onClick={() => onPick(text)}
            className="text-xs rounded-full border border-gray-300 dark:border-gray-600 bg-white dark:bg-gray-800 px-2 py-1 text-gray-700 dark:text-gray-200 hover:bg-gray-50 dark:hover:bg-gray-700 focus-visible:outline focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-blue-500"
          >
            {text}
          </button>
        );
      })}
    </div>
  );
}
