"use client";

import { useEffect, useRef } from "react";
import type { ChatCitation, ChatTurn } from "@/lib/api-client";
import type { Language } from "@/lib/i18n";
import { t } from "@/lib/i18n";
import { MessageBubble } from "./message-bubble";
import { StarterQuestions } from "./starter-questions";

interface ThreadMessage extends ChatTurn {
  citations?: ChatCitation[];
  doctorRouting?: boolean;
  refused?: boolean;
}

interface Props {
  thread: ThreadMessage[];
  pending: boolean;
  error: string | null;
  expired: boolean;
  language: Language;
  onPickStarter: (q: string) => void;
}

/**
 * Display-only chat thread (extracted from old QaPane).
 * Caller (StickyChatBar) owns the state + submit handler.
 * Auto-scrolls to bottom on new messages.
 */
export function QaThread({
  thread,
  pending,
  error,
  expired,
  language,
  onPickStarter,
}: Props) {
  const scrollRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    scrollRef.current?.scrollTo({
      top: scrollRef.current.scrollHeight,
      behavior: "smooth",
    });
  }, [thread, pending]);

  if (expired) {
    return (
      <div className="space-y-3 text-sm">
        <p className="text-gray-700 dark:text-gray-300">
          {t("error.session_expired", language)}
        </p>
        <a
          href="/"
          className="inline-block rounded bg-[var(--color-brand-500)] hover:bg-[var(--color-brand-600)] text-white px-3 py-1.5 text-sm focus-visible:outline focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-[var(--color-brand-500)]"
        >
          {t("upload.title", language)}
        </a>
      </div>
    );
  }

  return (
    <>
      <div
        ref={scrollRef}
        className="space-y-2"
        aria-live="polite"
      >
        {thread.length === 0 && (
          <p className="text-sm text-gray-500 dark:text-gray-400">
            {t("chat.try_these", language)}
          </p>
        )}
        {thread.map((m, i) => (
          <MessageBubble
            key={i}
            role={m.role}
            content={m.content}
            citations={m.citations}
            doctorRouting={m.doctorRouting}
            refused={m.refused}
            language={language}
          />
        ))}
        {pending && (
          <p className="text-sm text-gray-500 italic" role="status">
            {t("chat.thinking", language)}
          </p>
        )}
        {error && (
          <p className="text-sm text-rose-700 dark:text-rose-300">
            {t("chat.error", language)}
          </p>
        )}
      </div>

      {thread.length === 0 && (
        <div className="mt-2">
          <StarterQuestions language={language} onPick={onPickStarter} />
        </div>
      )}
    </>
  );
}
