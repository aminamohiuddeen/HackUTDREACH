import { createFileRoute, Link } from "@tanstack/react-router";
import { AlertTriangle, ArrowUpRight, Bot, Grid3x3, UserCheck } from "lucide-react";
import { cn } from "@/lib/utils";
import { useReach } from "@/lib/reach/store";
import { needsResponse } from "@/lib/reach/priority";
import { hasValidSurvey } from "@/lib/reach/classify";
import { PageHeader, Panel, PanelHeader } from "@/components/reach/primitives";
import { SectorGrid } from "@/components/reach/sector-grid";
import { Map as MapIcon } from "lucide-react";

export const Route = createFileRoute("/_authenticated/")({
  head: () => ({
    meta: [
      { property: "og:type", content: "website" },
      { name: "twitter:card", content: "summary_large_image" },
      { title: "Mission Overview — REACH" },
      { name: "description", content: "Command-center overview of active rescue cases, sector coverage, robot status and alerts." },
      { property: "og:title", content: "Mission Overview — REACH" },
      { property: "og:description", content: "Command-center overview of active rescue cases, sector coverage, robot status and alerts." },
    ],
  }),
  component: Overview,
});

function Overview() {
  const { cases, sectors, robots } = useReach();
  const respond = needsResponse(cases);
  const survivors = cases.filter((c) => c.classification === "likely_person" && hasValidSurvey(c.questionnaire) && c.status !== "resolved");
  const unsearched = sectors.filter((s) => s.coverage === "unsearched");
  const online = robots.filter((r) => r.connection !== "offline");

  const strip = [
    { label: "Need response now", value: respond.length, icon: AlertTriangle, tone: "text-critical", to: "/respond" as const, hash: undefined, urgent: respond.length > 0 },
    { label: "Confirmed survivors", value: survivors.length, icon: UserCheck, tone: "text-primary", to: "/survivors" as const, hash: undefined, urgent: false },
    { label: "Unsearched sectors", value: `${unsearched.length}/${sectors.length}`, icon: Grid3x3, tone: "text-warning", to: "/" as const, hash: "sector-map", urgent: false },
    { label: "Robots linked", value: `${online.length}/${robots.length}`, icon: Bot, tone: "text-success", to: "/robot" as const, hash: undefined, urgent: false },
  ];

  return (
    <div className="space-y-6">
      <PageHeader title="Mission Overview" />

      {/* The four numbers a manager needs first. Each opens its own board. */}
      <div className="panel grid grid-cols-2 divide-x divide-y overflow-hidden xl:grid-cols-4 xl:divide-y-0">
        {strip.map((s, i) => (
          <Link
            key={s.label}
            to={s.to}
            {...(s.hash ? { hash: s.hash } : {})}
            style={{ animationDelay: `${i * 0.5}s` }}
            className={cn(
              "group relative block px-5 py-5 text-left transition-all duration-200 hover:-translate-y-0.5 hover:bg-panel-raised/60",
              i === 0 ? "breathe" : "breathe-soft",
            )}
          >
            {i === 0 && s.urgent && <span className="absolute inset-y-0 left-0 w-1 bg-critical" aria-hidden />}
            <div className="flex items-center justify-between gap-2">
              <span className="label-caps">{s.label}</span>
              <s.icon style={{ animationDelay: `${i * 0.4}s` }} className={cn("float h-4 w-4 shrink-0 transition-transform duration-150 group-hover:scale-110", s.tone)} />
            </div>
            <div className={cn("mt-2 font-display text-5xl font-bold leading-none tracking-tight tabular", s.tone)}>{s.value}</div>
            <div className="mt-2 flex items-center gap-1 font-mono text-xs uppercase tracking-[0.14em] text-subtle transition-colors group-hover:text-primary">
              Open <ArrowUpRight className="h-3 w-3 transition-transform duration-150 group-hover:translate-x-0.5 group-hover:-translate-y-0.5" />
            </div>
          </Link>
        ))}
      </div>

      <div id="sector-map" className="scroll-mt-24">
        <Panel>
          <PanelHeader title="Sector map" icon={MapIcon} meta="A1–F6 · 250 m cells" />
          <div className="p-5"><SectorGrid /></div>
        </Panel>
      </div>
    </div>
  );
}
