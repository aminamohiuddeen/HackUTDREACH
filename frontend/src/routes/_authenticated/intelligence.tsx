import { useState } from "react";
import { createFileRoute, useNavigate } from "@tanstack/react-router";
import { toast } from "sonner";
import { CheckCircle2, CircleDashed, FileText, Loader2, MinusCircle, Play, RefreshCw, Sparkles, Wrench, AlertOctagon } from "lucide-react";
import { cn } from "@/lib/utils";
import { useCaseDetail, useReach } from "@/lib/reach/store";
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
      { name: "description", content: "AI-organized rescue reports, rationale, missing data and nearest relevant units for human decision. Powered by Nemotron." },
      { property: "og:title", content: "Mission Intelligence — REACH" },
      { property: "og:description", content: "AI-organized rescue reports for human decision support. Powered by Nemotron." },
    ],
  }),
  component: Intelligence,
});

const TOOL_ICON = { ok: CheckCircle2, partial: CircleDashed, skipped: MinusCircle };
const TOOL_CLS = { ok: "text-success", partial: "text-warning", skipped: "text-subtle" };

const TOOL_LABELS: Record<string, string> = {
  get_case_evidence: "Retrieving case data",
  search_protocol: "Searching triage protocols",
  get_sector_status: "Checking sector status",
  get_nearest_units: "Finding nearby units",
  create_incident_report: "Generating incident report",
  // Demo-mode seed names
  classify_detection: "Classifying detection",
  extract_needs: "Extracting survivor needs",
  query_nearby_units: "Finding nearby units",
  summarize_report: "Drafting incident report",
};

/** Splits "agent:tool_name()" into a readable agent label and step name. */
function parseTool(raw: string): { agent: string | null; name: string } {
  const cleaned = raw.replace(/\(\)$/, "").trim();
  const idx = cleaned.indexOf(":");
  return idx === -1 ? { agent: null, name: cleaned } : { agent: cleaned.slice(0, idx), name: cleaned.slice(idx + 1) };
}

/** Maps a backend tool name (e.g. "classifier:get_case_evidence") to a human-readable phrase. */
function formatToolName(tool: string): string {
  const { name } = parseTool(tool);
  const known = TOOL_LABELS[name];
  if (known) return known;
  const words = name.replace(/[_-]+/g, " ").trim();
  return words ? words.charAt(0).toUpperCase() + words.slice(1) : "Analysis step";
}

function formatAgent(tool: string): string | null {
  const { agent } = parseTool(tool);
  return agent ? `${agent.charAt(0).toUpperCase()}${agent.slice(1)} agent` : null;
}

/** Placeholder the adapter uses when an agent gave no reasoning; not useful to responders. */
const EMPTY_SUMMARY = "(no reasoning summary)";

function Intelligence() {
  const { cases, dispatch } = useReach();
  const { id } = Route.useSearch();
  const navigate = useNavigate({ from: "/intelligence" });
  const c = cases.find((x) => x.id === id) ?? cases[0];
  const [busy, setBusy] = useState<string | null>(null);
  useCaseDetail(c?.id);

  if (!c) {
    return (
      <div>
        <PageHeader title="Mission Intelligence" description="Powered by Nemotron. AI-organized rescue reports for operator review — the AI summarizes and retrieves context; it never selects, assigns, or dispatches units." />
        <Panel><p className="px-5 py-6 text-center text-sm text-muted-foreground">No active cases at this time.</p></Panel>
      </div>
    );
  }

  const hasRun = c.report.tools.length > 0;

  const analyze = async () => {
    setBusy(c.id);
    try {
      const report = await reachApi.analyzeCase(c.id, c.report);
      dispatch({ type: "report", caseId: c.id, report });
      toast.success("Analysis complete", { description: `Report for ${c.id} is ready. No units were assigned.` });
    } catch (e) {
      toast.error("Analysis failed", { description: e instanceof Error ? e.message : String(e) });
    } finally {
      setBusy(null);
    }
  };

  return (
    <div>
      <PageHeader title="Mission Intelligence" description="Powered by Nemotron. AI-organized rescue reports for operator review — the AI summarizes and retrieves context; it never selects, assigns, or dispatches units.">
        <Button onClick={analyze} disabled={busy !== null} className="gap-2">
          {busy ? <Loader2 className="h-4 w-4 animate-spin" /> : hasRun ? <RefreshCw className="h-4 w-4" /> : <Play className="h-4 w-4" />}
          {busy ? "Analyzing…" : hasRun ? "Re-run Analysis" : "Run Analysis"}
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
              <span className="inline-flex items-center gap-1.5 text-xs text-subtle"><Sparkles className="h-3.5 w-3.5" />Powered by Nemotron</span>
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
            <PanelHeader title="AI reasoning steps" icon={Wrench} meta={c.report.tools.length ? `${c.report.tools.length} steps` : undefined} />
            <ol>
              {c.report.tools.length === 0 && !busy && (
                <li className="flex flex-col items-center gap-3 px-5 py-10 text-center">
                  <span className="flex h-10 w-10 items-center justify-center rounded-full bg-muted">
                    <Sparkles className="h-5 w-5 text-subtle" />
                  </span>
                  <div>
                    <p className="text-sm font-medium">No analysis yet</p>
                    <p className="mt-1 text-sm text-muted-foreground">Run analysis to see the AI's reasoning and tool execution.</p>
                  </div>
                </li>
              )}
              {c.report.tools.map((t, i) => {
                const Icon = TOOL_ICON[t.status] ?? CircleDashed;
                const agent = formatAgent(t.tool);
                const summary = t.summary && t.summary !== EMPTY_SUMMARY ? t.summary : null;
                return (
                  <li key={i} className="fade-in-up flex items-start gap-4 border-b px-5 py-4 transition-colors last:border-0 hover:bg-muted/30">
                    <span className="mt-0.5 w-6 shrink-0 text-right font-mono text-xs text-subtle">{String(i + 1).padStart(2, "0")}</span>
                    <Icon className={cn("mt-0.5 h-4 w-4 shrink-0", TOOL_CLS[t.status])} />
                    <div className="flex min-w-0 flex-1 flex-col gap-1.5">
                      <div className="flex items-start justify-between gap-4">
                        <div className="flex min-w-0 flex-wrap items-center gap-2">
                          <span className="wrap-break-word text-sm font-medium">{formatToolName(t.tool)}</span>
                          {agent && <span className="rounded-sm border px-1.5 py-px text-[11px] text-subtle">{agent}</span>}
                        </div>
                        <span className="shrink-0 font-mono text-xs text-subtle">{fmtTime(t.at)}</span>
                      </div>
                      {summary && <p className="whitespace-normal wrap-break-word text-sm leading-relaxed text-muted-foreground">{summary}</p>}
                    </div>
                  </li>
                );
              })}
              {busy && (
                <li className="flex items-center gap-4 border-t px-5 py-4 text-sm text-muted-foreground first:border-0">
                  <span className="w-6 shrink-0" />
                  <Loader2 className="h-4 w-4 shrink-0 animate-spin text-primary" />
                  Analyzing case with AI agents…
                </li>
              )}
            </ol>
          </Panel>
        </div>

        <Panel className="h-fit xl:sticky xl:top-24">
          <PanelHeader title="Suggested response units">
            <span className="rounded-sm border border-warning/40 bg-warning/10 px-1.5 py-px text-[11px] font-medium text-warning">Suggestion only</span>
          </PanelHeader>
          <div className="p-5">
            <p className="mb-3 text-xs leading-relaxed text-muted-foreground">
              The AI lists nearby units for reference. It does not assign or dispatch them — the operator decides who to send.
            </p>
            <NearestUnits units={c.report.nearestUnits} />
          </div>
        </Panel>
      </div>
    </div>
  );
}
