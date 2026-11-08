import { useState } from "react";
import { createFileRoute, useNavigate } from "@tanstack/react-router";
import { toast } from "sonner";
import { CheckCircle2, CircleDashed, FileText, Loader2, MinusCircle, RefreshCw, Sparkles, Wrench, AlertOctagon } from "lucide-react";
import { cn } from "@/lib/utils";
import { useReach } from "@/lib/reach/store";
import { reachApi } from "@/lib/reach/api";
import { fmtTime } from "@/lib/reach/format";
import { Button } from "@/components/ui/button";
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs";
import { ClassificationBadge, ConfidenceDisplay, EnvWarning, Field, NearestUnits, PageHeader, Panel, PanelHeader, ScoreBadge, StatusBadge } from "@/components/reach/primitives";
import { Questionnaire, SensorTable } from "@/components/reach/case-detail";

export const Route = createFileRoute("/_authenticated/intelligence")({
  validateSearch: (s: Record<string, unknown>): { id?: string | undefined } => ({ id: typeof s["id"] === "string" ? s["id"] : undefined }),
  head: () => ({
    meta: [
      { property: "og:type", content: "website" },
      { name: "twitter:card", content: "summary_large_image" },
      { title: "Mission Intelligence — REACH" },
      { name: "description", content: "Nemotron-organized rescue reports, rationale, missing data and nearest relevant units for human decision." },
      { property: "og:title", content: "Mission Intelligence — REACH" },
      { property: "og:description", content: "Nemotron-organized rescue reports for human decision support." },
    ],
  }),
  component: Intelligence,
});

const TOOL_ICON = { ok: CheckCircle2, partial: CircleDashed, skipped: MinusCircle };
const TOOL_CLS = { ok: "text-success", partial: "text-warning", skipped: "text-subtle" };

function Intelligence() {
  const { cases, dispatch } = useReach();
  const { id } = Route.useSearch();
  const navigate = useNavigate({ from: "/intelligence" });
  const c = cases.find((x) => x.id === id) ?? cases[0];
  const [busy, setBusy] = useState<string | null>(null);

  if (!c) {
    return (
      <div>
        <PageHeader title="Nemotron Mission Intelligence" description="AI-organized rescue reports for operator review. Nemotron summarizes and retrieves context; it never selects, assigns, or dispatches units." />
        <Panel><p className="px-5 py-6 text-center text-sm text-muted-foreground">No cases loaded yet.</p></Panel>
      </div>
    );
  }

  const analyze = async () => {
    setBusy(c.id);
    try {
      const report = await reachApi.analyzeCase(c.id, c.report);
      dispatch({ type: "report", caseId: c.id, report });
      toast.success("Analysis complete", { description: `${c.id} report regenerated. No units were assigned.` });
    } catch (e) {
      toast.error("Analysis failed", { description: e instanceof Error ? e.message : String(e) });
    } finally {
      setBusy(null);
    }
  };

  return (
    <div>
      <PageHeader title="Nemotron Mission Intelligence" description="AI-organized rescue reports for operator review. Nemotron summarizes and retrieves context; it never selects, assigns, or dispatches units.">
        <Button onClick={analyze} disabled={busy !== null} className="gap-2">
          {busy ? <Loader2 className="h-4 w-4 animate-spin" /> : <RefreshCw className="h-4 w-4" />}
          {busy ? "Analyzing…" : "Re-run analysis"}
        </Button>
      </PageHeader>

      <div className="mb-5 flex gap-2 overflow-x-auto pb-1">
        {cases.map((x) => (
          <button key={x.id} onClick={() => navigate({ search: { id: x.id } })} aria-pressed={x.id === c.id}
            className={cn("shrink-0 rounded-lg border bg-card px-3 py-2 text-left transition-all hover:-translate-y-px hover:border-border-strong hover:shadow-sm", x.id === c.id && "border-primary bg-primary/6 ring-1 ring-primary/40")}>
            <div className="font-mono text-xs font-medium">{x.id}</div>
            <div className="mt-0.5 text-xs text-subtle">{x.sectorId} · {x.status === "verify" ? "VERIFY" : x.status.replace("_", " ")}</div>
          </button>
        ))}
      </div>

      <div className="grid gap-6 xl:grid-cols-[1fr_400px]">
        <div className="space-y-6">
          <Panel>
            <PanelHeader title="Incident report" icon={FileText} meta={`generated ${fmtTime(c.report.generatedAt)}`}>
              <span className="inline-flex items-center gap-1.5 text-xs text-subtle"><Sparkles className="h-3.5 w-3.5" />NVIDIA Nemotron</span>
            </PanelHeader>
            <div className={cn("p-5 transition-opacity", busy && "opacity-50")}>
              <p className="text-[15px] leading-relaxed">{c.report.incidentReport}</p>
              <div className="mt-5 grid gap-5 border-t pt-5 sm:grid-cols-2 lg:grid-cols-4">
                <Field label="Classification"><ClassificationBadge value={c.classification} /></Field>
                <Field label="Status"><div className="flex flex-wrap gap-1"><StatusBadge value={c.status} />{c.environmentalWarning && <EnvWarning text={c.environmentalWarning} />}</div></Field>
                <Field label="Integrity / health"><div className="flex flex-wrap gap-1"><ScoreBadge label="Environment" value={c.environmentScore} /><ScoreBadge label="Health" value={c.healthScore} /></div></Field>
                <Field label="Confidence"><ConfidenceDisplay value={c.confidence} compact /></Field>
              </div>
            </div>
          </Panel>

          <Panel>
            <Tabs defaultValue="rationale">
              <div className="border-b px-5 pt-3">
                <TabsList className="bg-transparent p-0">
                  {([["rationale", "Rationale"], ["needs", "Needs"], ["missing", `Missing data (${c.report.missingData.length})`], ["evidence", "Evidence"]] as const).map(([v, l]) => (
                    <TabsTrigger key={v} value={v} className="rounded-none border-b-2 border-transparent px-3 pb-2.5 data-[state=active]:border-primary data-[state=active]:bg-transparent data-[state=active]:shadow-none">{l}</TabsTrigger>
                  ))}
                </TabsList>
              </div>
              <div className="p-5">
                <TabsContent value="rationale" className="mt-0">
                  <p className="text-sm leading-relaxed text-muted-foreground">{c.report.rationale}</p>
                  <div className="mt-4"><div className="label-caps mb-1.5">Supporting evidence</div><ConfidenceDisplay value={c.confidence} /></div>
                </TabsContent>
                <TabsContent value="needs" className="mt-0">
                  {c.needs.length ? <ul className="space-y-2">{c.needs.map((n) => <li key={n} className="flex items-center gap-2 text-sm"><span className="h-1.5 w-1.5 rounded-full bg-primary" />{n}</li>)}</ul> : <p className="text-sm text-subtle">No needs reported.</p>}
                </TabsContent>
                <TabsContent value="missing" className="mt-0">
                  <ul className="space-y-2">
                    {c.report.missingData.map((m) => <li key={m} className="flex items-center gap-2 text-sm"><AlertOctagon className="h-3.5 w-3.5 text-warning" />{m}</li>)}
                  </ul>
                </TabsContent>
                <TabsContent value="evidence" className="mt-0 grid gap-5 lg:grid-cols-2">
                  <SensorTable s={c.sensors} />
                  <Questionnaire c={c} />
                </TabsContent>
              </div>
            </Tabs>
          </Panel>

          <Panel>
            <PanelHeader title="Tool execution timeline" icon={Wrench} meta={`${c.report.tools.length} calls`} />
            <ol className="divide-y">
              {c.report.tools.length === 0 && !busy && (
                <li className="px-5 py-6 text-center text-sm text-muted-foreground">
                  No analysis yet — click "Re-run analysis" to invoke Nemotron.
                </li>
              )}
              {c.report.tools.map((t, i) => {
                const Icon = TOOL_ICON[t.status];
                return (
                  <li key={i} className="flex items-center gap-4 px-5 py-3 fade-in-up">
                    <span className="w-6 font-mono text-xs text-subtle">{String(i + 1).padStart(2, "0")}</span>
                    <Icon className={cn("h-4 w-4", TOOL_CLS[t.status])} />
                    <span className="w-44 font-mono text-sm">{t.tool}()</span>
                    <span className="flex-1 text-sm text-muted-foreground">{t.summary}</span>
                    <span className="font-mono text-xs text-subtle">{fmtTime(t.at)}</span>
                  </li>
                );
              })}
              {busy && (
                <li className="flex items-center gap-4 px-5 py-3 text-sm text-muted-foreground"><span className="w-6" /><Loader2 className="h-4 w-4 animate-spin text-primary" />Running POST /api/cases/{c.id}/analyze…</li>
              )}
            </ol>
          </Panel>
        </div>

        <Panel className="h-fit xl:sticky xl:top-24">
          <PanelHeader title="Response units" />
          <div className="p-5"><NearestUnits units={c.report.nearestUnits} /></div>
        </Panel>
      </div>
    </div>
  );
}
