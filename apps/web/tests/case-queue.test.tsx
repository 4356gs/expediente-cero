import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { beforeEach, expect, it, vi } from "vitest";

import { CaseQueue } from "@/components/case-queue";
import { ApiError, listCases } from "@/lib/api";
import { caseDetail } from "./fixtures";

vi.mock("@/lib/api", async (importOriginal) => {
  const actual = await importOriginal<typeof import("@/lib/api")>();
  return { ...actual, listCases: vi.fn() };
});

beforeEach(() => vi.mocked(listCases).mockReset());

it("renders the reviewer queue with typed status and language", async () => {
  vi.mocked(listCases).mockResolvedValue({ items: [caseDetail], total: 1, offset: 0, limit: 100 });
  render(<CaseQueue />);
  expect(await screen.findByText("EC-DEMO-001")).toBeVisible();
  expect(screen.getByText("Contratación de personal")).toBeVisible();
  expect(screen.getByText("Galego")).toBeVisible();
  expect(screen.getByRole("link", { name: /Revisar/ })).toHaveAttribute("href", `/cases/${caseDetail.id}`);
});

it("renders empty and recoverable typed-error states", async () => {
  vi.mocked(listCases).mockResolvedValueOnce({ items: [], total: 0, offset: 0, limit: 100 });
  const { unmount } = render(<CaseQueue />);
  expect(await screen.findByText("Aún no hay expedientes")).toBeVisible();
  unmount();

  vi.mocked(listCases)
    .mockRejectedValueOnce(new ApiError(503, "api_unavailable", "API no disponible"))
    .mockResolvedValueOnce({ items: [], total: 0, offset: 0, limit: 100 });
  render(<CaseQueue />);
  expect(await screen.findByText("api_unavailable")).toBeVisible();
  await userEvent.click(screen.getByRole("button", { name: "Reintentar" }));
  expect(await screen.findByText("Aún no hay expedientes")).toBeVisible();
});
