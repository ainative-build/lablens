"use client";

import { useEffect, useRef, useState } from "react";
import dynamic from "next/dynamic";
import {
  askQuestion,
  SessionExpiredError,
  type ChatCitation,
  type ChatTurn,
} from "@/lib/api-client";
import type { Language } from "@/lib/i18n";
import { t } from "@/lib/i18n";

interface Props {
  jobId: string;
  language: Language;
}

interface ThreadMessage extends ChatTurn {
  citations?: ChatCitation[];
  doctorRouting?: boolean;
  refused?: boolean;
}

const STORAGE_KEY = (jobId: string) => `lablens.chat.${jobId}`;
const MAX_LEN = 500;

/**
 * Always-visible bottom chat bar (BloodGPT pattern).
 * - Collapsed: thin 64px bar with input + send
 * - Expanded: thread renders ABOVE the bar (max 50vh, scrolls)
 * - Lazy-load the thread renderer to keep initial bundle lean
 */
const ChatThread = dynamic(
  () =>
    import("@/components/chat/qa-thread").then((m) => ({
      default: m.QaThread,
    })),
  { ssr: false, loading: () => null }
);

export function StickyChatBar({ jobId, language }: Props) {
  const [thread, setThread] = useState<ThreadMessage[]>([]);
  const [pending, setPending] = useState(false);
  const [expanded, setExpanded] = useState(false);
  const [expired, setExpired] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [draft, setDraft] = useState("");
  const inputRef = useRef<HTMLTextAreaElement>(null);

  // Restore from localStorage on mount.
  useEffect(() => {
    if (typeof window === "undefined") return;
    const raw = window.localStorage.getItem(STORAGE_KEY(jobId));
    if (raw) {
      try {
        const saved = JSON.parse(raw) as ThreadMessage[];
        if (Array.isArray(saved) && saved.length > 0) {
          setThread(saved);
          setExpanded(true);
        }
      } catch {
        /* ignore */
      }
    }
  }, [jobId]);

  // Persist on every change.
  useEffect(() => {
    if (typeof window === "undefined") return;
    window.localStorage.setItem(STORAGE_KEY(jobId), JSON.stringify(thread));
  }, [jobId, thread]);

  const submit = async () => {
    const question = draft.trim();
    if (!question || pending || expired) return;
    setError(null);
    setExpanded(true);
    const userMsg: ThreadMessage = { role: "user", content: question };
    const next = [...thread, userMsg];
    setThread(next);
    setDraft("");
    setPending(true);

    try {
      const history: ChatTurn[] = next
        .slice(-7, -1)
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

  const submitWithText = (text: string) => {
    setDraft(text);
    setTimeout(() => {
      // submit fires on next tick after state update settles
      const fakeEvent = new KeyboardEvent("keydown", { key: "Enter" });
      inputRef.current?.dispatchEvent(fakeEvent);
    }, 0);
    // Direct call instead of relying on event:
    setExpanded(true);
    void (async () => {
      const next = [...thread, { role: "user" as const, content: text }];
      setThread(next);
      setDraft("");
      setPending(true);
      try {
        const history: ChatTurn[] = next
          .slice(-7, -1)
          .map((m) => ({ role: m.role, content: m.content }));
        const resp = await askQuestion(jobId, text, history, language);
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
        if (e instanceof SessionExpiredError) setExpired(true);
        else setError(e instanceof Error ? e.message : "error");
      } finally {
        setPending(false);
      }
    })();
  };

  const showThread = expanded && (thread.length > 0 || pending || expired);

  return (
    <div
      className="fixed inset-x-0 bottom-0 z-40 pb-safe pointer-events-none"
      aria-label={t("chat.title", language)}
    >
      {/* Thread (renders above the bar when expanded) */}
      {showThread && (
        <div className="pointer-events-auto mx-auto max-w-3xl px-3 mb-2">
          <div
            className="rounded-[var(--radius-card)] border border-[var(--color-border)] bg-[var(--color-surface)] shadow-[var(--shadow-elevated)] overflow-hidden"
            style={{ maxHeight: "min(50dvh, 480px)" }}
          >
            <div className="flex items-center justify-between px-3 py-2 border-b border-[var(--color-border)]">
              <span className="text-sm font-semibold text-[var(--foreground)]">
                {t("chat.title", language)}
              </span>
              <button
                type="button"
                onClick={() => setExpanded(false)}
                aria-label="Collapse chat"
                className="text-gray-500 hover:text-gray-800 dark:hover:text-gray-200 text-lg leading-none focus-visible:outline focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-[var(--color-brand-500)] rounded"
              >
                ✕
              </button>
            </div>
            <div className="p-3" style={{ maxHeight: "calc(min(50dvh, 480px) - 50px)", overflowY: "auto" }}>
              <ChatThread
                thread={thread}
                pending={pending}
                error={error}
                expired={expired}
                language={language}
                onPickStarter={submitWithText}
              />
            </div>
          </div>
        </div>
      )}

      {/* Always-visible bottom bar */}
      <div className="pointer-events-auto bg-[var(--color-surface)] border-t border-[var(--color-border)] shadow-[var(--shadow-elevated)]">
        <div className="mx-auto max-w-3xl px-3 py-2 flex items-center gap-2">
          <span
            aria-hidden
            className="inline-flex items-center justify-center h-8 w-8 rounded-full bg-[var(--color-brand-500)] text-white text-sm shrink-0"
          >
            💬
          </span>
          <textarea
            ref={inputRef}
            value={draft}
            onChange={(e) => setDraft(e.target.value.slice(0, MAX_LEN))}
            onFocus={() => setExpanded(true)}
            onKeyDown={(e) => {
              if (e.key === "Enter" && !e.shiftKey) {
                e.preventDefault();
                submit();
              }
            }}
            disabled={pending || expired}
            placeholder={t("chat.placeholder", language)}
            rows={1}
            className="flex-1 resize-none rounded-full border border-[var(--color-border)] bg-[var(--color-surface-muted)] text-[var(--foreground)] text-sm px-4 py-2 focus-visible:outline focus-visible:outline-2 focus-visible:outline-offset-1 focus-visible:outline-[var(--color-brand-500)] disabled:opacity-60"
            aria-label={t("chat.placeholder", language)}
          />
          <button
            type="button"
            onClick={submit}
            disabled={pending || expired || draft.trim().length === 0}
            aria-label={t("chat.send", language)}
            className="inline-flex items-center justify-center h-9 w-9 rounded-full bg-[var(--color-brand-500)] hover:bg-[var(--color-brand-600)] text-white shrink-0 disabled:opacity-50 focus-visible:outline focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-[var(--color-brand-500)]"
          >
            ➤
          </button>
        </div>
      </div>
    </div>
  );
}
