import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { beforeEach, expect, it, vi } from "vitest";

import { CaseWorkspace } from "@/components/case-workspace";
import * as api from "@/lib/api";
import { analysis, caseDetail, caseId, decision, draft, timeline, validation } from "./fixtures";

vi.mock("@/lib/api", async (importOriginal) => {
  const actual = await importOriginal<typeof import("@/lib/api")>();
  return {
    ...actual,
    getCase: vi.fn(), getAnalysis: vi.fn(), getValidation: vi.fn(), getDraft: vi.fn(),
    getDecision: vi.fn(), getTimeline: vi.fn(), analyzeCase: vi.fn(), validateCase: vi.fn(),
    generateDraft: vi.fn(), updateDraft: vi.fn(), decideCase: vi.fn(),
  };
});

beforeEach(() => {
  vi.mocked(api.getCase).mockResolvedValue(caseDetail);
  vi.mocked(api.getAnalysis).mockResolvedValue(analysis);
  vi.mocked(api.getValidation).mockResolvedValue(validation);
  vi.mocked(api.getDraft).mockResolvedValue(draft);
  vi.mocked(api.getDecision).mockRejectedValue(new api.ApiError(404, "review_decision_not_found", "Missing"));
  vi.mocked(api.getTimeline).mockResolvedValue(timeline);
  vi.mocked(api.decideCase).mockResolvedValue(decision);
  vi.mocked(api.generateDraft).mockResolvedValue(draft);
  vi.mocked(api.updateDraft).mockResolvedValue({ ...draft, reviewed_text: "Editado", version: 2 });
});

it("keeps four evidence regions separate and blocks approval", async () => {
  const user = userEvent.setup();
  render(<CaseWorkspace caseId={caseId} />);
  expect(await screen.findByRole("heading", { name: "Información fuente" })).toBeVisible();
  expect(screen.getByRole("heading", { name: "Análisis estructurado" })).toBeVisible();
  expect(screen.getByRole("heading", { name: "Validación independiente" })).toBeVisible();
  expect(screen.getByRole("heading", { name: "Salida revisada por una persona" })).toBeVisible();
  expect(screen.getByText("Texto original del modelo · inmutable")).toBeVisible();
  expect(screen.getByRole("button", { name: "Aprobar" })).toBeDisabled();
  expect(screen.getByText("Aprobación bloqueada")).toBeVisible();

  await user.type(screen.getByLabelText("Nombre o etiqueta del revisor"), "Ana");
  expect(screen.getByRole("button", { name: "Rechazar" })).toBeDisabled();
  await user.type(screen.getByLabelText(/Razón de rechazo/), "Debe revisarse");
  expect(screen.getByRole("button", { name: "Rechazar" })).toBeEnabled();
  await user.click(screen.getByRole("button", { name: "Rechazar" }));
  expect(api.decideCase).toHaveBeenCalledWith(caseId, "rejected", "Ana", "Debe revisarse");
});

it("renders an explicit model refusal and offers refresh", async () => {
  vi.mocked(api.getDraft).mockRejectedValue(new api.ApiError(404, "follow_up_draft_not_found", "Missing"));
  vi.mocked(api.generateDraft).mockRejectedValue(new api.ApiError(502, "follow_up_refused", "Follow-up generation failed."));
  const user = userEvent.setup();
  render(<CaseWorkspace caseId={caseId} />);
  await user.click(await screen.findByRole("button", { name: "Generar follow-up" }));
  expect(await screen.findByRole("alert")).toHaveTextContent("El modelo rechazó generar el borrador");
  expect(screen.getByRole("alert")).toHaveTextContent("Follow-up generation failed.");
});

it("preserves edited text when the backend reports a version conflict", async () => {
  vi.mocked(api.updateDraft).mockRejectedValue(new api.ApiError(409, "follow_up_version_conflict", "The draft is stale."));
  const user = userEvent.setup();
  render(<CaseWorkspace caseId={caseId} />);
  const textarea = await screen.findByLabelText("Texto revisado");
  await user.clear(textarea);
  await user.type(textarea, "Mi edición local");
  await user.click(screen.getByRole("button", { name: "Guardar edición" }));
  expect(await screen.findByRole("alert")).toHaveTextContent("follow_up_version_conflict");
  expect(textarea).toHaveValue("Mi edición local");
});

it("renders an immutable terminal human decision", async () => {
  vi.mocked(api.getCase).mockResolvedValue({ ...caseDetail, status: "rejected" });
  vi.mocked(api.getDecision).mockResolvedValue(decision);
  render(<CaseWorkspace caseId={caseId} />);
  expect(await screen.findByRole("heading", { name: "Expediente rechazado" })).toBeVisible();
  expect(screen.getByText("Debe corrixirse a data.")).toBeVisible();
  expect(screen.getByLabelText("Texto revisado")).toBeDisabled();
});
