"use client";

import { useEffect, useRef, useState } from "react";
import {
  askQuestion,
  SessionExpiredError,
  type ChatCitation,
  type ChatTurn,
} from "@/lib/api-client";
import type { Language } from "@/lib/i18n";
import { t } from "@/lib/i18n";
import { MessageBubble } from "./message-bubble";
import { QaInput } from "./qa-input";
import { StarterQuestions } from "./starter-questions";

interface Props {
  jobId: string;
  language: Language;
  onClose: () => void;
}

interface ThreadMessage extends ChatTurn {
  citations?: ChatCitation[];
  doctorRouting?: boolean;
  refused?: boolean;
}

const STORAGE_KEY = (jobId: string) => `lablens.chat.${jobId}`;

export function QaPane({ jobId, language, onClose }: Props) {
  const [thread, setThread] = useState<ThreadMessage[]>([]);
  const [pending, setPending] = useState(false);
  const [expired, setExpired] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const scrollRef = useRef<HTMLDivElement>(null);

  // Restore from localStorage on mount.
  useEffect(() => {
    if (typeof window === "undefined") return;
    const raw = window.localStorage.getItem(STORAGE_KEY(jobId));
    if (raw) {
      try {
        const saved = JSON.parse(raw) as ThreadMessage[];
        if (Array.isArray(saved)) setThread(saved);
      } catch {
        // ignore
      }
    }
  }, [jobId]);

  // Persist on every change.
  useEffect(() => {
    if (typeof window === "undefined") return;
    window.localStorage.setItem(STORAGE_KEY(jobId), JSON.stringify(thread));
  }, [jobId, thread]);

  // Auto-scroll on new message.
  useEffect(() => {
    scrollRef.current?.scrollTo({
      top: scrollRef.current.scrollHeight,
      behavior: "smooth",
    });
  }, [thread, pending]);

  const submit = async (question: string) => {
    if (pending || expired) return;
    setError(null);
    const userMsg: ThreadMessage = { role: "user", content: question };
    const next = [...thread, userMsg];
    setThread(next);
    setPending(true);

    try {
      // History: only role/content (server validates anyway).
      const history: ChatTurn[] = next
        .slice(-7, -1) // last 6 turns before the new question
        .map((m) => ({ role: m.role, content: m.content }));

      const resp = await askQuestion(jobId, question, history, language);
      setThread((prev) => [
        ...prev,
        {
          role: "assistant",
          content: resp.answer,
          citations: resp.citations,
          doctorRouting: resp.doctor_routing,
          refused: resp.refused,
        },
      ]);
    } catch (e) {
      if (e instanceof SessionExpiredError) {
        setExpired(true);
      } else {
        setError(e instanceof Error ? e.message : "error");
      }
    } finally {
      setPending(false);
    }
  };

  return (
    <aside
      role="complementary"
      aria-label={t("chat.title", language)}
      className="fixed inset-x-0 bottom-0 md:left-auto md:bottom-4 md:right-4 md:w-96 z-40 bg-white dark:bg-gray-900 border border-gray-200 dark:border-gray-700 rounded-t-lg md:rounded-lg shadow-2xl flex flex-col"
      style={{ maxHeight: "min(80vh, 600px)" }}
    >
      <header className="flex items-center justify-between px-4 py-3 border-b border-gray-200 dark:border-gray-700">
        <h2 className="font-semibold text-gray-900 dark:text-gray-100 text-sm">
          {t("chat.title", language)}
        </h2>
        <button
          type="button"
          onClick={onClose}
          aria-label="Close"
          className="text-gray-500 hover:text-gray-800 dark:hover:text-gray-200 focus-visible:outline focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-blue-500 rounded text-lg leading-none"
        >
          ✕
        </button>
      </header>

      {expired ? (
        <SessionExpiredCard language={language} />
      ) : (
        <>
          <div
            ref={scrollRef}
            className="flex-1 overflow-y-auto p-3 space-y-2"
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
            <div className="px-3 pb-2">
              <StarterQuestions language={language} onPick={submit} />
            </div>
          )}

          <QaInput
            disabled={pending}
            language={language}
            onSubmit={submit}
          />
        </>
      )}
    </aside>
  );
}

function SessionExpiredCard({ language }: { language: Language }) {
  return (
    <div className="p-4 space-y-3 text-sm">
      <p className="text-gray-700 dark:text-gray-300">
        {t("error.session_expired", language)}
      </p>
      <a
        href="/"
        className="inline-block rounded bg-blue-600 hover:bg-blue-700 text-white px-3 py-1.5 text-sm focus-visible:outline focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-blue-500"
      >
        {t("upload.title", language)}
      </a>
    </div>
  );
}
