import { useEffect, useState } from "react";
import { createFileRoute } from "@tanstack/react-router";
import { Activity, Bot, MapPin, Move3d, Orbit, Radar, Ruler, Thermometer, Wind, MessageSquareText, Wifi } from "lucide-react";
import { cn } from "@/lib/utils";
import { useReach } from "@/lib/reach/store";
import { fmtCoord, fmtTime } from "@/lib/reach/format";
import type { Reading, Robot, Vec3 } from "@/lib/reach/types";
import { NotAvailable, PageHeader, Panel, PanelHeader, ProvenanceTag } from "@/components/reach/primitives";
import { QUESTIONS } from "@/lib/reach/mock-data";

export const Route = createFileRoute("/_authenticated/robot")({
  head: () => ({
    meta: [
      { property: "og:type", content: "website" },
      { name: "twitter:card", content: "summary_large_image" },
      { title: "Robot Monitor — REACH" },
      { name: "description", content: "Live-style telemetry from REACH search robots: thermal, IR, motion, IMU and OLED answers." },
      { property: "og:title", content: "Robot Monitor — REACH" },
      { property: "og:description", content: "Live-style telemetry from REACH search robots." },
    ],
  }),
  component: RobotMonitor,
});

/** Adds small jitter to sensor-sourced values only; manual and unavailable values never change. */
function useLive(robot: Robot): Robot {
  const [tick, setTick] = useState(0);
  useEffect(() => {
    const id = setInterval(() => setTick((t) => t + 1), 2000);
    return () => clearInterval(id);
  }, []);
  if (tick === 0) return robot;
  const j = (n: number, amp: number) => Math.round((n + Math.sin(tick * 1.7 + n) * amp) * 100) / 100;
  const jr = (r: Reading<number>, amp: number): Reading<number> => (r.source === "sensor" && r.value !== null ? { ...r, value: j(r.value, amp) } : r);
  const jv = (r: Reading<Vec3>, amp: number): Reading<Vec3> =>
    r.source === "sensor" && r.value ? { ...r, value: { x: j(r.value.x, amp), y: j(r.value.y, amp), z: j(r.value.z, amp) } } : r;
  return {
    ...robot,
    timestamp: new Date(new Date(robot.timestamp).getTime() + tick * 2000).toISOString(),
    sensors: {
      ...robot.sensors,
      temperatureC: jr(robot.sensors.temperatureC, 0.2),
      accel: jv(robot.sensors.accel, 0.03),
      gyro: jv(robot.sensors.gyro, 0.15),
    },
  };
}

function RobotMonitor() {
  const { robots } = useReach();
  const [id, setId] = useState(robots[0]!.id);
  const base = robots.find((r) => r.id === id)!;
  const r = useLive(base);
  const s = r.sensors;

  return (
    <div>
      <PageHeader title="Robot Monitor" description="Telemetry per robot. Each value is tagged as a sensor reading, a manual operator estimate, or unavailable.">
        <div className="flex rounded-lg border bg-card p-1" role="tablist">
          {robots.map((x) => (
            <button key={x.id} role="tab" aria-selected={x.id === id} onClick={() => setId(x.id)}
              className={cn("rounded-md px-3 py-1.5 font-mono text-xs transition-colors", x.id === id ? "bg-primary text-primary-foreground" : "text-muted-foreground hover:text-foreground")}>
              {x.id}
            </button>
          ))}
        </div>
      </PageHeader>

      <div className="mb-5 flex flex-wrap items-center gap-x-6 gap-y-2 text-xs text-muted-foreground">
        <span className="label-caps">Legend</span>
        <span className="flex items-center gap-2"><ProvenanceTag source="sensor" /> Actual reading</span>
        <span className="flex items-center gap-2"><ProvenanceTag source="manual" /> Operator-entered estimate</span>
        <span className="flex items-center gap-2"><ProvenanceTag source="unavailable" /> No data — not inferred</span>
      </div>

      <div className="grid gap-4 md:grid-cols-2 xl:grid-cols-4">
        <Card icon={Bot} label="Robot ID"><Big>{r.id}</Big></Card>
        <Card icon={Wifi} label="Connection">
          <div className="flex items-center gap-2">
            <span className={cn("h-2.5 w-2.5 rounded-full", r.connection === "online" ? "bg-success pulse-dot" : r.connection === "degraded" ? "bg-warning" : "bg-critical")} />
            <span className="text-xl font-semibold capitalize">{r.connection}</span>
          </div>
        </Card>
        <Card icon={Activity} label="Timestamp"><Big>{fmtTime(r.timestamp)}</Big></Card>
        <Card icon={MapPin} label="Location" tag={<span className="rounded-sm border px-1.5 font-mono text-xs uppercase text-muted-foreground">{r.locationSource === "gps" ? "GPS" : "Operator"}</span>}>
          <div className="font-mono text-sm">{fmtCoord(r.lat, r.lon)}</div>
          <div className="mt-1 text-xs text-muted-foreground">Sector <span className="font-mono">{r.sectorId}</span> · <span className="capitalize">{r.zone}</span> zone</div>
        </Card>

        <NumCard icon={Thermometer} label="Temperature" r={s.temperatureC} unit="°C" warn={(v) => v >= 45} />
        <BoolCard icon={Radar} label="Infrared trigger" r={s.irTriggered} on="Triggered" off="Not triggered" note="IR alone never confirms a person" />
        <BoolCard icon={Wind} label="Motion detection" r={s.motionDetected} on="Motion" off="No motion" />

        <VecCard icon={Move3d} label="Accelerometer" r={s.accel} unit="m/s²" />
        <VecCard icon={Orbit} label="Gyroscope" r={s.gyro} unit="°/s" />
        <NumCard icon={Ruler} label="Anomaly area" r={s.anomalyAreaCm2} unit="cm²" />
      </div>

      <Panel className="mt-6">
        <PanelHeader title="Latest OLED questionnaire" icon={MessageSquareText} meta={r.questionnaire ? `${r.questionnaire.filter((q) => q.answer).length}/5 answered` : "no session"} />
        <ol className="grid divide-y md:grid-cols-5 md:divide-x md:divide-y-0">
          {QUESTIONS.map((q, i) => {
            const a = r.questionnaire?.[i]?.answer ?? null;
            return (
              <li key={q} className="p-4">
                <div className="font-mono text-xs text-subtle">Q{i + 1}</div>
                <div className="mt-1 text-sm text-muted-foreground">{q}</div>
                <div className={cn("mt-3 text-lg font-semibold", !a && "text-sm font-normal text-subtle")}>{a ?? (r.questionnaire ? "Not answered" : "No response")}</div>
              </li>
            );
          })}
        </ol>
      </Panel>
    </div>
  );
}

function Card({ icon: Icon, label, tag, children, className }: { icon: React.ComponentType<{ className?: string }>; label: string; tag?: React.ReactNode; children: React.ReactNode; className?: string }) {
  return (
    <div className={cn("panel panel-hover p-4", className)}>
      <div className="mb-3 flex items-center justify-between gap-2">
        <span className="flex items-center gap-2 text-xs font-medium text-muted-foreground">
          <span className="flex h-6 w-6 items-center justify-center rounded-md bg-muted"><Icon className="h-3.5 w-3.5 text-muted-foreground" /></span>
          {label}
        </span>
        {tag}
      </div>
      {children}
    </div>
  );
}
const Big = ({ children }: { children: React.ReactNode }) => <div className="font-mono text-xl font-semibold leading-none tabular">{children}</div>;

function NumCard({ icon, label, r, unit, warn }: { icon: React.ComponentType<{ className?: string }>; label: string; r: Reading<number>; unit: string; warn?: (v: number) => boolean }) {
  const hot = r.value !== null && warn?.(r.value);
  return (
    <Card icon={icon} label={label} tag={<ProvenanceTag source={r.source} />} className={cn(r.source === "manual" && "border-dashed")}>
      {r.value === null ? <NotAvailable /> : (
        <div className={cn("font-mono text-3xl font-semibold leading-none tabular transition-colors", hot && "text-thermal")}>
          {r.source === "manual" && <span className="mr-0.5 text-xl text-warning">~</span>}
          {r.value.toFixed(unit === "°C" ? 1 : 0)}<span className="ml-1.5 text-xs font-normal uppercase tracking-wider text-muted-foreground">{unit}</span>
        </div>
      )}
    </Card>
  );
}

function BoolCard({ icon, label, r, on, off, note }: { icon: React.ComponentType<{ className?: string }>; label: string; r: Reading<boolean>; on: string; off: string; note?: string }) {
  return (
    <Card icon={icon} label={label} tag={<ProvenanceTag source={r.source} />}>
      {r.value === null ? <NotAvailable /> : (
        <div className="flex items-center gap-2">
          <span className={cn("h-2.5 w-2.5 rounded-full", r.value ? "bg-warning" : "bg-muted-foreground/40")} />
          <span className={cn("text-xl font-semibold", !r.value && "text-muted-foreground")}>{r.value ? on : off}</span>
        </div>
      )}
      {note && r.value && <p className="mt-2 text-xs text-subtle">{note}</p>}
    </Card>
  );
}

function VecCard({ icon, label, r, unit }: { icon: React.ComponentType<{ className?: string }>; label: string; r: Reading<Vec3>; unit: string }) {
  return (
    <Card icon={icon} label={`${label} · ${unit}`} tag={<ProvenanceTag source={r.source} />}>
      {!r.value ? <NotAvailable /> : (
        <div className="grid grid-cols-3 gap-2">
          {(["x", "y", "z"] as const).map((k) => (
            <div key={k} className="rounded-md bg-background/50 px-2 py-1.5">
              <div className="font-mono text-xs uppercase text-subtle">{k}</div>
              <div className="font-mono text-sm tabular">{r.value![k].toFixed(2)}</div>
            </div>
          ))}
        </div>
      )}
    </Card>
  );
}
