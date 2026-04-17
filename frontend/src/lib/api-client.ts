const API_BASE = process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000";

export async function uploadReport(
  file: File,
  language: string
): Promise<string> {
  const formData = new FormData();
  formData.append("file", file);
  const resp = await fetch(
    `${API_BASE}/analyze-report?language=${language}`,
    { method: "POST", body: formData }
  );
  if (!resp.ok) {
    const err = await resp.json().catch(() => ({}));
    throw new Error(err.detail || `Upload failed: ${resp.status}`);
  }
  const data = await resp.json();
  return data.job_id;
}

// ─── Locked Phase 1 contract — see plans/260417-0010-summary-first-report-ux ───
export type Status = "green" | "yellow" | "orange" | "red";
export type Severity = "normal" | "mild" | "moderate" | "critical";
export type Direction = "high" | "low" | "in-range" | "indeterminate";

export interface TopFinding {
  test_name: string;
  value: number | string;
  unit: string | null;
  direction: "high" | "low" | "indeterminate";
  severity: "mild" | "moderate" | "critical";
  is_panic: boolean;
  health_topic: string;
  plain_language_key: string;
}

export interface ReportSummary {
  overall_status: Status;
  headline: string;
  top_findings: TopFinding[];
  next_steps_key: Status;
  indeterminate_count: number;
  uncertainty_note_key: string | null;
}

export interface TopicGroup {
  topic: string;
  topic_label_key: string;
  status: Status;
  summary: string;
  abnormal_count: number;
  indeterminate_count: number;
  // PR #6 calibration v2: minor_count tracks low-clinical-impact abnormals
  // (Basophils, NRBC, PDW, etc.) separately from "worth follow-up".
  minor_count?: number;
  total_count: number;
  results: InterpretedValue[];
}

export interface AnalysisResult {
  job_id: string;
  status: "queued" | "processing" | "completed" | "failed";
  result?: {
    summary?: ReportSummary;
    topic_groups?: TopicGroup[];
    values: InterpretedValue[];
    explanations: Explanation[];
    panels: Panel[];
    coverage_score: string;
    disclaimer: string;
    language: string;
    audit?: Record<string, unknown>;
  };
  error?: string;
}

export interface InterpretedValue {
  test_name: string;
  loinc_code: string | null;
  value: number | string;
  unit: string;
  direction: string;
  severity: string;
  // PR #6 calibration v2: display_severity is severity capped for UI
  // (low-clinical-impact tests never show "moderate"/"critical").
  // is_minor flags low-clinical-impact abnormals so the card uses a
  // "Minor" badge variant.
  display_severity?: string;
  is_minor?: boolean;
  is_panic: boolean;
  actionability: string;
  confidence: string;
  // Phase 3 uncertainty tag. "classified" is the baseline trustworthy
  // state; low_confidence means severity was suppressed to normal
  // because rule support was weak; could_not_classify means the
  // direction itself is indeterminate. Absent on older payloads.
  classification_state?: "classified" | "low_confidence" | "could_not_classify";
  reference_range_low: number | null;
  reference_range_high: number | null;
  range_source: string;
  range_trust?: string;
  evidence_trace: Record<string, unknown>;
  section_type?: string | null;
  verification_verdict?: string;
  unit_confidence?: string;
  health_topic?: string | null;
}

export interface Explanation {
  test_name: string;
  summary: string;
  what_it_means: string;
  next_steps: string;
  language: string;
  sources: string[];
}

export interface Panel {
  panel_name: string;
  expected: string[];
  present: string[];
  missing: string[];
}

/**
 * Thrown when polling for a job ID that the backend has no record of.
 * Happens after a backend restart (in-memory job_store wiped) or when the
 * job ID in the URL was never valid. Distinct from network errors so the
 * polling loop can stop retrying and surface a clear error to the user.
 */
export class JobNotFoundError extends Error {
  constructor() {
    super("job_not_found");
    this.name = "JobNotFoundError";
  }
}

export async function pollResult(jobId: string): Promise<AnalysisResult> {
  const resp = await fetch(`${API_BASE}/analysis/${jobId}`);
  if (resp.status === 404) throw new JobNotFoundError();
  if (!resp.ok) throw new Error(`Poll failed: ${resp.status}`);
  return resp.json();
}

export function getExportUrl(jobId: string): string {
  return `${API_BASE}/analysis/${jobId}/export`;
}

// ─── Phase 3: Q&A endpoint client ───
export interface ChatTurn {
  role: "user" | "assistant";
  content: string;
}

export interface ChatCitation {
  test_name: string;
  value: string | number;
  unit: string | null;
  health_topic: string | null;
}

export interface ChatResponse {
  answer: string;
  citations: ChatCitation[];
  follow_ups: string[];
  doctor_routing: boolean;
  refused: boolean;
  refusal_reason: string | null;
}

export class SessionExpiredError extends Error {
  constructor() {
    super("session_expired");
  }
}

export async function askQuestion(
  jobId: string,
  question: string,
  history: ChatTurn[] = [],
  language: string = "en"
): Promise<ChatResponse> {
  const resp = await fetch(`${API_BASE}/api/chat`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({
      job_id: jobId,
      question,
      history: history.slice(-6),
      language,
    }),
  });
  if (resp.status === 410) throw new SessionExpiredError();
  if (!resp.ok) {
    const err = await resp.json().catch(() => ({}));
    throw new Error(err.detail || `Chat failed: ${resp.status}`);
  }
  return resp.json();
}
