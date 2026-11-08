import { useState, type ReactNode } from "react";
import {
  AlertTriangle,
  Bot,
  CheckCircle2,
  ChevronDown,
  CircleDashed,
  CircleHelp,
  Flame,
  Ambulance,
  LifeBuoy,
  ShieldAlert,
  Sparkles,
  User,
  Box,
  Search,
} from "lucide-react";
import { cn } from "@/lib/utils";
import { fmtTime } from "@/lib/reach/format";
import type {
  CaseStatus,
  Classification,
  Confidence,
  Provenance,
  ResponseUnit,
  Score,
  TimelineEvent,
  VerificationOutcome,
} from "@/lib/reach/types";
import { scoreBand, type ScoreBand } from "@/lib/reach/priority";

export function Panel({ className, children }: { className?: string; children: ReactNode }) {
  return <section className={cn("panel", className)}>{children}</section>;
}

export function PanelHeader({
  title,
  icon: Icon,
  meta,
  children,
}: {
  title: string;
  icon?: React.ComponentType<{ className?: string }>;
  meta?: ReactNode;
  children?: ReactNode;
}) {
  return (
    <header className="flex items-center justify-between gap-3 border-b px-5 py-3.5">
      <div className="flex min-w-0 items-baseline gap-2.5">
        {Icon && (
          <span className="flex h-6 w-6 shrink-0 translate-y-0.5 items-center justify-center rounded-md bg-primary/10">
            <Icon className="h-3.5 w-3.5 text-primary" />
          </span>
        )}
        <h2 className="truncate font-display text-base font-semibold uppercase tracking-[0.06em]">{title}</h2>
        {meta && <span className="font-mono text-xs text-subtle">{meta}</span>}
      </div>
      {children}
    </header>
  );
}

type Tone = "info" | "warning" | "critical" | "success" | "neutral" | "thermal";
const toneCls: Record<Tone, string> = {
  info: "bg-primary/12 text-primary border-primary/30",
  warning: "bg-warning/12 text-warning border-warning/30",
  critical: "bg-critical/12 text-critical border-critical/35",
  success: "bg-success/12 text-success border-success/30",
  neutral: "bg-muted text-muted-foreground border-border-strong",
  thermal: "bg-thermal/12 text-thermal border-thermal/35",
};

export function Pill({ tone = "neutral", icon: Icon, children, className }: { tone?: Tone; icon?: React.ComponentType<{ className?: string }>; children: ReactNode; className?: string }) {
  return (
    <span className={cn("inline-flex items-center gap-1.5 whitespace-nowrap rounded-md border px-2 py-0.5 text-xs font-medium", toneCls[tone], className)}>
      {Icon && <Icon className="h-3 w-3" />}
      {children}
    </span>
  );
}

const CLASS_META: Record<Classification, { label: string; tone: Tone; icon: typeof User }> = {
  likely_person: { label: "likely_person", tone: "critical", icon: User },
  possible_person: { label: "possible_person", tone: "warning", icon: CircleHelp },
  object: { label: "object", tone: "neutral", icon: Box },
};
export function ClassificationBadge({ value }: { value: Classification }) {
  const m = CLASS_META[value];
  return (
    <Pill tone={m.tone} icon={m.icon} className="font-mono">
      {m.label}
    </Pill>
  );
}

const STATUS_META: Record<CaseStatus, { label: string; tone: Tone; icon: typeof User }> = {
  ranked: { label: "Ranked", tone: "info", icon: ShieldAlert },
  verify: { label: "VERIFY", tone: "warning", icon: Search },
  cleared: { label: "Cleared", tone: "success", icon: CheckCircle2 },
  not_ranked: { label: "Not ranked", tone: "neutral", icon: CircleDashed },
  resolved: { label: "Resolved", tone: "success", icon: CheckCircle2 },
};
export function StatusBadge({ value }: { value: CaseStatus }) {
  const m = STATUS_META[value];
  return (
    <Pill tone={m.tone} icon={m.icon}>
      {m.label}
    </Pill>
  );
}

const SCORE_TONE: Record<ScoreBand, Tone> = { good: "success", fair: "warning", poor: "critical", unknown: "neutral" };
/** 0–100 condition score with a mini meter. null renders as "—" (unknown), never a guess. */
export function ScoreBadge({ label, value }: { label: string; value: Score }) {
  const tone = SCORE_TONE[scoreBand(value)];
  return (
    <span className={cn("inline-flex items-center gap-1.5 rounded-md border px-2 py-0.5 text-xs font-medium", toneCls[tone])}>
      <span className="font-mono text-xs uppercase tracking-wider opacity-75">{label}</span>
      {value == null ? (
        <span className="font-mono text-subtle">—</span>
      ) : (
        <>
          <span className="h-1 w-7 overflow-hidden rounded-full bg-current/20" aria-hidden>
            <span className="block h-full rounded-full bg-current" style={{ width: `${value}%` }} />
          </span>
          <span className="font-mono tabular">{value}</span>
        </>
      )}
    </span>
  );
}

export function EnvWarning({ text }: { text: string }) {
  return (
    <Pill tone="thermal" icon={Flame}>
      {text}
    </Pill>
  );
}

const VERIFY_META: Record<VerificationOutcome, { label: string; tone: Tone }> = {
  pending: { label: "Awaiting review", tone: "warning" },
  needs_verification: { label: "Still needs verification", tone: "warning" },
  person_confirmed: { label: "Person confirmed", tone: "critical" },
  ruled_out: { label: "Detection ruled out", tone: "success" },
};
export function VerificationBadge({ value }: { value: VerificationOutcome }) {
  const m = VERIFY_META[value];
  return <Pill tone={m.tone}>{m.label}</Pill>;
}

export function ConfidenceDisplay({ value, compact }: { value: Confidence; compact?: boolean }) {
  return (
    <div className="space-y-1.5">
      <span className="inline-flex items-center gap-1.5 font-mono text-xs text-muted-foreground">
        <CircleDashed className="h-3 w-3" />
        {value.label}
      </span>
      {!compact && value.evidence.length > 0 && (
        <ul className="space-y-0.5 text-xs text-muted-foreground">
          {value.evidence.map((e) => (
            <li key={e} className="flex gap-1.5">
              <span className="text-subtle">—</span>
              {e}
            </li>
          ))}
        </ul>
      )}
    </div>
  );
}

export function ProvenanceTag({ source }: { source: Provenance }) {
  if (source === "sensor")
    return <span className="rounded-sm bg-primary/12 px-1.5 py-px font-mono text-xs font-medium uppercase tracking-wider text-primary">sensor</span>;
  if (source === "manual")
    return <span className="rounded-sm bg-warning/12 px-1.5 py-px font-mono text-xs font-medium uppercase tracking-wider text-warning">est · manual</span>;
  return <span className="rounded-sm bg-muted px-1.5 py-px font-mono text-xs font-medium uppercase tracking-wider text-subtle">n/a</span>;
}

export const NotAvailable = () => <span className="font-mono text-sm text-subtle">— unavailable</span>;

const UNIT_ICON = { EMS: Ambulance, FIRE: Flame, SAR: LifeBuoy };
export function NearestUnits({ units }: { units: ResponseUnit[] }) {
  return (
    <div>
      <div className="mb-3 flex items-center gap-2 rounded-md border border-warning/30 bg-warning/8 px-3 py-2">
        <AlertTriangle className="h-3.5 w-3.5 shrink-0 text-warning" />
        <p className="text-xs text-muted-foreground">
          <span className="font-semibold text-foreground">Nearest Relevant Units (Human Decision Required)</span>
        </p>
      </div>
      {units.length === 0 ? (
        <p className="text-sm text-subtle">No units retrieved for this case.</p>
      ) : (
        <ul className="divide-y rounded-lg border">
          {units.map((u) => {
            const Icon = UNIT_ICON[u.type];
            return (
              <li key={u.id} className="flex items-center gap-3 px-3 py-2.5 transition-colors hover:bg-panel-raised/50">
                <span className="flex h-7 w-7 items-center justify-center rounded-md bg-muted">
                  <Icon className="h-3.5 w-3.5 text-muted-foreground" />
                </span>
                <span className="font-mono text-sm font-medium">{u.id}</span>
                <span className="rounded-sm border px-1.5 font-mono text-xs text-subtle">{u.type}</span>
                <span className="ml-auto text-xs text-muted-foreground">{u.availability ?? <span className="text-subtle">Availability not supplied</span>}</span>
                <span className="w-16 text-right font-mono text-sm tabular">{u.distanceKm.toFixed(1)} km</span>
              </li>
            );
          })}
        </ul>
      )}
    </div>
  );
}

const ACTOR_META = {
  robot: { icon: Bot, cls: "text-primary bg-primary/12" },
  nemotron: { icon: Sparkles, cls: "text-muted-foreground bg-muted" },
  operator: { icon: User, cls: "text-warning bg-warning/12" },
  system: { icon: CircleDashed, cls: "text-subtle bg-muted" },
};
export function Timeline({ events }: { events: TimelineEvent[] }) {
  const sorted = [...events].sort((a, b) => a.at.localeCompare(b.at));
  return (
    <ol className="relative space-y-4 before:absolute before:top-2 before:bottom-2 before:left-[13px] before:w-px before:bg-border">
      {sorted.map((e) => {
        const m = ACTOR_META[e.actor];
        return (
          <li key={e.id} className="relative flex gap-3 fade-in-up">
            <span className={cn("relative z-10 flex h-7 w-7 shrink-0 items-center justify-center rounded-full ring-4 ring-card", m.cls)}>
              <m.icon className="h-3.5 w-3.5" />
            </span>
            <div className="min-w-0 pt-0.5">
              <div className="flex flex-wrap items-baseline gap-x-2">
                <span className={cn("text-sm font-medium", e.actor === "nemotron" && "font-mono text-sm")}>{e.title}</span>
                <span className="font-mono text-xs text-subtle">{fmtTime(e.at)}</span>
              </div>
              {e.detail && <p className="mt-0.5 text-xs leading-relaxed text-muted-foreground">{e.detail}</p>}
            </div>
          </li>
        );
      })}
    </ol>
  );
}

/** Consistent empty state: icon chip, title, one-line guidance. */
export function EmptyState({ icon: Icon, title, message }: { icon: React.ComponentType<{ className?: string }>; title: string; message: string }) {
  return (
    <div className="flex flex-col items-center gap-2.5 px-6 py-14 text-center">
      <span className="flex h-11 w-11 items-center justify-center rounded-full border bg-muted">
        <Icon className="h-5 w-5 text-subtle" />
      </span>
      <p className="text-sm font-semibold">{title}</p>
      <p className="max-w-sm text-xs leading-relaxed text-muted-foreground">{message}</p>
    </div>
  );
}

export function Field({ label, children, className }: { label: string; children: ReactNode; className?: string }) {
  return (
    <div className={className}>
      <div className="label-caps mb-1">{label}</div>
      <div className="text-sm">{children}</div>
    </div>
  );
}

/** Click-to-expand section: keeps detail one click away instead of on screen. */
export function Disclosure({ label, meta, defaultOpen = false, children }: { label: string; meta?: string; defaultOpen?: boolean; children: ReactNode }) {
  const [open, setOpen] = useState(defaultOpen);
  return (
    <section className="rounded-md border">
      <button
        onClick={() => setOpen(!open)}
        aria-expanded={open}
        className="flex w-full items-center gap-2 px-3.5 py-2.5 text-left transition-colors hover:bg-panel-raised/50"
      >
        <ChevronDown className={cn("h-3.5 w-3.5 text-subtle transition-transform", !open && "-rotate-90")} />
        <span className="label-caps !text-foreground/70">{label}</span>
        {meta && <span className="font-mono text-xs text-subtle">{meta}</span>}
        {!open && <span className="ml-auto font-mono text-xs uppercase tracking-wider text-primary">Show</span>}
      </button>
      {open && <div className="border-t px-3.5 py-3.5 fade-in-up">{children}</div>}
    </section>
  );
}

export function PageHeader({ title, description, children }: { title: string; description?: string; children?: ReactNode }) {
  return (
    <div className="mb-6 flex flex-wrap items-end justify-between gap-4">
      <div>
        <div className="eyebrow mb-1.5 flex items-center gap-2"><span className="inline-block h-px w-5 bg-primary" aria-hidden />REACH Command</div>
        <h1 className="font-display text-3xl font-bold uppercase tracking-[0.03em]">{title}</h1>
        {description && <p className="mt-1 max-w-2xl text-sm text-muted-foreground">{description}</p>}
      </div>
      {children}
    </div>
  );
}
