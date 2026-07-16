export type ProcedureType =
  | "self_employed_registration"
  | "employee_hiring"
  | "grant_application";
export type OutputLanguage = "es" | "gl";
export type CaseStatus =
  | "draft"
  | "analyzing"
  | "analyzed"
  | "needs_review"
  | "approved"
  | "rejected"
  | "analysis_failed";

export interface SourceMessage {
  id: string;
  case_id: string;
  content: string;
  is_synthetic: boolean;
  created_at: string;
}

export interface DocumentMetadata {
  id: string;
  case_id: string;
  document_type: string;
  display_name: string;
  is_synthetic: boolean;
  created_at: string;
}

export interface CaseSummary {
  id: string;
  reference: string;
  procedure_type: ProcedureType;
  output_language: OutputLanguage;
  status: CaseStatus;
  created_at: string;
  updated_at: string;
}

export interface CaseDetail extends CaseSummary {
  source_messages: SourceMessage[];
  documents: DocumentMetadata[];
}

export interface CaseList {
  items: CaseSummary[];
  total: number;
  offset: number;
  limit: number;
}

export interface CaseCreateInput {
  reference: string;
  procedure_type: ProcedureType;
  output_language: OutputLanguage;
  is_synthetic: true;
  source_messages: Array<{ content: string; is_synthetic: true }>;
  documents: Array<{
    document_type: string;
    display_name: string;
    is_synthetic: true;
  }>;
}

export interface ExtractedFact {
  field: string;
  value: string | null;
  source_reference: string | null;
  status: "stated" | "inferred" | "unknown";
}

export interface IntakeAnalysis {
  id: string;
  case_id: string;
  procedure_type: ProcedureType;
  procedure_reason: string;
  facts: ExtractedFact[];
  assumptions: string[];
  unresolved_questions: Array<{
    code: string;
    question: string;
    reason: string;
    blocking: boolean;
  }>;
  contradictions: Array<{
    code: string;
    description: string;
    source_references: string[];
    blocking: boolean;
  }>;
  requested_output_language: OutputLanguage;
  prompt_version: string;
  model_run_id: string;
  created_at: string;
}

export interface ChecklistResult {
  id: string;
  item_code: string;
  label: string;
  required: boolean;
  status: "present" | "missing" | "not_applicable" | "needs_review";
  evidence_reference: string | null;
}

export interface ValidationFinding {
  id: string;
  code: string;
  severity: "info" | "warning" | "blocking";
  message: string;
  field_reference: string | null;
  created_at: string;
}

export interface ValidationResult {
  template_version: string;
  validation_completed_at: string;
  has_blocking_findings: boolean;
  checklist_results: ChecklistResult[];
  findings: ValidationFinding[];
}

export interface FollowUpDraft {
  id: string;
  case_id: string;
  language: OutputLanguage;
  model_text: string;
  reviewed_text: string;
  prompt_version: string;
  model_run_id: string;
  version: number;
  created_at: string;
  updated_at: string;
}

export interface ReviewDecision {
  id: string;
  case_id: string;
  decision: "approved" | "rejected";
  reason: string | null;
  actor: { label: string };
  created_at: string;
}

export interface AuditEvent {
  id: string;
  event_type: string;
  actor_type: string;
  actor_label: string;
  recorded_at: string;
  metadata: Record<string, string>;
}

export interface Timeline {
  case_id: string;
  events: AuditEvent[];
}

export interface ErrorEnvelope {
  error: {
    code: string;
    message: string;
    issues: Array<{ location: Array<string | number>; message: string; type: string }>;
  };
}
