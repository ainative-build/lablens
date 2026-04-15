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

export interface AnalysisResult {
  job_id: string;
  status: "queued" | "processing" | "completed" | "failed";
  result?: {
    values: InterpretedValue[];
    explanations: Explanation[];
    panels: Panel[];
    coverage_score: string;
    disclaimer: string;
    language: string;
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
  is_panic: boolean;
  actionability: string;
  confidence: string;
  reference_range_low: number | null;
  reference_range_high: number | null;
  range_source: string;
  evidence_trace: Record<string, unknown>;
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

export async function pollResult(jobId: string): Promise<AnalysisResult> {
  const resp = await fetch(`${API_BASE}/analysis/${jobId}`);
  if (!resp.ok) throw new Error(`Poll failed: ${resp.status}`);
  return resp.json();
}

export function getExportUrl(jobId: string): string {
  return `${API_BASE}/analysis/${jobId}/export`;
}
