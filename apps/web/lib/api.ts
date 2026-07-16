import type {
  CaseCreateInput,
  CaseDetail,
  CaseList,
  ErrorEnvelope,
  FollowUpDraft,
  IntakeAnalysis,
  ReviewDecision,
  Timeline,
  ValidationResult,
} from "./types";

const API_ROOT = "/api/backend/cases";

export class ApiError extends Error {
  constructor(
    public readonly status: number,
    public readonly code: string,
    message: string,
    public readonly issues: ErrorEnvelope["error"]["issues"] = [],
  ) {
    super(message);
    this.name = "ApiError";
  }
}

async function apiRequest<T>(path: string, init?: RequestInit): Promise<T> {
  const response = await fetch(`${API_ROOT}${path}`, {
    ...init,
    cache: "no-store",
    headers: init?.body
      ? { "Content-Type": "application/json", ...init.headers }
      : init?.headers,
  });
  if (!response.ok) {
    let envelope: ErrorEnvelope | null = null;
    try {
      envelope = (await response.json()) as ErrorEnvelope;
    } catch {
      // A non-API proxy failure is normalized below.
    }
    throw new ApiError(
      response.status,
      envelope?.error.code ?? "unexpected_error",
      envelope?.error.message ?? "No se pudo completar la operación.",
      envelope?.error.issues ?? [],
    );
  }
  return (await response.json()) as T;
}

export function listCases(): Promise<CaseList> {
  return apiRequest<CaseList>("?limit=100");
}

export function createCase(payload: CaseCreateInput): Promise<CaseDetail> {
  return apiRequest<CaseDetail>("", { method: "POST", body: JSON.stringify(payload) });
}

export function getCase(caseId: string): Promise<CaseDetail> {
  return apiRequest<CaseDetail>(`/${caseId}`);
}

export function getAnalysis(caseId: string): Promise<IntakeAnalysis> {
  return apiRequest<IntakeAnalysis>(`/${caseId}/analysis`);
}

export function analyzeCase(caseId: string): Promise<unknown> {
  return apiRequest(`/${caseId}/analysis`, { method: "POST" });
}

export function getValidation(caseId: string): Promise<ValidationResult> {
  return apiRequest<ValidationResult>(`/${caseId}/validation-result`);
}

export function validateCase(caseId: string): Promise<unknown> {
  return apiRequest(`/${caseId}/validation`, { method: "POST" });
}

export function getDraft(caseId: string): Promise<FollowUpDraft> {
  return apiRequest<FollowUpDraft>(`/${caseId}/follow-up-draft`);
}

export function generateDraft(caseId: string): Promise<FollowUpDraft> {
  return apiRequest<FollowUpDraft>(`/${caseId}/follow-up-draft`, { method: "POST" });
}

export function updateDraft(
  caseId: string,
  reviewedText: string,
  expectedVersion: number,
): Promise<FollowUpDraft> {
  return apiRequest<FollowUpDraft>(`/${caseId}/follow-up-draft`, {
    method: "PATCH",
    body: JSON.stringify({ reviewed_text: reviewedText, expected_version: expectedVersion }),
  });
}

export function getDecision(caseId: string): Promise<ReviewDecision> {
  return apiRequest<ReviewDecision>(`/${caseId}/review-decision`);
}

export function decideCase(
  caseId: string,
  decision: "approved" | "rejected",
  reviewerLabel: string,
  reason: string | null,
): Promise<ReviewDecision> {
  return apiRequest<ReviewDecision>(`/${caseId}/review-decision`, {
    method: "POST",
    body: JSON.stringify({ decision, reason, actor: { label: reviewerLabel } }),
  });
}

export function getTimeline(caseId: string): Promise<Timeline> {
  return apiRequest<Timeline>(`/${caseId}/timeline`);
}
