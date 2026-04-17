"use client";

import { useEffect, useState } from "react";
import dynamic from "next/dynamic";
import {
  askQuestion,
  SessionExpiredError,
  type ChatCitation,
  type ChatTurn,
} from "@/lib/api-client";
import type { Language } from "@/lib/i18n";
import { t } from "@/lib/i18n";
import { QaInput } from "@/components/chat/qa-input";
import {
  ASK_EVENT,
  type AskEventDetail,
} from "@/components/suggested-questions";

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

// Lazy-load the thread renderer so the floating button stays light when
// the user hasn't engaged the chat yet.
const ChatThread = dynamic(
  () =>
    import("@/components/chat/qa-thread").then((m) => ({
      default: m.QaThread,
    })),
  { ssr: false, loading: () => null }
);

/**
 * Floating chat button + larger dialog (BloodGPT-inspired but bigger than
 * the original LabLens panel). Brings back the starter-questions UX for
 * empty threads via QaThread → StarterQuestions.
 *
 * Sizing:
 *   - Desktop ≥md: fixed bottom-right card, 480px wide, min(720px, 80dvh) tall
 *   - Mobile <md: full bottom-sheet, full width, 90dvh tall
 *
 * State + persistence are owned here; thread + input are display-only.
 */
export function ChatDock({ jobId, language }: Props) {
  const [open, setOpen] = useState(false);
  const [thread, setThread] = useState<ThreadMessage[]>([]);
  const [pending, setPending] = useState(false);
  const [expired, setExpired] = useState(false);
  const [error, setError] = useState<string | null>(null);

  // Restore on mount (also restores expired flag indirectly — if thread had
  // a previous server-side 410 we'd see it next request).
  useEffect(() => {
    if (typeof window === "undefined") return;
    const raw = window.localStorage.getItem(STORAGE_KEY(jobId));
    if (raw) {
      try {
        const saved = JSON.parse(raw) as ThreadMessage[];
        if (Array.isArray(saved)) setThread(saved);
      } catch {
        /* ignore */
      }
    }
  }, [jobId]);

  // Persist
  useEffect(() => {
    if (typeof window === "undefined") return;
    window.localStorage.setItem(STORAGE_KEY(jobId), JSON.stringify(thread));
  }, [jobId, thread]);

  // Esc closes the dialog
  useEffect(() => {
    if (!open) return;
    const onKey = (e: KeyboardEvent) => {
      if (e.key === "Escape") setOpen(false);
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [open]);

  // Listen for "ask this question" events from the pinned SuggestedQuestions
  // panel. Opens the dialog and auto-submits the question.
  useEffect(() => {
    if (typeof window === "undefined") return;
    const handler = (e: Event) => {
      const ce = e as CustomEvent<AskEventDetail>;
      const q = ce.detail?.question;
      if (!q) return;
      setOpen(true);
      // Fire submit after React has had a chance to render the dialog.
      setTimeout(() => void submit(q), 0);
    };
    window.addEventListener(ASK_EVENT, handler as EventListener);
    return () =>
      window.removeEventListener(ASK_EVENT, handler as EventListener);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [thread, pending, expired]);

  const submit = async (question: string) => {
    if (pending || expired) return;
    setError(null);
    const userMsg: ThreadMessage = { role: "user", content: question };
    const next = [...thread, userMsg];
    setThread(next);
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
      if (e instanceof SessionExpiredError) setExpired(true);
      else setError(e instanceof Error ? e.message : "error");
    } finally {
      setPending(false);
    }
  };

  return (
    <>
      {/* Floating button — only visible when dialog closed */}
      {!open && (
        <button
          type="button"
          onClick={() => setOpen(true)}
          className="fixed bottom-4 right-4 z-30 inline-flex items-center gap-2 rounded-full bg-[var(--color-brand-500)] hover:bg-[var(--color-brand-600)] text-white px-5 py-3 text-sm font-medium shadow-[var(--shadow-elevated)] focus-visible:outline focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-[var(--color-brand-500)] pb-safe"
          aria-label={t("chat.cta_open", language)}
        >
          <span aria-hidden>💬</span>
          {t("chat.cta_open", language)}
        </button>
      )}

      {/* Dialog */}
      {open && (
        <aside
          role="dialog"
          aria-modal="false"
          aria-label={t("chat.title", language)}
          className="fixed z-40 inset-x-0 bottom-0 md:inset-auto md:right-4 md:bottom-4 md:w-[480px] md:max-w-[calc(100vw-2rem)] flex flex-col bg-[var(--color-surface)] border border-[var(--color-border)] rounded-t-[var(--radius-card)] md:rounded-[var(--radius-card)] shadow-[var(--shadow-elevated)] pb-safe"
          style={{
            // Big dialog: 720px tall capped at 80dvh on desktop; 90dvh on mobile.
            height: "min(720px, 80dvh)",
            maxHeight: "90dvh",
          }}
        >
          {/* Header */}
          <header className="flex items-center justify-between px-4 py-3 border-b border-[var(--color-border)] shrink-0">
            <h2 className="font-semibold text-[var(--foreground)]">
              {t("chat.title", language)}
            </h2>
            <button
              type="button"
              onClick={() => setOpen(false)}
              aria-label="Close chat"
              className="text-gray-500 hover:text-gray-800 dark:hover:text-gray-200 focus-visible:outline focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-[var(--color-brand-500)] rounded text-lg leading-none"
            >
              ✕
            </button>
          </header>

          {/* Thread (scrollable) — QaThread shows StarterQuestions when empty */}
          <div className="flex-1 overflow-y-auto px-4 py-3">
            <ChatThread
              thread={thread}
              pending={pending}
              error={error}
              expired={expired}
              language={language}
              onPickStarter={submit}
            />
          </div>

          {/* Input */}
          <div className="shrink-0 border-t border-[var(--color-border)]">
            <QaInput
              disabled={pending || expired}
              language={language}
              onSubmit={submit}
            />
          </div>
        </aside>
      )}
    </>
  );
}
