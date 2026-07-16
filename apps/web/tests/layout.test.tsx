import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";

import RootLayout from "@/app/layout";

describe("RootLayout", () => {
  it("shows the synthetic, human-review, no-advice, and no-submission boundary", () => {
    render(<RootLayout><p>Contenido</p></RootLayout>);

    expect(screen.getByText("Entorno sintético")).toBeInTheDocument();
    expect(screen.getByLabelText("Límites de la demostración")).toHaveTextContent(
      "La salida requiere revisión humana, no es asesoramiento profesional y no se presenta ante ningún organismo.",
    );
  });
});
