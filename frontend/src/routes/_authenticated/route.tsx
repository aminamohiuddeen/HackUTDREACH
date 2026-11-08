import { createFileRoute, Outlet } from "@tanstack/react-router";
import { Loader2 } from "lucide-react";
import { ReachProvider } from "@/lib/reach/store";
import { AppShell } from "@/components/reach/app-shell";

// DEMO BYPASS — remove this whole block and restore the imports/gates below
// before final submission. See git history for the original.
const DEMO_ACCOUNT = { userId: "demo-user", role: "first_responder" as const };

export const Route = createFileRoute("/_authenticated")({
  ssr: false,
  // ORIGINAL beforeLoad:
  // beforeLoad: async () => {
  //   const { data, error } = await supabase.auth.getUser();
  //   if (error || !data.user) throw redirect({ to: "/auth", search: { reason: error ? "expired" : undefined }, replace: true });
  // },
  // ORIGINAL loader:
  // loader: async () => {
  //   try { return await getApprovedAccount(); }
  //   catch { throw redirect({ to: "/auth", search: { reason: "unapproved" }, replace: true }); }
  // },
  loader: () => DEMO_ACCOUNT,
  pendingMs: 0,
  pendingComponent: () => <div className="flex min-h-svh items-center justify-center gap-3 bg-background" role="status"><Loader2 className="h-5 w-5 text-primary motion-safe:animate-spin" />Verifying secure access…</div>,
  component: MissionLayout,
});

function MissionLayout() {
  const account = Route.useLoaderData();
  return <ReachProvider key={account.userId}><AppShell account={account}><Outlet /></AppShell></ReachProvider>;
}