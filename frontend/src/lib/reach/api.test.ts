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
    await expect(reachApi.getCases()).rejects.toThrow("mapping pending");
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