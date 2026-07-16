import type { CaseStatus, OutputLanguage, ProcedureType } from "./types";

export const procedureLabels: Record<ProcedureType, string> = {
  self_employed_registration: "Alta de autónomo",
  employee_hiring: "Contratación de personal",
  grant_application: "Solicitud de ayuda",
};

export const statusLabels: Record<CaseStatus, string> = {
  draft: "Pendiente de análisis",
  analyzing: "Analizando",
  analyzed: "Pendiente de validación",
  needs_review: "Revisión humana",
  approved: "Aprobado",
  rejected: "Rechazado",
  analysis_failed: "Análisis fallido",
};

export const languageLabels: Record<OutputLanguage, string> = {
  es: "Español",
  gl: "Galego",
};

export function formatDate(value: string): string {
  return new Intl.DateTimeFormat("es-ES", {
    dateStyle: "medium",
    timeStyle: "short",
  }).format(new Date(value));
}
