import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { expect, it, vi } from "vitest";

import { EmptyArtifact, ErrorState, LoadingState } from "@/components/status";

it("renders accessible loading, empty, and retry states", async () => {
  const retry = vi.fn();
  const { rerender } = render(<LoadingState label="Cargando pruebas" />);
  expect(screen.getByRole("status")).toHaveTextContent("Cargando pruebas");
  rerender(<EmptyArtifact>Sin artefacto</EmptyArtifact>);
  expect(screen.getByText("Sin artefacto")).toBeVisible();
  rerender(<ErrorState message="Falló" code="typed_error" onRetry={retry} />);
  await userEvent.click(screen.getByRole("button", { name: "Reintentar" }));
  expect(retry).toHaveBeenCalledOnce();
  expect(screen.getByRole("alert")).toHaveTextContent("typed_error");
});
