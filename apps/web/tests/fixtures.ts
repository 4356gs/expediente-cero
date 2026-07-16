import type {
  CaseDetail,
  FollowUpDraft,
  IntakeAnalysis,
  ReviewDecision,
  Timeline,
  ValidationResult,
} from "@/lib/types";

export const caseId = "11111111-1111-4111-8111-111111111111";
export const now = "2026-07-16T12:00:00Z";

export const caseDetail: CaseDetail = {
  id: caseId,
  reference: "EC-DEMO-001",
  procedure_type: "employee_hiring",
  output_language: "gl",
  status: "needs_review",
  created_at: now,
  updated_at: now,
  source_messages: [
    { id: "message-1", case_id: caseId, content: "Mensaxe sintética", is_synthetic: true, created_at: now },
  ],
  documents: [
    { id: "document-1", case_id: caseId, document_type: "employment_contract", display_name: "Contrato sintético.pdf", is_synthetic: true, created_at: now },
  ],
};

export const analysis: IntakeAnalysis = {
  id: "analysis-1",
  case_id: caseId,
  procedure_type: "employee_hiring",
  procedure_reason: "A mensaxe solicita unha contratación sintética.",
  facts: [{ field: "employee_name", value: "Persoa sintética", source_reference: "message:message-1", status: "stated" }],
  assumptions: ["A data debe confirmarse"],
  unresolved_questions: [{ code: "date", question: "Cal é a data correcta?", reason: "Datas distintas", blocking: true }],
  contradictions: [{ code: "date_mismatch", description: "As datas non coinciden", source_references: ["message:message-1", "document:document-1"], blocking: true }],
  requested_output_language: "gl",
  prompt_version: "intake-analysis-v1",
  model_run_id: "run-analysis-1",
  created_at: now,
};

export const validation: ValidationResult = {
  template_version: "deterministic-validation-v1",
  validation_completed_at: now,
  has_blocking_findings: true,
  checklist_results: [{ id: "check-1", item_code: "employee.start", label: "Data de inicio", required: true, status: "needs_review", evidence_reference: null }],
  findings: [{ id: "finding-1", code: "employment_start_date_mismatch", severity: "blocking", message: "As datas de inicio non coinciden.", field_reference: "contract_start_date", created_at: now }],
};

export const draft: FollowUpDraft = {
  id: "draft-1",
  case_id: caseId,
  language: "gl",
  model_text: "Confirme a data de inicio, por favor.",
  reviewed_text: "Confirme a data de inicio, por favor.",
  prompt_version: "follow-up-draft-v1",
  model_run_id: "run-draft-1",
  version: 1,
  created_at: now,
  updated_at: now,
};

export const decision: ReviewDecision = {
  id: "decision-1",
  case_id: caseId,
  decision: "rejected",
  reason: "Debe corrixirse a data.",
  actor: { label: "Ana" },
  created_at: now,
};

export const timeline: Timeline = {
  case_id: caseId,
  events: [{ id: "event-1", event_type: "case_status_changed", actor_type: "system", actor_label: "workflow", recorded_at: now, metadata: { new_status: "needs_review" } }],
};
