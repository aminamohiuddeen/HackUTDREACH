import { createFileRoute, Link, useNavigate } from "@tanstack/react-router";
import { ArrowLeft, ChevronRight, HeartPulse } from "lucide-react";
import { useReach } from "@/lib/reach/store";
import { hasValidSurvey } from "@/lib/reach/classify";
import { fmtTime } from "@/lib/reach/format";
import { EmptyState, PageHeader, Panel, PanelHeader, ScoreBadge } from "@/components/reach/primitives";
import { CaseDetail } from "@/components/reach/case-detail";

export const Route = createFileRoute("/_authenticated/survivors")({
  validateSearch: (s: Record<string, unknown>): { id?: string | undefined } => ({ id: typeof s["id"] === "string" ? s["id"] : undefined }),
  head: () => ({
    meta: [
      { property: "og:type", content: "website" },
      { name: "twitter:card", content: "summary_large_image" },
      { title: "Confirmed Survivors — REACH" },
      { name: "description", content: "Survey-confirmed survivors with live condition readings." },
      { property: "og:title", content: "Confirmed Survivors — REACH" },
      { property: "og:description", content: "Survey-confirmed survivors with live condition readings." },
    ],
  }),
  component: Survivors,
});

function Survivors() {
  const { cases } = useReach();
  const { id } = Route.useSearch();
  const navigate = useNavigate({ from: "/survivors" });
  const list = cases.filter((c) => c.classification === "likely_person" && hasValidSurvey(c.questionnaire));
  // Look up across all cases so the detail view stays open after the case is closed.
  const open = id ? cases.find((c) => c.id === id) : undefined;

  if (open) {
    return (
      <div className="space-y-6">
        <PageHeader title={open.id}>
          <Link to="/survivors" className="inline-flex items-center gap-1.5 rounded-md border px-3 py-2 text-xs font-semibold transition-colors hover:bg-panel-raised/60">
            <ArrowLeft className="h-3.5 w-3.5" /> Back to survivors
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
      <PageHeader title="Confirmed Survivors" />
      <Panel>
        <PanelHeader title="Survivor condition" icon={HeartPulse} meta={`${list.length} confirmed`} />
        {list.length === 0 ? (
          <EmptyState icon={HeartPulse} title="No confirmed survivors yet" message="Survivors appear here once a detection is classified as a likely person and the OLED questionnaire is answered." />
        ) : (
          <ol className="divide-y">
            {list.map((c) => {
              return (
                <li key={c.id}>
                  <button
                    onClick={() => navigate({ search: { id: c.id } })}
                    className="flex w-full flex-col gap-3 px-5 py-4 text-left transition-colors hover:bg-panel-raised/50 sm:flex-row sm:items-center"
                  >
                    <div className="min-w-0 flex-1">
                      <div className="flex flex-wrap items-center gap-2">
                        <span className="font-mono text-sm font-semibold">{c.id}</span>
                        <ScoreBadge label="Health" value={c.healthScore} />
                        <span className="text-xs text-muted-foreground">Sector <span className="font-mono text-foreground">{c.sectorId}</span></span>
                      </div>
                      <div className="mt-1 font-mono text-xs text-subtle">Detected {fmtTime(c.detectedAt)}</div>
                    </div>
                    <div className="flex shrink-0 items-center gap-6">
                      <ChevronRight className="h-4 w-4 text-subtle" />
                    </div>
                  </button>
                </li>
              );
            })}
          </ol>
        )}
      </Panel>
    </div>
  );
}
