import { useEffect, useState, type ReactNode } from "react";
import { Link, useNavigate, useRouterState } from "@tanstack/react-router";
import { useQueryClient } from "@tanstack/react-query";
import { Bot, FolderSearch, HeartPulse, LayoutGrid, ScanSearch, Siren, Sparkles, Radio, FlaskConical, LogOut, Loader2 } from "lucide-react";
import { Button } from "@/components/ui/button";
import { supabase } from "@/integrations/supabase/client";
import type { ReachRole } from "@/lib/auth/access";
import { toast } from "sonner";
import { cn } from "@/lib/utils";
import { useReach } from "@/lib/reach/store";
import { DEMO_MODE } from "@/lib/reach/api";
import { SCENARIOS } from "@/lib/reach/mock-data";
import type { ScenarioKey } from "@/lib/reach/types";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select";

const NAV = [
  { to: "/", label: "Mission Overview", icon: LayoutGrid },
  { to: "/respond", label: "Need Response", icon: Siren },
  { to: "/survivors", label: "Survivors", icon: HeartPulse },
  { to: "/robot", label: "Robot Monitor", icon: Bot },
  { to: "/cases", label: "Rescue Cases", icon: FolderSearch },
  { to: "/verify", label: "VERIFY Queue", icon: ScanSearch },
  { to: "/intelligence", label: "Mission Intelligence", icon: Sparkles },
] as const;

function Clock() {
  const [now, setNow] = useState<Date | null>(null);
  useEffect(() => {
    setNow(new Date());
    const id = setInterval(() => setNow(new Date()), 1000);
    return () => clearInterval(id);
  }, []);
  return <span className="font-mono text-sm tabular">{now ? now.toISOString().slice(11, 19) + "Z" : "--:--:--Z"}</span>;
}

export function AppShell({ children, account }: { children: ReactNode; account: { userId: string; role: ReachRole } }) {
  const queryClient = useQueryClient();
  const navigate = useNavigate();
  const [signingOut, setSigningOut] = useState(false);
  async function signOut() {
    setSigningOut(true);
    await queryClient.cancelQueries();
    queryClient.clear();
    const { error } = await supabase.auth.signOut();
    if (error) { toast.error("Could not sign out. Please try again."); setSigningOut(false); return; }
    await navigate({ to: "/auth", search: { reason: undefined }, replace: true });
  }
  const path = useRouterState({ select: (s) => s.location.pathname });
  const { cases, robots, scenario, dispatch } = useReach();
  const verifyCount = cases.filter((c) => c.status === "verify").length;
  const online = robots.filter((r) => r.connection !== "offline").length;

  return (
    <div className="min-h-screen">
      <aside className="fixed inset-y-0 left-0 z-20 flex w-60 flex-col border-r border-sidebar-border bg-sidebar">
        <div className="flex h-16 items-center gap-3 border-b border-sidebar-border px-5">
          <span className="flex h-8 w-8 items-center justify-center rounded-sm bg-primary text-primary-foreground">
            <Radio className="h-4 w-4" />
          </span>
          <div className="leading-tight">
            <div className="font-display text-lg font-bold tracking-[0.14em] text-sidebar-accent-foreground">REACH</div>
            <div className="font-mono text-xs uppercase tracking-[0.18em] text-sidebar-foreground/50">Search & Rescue Ops</div>
          </div>
        </div>
        <nav className="flex-1 space-y-px p-3" aria-label="Main">
          <div className="px-2.5 pt-2 pb-2 font-mono text-xs font-medium uppercase tracking-[0.2em] text-sidebar-foreground/40">Operations</div>
          {NAV.map((n) => {
            const active = n.to === "/" ? path === "/" : path.startsWith(n.to);
            return (
              <Link
                key={n.to}
                to={n.to}
                className={cn(
                  "group relative flex items-center gap-3 rounded-sm px-2.5 py-2 text-sm transition-colors",
                  active ? "bg-sidebar-accent font-medium text-sidebar-accent-foreground" : "text-sidebar-foreground/70 hover:bg-sidebar-accent/50 hover:text-sidebar-accent-foreground",
                )}
              >
                {active && <span className="absolute inset-y-1.5 left-0 w-0.5 rounded-full bg-primary" aria-hidden />}
                <n.icon className={cn("h-4 w-4", active ? "text-primary" : "text-sidebar-foreground/40 group-hover:text-sidebar-foreground/70")} />
                <span className="flex-1">{n.label}</span>
                {n.to === "/verify" && verifyCount > 0 && (
                  <span className="rounded-sm bg-warning px-1.5 font-mono text-xs font-semibold text-warning-foreground">{verifyCount}</span>
                )}
              </Link>
            );
          })}
        </nav>
        <div className="border-t border-sidebar-border p-4 font-mono text-xs uppercase leading-relaxed tracking-[0.14em] text-sidebar-foreground/35">
          Rescue · Evaluation · Assistance · Coordination · Hope
        </div>
      </aside>

      <div className="pl-60">
        <header className="sticky top-0 z-10 flex h-16 items-center gap-4 border-b border-border-strong bg-background/95 px-6 backdrop-blur">
          <div className="min-w-0">
            <div className="label-caps">Active mission</div>
            <div className="truncate font-display text-base font-semibold tracking-wide">OPERATION BRIGHTWATER <span className="hidden text-muted-foreground 2xl:inline">· Flood & collapse, Grid A1–F6</span></div>
          </div>
          <div className="hidden shrink-0 items-center gap-4 border-l pl-4 xl:flex">
            <div className="whitespace-nowrap">
              <div className="label-caps">Mission time</div>
              <Clock />
            </div>
            <div className="whitespace-nowrap">
              <div className="label-caps">Robots</div>
              <span className="flex items-center gap-1.5 font-mono text-sm"><span className="h-1.5 w-1.5 rounded-full bg-success pulse-dot" />{online}/{robots.length} linked</span>
            </div>
          </div>
          <div className="ml-auto flex items-center gap-3">
            {DEMO_MODE && (
            <div className="flex items-center gap-2">
              <FlaskConical className="h-3.5 w-3.5 text-subtle" />
              <Select value={scenario} onValueChange={(v) => dispatch({ type: "scenario", key: v as ScenarioKey })}>
                <SelectTrigger className="h-8 w-[200px] text-xs" aria-label="Simulated scenario">
                  <SelectValue />
                </SelectTrigger>
                <SelectContent>
                  {(Object.keys(SCENARIOS) as ScenarioKey[]).map((k, i) => (
                    <SelectItem key={k} value={k} className="text-xs">
                      {i + 1}. {SCENARIOS[k].label}
                    </SelectItem>
                  ))}
                </SelectContent>
              </Select>
            </div>
            )}
            {DEMO_MODE && (
              <span className="inline-flex items-center gap-1.5 whitespace-nowrap rounded-md border border-warning/40 bg-warning/10 px-2.5 py-1 text-xs font-semibold text-warning" title="Simulated data">
                <span className="h-1.5 w-1.5 rounded-full bg-warning" />
                DEMO MODE
              </span>
            )}
            <Button variant="ghost" size="icon" onClick={signOut} disabled={signingOut} aria-label="Sign out" title={`Sign out · ${account.role === "administrator" ? "Administrator" : "First Responder"}`}>
              {signingOut ? <Loader2 className="motion-safe:animate-spin" /> : <LogOut />}
            </Button>
          </div>
        </header>
        <main className="mx-auto max-w-[1440px] px-8 py-7">{children}</main>
      </div>
    </div>
  );
}
