"use client";

import Link from "next/link";
import { useCallback, useEffect, useState } from "react";

import { EmptyArtifact, ErrorState, LoadingState } from "./status";
import {
  ApiError,
  analyzeCase,
  decideCase,
  generateDraft,
  getAnalysis,
  getCase,
  getDecision,
  getDraft,
  getTimeline,
  getValidation,
  updateDraft,
  validateCase,
} from "@/lib/api";
import { formatDate, languageLabels, procedureLabels, statusLabels } from "@/lib/labels";
import type {
  CaseDetail,
  FollowUpDraft,
  IntakeAnalysis,
  ReviewDecision,
  Timeline,
  ValidationResult,
} from "@/lib/types";

const EMPTY_CODES = new Set([
  "analysis_not_found",
  "validation_result_not_found",
  "follow_up_draft_not_found",
  "review_decision_not_found",
]);

interface WorkspaceData {
  caseDetail: CaseDetail;
  analysis: IntakeAnalysis | null;
  validation: ValidationResult | null;
  draft: FollowUpDraft | null;
  decision: ReviewDecision | null;
  timeline: Timeline;
}

async function fetchWorkspace(caseId: string): Promise<WorkspaceData> {
  const [caseDetail, analysis, validation, draft, decision, timeline] = await Promise.all([
    getCase(caseId),
    optional(getAnalysis(caseId)),
    optional(getValidation(caseId)),
    optional(getDraft(caseId)),
    optional(getDecision(caseId)),
    getTimeline(caseId),
  ]);
  return { caseDetail, analysis, validation, draft, decision, timeline };
}

async function optional<T>(promise: Promise<T>): Promise<T | null> {
  try {
    return await promise;
  } catch (error) {
    if (error instanceof ApiError && EMPTY_CODES.has(error.code)) return null;
    throw error;
  }
}

export function CaseWorkspace({ caseId }: { caseId: string }) {
  const [data, setData] = useState<WorkspaceData | null>(null);
  const [error, setError] = useState<ApiError | null>(null);
  const [actionError, setActionError] = useState<ApiError | null>(null);
  const [busy, setBusy] = useState<string | null>(null);
  const [reviewedText, setReviewedText] = useState("");
  const [reviewer, setReviewer] = useState("");
  const [reason, setReason] = useState("");

  const load = useCallback(async () => {
    try {
      const result = await fetchWorkspace(caseId);
      setError(null);
      setData(result);
      setReviewedText(result.draft?.reviewed_text ?? "");
    } catch (caught) {
      setError(caught instanceof ApiError ? caught : new ApiError(0, "unexpected_error", "Error inesperado."));
    }
  }, [caseId]);

  useEffect(() => {
    let active = true;
    void fetchWorkspace(caseId)
      .then((result) => {
        if (!active) return;
        setData(result);
        setReviewedText(result.draft?.reviewed_text ?? "");
      })
      .catch((caught: unknown) => {
        if (!active) return;
        setError(
          caught instanceof ApiError
            ? caught
            : new ApiError(0, "unexpected_error", "Error inesperado."),
        );
      });
    return () => {
      active = false;
    };
  }, [caseId]);

  async function runAction(name: string, action: () => Promise<unknown>) {
    setBusy(name);
    setActionError(null);
    try {
      await action();
      await load();
    } catch (caught) {
      setActionError(caught instanceof ApiError ? caught : new ApiError(0, "unexpected_error", "Error inesperado."));
    } finally {
      setBusy(null);
    }
  }

  if (!data && !error) return <div className="pageShell"><LoadingState /></div>;
  if (error) return <div className="pageShell"><ErrorState message={error.message} code={error.code} onRetry={load} /></div>;
  if (!data) return null;

  const terminal = data.caseDetail.status === "approved" || data.caseDetail.status === "rejected";
  const approvalBlocked = data.validation?.has_blocking_findings ?? false;
  const canDecide = data.caseDetail.status === "needs_review" && Boolean(data.draft) && !data.decision;
  const rejectionReasonMissing = reason.trim().length === 0;

  return (
    <div className="pageShell workspaceShell">
      <nav className="breadcrumb" aria-label="Migas de pan"><Link href="/">Expedientes</Link><span aria-hidden="true">/</span><span>{data.caseDetail.reference}</span></nav>
      <header className="workspaceHeader">
        <div><p className="eyebrow">{procedureLabels[data.caseDetail.procedure_type]}</p><h1>{data.caseDetail.reference}</h1><div className="metaLine"><span className={`statusBadge status-${data.caseDetail.status}`}>{statusLabels[data.caseDetail.status]}</span><span>{languageLabels[data.caseDetail.output_language]}</span><span>Actualizado {formatDate(data.caseDetail.updated_at)}</span></div></div>
        <button className="button ghost" onClick={load} disabled={Boolean(busy)}>Actualizar</button>
      </header>

      {actionError ? (
        <div className={`inlineAlert ${actionError.code.includes("refused") ? "refusalAlert" : ""}`} role="alert" aria-live="assertive">
          <strong>{actionError.code === "follow_up_refused" ? "El modelo rechazó generar el borrador" : actionError.code}</strong>
          <span>{actionError.message}</span>
          {actionError.code.includes("conflict") || actionError.code === "follow_up_generation_in_progress" ? <button className="textButton" onClick={load}>Actualizar expediente</button> : null}
        </div>
      ) : null}

      <section className="workflowBar" aria-label="Progreso del expediente">
        {["Fuente", "Análisis", "Validación", "Revisión humana"].map((label, index) => {
          const reached = [true, Boolean(data.analysis), Boolean(data.validation), Boolean(data.draft)][index];
          return <div className={reached ? "workflowStep reached" : "workflowStep"} key={label}><span>{index + 1}</span><strong>{label}</strong></div>;
        })}
      </section>

      <div className="evidenceGrid">
        <section className="evidenceCard sourceCard" aria-labelledby="source-title">
          <EvidenceHeader number="01" eyebrow="Evidencia original" title="Información fuente" id="source-title" />
          <dl className="detailList"><div><dt>Procedimiento</dt><dd>{procedureLabels[data.caseDetail.procedure_type]}</dd></div><div><dt>Idioma solicitado</dt><dd>{languageLabels[data.caseDetail.output_language]}</dd></div><div><dt>Naturaleza</dt><dd>Sintética</dd></div></dl>
          <h3>Mensajes</h3>
          {data.caseDetail.source_messages.map((message) => <blockquote key={message.id}>{message.content}<cite>{message.id}</cite></blockquote>)}
          <h3>Documentos declarados</h3>
          {data.caseDetail.documents.length ? <ul className="documentList">{data.caseDetail.documents.map((document) => <li key={document.id}><span aria-hidden="true">▤</span><div><strong>{document.display_name}</strong><small>{document.document_type} · sintético</small></div></li>)}</ul> : <EmptyArtifact>No se declararon documentos sintéticos.</EmptyArtifact>}
        </section>

        <section className="evidenceCard modelCard" aria-labelledby="analysis-title">
          <EvidenceHeader number="02" eyebrow="Derivado del modelo" title="Análisis estructurado" id="analysis-title" />
          {!data.analysis ? <div><EmptyArtifact>El expediente aún no tiene análisis persistido.</EmptyArtifact>{["draft", "analysis_failed"].includes(data.caseDetail.status) ? <button className="button primary" disabled={Boolean(busy)} onClick={() => runAction("analysis", () => analyzeCase(caseId))}>{busy === "analysis" ? "Analizando…" : data.caseDetail.status === "analysis_failed" ? "Reintentar análisis" : "Analizar intake"}</button> : null}</div> : <AnalysisPanel analysis={data.analysis} />}
        </section>

        <section className="evidenceCard validationCard" aria-labelledby="validation-title">
          <EvidenceHeader number="03" eyebrow="Código determinista" title="Validación independiente" id="validation-title" />
          {!data.validation ? <div><EmptyArtifact>La validación determinista todavía no se ha ejecutado.</EmptyArtifact>{data.caseDetail.status === "analyzed" ? <button className="button primary" disabled={Boolean(busy)} onClick={() => runAction("validation", () => validateCase(caseId))}>{busy === "validation" ? "Validando…" : "Ejecutar validación"}</button> : null}</div> : <ValidationPanel validation={data.validation} />}
        </section>

        <section className="evidenceCard humanCard" aria-labelledby="human-title">
          <EvidenceHeader number="04" eyebrow="Control profesional" title="Salida revisada por una persona" id="human-title" />
          {!data.draft ? <div><EmptyArtifact>No existe un borrador de follow-up.</EmptyArtifact>{data.caseDetail.status === "needs_review" ? <button className="button primary" disabled={Boolean(busy)} onClick={() => runAction("draft", () => generateDraft(caseId))}>{busy === "draft" ? "Generando…" : "Generar follow-up"}</button> : null}</div> : (
            <div className="draftReview">
              <div className="modelOriginal"><span className="fieldLabel">Texto original del modelo · inmutable</span><p>{data.draft.model_text}</p><small>{data.draft.prompt_version} · versión humana {data.draft.version}</small></div>
              <label className="field"><span>Texto revisado</span><textarea value={reviewedText} onChange={(event) => setReviewedText(event.target.value)} rows={8} maxLength={4000} disabled={terminal} /></label>
              {!terminal ? <button className="button secondary" disabled={Boolean(busy) || reviewedText.trim() === data.draft.reviewed_text} onClick={() => runAction("edit", () => updateDraft(caseId, reviewedText, data.draft!.version))}>{busy === "edit" ? "Guardando…" : "Guardar edición"}</button> : null}
              {data.decision ? <DecisionSummary decision={data.decision} /> : (
                <div className="decisionBox">
                  <h3>Decisión exclusivamente humana</h3>
                  <label className="field"><span>Nombre o etiqueta del revisor</span><input value={reviewer} onChange={(event) => setReviewer(event.target.value)} maxLength={128} required /></label>
                  <label className="field"><span>Razón de rechazo</span><textarea value={reason} onChange={(event) => setReason(event.target.value)} rows={3} maxLength={2000} aria-describedby="reason-help" /><small id="reason-help">Obligatoria solo para rechazar.</small></label>
                  {approvalBlocked ? <p className="blockingNotice" role="status"><strong>Aprobación bloqueada</strong>Hay findings deterministas blocking que deben resolverse.</p> : null}
                  <div className="decisionActions">
                    <button className="button approve" disabled={!canDecide || approvalBlocked || !reviewer.trim() || Boolean(busy)} onClick={() => runAction("approve", () => decideCase(caseId, "approved", reviewer, null))}>{busy === "approve" ? "Aprobando…" : "Aprobar"}</button>
                    <button className="button reject" disabled={!canDecide || !reviewer.trim() || rejectionReasonMissing || Boolean(busy)} onClick={() => runAction("reject", () => decideCase(caseId, "rejected", reviewer, reason))}>{busy === "reject" ? "Rechazando…" : "Rechazar"}</button>
                  </div>
                </div>
              )}
            </div>
          )}
        </section>
      </div>

      <TimelinePanel timeline={data.timeline} />
    </div>
  );
}

function EvidenceHeader({ number, eyebrow, title, id }: { number: string; eyebrow: string; title: string; id: string }) {
  return <header className="evidenceHeader"><span className="evidenceNumber" aria-hidden="true">{number}</span><div><p className="eyebrow">{eyebrow}</p><h2 id={id}>{title}</h2></div></header>;
}

function AnalysisPanel({ analysis }: { analysis: IntakeAnalysis }) {
  return <div><p className="summaryText">{analysis.procedure_reason}</p><div className="factGrid">{analysis.facts.map((fact) => <div className="factItem" key={fact.field}><span>{fact.field}</span><strong>{fact.value ?? "Sin valor"}</strong><small className={`fact-${fact.status}`}>{fact.status} · {fact.source_reference ?? "sin referencia"}</small></div>)}</div><ListGroup title="Suposiciones" items={analysis.assumptions} empty="Sin suposiciones." /><ListGroup title="Preguntas sin resolver" items={analysis.unresolved_questions.map((item) => `${item.blocking ? "[Blocking] " : ""}${item.question}`)} empty="Sin preguntas abiertas." /><ListGroup title="Contradicciones" items={analysis.contradictions.map((item) => `${item.blocking ? "[Blocking] " : ""}${item.description}`)} empty="Sin contradicciones del modelo." /><p className="provenance">Prompt {analysis.prompt_version} · Run {analysis.model_run_id}</p></div>;
}

function ListGroup({ title, items, empty }: { title: string; items: string[]; empty: string }) {
  return <div className="listGroup"><h3>{title}</h3>{items.length ? <ul>{items.map((item, index) => <li key={`${index}-${item}`}>{item}</li>)}</ul> : <p>{empty}</p>}</div>;
}

function ValidationPanel({ validation }: { validation: ValidationResult }) {
  return <div><div className={`validationSummary ${validation.has_blocking_findings ? "hasBlocking" : "clear"}`}><strong>{validation.has_blocking_findings ? "Requiere intervención" : "Sin bloqueos deterministas"}</strong><span>{validation.findings.length} findings · {validation.checklist_results.length} controles</span></div><h3>Checklist</h3><ul className="checklist">{validation.checklist_results.map((item) => <li key={item.id}><span className={`checkStatus check-${item.status}`}>{item.status}</span><div><strong>{item.label}</strong><small>{item.required ? "Obligatorio" : "Opcional"}{item.evidence_reference ? ` · ${item.evidence_reference}` : ""}</small></div></li>)}</ul><h3>Findings</h3>{validation.findings.length ? <ul className="findingList">{validation.findings.map((finding) => <li className={`finding-${finding.severity}`} key={finding.id}><span>{finding.severity}</span><div><strong>{finding.message}</strong><small>{finding.code}{finding.field_reference ? ` · ${finding.field_reference}` : ""}</small></div></li>)}</ul> : <EmptyArtifact>No hay findings deterministas.</EmptyArtifact>}<p className="provenance">{validation.template_version} · {formatDate(validation.validation_completed_at)}</p></div>;
}

function DecisionSummary({ decision }: { decision: ReviewDecision }) {
  return <div className={`decisionSummary decision-${decision.decision}`} role="status"><span className="stateIcon" aria-hidden="true">{decision.decision === "approved" ? "✓" : "×"}</span><div><p className="eyebrow">Decisión final</p><h3>{decision.decision === "approved" ? "Expediente aprobado" : "Expediente rechazado"}</h3><p>Por {decision.actor.label} · {formatDate(decision.created_at)}</p>{decision.reason ? <blockquote>{decision.reason}</blockquote> : null}</div></div>;
}

function TimelinePanel({ timeline }: { timeline: Timeline }) {
  return <section className="timelineCard" aria-labelledby="timeline-title"><div className="sectionHeading"><div><p className="eyebrow">Trazabilidad</p><h2 id="timeline-title">Timeline de auditoría</h2></div><span>{timeline.events.length} eventos</span></div>{timeline.events.length ? <ol className="timeline">{timeline.events.map((event) => <li key={event.id}><span className="timelineDot" aria-hidden="true" /><div><strong>{event.event_type.replaceAll("_", " ")}</strong><p>{event.actor_label} · {event.actor_type}</p><time dateTime={event.recorded_at}>{formatDate(event.recorded_at)}</time>{Object.keys(event.metadata).length ? <details><summary>Metadatos sanitizados</summary><dl>{Object.entries(event.metadata).map(([key, value]) => <div key={key}><dt>{key}</dt><dd>{value}</dd></div>)}</dl></details> : null}</div></li>)}</ol> : <EmptyArtifact>Aún no hay eventos de auditoría.</EmptyArtifact>}<p className="timelineNote">Los eventos con la misma marca temporal se muestran en orden estable, sin implicar causalidad.</p></section>;
}
