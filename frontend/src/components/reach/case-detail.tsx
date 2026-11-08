import { Link } from "@tanstack/react-router";
//import { Ambulance, CheckCircle2, Flame, LifeBuoy, Sparkles } from "lucide-react";
import { Sparkles } from "lucide-react";
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
  SourceBadge,
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

export function CaseDetail({ c, bare }: { c: RescueCase; bare?: boolean }) {
  return (
    <div className="space-y-6 fade-in-up" key={c.id}>
      {bare ? (
        <div className="flex justify-end">
          <Link to="/intelligence" search={{ id: c.id }} className="inline-flex items-center gap-1.5 text-xs text-primary hover:underline">
            <Sparkles className="h-3.5 w-3.5" /> AI analysis
          </Link>
        </div>
      ) : (
        <div>
          <div className="flex items-center justify-between">
            <span className="font-mono text-lg font-semibold">{c.id}</span>
            <Link to="/intelligence" search={{ id: c.id }} className="inline-flex items-center gap-1.5 text-xs text-primary hover:underline">
              <Sparkles className="h-3.5 w-3.5" /> AI analysis
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
        <Field label="Robot" className="bg-card p-4"><div className="flex flex-wrap items-center gap-2"><span className="font-mono">{c.robotId}</span><SourceBadge value={c.source} /></div></Field>
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
      <Disclosure label="AI rationale · Powered by Nemotron">
        <p className="text-sm leading-relaxed text-muted-foreground">{c.report.rationale}</p>
      </Disclosure>
      <section><NearestUnits units={c.report.nearestUnits} /></section>
      <Disclosure label="Evidence timeline" meta={`${c.events.length} events`}>
        <Timeline events={c.events} />
      </Disclosure>
    </div>
  );
}