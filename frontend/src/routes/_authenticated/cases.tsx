import { useMemo, useState } from "react";
import { createFileRoute, useNavigate } from "@tanstack/react-router";
import { ChevronDown, Inbox, MapPin, MessageSquareOff, Search, X } from "lucide-react";
import { cn } from "@/lib/utils";
import { useCaseDetail, useReach } from "@/lib/reach/store";
import { fmtCoord, fmtTime } from "@/lib/reach/format";
import { hasValidSurvey } from "@/lib/reach/classify";
import type { CaseStatus, Classification, RescueCase } from "@/lib/reach/types";
import { Input } from "@/components/ui/input";
import { ClassificationBadge, ConfidenceScore, EmptyState, EnvWarning, PageHeader, ScoreBadge, SourceBadge, StatusBadge, VerificationBadge } from "@/components/reach/primitives";
import { CaseDetail } from "@/components/reach/case-detail";

export const Route = createFileRoute("/_authenticated/cases")({
  validateSearch: (s: Record<string, unknown>): { id?: string | undefined } => ({ id: typeof s["id"] === "string" ? s["id"] : undefined }),
  head: () => ({
    meta: [
      { property: "og:type", content: "website" },
      { name: "twitter:card", content: "summary_large_image" },
      { title: "Rescue Cases — REACH" },
      { name: "description", content: "Searchable rescue case management with full evidence, questionnaire answers and nearest response units." },
      { property: "og:title", content: "Rescue Cases — REACH" },
      { property: "og:description", content: "Searchable rescue case management for search-and-rescue operators." },
    ],
  }),
  component: Cases,
});

const CLASSES: (Classification | "all")[] = ["all", "likely_person", "possible_person", "object"];
const STATUSES: (CaseStatus | "all")[] = ["all", "ranked", "verify", "not_ranked", "cleared", "resolved"];
const STATUS_LABEL: Record<string, string> = { all: "All", ranked: "Ranked", verify: "VERIFY", not_ranked: "Not ranked", cleared: "Cleared", resolved: "Resolved" };

/** Operational order: what needs people first, resolved last. */
const ORDER: Record<CaseStatus, number> = { ranked: 0, verify: 1, not_ranked: 2, cleared: 3, resolved: 4 };

function Cases() {
  const { cases } = useReach();
  const { id } = Route.useSearch();
  useCaseDetail(id);
  const navigate = useNavigate({ from: "/cases" });
  const [q, setQ] = useState("");
  const [cls, setCls] = useState<Classification | "all">("all");
  const [st, setSt] = useState<CaseStatus | "all">("all");

  const rows = useMemo(() => {
    const term = q.trim().toLowerCase();
    return cases
      .filter((c) => {
        if (cls !== "all" && c.classification !== cls) return false;
        if (st !== "all" && c.status !== st) return false;
        if (!term) return true;
        return [c.id, c.robotId, c.sectorId, c.zone, ...c.needs, c.report.incidentReport].join(" ").toLowerCase().includes(term);
      })
      .sort((a, b) => ORDER[a.status] - ORDER[b.status] || a.detectedAt.localeCompare(b.detectedAt));
  }, [cases, q, cls, st]);

  const openId = id ?? null;

  return (
    <div>
      <PageHeader title="Rescue Cases" description="Every detection as a full case card — report and survey answers up front. Classification confidence and condition scores are tracked separately; cases are never closed automatically." />
      <div className="mb-4 flex flex-wrap items-center gap-3">
        <div className="relative w-72">
          <Search className="absolute top-1/2 left-3 h-4 w-4 -translate-y-1/2 text-subtle" />
          <Input value={q} onChange={(e) => setQ(e.target.value)} placeholder="Search case, sector, robot, need…" className="bg-card pl-9" aria-label="Search cases" />
          {q && <button onClick={() => setQ("")} aria-label="Clear search" className="absolute top-1/2 right-2.5 -translate-y-1/2 text-subtle hover:text-foreground"><X className="h-4 w-4" /></button>}
        </div>
        <Segmented options={CLASSES} value={cls} onChange={setCls} label={(o) => (o === "all" ? "All classes" : o)} mono />
        <Segmented options={STATUSES} value={st} onChange={setSt} label={(o) => STATUS_LABEL[o] ?? o} />
        <span className="ml-auto font-mono text-xs text-subtle">{rows.length} of {cases.length}</span>
      </div>

      <div className="space-y-3">
        {rows.map((c) => (
          <CaseCard key={c.id} c={c} open={openId === c.id} onToggle={() => navigate({ search: openId === c.id ? {} : { id: c.id } })} />
        ))}
        {rows.length === 0 && (
          <div className="panel">
            {cases.length === 0 ? (
              <EmptyState icon={Inbox} title="No active cases at this time" message="New cases appear here automatically as robots report detections." />
            ) : (
              <EmptyState icon={Search} title="No cases match" message="Try clearing the search or widening the classification and status filters." />
            )}
          </div>
        )}
      </div>
    </div>
  );
}

function CaseCard({ c, open, onToggle }: { c: RescueCase; open: boolean; onToggle: () => void }) {
  const survey = hasValidSurvey(c.questionnaire);
  const answered = c.questionnaire?.filter((q) => q.answer) ?? [];
  return (
    <article className={cn("panel overflow-hidden transition-colors", open && "border-primary/50")}>
      <button onClick={onToggle} aria-expanded={open} className="block w-full px-5 py-4 text-left transition-colors hover:bg-panel-raised/60">
        <div className="flex flex-wrap items-center gap-x-3 gap-y-2">
          <span className="font-mono text-sm font-semibold">{c.id}</span>
          <SourceBadge value={c.source} />
          <ClassificationBadge value={c.classification} />
          <StatusBadge value={c.status} />
          <ConfidenceScore value={c.confidence} />
          <ScoreBadge label="Environment" value={c.environmentScore} />
          <ScoreBadge label="Health" value={c.healthScore} />
          {c.verification && <VerificationBadge value={c.verification} />}
          {c.environmentalWarning && <EnvWarning text={c.environmentalWarning} />}
          <span className="ml-auto flex items-center gap-3 font-mono text-xs text-subtle">
            {fmtTime(c.detectedAt)} · {c.robotId}
            <ChevronDown className={cn("h-4 w-4 transition-transform", open && "rotate-180")} />
          </span>
        </div>
        <div className="mt-1.5 flex items-center gap-1.5 text-xs text-muted-foreground">
          <MapPin className="h-3 w-3" />
          Sector <span className="font-mono text-foreground">{c.sectorId}</span> · <span className="capitalize">{c.zone}</span> · <span className="font-mono">{fmtCoord(c.lat, c.lon)}</span>
        </div>
        <p className="mt-2 max-w-4xl text-sm leading-relaxed text-muted-foreground">{c.report.incidentReport}</p>
        <div className="mt-3 flex flex-wrap items-center gap-x-5 gap-y-2">
          {survey ? (
            <div className="flex flex-wrap gap-x-4 gap-y-1">
              {answered.map((q) => (
                <span key={q.questionId} className="text-xs"><span className="text-subtle">{q.question}</span> <span className="font-medium">{q.answer}</span></span>
              ))}
            </div>
          ) : (
            <span className="flex items-center gap-1.5 text-xs text-muted-foreground"><MessageSquareOff className="h-3.5 w-3.5" />No questionnaire response</span>
          )}
          {c.needs.length > 0 && (
            <div className="flex flex-wrap gap-1.5">
              {c.needs.map((n) => <span key={n} className="rounded-md bg-muted px-2 py-0.5 text-xs">{n}</span>)}
            </div>
          )}
        </div>
      </button>
      {open && (
        <div className="border-t bg-background/30 px-5 py-5">
          <CaseDetail c={c} bare />
        </div>
      )}
    </article>
  );
}

function Segmented<T extends string>({ options, value, onChange, label, mono }: { options: T[]; value: T; onChange: (v: T) => void; label: (o: T) => string; mono?: boolean }) {
  return (
    <div className="flex rounded-lg border bg-card p-0.5">
      {options.map((o) => (
        <button key={o} onClick={() => onChange(o)} aria-pressed={value === o}
          className={cn("rounded-md px-2.5 py-1 text-xs transition-colors", mono && o !== "all" && "font-mono", value === o ? "bg-secondary text-foreground" : "text-muted-foreground hover:text-foreground")}>
          {label(o)}
        </button>
      ))}
    </div>
  );
}
