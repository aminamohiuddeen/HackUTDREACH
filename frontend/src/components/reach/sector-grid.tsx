import { useState } from "react";
import { Link } from "@tanstack/react-router";
import { Bot, Info } from "lucide-react";
import { cn } from "@/lib/utils";
import { useReach } from "@/lib/reach/store";
import { fmtTime } from "@/lib/reach/format";
import type { Classification, SectorCoverage } from "@/lib/reach/types";
import { ClassificationBadge, StatusBadge } from "./primitives";

const COVER_CLS: Record<SectorCoverage, string> = {
  searched: "bg-success/15",
  partial: "bg-warning/10 [background-image:repeating-linear-gradient(135deg,transparent_0_6px,color-mix(in_oklab,var(--warning)_18%,transparent)_6px_7px)]",
  unsearched: "bg-transparent",
};
const DOT: Record<Classification, string> = {
  likely_person: "bg-critical",
  possible_person: "bg-warning",
  object: "bg-subtle",
};

export function SectorGrid() {
  const { sectors, cases, robots } = useReach();
  const [selected, setSelected] = useState("D3");
  const sel = sectors.find((s) => s.id === selected)!;
  const selCases = cases.filter((c) => c.sectorId === selected);
  const selRobots = robots.filter((r) => r.sectorId === selected);

  return (
    <div className="grid gap-5 lg:grid-cols-[1fr_280px]">
      <div>
        <div className="grid grid-cols-[20px_1fr] grid-rows-[20px_1fr] gap-1">
          <span />
          <div className="grid grid-cols-6">
            {[1, 2, 3, 4, 5, 6].map((n) => (
              <span key={n} className="text-center font-mono text-xs text-subtle">{n}</span>
            ))}
          </div>
          <div className="grid grid-rows-6">
            {["A", "B", "C", "D", "E", "F"].map((r) => (
              <span key={r} className="flex items-center font-mono text-xs text-subtle">{r}</span>
            ))}
          </div>
          {/* Map surface */}
          <div className="map-surface relative overflow-hidden rounded-lg border border-border-strong">
            <div className="relative z-10 grid grid-cols-6 grid-rows-6">
              {sectors.map((s, idx) => {
                const sc = cases.filter((c) => c.sectorId === s.id && c.status !== "resolved");
                const rb = robots.filter((r) => r.sectorId === s.id);
                const active = s.id === selected;
                return (
                  <button
                    key={s.id}
                    onClick={() => setSelected(s.id)}
                    aria-label={`Sector ${s.id}, ${s.coverage}, ${sc.length} detections`}
                    aria-pressed={active}
                    style={{ animationDelay: `${idx * 18}ms` }}
                    className={cn(
                      "pop-in group relative aspect-[4/3] border-r border-b border-foreground/10 text-left transition-all duration-200 hover:z-20 hover:bg-card/60 focus-visible:outline-2 focus-visible:outline-ring",
                      COVER_CLS[s.coverage],
                      active && "z-20 bg-primary/10 outline-2 outline-primary breathe",
                    )}
                  >
                    <span className={cn("absolute top-1 left-1.5 font-mono text-[11px] font-medium transition-colors", active ? "text-primary" : "text-foreground/45 group-hover:text-foreground")}>{s.id}</span>
                    {rb.length > 0 && (
                      <span className="absolute inset-0 flex items-center justify-center">
                        <span className="radar-sweep absolute h-16 w-16 rounded-full bg-[conic-gradient(from_0deg,color-mix(in_oklab,var(--primary)_28%,transparent),transparent_30%)]" aria-hidden />
                        <span className="relative flex h-6 w-6 items-center justify-center rounded-full bg-primary text-primary-foreground shadow-md">
                          <span className="ping-ring absolute inset-0 rounded-full bg-primary" aria-hidden />
                          <Bot className="relative h-3.5 w-3.5" />
                        </span>
                      </span>
                    )}
                    <span className="absolute bottom-1.5 right-1.5 flex gap-1.5">
                      {sc.map((c, j) => (
                        <span key={c.id} className="relative flex h-2.5 w-2.5">
                          <span style={{ animationDelay: `${j * 0.4}s` }} className={cn("ping-ring absolute inset-0 rounded-full", DOT[c.classification])} aria-hidden />
                          <span className={cn("relative h-2.5 w-2.5 rounded-full ring-2 ring-card", DOT[c.classification])} />
                        </span>
                      ))}
                    </span>
                  </button>
                );
              })}
            </div>
            {/* Compass + scale */}
            <div className="pointer-events-none absolute top-2 right-2 z-30 flex h-9 w-9 flex-col items-center justify-center rounded-full border bg-card/90 font-mono text-[11px] font-semibold shadow-sm">
              <span className="text-primary">N</span>
              <span className="-mt-1 h-2 w-px bg-primary" />
            </div>
            <div className="pointer-events-none absolute bottom-2 left-2 z-30 flex items-center gap-1.5 rounded bg-card/90 px-2 py-1 font-mono text-[11px] text-muted-foreground shadow-sm">
              <span className="h-1 w-10 border-x border-b border-foreground/60" /> 250 m
            </div>
          </div>
        </div>
        <div className="mt-4 flex flex-wrap items-center gap-x-5 gap-y-2 text-xs text-muted-foreground">
          <span className="label-caps">Coverage</span>
          <Legend cls="bg-success/30 border-success/40" label="Searched" />
          <Legend cls="bg-warning/25 border-warning/40" label="Partial" />
          <Legend cls="bg-background border-border-strong" label="Unsearched" />
          <span className="label-caps ml-2">Detections</span>
          <Dot cls="bg-critical" label="Likely person" />
          <Dot cls="bg-warning" label="Possible person" />
          <Dot cls="bg-subtle" label="Object" />
        </div>
      </div>

      <aside key={sel.id} className="fade-in-up panel h-fit p-4 lg:sticky lg:top-24">
        <div className="flex items-baseline justify-between border-b pb-3">
          <span className="font-display text-3xl font-bold tracking-wide">{sel.id}</span>
          <span className="rounded-sm border px-1.5 py-0.5 font-mono text-xs uppercase tracking-wider text-muted-foreground">{sel.zone} zone</span>
        </div>
        <dl className="mt-3 space-y-2.5 text-sm">
          <div className="flex items-center justify-between"><dt className="text-muted-foreground">Coverage</dt><dd className="flex items-center gap-1.5 capitalize"><span className={cn("h-2 w-2 rounded-full", sel.coverage === "searched" ? "bg-success" : sel.coverage === "partial" ? "bg-warning" : "bg-subtle")} />{sel.coverage}</dd></div>
          <div className="flex items-center justify-between"><dt className="text-muted-foreground">Last sweep</dt><dd className="font-mono text-xs tabular">{sel.lastSweep ? fmtTime(sel.lastSweep) : "—"}</dd></div>
          <div className="flex items-center justify-between"><dt className="text-muted-foreground">Robots</dt><dd className="font-mono text-xs">{selRobots.map((r) => r.id).join(", ") || "—"}</dd></div>
        </dl>
        <div className="mt-4 border-t pt-3 label-caps">Detections</div>
        {selCases.length === 0 ? (
          <p className="mt-2 rounded-md border border-dashed px-3 py-3 text-center text-xs text-subtle">None recorded in {sel.id}.</p>
        ) : (
          <ul className="mt-2 space-y-2">
            {selCases.map((c) => (
              <li key={c.id}>
                <Link to="/cases" search={{ id: c.id }} className="block rounded-md border p-2.5 transition-all hover:-translate-y-px hover:border-border-strong hover:shadow-sm">
                  <div className="font-mono text-xs font-medium">{c.id}</div>
                  <div className="mt-1.5 flex flex-wrap gap-1"><ClassificationBadge value={c.classification} /><StatusBadge value={c.status} /></div>
                </Link>
              </li>
            ))}
          </ul>
        )}
        <p className="mt-4 flex gap-1.5 text-xs leading-relaxed text-subtle">
          <Info className="mt-0.5 h-3 w-3 shrink-0" />
          Sector coverage is tracked separately. Clearing a detection never marks a sector as searched or safe.
        </p>
      </aside>
    </div>
  );
}

const Legend = ({ cls, label }: { cls: string; label: string }) => (
  <span className="flex items-center gap-1.5"><span className={cn("h-3 w-3 rounded-sm border", cls)} />{label}</span>
);
const Dot = ({ cls, label }: { cls: string; label: string }) => (
  <span className="flex items-center gap-1.5"><span className={cn("h-2 w-2 rounded-full", cls)} />{label}</span>
);
