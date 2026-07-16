import { describe, expect, it, vi } from "vitest";

import {
  ApiError,
  analyzeCase,
  createCase,
  decideCase,
  generateDraft,
  getAnalysis,
  getCase,
  getDecision,
  getDraft,
  getTimeline,
  getValidation,
  listCases,
  updateDraft,
  validateCase,
} from "@/lib/api";

const jsonResponse = (body: unknown, status = 200) =>
  new Response(JSON.stringify(body), { status, headers: { "Content-Type": "application/json" } });

describe("typed API client", () => {
  it("maps every reviewer operation to the same-origin proxy", async () => {
    const fetchMock = vi
      .spyOn(globalThis, "fetch")
      .mockImplementation(async () => jsonResponse({ ok: true }));
    const input = {
      reference: "EC-1",
      procedure_type: "grant_application" as const,
      output_language: "es" as const,
      is_synthetic: true as const,
      source_messages: [{ content: "Sintético", is_synthetic: true as const }],
      documents: [],
    };
    await listCases();
    await createCase(input);
    await getCase("case-1");
    await getAnalysis("case-1");
    await analyzeCase("case-1");
    await getValidation("case-1");
    await validateCase("case-1");
    await getDraft("case-1");
    await generateDraft("case-1");
    await updateDraft("case-1", "Revisado", 2);
    await getDecision("case-1");
    await decideCase("case-1", "rejected", "Ana", "Razón");
    await getTimeline("case-1");

    const calls = fetchMock.mock.calls;
    expect(calls).toHaveLength(13);
    expect(calls.every(([url]) => String(url).startsWith("/api/backend/cases"))).toBe(true);
    expect(calls.some(([url]) => String(url).includes("openai"))).toBe(false);
    expect(calls[1]?.[1]?.method).toBe("POST");
    expect(calls[9]?.[1]?.method).toBe("PATCH");
    expect(JSON.parse(String(calls[11]?.[1]?.body))).toEqual({
      decision: "rejected",
      reason: "Razón",
      actor: { label: "Ana" },
    });
  });

  it("decodes typed error envelopes", async () => {
    vi.spyOn(globalThis, "fetch").mockResolvedValue(
      jsonResponse(
        { error: { code: "follow_up_version_conflict", message: "The draft is stale.", issues: [] } },
        409,
      ),
    );
    await expect(updateDraft("case-1", "Texto", 1)).rejects.toMatchObject({
      status: 409,
      code: "follow_up_version_conflict",
      message: "The draft is stale.",
    });
  });

  it("normalizes a non-API proxy failure", async () => {
    vi.spyOn(globalThis, "fetch").mockResolvedValue(new Response("gateway", { status: 502 }));
    const error = await getCase("case-1").catch((caught: unknown) => caught);
    expect(error).toBeInstanceOf(ApiError);
    expect(error).toMatchObject({ code: "unexpected_error", status: 502 });
  });
});
