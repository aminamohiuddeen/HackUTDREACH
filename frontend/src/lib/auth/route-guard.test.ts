import { describe, expect, it, vi } from "vitest";

const getUser = vi.hoisted(() => vi.fn());
const account = vi.hoisted(() => vi.fn());
vi.mock("@/integrations/supabase/client", () => ({ supabase: { auth: { getUser } } }));
vi.mock("./account.functions", () => ({ getApprovedAccount: account }));
vi.mock("@/components/reach/app-shell", () => ({ AppShell: () => null }));
import { Route } from "@/routes/_authenticated/route";

describe("protected REACH access", () => {
  it("redirects an unauthenticated visitor before rendering mission content", async () => {
    getUser.mockResolvedValue({ data: { user: null }, error: null });
    const guard = Route.options.beforeLoad;
    if (!guard) throw new Error("Missing dashboard guard");
    await expect(Reflect.apply(guard, null, [{}])).rejects.toMatchObject({ options: { to: "/auth", replace: true } });
  });
  it("allows a provider-verified identity through the session gate", async () => {
    getUser.mockResolvedValue({ data: { user: { id: "verified-user" } }, error: null });
    const guard = Route.options.beforeLoad;
    if (!guard) throw new Error("Missing dashboard guard");
    await expect(Reflect.apply(guard, null, [{}])).resolves.toBeUndefined();
  });
  it("denies mission access when server-side approval fails", async () => {
    account.mockRejectedValue(new Error("Not approved"));
    const loader = Route.options.loader;
    if (typeof loader !== "function") throw new Error("Missing approval loader");
    await expect(Reflect.apply(loader, null, [{}])).rejects.toMatchObject({ options: { to: "/auth", search: { reason: "unapproved" } } });
  });
});