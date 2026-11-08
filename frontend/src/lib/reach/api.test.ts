import { beforeEach, describe, expect, it, vi } from "vitest";

const session = vi.hoisted(() => vi.fn());
vi.mock("@/integrations/supabase/client", () => ({ supabase: { auth: { getSession: session } } }));

describe("future FastAPI authenticated requests", () => {
  beforeEach(() => { vi.resetModules(); vi.unstubAllEnvs(); vi.unstubAllGlobals(); });
  it("attaches the provider access token as a Bearer header", async () => {
    vi.stubEnv("VITE_REACH_API_BASE", "https://fastapi.example.test");
    session.mockResolvedValue({ data: { session: { access_token: "unit-test-token" } }, error: null });
    const fetcher = vi.fn().mockResolvedValue({ ok: true, json: async () => [] }); vi.stubGlobal("fetch", fetcher);
    const { reachApi } = await import("./api");
    await expect(reachApi.getCases()).resolves.toEqual([]);
    expect(fetcher).toHaveBeenCalledOnce();
    expect(new Headers(fetcher.mock.calls[0]?.[1]?.headers).get("Authorization")).toBe("Bearer unit-test-token");
  });
  it("does not send a future FastAPI request without a session", async () => {
    vi.stubEnv("VITE_REACH_API_BASE", "https://fastapi.example.test");
    session.mockResolvedValue({ data: { session: null }, error: null });
    const fetcher = vi.fn(); vi.stubGlobal("fetch", fetcher);
    const { reachApi } = await import("./api");
    await expect(reachApi.getCases()).rejects.toThrow("session has expired");
    expect(fetcher).not.toHaveBeenCalled();
  });
});
describe("questionnaire from case detail", () => {
  beforeEach(() => { vi.resetModules(); vi.unstubAllEnvs(); vi.unstubAllGlobals(); });
  const detail = (surveys: unknown[]) => {
    vi.stubEnv("VITE_REACH_API_BASE", "https://fastapi.example.test");
    session.mockResolvedValue({ data: { session: { access_token: "t" } }, error: null });
    vi.stubGlobal("fetch", vi.fn().mockResolvedValue({ ok: true, json: async () => ({ telemetry: [], surveys }) }));
  };
  const answers = { injured: "yes", trapped: "yes", breathing_difficulty: "no", others_present: "yes", immediate_help: "yes" };

  it("shows the pod's own answers next to the yes/no answers", async () => {
    detail([{ id: 1, timestamp: "2026-11-08T20:00:57Z", answers,
      details: { people_count: 5, can_move: false, needs_water_or_medication: true } }]);
    const { reachApi } = await import("./api");
    const d = await reachApi.getCaseDetail("RC-1107-001");
    const q = d.questionnaire!;
    expect(q[1]!.answer).toBe("yes · can't move on their own");
    expect(q[3]!.answer).toBe("yes · 5 people with them");
    expect(q[4]!.question).toBe("Needs water or medication?");
    expect(d.questionnaireMeta).toEqual({ receivedAt: "2026-11-08T20:00:57Z", total: 1 });
  });

  it("keeps plain answers when a survey has no details", async () => {
    detail([{ id: 1, timestamp: "2026-11-08T20:00:57Z", answers }]);
    const { reachApi } = await import("./api");
    const q = (await reachApi.getCaseDetail("RC-1107-001")).questionnaire!;
    expect(q[3]!.answer).toBe("yes");
    expect(q[4]!.question).toBe("Need immediate help?");
  });
});
