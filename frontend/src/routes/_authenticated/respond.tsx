import { createFileRoute, Link, useNavigate } from "@tanstack/react-router";
import { ArrowLeft, ChevronRight, MapPin } from "lucide-react";
import { cn } from "@/lib/utils";
import { useCaseDetail, useReach } from "@/lib/reach/store";
import { needsResponse } from "@/lib/reach/priority";
import { fmtCoord } from "@/lib/reach/format";
import { EmptyState, EnvWarning, PageHeader, Panel, PanelHeader, ScoreBadge, StatusBadge } from "@/components/reach/primitives";
import { CaseDetail } from "@/components/reach/case-detail";
import { AlertTriangle } from "lucide-react";

export const Route = createFileRoute("/_authenticated/respond")({
  validateSearch: (s: Record<string, unknown>): { id?: string | undefined } => ({ id: typeof s["id"] === "string" ? s["id"] : undefined }),
  head: () => ({
    meta: [
      { property: "og:type", content: "website" },
      { name: "twitter:card", content: "summary_large_image" },
      { title: "Need Response Now — REACH" },
      { name: "description", content: "Cases that need a human response decision, ranked by urgency." },
      { property: "og:title", content: "Need Response Now — REACH" },
      { property: "og:description", content: "Cases that need a human response decision, ranked by urgency." },
    ],
  }),
  component: Respond,
});

function Respond() {
  const { cases } = useReach();
  const { id } = Route.useSearch();
  useCaseDetail(id);
  const navigate = useNavigate({ from: "/respond" });
  const list = needsResponse(cases);
  // Look up across all cases so the detail view stays open after the case is closed.
  const open = id ? cases.find((c) => c.id === id) : undefined;

  if (open) {
    return (
      <div className="space-y-6">
        <PageHeader title={open.id}>
          <Link to="/respond" className="inline-flex items-center gap-1.5 rounded-md border px-3 py-2 text-xs font-semibold transition-colors hover:bg-panel-raised/60">
            <ArrowLeft className="h-3.5 w-3.5" /> Back to response board
          </Link>
        </PageHeader>
        <Panel className="p-5">
          <CaseDetail c={open} bare />
        </Panel>
      </div>
    );
  }

  return (
    <div className="space-y-6">
      <PageHeader title="Need Response Now" />
      <Panel>
        <PanelHeader title="Response board" icon={AlertTriangle} meta={`${list.length} cases · ranked by urgency`} />
        {list.length === 0 ? (
          <EmptyState icon={AlertTriangle} title="Nothing needs a response" message="No ranked survivors or pending verifications right now. New detections will appear here as robots report in." />
        ) : (
          <ol className="divide-y">
            {list.map((c, i) => (
              <li key={c.id}>
                <button
                  onClick={() => navigate({ search: { id: c.id } })}
                  className="flex w-full items-center gap-4 px-5 py-4 text-left transition-colors hover:bg-panel-raised/50"
                >
                  <span className={cn(
                    "flex h-9 w-9 shrink-0 items-center justify-center rounded-sm border font-display text-lg font-bold",
                    c.status === "verify" ? "border-warning/40 bg-warning/10 text-warning" : "border-critical/35 bg-critical/8 text-critical",
                  )}>
                    {String(i + 1).padStart(2, "0")}
                  </span>
                  <div className="min-w-0 flex-1">
                    <div className="flex flex-wrap items-center gap-2">
                      <span className="font-mono text-sm font-semibold">{c.id}</span>
                      <StatusBadge value={c.status} />
                      <ScoreBadge label="Environment" value={c.environmentScore} />
                      <ScoreBadge label="Health" value={c.healthScore} />
                      {c.environmentalWarning && <EnvWarning text={c.environmentalWarning} />}
                    </div>
                    <div className="mt-1 flex items-center gap-1.5 text-xs text-muted-foreground">
                      <MapPin className="h-3 w-3" />
                      Sector <span className="font-mono text-foreground">{c.sectorId}</span> · <span className="capitalize">{c.zone}</span> · <span className="font-mono">{fmtCoord(c.lat, c.lon)}</span>
                    </div>
                  </div>
                  <ChevronRight className="h-4 w-4 shrink-0 text-subtle" />
                </button>
              </li>
            ))}
          </ol>
        )}
      </Panel>
    </div>
  );
}
