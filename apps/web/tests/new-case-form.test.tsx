import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { beforeEach, expect, it, vi } from "vitest";

import { NewCaseForm } from "@/components/new-case-form";
import { ApiError, createCase } from "@/lib/api";
import { caseDetail } from "./fixtures";

const push = vi.fn();
vi.mock("next/navigation", () => ({ useRouter: () => ({ push }) }));
vi.mock("@/lib/api", async (importOriginal) => {
  const actual = await importOriginal<typeof import("@/lib/api")>();
  return { ...actual, createCase: vi.fn() };
});

beforeEach(() => {
  push.mockReset();
  vi.mocked(createCase).mockReset();
});

it("creates a bounded Galician synthetic intake", async () => {
  vi.mocked(createCase).mockResolvedValue(caseDetail);
  const user = userEvent.setup();
  render(<NewCaseForm />);
  await user.type(screen.getByLabelText("Referencia"), "EC-DEMO-001");
  await user.click(screen.getByLabelText("Contratación de personal"));
  await user.click(screen.getByLabelText("Galego"));
  await user.type(screen.getByLabelText("Mensaje fuente sintético"), "Mensaxe sintética");
  await user.type(screen.getByLabelText("Tipo"), "employment_contract");
  await user.type(screen.getByLabelText("Nombre visible"), "Contrato sintético.pdf");
  await user.click(screen.getByRole("button", { name: "Crear expediente" }));
  expect(createCase).toHaveBeenCalledWith(expect.objectContaining({
    procedure_type: "employee_hiring",
    output_language: "gl",
    is_synthetic: true,
    documents: [expect.objectContaining({ is_synthetic: true })],
  }));
  expect(push).toHaveBeenCalledWith(`/cases/${caseDetail.id}`);
});

it("shows the typed create error without navigating", async () => {
  vi.mocked(createCase).mockRejectedValue(new ApiError(409, "persistence_conflict", "Referencia duplicada"));
  const user = userEvent.setup();
  render(<NewCaseForm />);
  await user.type(screen.getByLabelText("Referencia"), "EC-DEMO-001");
  await user.type(screen.getByLabelText("Mensaje fuente sintético"), "Solicitud sintética");
  await user.click(screen.getByRole("button", { name: "Crear expediente" }));
  expect(await screen.findByRole("alert")).toHaveTextContent("persistence_conflict");
  expect(push).not.toHaveBeenCalled();
});
