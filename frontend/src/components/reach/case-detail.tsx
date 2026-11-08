import { useState } from "react";
import { Link } from "@tanstack/react-router";
import { Ambulance, CheckCircle2, Flame, LifeBuoy, Send, Sparkles } from "lucide-react";
import { cn } from "@/lib/utils";
import { useReach } from "@/lib/reach/store";
import type { RescueCase, SensorSnapshot } from "@/lib/reach/types";
import { fmtCoord, fmtTime } from "@/lib/reach/format";
import {
  ClassificationBadge,
  ConfidenceDisplay,
  Disclosure,
  EnvWarning,
  Field,
  NearestUnits,
  ProvenanceTag,
  ScoreBadge,
  StatusBadge,
  Timeline,
  VerificationBadge,
} from "./primitives";

export function SensorTable({ s }: { s: SensorSnapshot }) {
  const vec = (v: { x: number; y: number; z: number } | null) => (v ? `${v.x.toFixed(2)} / ${v.y.toFixed(2)} / ${v.z.toFixed(2)}` : null);
  const bool = (b: boolean | null) => (b === null ? null : b ? "Yes" : "No");
  const rows: [string, string | null, typeof s.temperatureC.source][] = [
    ["Temperature", s.temperatureC.value !== null ? `${s.temperatureC.value} °C` : null, s.temperatureC.source],
    ["IR trigger", bool(s.irTriggered.value), s.irTriggered.source],
    ["Water", bool(s.waterDetected.value), s.waterDetected.source],
    ["Motion", bool(s.motionDetected.value), s.motionDetected.source],
    ["Accel X/Y/Z", vec(s.accel.value), s.accel.source],
    ["Gyro X/Y/Z", vec(s.gyro.value), s.gyro.source],
    ["Anomaly area", s.anomalyAreaCm2.value !== null ? `${s.anomalyAreaCm2.value} cm²` : null, s.anomalyAreaCm2.source],
  ];
  return (
    <dl className="divide-y rounded-lg border">
      {rows.map(([k, val, src]) => (
        <div key={k} className="flex items-center gap-3 px-3 py-2 text-sm">
          <dt className="w-28 shrink-0 text-muted-foreground">{k}</dt>
          <dd className="flex-1 font-mono text-sm">{val ?? <span className="text-subtle">—</span>}</dd>
          <ProvenanceTag source={src} />
        </div>
      ))}
    </dl>
  );
}

export function Questionnaire({ c }: { c: RescueCase }) {
  if (!c.questionnaire) return <p className="text-sm text-subtle">No OLED questionnaire response received.</p>;
  return (
    <ol className="space-y-1.5">
      {c.questionnaire.map((q) => (
        <li key={q.questionId} className="flex gap-3 text-sm">
          <span className="w-6 font-mono text-xs text-subtle">Q{q.questionId}</span>
          <span className="flex-1 text-muted-foreground">{q.question}</span>
          <span className={q.answer ? "font-medium" : "text-subtle"}>{q.answer ?? "—"}</span>
        </li>
      ))}
    </ol>
  );
}

const UNIT_ICON = { EMS: Ambulance, FIRE: Flame, SAR: LifeBuoy };

/** Human dispatch controls: the operator picks a unit and confirms; REACH never chooses. */
function DispatchPanel({ c }: { c: RescueCase }) {
  const { dispatch } = useReach();
  const [selected, setSelected] = useState<string | null>(null);

  if (c.status === "resolved") {
    return (
      <section className="flex items-center gap-2.5 rounded-md border border-success/35 bg-success/8 px-4 py-3">
        <CheckCircle2 className="h-4 w-4 shrink-0 text-success" />
        <p className="text-sm">
          Case closed by operator{c.dispatchedUnit ? <> — <span className="font-mono font-medium">{c.dispatchedUnit.unitId}</span> dispatched at {fmtTime(c.dispatchedUnit.at)}</> : ""}.
        </p>
        <label className="ml-auto flex cursor-not-allowed items-center gap-2 text-xs font-semibold text-success">
          <input type="checkbox" checked readOnly disabled className="h-4 w-4 accent-success" />
          Case closed
        </label>
      </section>
    );
  }

  if (c.status === "cleared" || c.status === "not_ranked") return null;

  const units = [...c.report.nearestUnits].sort((a, b) => a.distanceKm - b.distanceKm);

  if (c.dispatchedUnit) {
    return (
      <section className="rounded-md border border-primary/35 bg-primary/5 px-4 py-3">
        <div className="flex flex-wrap items-center gap-3">
          <Send className="h-4 w-4 shrink-0 text-primary" />
          <p className="text-sm">
            <span className="font-mono font-medium">{c.dispatchedUnit.unitId}</span> dispatched at {fmtTime(c.dispatchedUnit.at)} — confirmed by operator
          </p>
          <label className="ml-auto flex cursor-pointer items-center gap-2 rounded-md border border-success/50 bg-success/10 px-3 py-1.5 text-xs font-semibold text-success transition-colors hover:bg-success/20">
            <input
              type="checkbox"
              className="h-4 w-4 accent-success"
              onChange={() => dispatch({ type: "resolve", caseId: c.id })}
            />
            Close case — mark resolved
          </label>
        </div>
      </section>
    );
  }

  return (
    <section className="rounded-md border px-4 py-3.5">
      <div className="label-caps mb-2.5">Dispatch a unit — operator decision</div>
      {units.length === 0 ? (
        <p className="text-sm text-subtle">No units retrieved for this case.</p>
      ) : (
        <div className="flex flex-wrap items-center gap-2">
          {units.map((u) => {
            const Icon = UNIT_ICON[u.type];
            const on = selected === u.id;
            return (
              <button
                key={u.id}
                onClick={() => setSelected(on ? null : u.id)}
                aria-pressed={on}
                className={cn(
                  "flex items-center gap-2 rounded-md border px-3 py-2 text-left transition-colors hover:border-border-strong hover:bg-panel-raised/60",
                  on && "border-primary bg-primary/8 ring-1 ring-primary",
                )}
              >
                <Icon className="h-4 w-4 text-muted-foreground" />
                <span className="font-mono text-xs font-medium">{u.id}</span>
                <span className="font-mono text-xs text-subtle">{u.type} · {u.distanceKm.toFixed(1)} km</span>
              </button>
            );
          })}
          <button
            disabled={!selected}
            onClick={() => selected && dispatch({ type: "dispatch_unit", caseId: c.id, unitId: selected })}
            className="ml-auto inline-flex items-center gap-1.5 rounded-md bg-primary px-3.5 py-2 text-xs font-semibold text-primary-foreground transition-opacity hover:opacity-90 disabled:cursor-not-allowed disabled:opacity-40"
          >
            <Send className="h-3.5 w-3.5" /> Confirm dispatch
          </button>
        </div>
      )}
    </section>
  );
}

export function CaseDetail({ c, bare }: { c: RescueCase; bare?: boolean }) {
  return (
    <div className="space-y-6 fade-in-up" key={c.id}>
      {bare ? (
        <div className="flex justify-end">
          <Link to="/intelligence" search={{ id: c.id }} className="inline-flex items-center gap-1.5 text-xs text-primary hover:underline">
            <Sparkles className="h-3.5 w-3.5" /> Nemotron view
          </Link>
        </div>
      ) : (
        <div>
          <div className="flex items-center justify-between">
            <span className="font-mono text-lg font-semibold">{c.id}</span>
            <Link to="/intelligence" search={{ id: c.id }} className="inline-flex items-center gap-1.5 text-xs text-primary hover:underline">
              <Sparkles className="h-3.5 w-3.5" /> Nemotron view
            </Link>
          </div>
          <div className="mt-2 flex flex-wrap gap-1.5">
            <ClassificationBadge value={c.classification} />
            <StatusBadge value={c.status} />
            <ScoreBadge label="Environment integrity" value={c.environmentScore} />
            <ScoreBadge label="Health" value={c.healthScore} />
            {c.verification && <VerificationBadge value={c.verification} />}
            {c.environmentalWarning && <EnvWarning text={c.environmentalWarning} />}
          </div>
        </div>
      )}

      <div className="grid grid-cols-2 gap-px overflow-hidden rounded-lg border bg-border">
        <Field label="Detected" className="bg-card p-4"><span className="font-mono tabular">{fmtTime(c.detectedAt)}</span></Field>
        <Field label="Robot" className="bg-card p-4"><span className="font-mono">{c.robotId}</span></Field>
        <Field label="Sector / zone" className="bg-card p-4"><span className="font-mono">{c.sectorId}</span> · <span className="capitalize">{c.zone}</span></Field>
        <Field label={`Location · ${c.locationSource === "gps" ? "GPS" : "Operator"}`} className="bg-card p-4"><span className="font-mono text-xs">{fmtCoord(c.lat, c.lon)}</span></Field>
        <Field label="Confidence" className="col-span-2 bg-card p-4"><ConfidenceDisplay value={c.confidence} /></Field>
        <Field label="Reported needs" className="col-span-2 bg-card p-4">
          {c.needs.length ? <div className="flex flex-wrap gap-1.5">{c.needs.map((n) => <span key={n} className="rounded-md bg-muted px-2 py-0.5 text-xs">{n}</span>)}</div> : <span className="text-subtle">None reported</span>}
        </Field>
      </div>

      <Disclosure label="Sensor readings" meta="9 channels">
        <SensorTable s={c.sensors} />
      </Disclosure>
      <Disclosure label="Questionnaire" meta={c.questionnaire ? `${c.questionnaire.filter((q) => q.answer).length}/${c.questionnaire.length} answered` : "no response"} defaultOpen>
        <Questionnaire c={c} />
      </Disclosure>
      <Disclosure label="Nemotron rationale">
        <p className="text-sm leading-relaxed text-muted-foreground">{c.report.rationale}</p>
      </Disclosure>
      <section><NearestUnits units={c.report.nearestUnits} /></section>
      <DispatchPanel c={c} />
      <Disclosure label="Evidence timeline" meta={`${c.events.length} events`}>
        <Timeline events={c.events} />
      </Disclosure>
    </div>
  );
}
