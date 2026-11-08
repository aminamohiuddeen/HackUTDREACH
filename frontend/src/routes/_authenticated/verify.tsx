import { useState } from "react";
import { createFileRoute } from "@tanstack/react-router";
import { toast } from "sonner";
import { AlertOctagon, CheckCircle2, Clock, Info, MapPin, Radar, Ruler, ScanSearch, UserCheck, Wind, XCircle, MessageSquareOff, MessageSquareText } from "lucide-react";
import { cn } from "@/lib/utils";
import { useReach } from "@/lib/reach/store";
import { fmtCoord, fmtTime } from "@/lib/reach/format";
import { hasValidSurvey } from "@/lib/reach/classify";
import type { RescueCase, VerificationOutcome } from "@/lib/reach/types";
import { Button } from "@/components/ui/button";
import { Textarea } from "@/components/ui/textarea";
import { ClassificationBadge, Disclosure, PageHeader, Panel, PanelHeader, ProvenanceTag, StatusBadge, Timeline, VerificationBadge } from "@/components/reach/primitives";

export const Route = createFileRoute("/_authenticated/verify")({
  head: () => ({
    meta: [
      { property: "og:type", content: "website" },
      { name: "twitter:card", content: "summary_large_image" },
      { title: "VERIFY Queue — REACH" },
      { name: "description", content: "Human verification queue for ambiguous possible-person detections." },
      { property: "og:title", content: "VERIFY Queue — REACH" },
      { property: "og:description", content: "Human verification queue for ambiguous possible-person detections." },
    ],
  }),
  component: VerifyQueue,
});

/** Cases that entered VERIFY stay in this queue (with their outcome) — never auto-closed. */
function VerifyQueue() {
  const { cases, sectors } = useReach();
  const queue = cases.filter((c) => c.verification !== null);
  const [id, setId] = useState(queue.find((c) => c.status === "verify")?.id ?? queue[0]?.id);
  const c = queue.find((x) => x.id === id);
  const open = queue.filter((x) => x.status === "verify").length;

  return (
    <div>
      <PageHeader title="VERIFY Queue" description="Ambiguous detections needing human investigation. Cases are never auto-closed.">
        <div className="flex items-center gap-2 rounded-lg border border-warning/35 bg-warning/8 px-3 py-2">
          <ScanSearch className="h-4 w-4 text-warning" />
          <span className="font-mono text-sm font-semibold text-warning">{open}</span>
          <span className="text-xs text-muted-foreground">awaiting decision</span>
        </div>
      </PageHeader>

      <div className="grid gap-6 xl:grid-cols-[300px_1fr]">
        <div className="space-y-2">
          {queue.map((x) => (
            <button key={x.id} onClick={() => setId(x.id)} aria-pressed={x.id === id}
              className={cn("panel panel-hover w-full p-4 text-left", x.id === id && "border-warning/60 ring-1 ring-warning/40")}>
              <div className="flex items-center justify-between">
                <span className="font-mono text-sm font-medium">{x.id}</span>
                <span className="font-mono text-xs text-subtle">{fmtTime(x.detectedAt)}</span>
              </div>
              <div className="mt-1 text-xs text-muted-foreground">Sector <span className="font-mono">{x.sectorId}</span> · <span className="capitalize">{x.zone}</span></div>
              <div className="mt-2.5 flex flex-wrap gap-1.5">
                <VerificationBadge value={x.verification!} />
              </div>
            </button>
          ))}
        </div>
        {c && <VerifyDetail key={c.id} c={c} sectorCoverage={sectors.find((s) => s.id === c.sectorId)?.coverage ?? "unsearched"} />}
      </div>
    </div>
  );
}

type TimelineFilterKey = "all" | "human" | "robot" | "nemotron";
const TIMELINE_FILTERS: { key: TimelineFilterKey; label: string; match: (a: string) => boolean }[] = [
  { key: "all", label: "All", match: () => true },
  { key: "human", label: "Human decisions", match: (a) => a === "operator" },
  { key: "robot", label: "Robot", match: (a) => a === "robot" },
  { key: "nemotron", label: "Nemotron", match: (a) => a === "nemotron" || a === "system" },
];

function VerifyDetail({ c, sectorCoverage }: { c: RescueCase; sectorCoverage: string }) {
  const { dispatch } = useReach();
  const [note, setNote] = useState("");
  const s = c.sensors;
  const survey = hasValidSurvey(c.questionnaire);
  const missing = c.report.missingData;
  const [filter, setFilter] = useState<TimelineFilterKey>("all");
  const matcher = TIMELINE_FILTERS.find((f) => f.key === filter)!.match;
  const shownEvents = c.events.filter((e) => matcher(e.actor));

  const record = (outcome: Exclude<VerificationOutcome, "pending">) => {
    dispatch({ type: "verify", caseId: c.id, outcome, note: note.trim() });
    setNote("");
    toast.success(
      outcome === "ruled_out" ? "Detection ruled out" : outcome === "person_confirmed" ? "Person confirmed" : "Kept in verification",
      { description: outcome === "ruled_out" ? `Sector ${c.sectorId} coverage unchanged (${sectorCoverage}).` : `${c.id} decision logged to timeline.` },
    );
  };

  return (
    <div className="grid gap-6 2xl:grid-cols-[1fr_380px]">
      <div className="space-y-6">
        <Panel>
          <div className="flex flex-wrap items-start justify-between gap-4 border-b px-5 py-4">
            <div>
              <div className="flex items-center gap-2">
                <span className="font-mono text-lg font-semibold">{c.id}</span>
                <ClassificationBadge value={c.classification} />
                <StatusBadge value={c.status} />
              </div>
              <div className="mt-1.5 flex items-center gap-1.5 text-sm text-muted-foreground">
                <MapPin className="h-3.5 w-3.5" />
                <span className="font-mono text-xs">{fmtCoord(c.lat, c.lon)}</span>
                <span className="text-subtle">·</span> Sector <span className="font-mono">{c.sectorId}</span>
                <span className="text-subtle">·</span> <span className="rounded-sm border px-1 font-mono text-xs uppercase">{c.locationSource}</span>
              </div>
            </div>
            <span className="font-mono text-xs text-subtle">Confidence: {c.confidence.label}</span>
          </div>

          <div className="grid gap-px bg-border sm:grid-cols-2 lg:grid-cols-4">
            <Evidence icon={Radar} label="Infrared" value={s.irTriggered.value === null ? null : s.irTriggered.value ? "Triggered" : "Not triggered"} src={s.irTriggered.source} tone={s.irTriggered.value ? "warning" : undefined} />
            <Evidence icon={Wind} label="Motion" value={s.motionDetected.value === null ? null : s.motionDetected.value ? "Detected" : "None"} src={s.motionDetected.source} tone={s.motionDetected.value ? "warning" : undefined} />
            <Evidence icon={Ruler} label="Anomaly area" value={s.anomalyAreaCm2.value !== null ? `${s.anomalyAreaCm2.value} cm²` : null} src={s.anomalyAreaCm2.source} />
            <Evidence icon={MapPin} label="Surrounding zone" value={c.zone} capitalize src="sensor" hideSrc />
          </div>

          <div className="grid gap-6 p-5 lg:grid-cols-2">
            <Disclosure label="Why this remains uncertain" meta={`${c.uncertaintyReasons.length} factors`} defaultOpen>
              <ul className="space-y-2">
                {c.uncertaintyReasons.map((r) => (
                  <li key={r} className="flex gap-2 text-sm leading-relaxed"><span className="mt-2 h-1 w-1 shrink-0 rounded-full bg-warning" />{r}</li>
                ))}
              </ul>
            </Disclosure>
            <div className="space-y-4">
              <div>
                <div className="label-caps mb-2">Questionnaire</div>
                <div className={cn("flex items-center gap-2 rounded-lg border px-3 py-2 text-sm", survey ? "border-success/30 text-success" : "border-dashed text-muted-foreground")}>
                  {survey ? <MessageSquareText className="h-4 w-4" /> : <MessageSquareOff className="h-4 w-4" />}
                  {survey ? "Survey response available" : "No survey response — unavailable"}
                </div>
              </div>
              <div>
                <div className="label-caps mb-2 flex items-center gap-1.5"><AlertOctagon className="h-3 w-3" />Missing evidence</div>
                <div className="flex flex-wrap gap-1.5">
                  {missing.map((m) => <span key={m} className="rounded-md border border-dashed px-2 py-0.5 text-xs text-muted-foreground">{m}</span>)}
                </div>
              </div>
            </div>
          </div>
        </Panel>

        <Panel>
          <PanelHeader title="Human verification" icon={UserCheck} meta={c.verification ? undefined : ""}>
            <VerificationBadge value={c.verification!} />
          </PanelHeader>
          <div className="space-y-4 p-5">
            <Textarea value={note} onChange={(e) => setNote(e.target.value)} placeholder="Field note (optional): what was checked, by whom, how…" className="min-h-20 bg-background/50" aria-label="Verification note" />
            <div className="grid gap-3 sm:grid-cols-3">
              <Button variant="outline" onClick={() => record("needs_verification")} className="h-auto flex-col items-start gap-1 border-warning/40 py-3 text-left hover:border-warning hover:bg-warning/10">
                <span className="flex items-center gap-2 font-semibold text-warning"><Clock className="h-4 w-4" />Still needs verification</span>
                <span className="text-xs font-normal whitespace-normal text-muted-foreground">Keep open; log investigation step</span>
              </Button>
              <Button variant="outline" onClick={() => record("person_confirmed")} className="h-auto flex-col items-start gap-1 border-critical/40 py-3 text-left hover:border-critical hover:bg-critical/10">
                <span className="flex items-center gap-2 font-semibold text-critical"><CheckCircle2 className="h-4 w-4" />Person confirmed</span>
                <span className="text-xs font-normal whitespace-normal text-muted-foreground">Moves to ranked, likely_person</span>
              </Button>
              <Button variant="outline" onClick={() => record("ruled_out")} className="h-auto flex-col items-start gap-1 py-3 text-left hover:border-success hover:bg-success/10">
                <span className="flex items-center gap-2 font-semibold text-success"><XCircle className="h-4 w-4" />Detection ruled out</span>
                <span className="text-xs font-normal whitespace-normal text-muted-foreground">This detection only — sector unchanged</span>
              </Button>
            </div>
            <p className="flex gap-2 rounded-md bg-background/50 px-3 py-2 text-xs text-muted-foreground">
              <Info className="mt-0.5 h-3.5 w-3.5 shrink-0 text-primary" />
              <span>Sector <span className="font-mono text-foreground">{c.sectorId}</span> is <span className="font-medium text-foreground">{sectorCoverage}</span> — ruling out never marks it searched or safe.</span>
            </p>
          </div>
        </Panel>
      </div>

      <Panel className="h-fit">
        <PanelHeader title="Investigation timeline" icon={Clock} meta={`${shownEvents.length} of ${c.events.length}`} />
        <div className="flex flex-wrap gap-1.5 border-b px-5 py-3" role="group" aria-label="Filter timeline">
          {TIMELINE_FILTERS.map((f) => (
            <button
              key={f.key}
              type="button"
              aria-pressed={filter === f.key}
              onClick={() => setFilter(f.key)}
              className={cn(
                "rounded-full border px-3 py-1 text-xs font-medium transition-colors",
                filter === f.key ? "border-primary bg-primary text-primary-foreground" : "text-muted-foreground hover:border-primary/50 hover:text-foreground",
              )}
            >
              {f.label} <span className="font-mono opacity-70">{c.events.filter((e) => f.match(e.actor)).length}</span>
            </button>
          ))}
        </div>
        <div className="p-5">
          {shownEvents.length ? <Timeline events={shownEvents} /> : <p className="text-sm text-muted-foreground">No {TIMELINE_FILTERS.find((f) => f.key === filter)!.label.toLowerCase()} events yet.</p>}
        </div>
      </Panel>
    </div>
  );
}

function Evidence({ icon: Icon, label, value, src, tone, capitalize, hideSrc }: { icon: React.ComponentType<{ className?: string }>; label: string; value: string | null; src: "sensor" | "manual" | "unavailable"; tone?: "warning" | undefined; capitalize?: boolean; hideSrc?: boolean }) {
  return (
    <div className="bg-card px-5 py-4">
      <div className="flex items-center justify-between">
        <span className="flex items-center gap-1.5 text-xs text-muted-foreground"><Icon className="h-3.5 w-3.5 text-subtle" />{label}</span>
        {!hideSrc && <ProvenanceTag source={src} />}
      </div>
      <div className={cn("mt-2 text-lg font-semibold", tone === "warning" && "text-warning", capitalize && "capitalize", value === null && "font-mono text-sm font-normal text-subtle")}>{value ?? "— unavailable"}</div>
    </div>
  );
}
