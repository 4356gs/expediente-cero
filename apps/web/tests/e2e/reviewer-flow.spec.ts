import { expect, type Page, test } from "@playwright/test";

const now = "2026-07-16T12:00:00Z";
const caseId = "11111111-1111-4111-8111-111111111111";

interface Scenario {
  procedure: "self_employed_registration" | "employee_hiring" | "grant_application";
  procedureLabel: string;
  language: "es" | "gl";
  languageLabel: string;
  reference: string;
}

async function mockReviewerApi(page: Page, scenario: Scenario) {
  await page.unrouteAll({ behavior: "wait" });
  const caseDetail = {
    id: caseId,
    reference: scenario.reference,
    procedure_type: scenario.procedure,
    output_language: scenario.language,
    status: "needs_review",
    created_at: now,
    updated_at: now,
    source_messages: [{ id: "message-1", case_id: caseId, content: "Solicitud completamente sintética", is_synthetic: true, created_at: now }],
    documents: [],
  };
  await page.route("**/api/backend/cases**", async (route) => {
    const request = route.request();
    const pathname = new URL(request.url()).pathname;
    if (pathname === "/api/backend/cases" && request.method() === "POST") {
      const payload = request.postDataJSON();
      expect(payload.procedure_type).toBe(scenario.procedure);
      expect(payload.output_language).toBe(scenario.language);
      expect(payload.is_synthetic).toBe(true);
      return route.fulfill({ json: caseDetail, status: 201 });
    }
    if (pathname === `/api/backend/cases/${caseId}`) return route.fulfill({ json: caseDetail });
    if (pathname.endsWith("/analysis")) return route.fulfill({ json: {
      id: "analysis-1", case_id: caseId, procedure_type: scenario.procedure,
      procedure_reason: "Clasificación sintética", facts: [], assumptions: [],
      unresolved_questions: [], contradictions: [], requested_output_language: scenario.language,
      prompt_version: "intake-analysis-v1", model_run_id: "run-1", created_at: now,
    } });
    if (pathname.endsWith("/validation-result")) return route.fulfill({ json: {
      template_version: "deterministic-validation-v1", validation_completed_at: now,
      has_blocking_findings: false, checklist_results: [], findings: [],
    } });
    if (pathname.endsWith("/follow-up-draft")) return route.fulfill({ json: {
      id: "draft-1", case_id: caseId, language: scenario.language,
      model_text: "Texto sintético do modelo", reviewed_text: "Texto sintético do modelo",
      prompt_version: "follow-up-draft-v1", model_run_id: "run-2", version: 1,
      created_at: now, updated_at: now,
    } });
    if (pathname.endsWith("/review-decision")) return route.fulfill({
      status: 404,
      json: { error: { code: "review_decision_not_found", message: "Missing", issues: [] } },
    });
    if (pathname.endsWith("/timeline")) return route.fulfill({ json: { case_id: caseId, events: [] } });
    return route.fulfill({ status: 404, json: { error: { code: "not_found", message: "Missing", issues: [] } } });
  });
}

const scenarios: Scenario[] = [
  { procedure: "self_employed_registration", procedureLabel: "Alta de autónomo", language: "es", languageLabel: "Español", reference: "EC-AUTONOMO" },
  { procedure: "employee_hiring", procedureLabel: "Contratación de personal", language: "gl", languageLabel: "Galego", reference: "EC-CONTRATO" },
  { procedure: "grant_application", procedureLabel: "Solicitud de ayuda", language: "es", languageLabel: "Español", reference: "EC-AYUDA" },
];

test("completa y reabre los tres procedimientos en la misma interfaz", async ({ page }) => {
  for (const scenario of scenarios) {
    await mockReviewerApi(page, scenario);
    await page.goto("/cases/new");
    await page.getByLabel("Referencia").fill(scenario.reference);
    await page.getByLabel(scenario.procedureLabel).check();
    await page.getByLabel(scenario.languageLabel).check();
    await page.getByLabel("Mensaje fuente sintético").fill("Solicitud completamente sintética");
    const submit = page.getByRole("button", { name: "Crear expediente" });
    await submit.focus();
    await submit.press("Enter");

    await expect(page).toHaveURL(`/cases/${caseId}`);
    await expect(page.getByRole("heading", { name: scenario.reference })).toBeVisible();
    await expect(page.getByText(scenario.procedureLabel).first()).toBeVisible();
    await expect(page.getByText(scenario.languageLabel).first()).toBeVisible();
    await expect(page.getByRole("heading", { name: "Información fuente" })).toBeVisible();
    await expect(page.getByRole("heading", { name: "Análisis estructurado" })).toBeVisible();
    await expect(page.getByRole("heading", { name: "Validación independiente" })).toBeVisible();
    await expect(page.getByRole("heading", { name: "Salida revisada por una persona" })).toBeVisible();

    await page.reload();
    await expect(page.getByText("Texto original del modelo · inmutable")).toBeVisible();
  }
});
