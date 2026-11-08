import { createFileRoute, Outlet, redirect } from "@tanstack/react-router";
import { Loader2 } from "lucide-react";
import { supabase } from "@/integrations/supabase/client";
import { getApprovedAccount } from "@/lib/auth/account.functions";
import { ReachProvider } from "@/lib/reach/store";
import { AppShell } from "@/components/reach/app-shell";

export const Route = createFileRoute("/_authenticated")({
  ssr: false,
  beforeLoad: async () => {
    const { data, error } = await supabase.auth.getUser();
    if (error || !data.user) throw redirect({ to: "/auth", search: { reason: error ? "expired" : undefined }, replace: true });
  },
  loader: async () => {
    try { return await getApprovedAccount(); }
    catch { throw redirect({ to: "/auth", search: { reason: "unapproved" }, replace: true }); }
  },
  pendingMs: 0,
  pendingComponent: () => <div className="flex min-h-svh items-center justify-center gap-3 bg-background" role="status"><Loader2 className="h-5 w-5 text-primary motion-safe:animate-spin" />Verifying secure access…</div>,
  component: MissionLayout,
});

function MissionLayout() {
  const account = Route.useLoaderData();
  return <ReachProvider key={account.userId}><AppShell account={account}><Outlet /></AppShell></ReachProvider>;
}