// API adapter for the FastAPI backend.
// NOTE: auth header + Supabase session check bypassed for demo.
// The adapt* functions below map the actual backend response shape.
import { buildCases, buildRobots, buildSectors } from "./mock-data";
import type { NemotronReport, RescueCase, ResponseUnit, Robot, Sector } from "./types";

const API_BASE = (import.meta.env["VITE_REACH_API_BASE"] as string | undefined) ?? "";
export const DEMO_MODE = API_BASE === "";

async function getJson(path: string, init?: RequestInit): Promise<unknown> {
  const headers = new Headers(init?.headers);
  headers.set("Accept", "application/json");
  if (init?.method === "POST") headers.set("Content-Type", "application/json");
  const res = await fetch(`${API_BASE}${path}`, { ...init, headers });
  if (!res.ok) throw new Error(`REACH API ${path} failed: ${res.status}`);
  return res.json();
}

// --- backend shapes ---

type BackendCase = {
  id: number;
  robot_id: string;
  sector: string;
  classification: "likely_person" | "possible_person" | "object" | "unknown";
  confidence: number;
  status: "verify" | "ranked" | "unverified" | "cleared" | "dispatched" | "resolved";
  missing_signals: string[];
  signals: string[];
  urgent: boolean;
  urgent_reasons: string[];
  location: { lat: number; lng: number } | null;
  source: string;
  rank: number | null;
  created_at: string;
  updated_at: string;
  telemetry?: BackendTelemetry[];
  surveys?: BackendSurvey[];
  latest_report?: BackendReport | null;
};

type BackendTelemetry = {
  id: number;
  temperature_c: number;
  water_detected: boolean;
  infrared_triggered: boolean;
  anomaly_size_cm2: number | null;
  motion_detected: boolean;
  location_zone: string;
  accelerometer: { x: number; y: number; z: number };
  gyroscope: { x: number; y: number; z: number };
  location: { lat: number; lng: number; source: string };
  timestamp: string;
  source: string;
};

type BackendSurvey = {
  id: number;
  answers: Record<string, string>;
  timestamp: string;
};

type BackendReport = {
  report_id: number;
  rationale: string;
  rationale_conflict: string[];
  classification: string | null;
  status: string | null;
  created_at: string;
};

type BackendAnalyzeResponse = {
  report?: {
    classification: string;
    confidence: number;
    status: string;
    risk_level: string;
    needs: string[];
    nearest_relevant_units: { unit_id: string; name: string; unit_type: string; distance_km: number }[];
    protocol_cited: string;
    rationale: string;
    rationale_conflict: string[];
  };
  tool_log?: { agent: string; tool: string; thought: string | null }[];
};

// --- helpers ---

const SENSOR_SRC = "sensor" as const;
const UNAVAILABLE_SRC = "unavailable" as const;

function sensorField<T>(value: T | null | undefined): { value: T | null; source: "sensor" | "unavailable" } {
  return value === null || value === undefined
    ? { value: null, source: UNAVAILABLE_SRC }
    : { value, source: SENSOR_SRC };
}

// Case IDs: frontend uses "RC-1107-002" style, backend uses integers.
// We stash the backend integer on each RescueCase as `backendId` so analyzeCase can find it.
type RescueCaseWithBackendId = RescueCase & { backendId: number };

function adaptOneCase(raw: BackendCase): RescueCaseWithBackendId {
  const t = raw.telemetry?.[raw.telemetry.length - 1];
  const latestSurvey = raw.surveys?.[raw.surveys.length - 1];
  const answers = latestSurvey?.answers ?? {};

  const questionnaire = latestSurvey
    ? [
        { questionId: 1, question: "Injured?", answer: answers.injured ?? "—" },
        { questionId: 2, question: "Trapped?", answer: answers.trapped ?? "—" },
        { questionId: 3, question: "Breathing difficulty?", answer: answers.breathing_difficulty ?? "—" },
        { questionId: 4, question: "Others present?", answer: answers.others_present ?? "—" },
        { questionId: 5, question: "Need immediate help?", answer: answers.immediate_help ?? "—" },
      ]
    : null;

  const zone = (t?.location_zone ?? "unknown") as "residential" | "industrial" | "road" | "unknown";
  const locSource = t?.location?.source === "operator" ? "operator" : "gps";

  const report: NemotronReport = {
    generatedAt: raw.latest_report?.created_at ?? raw.updated_at,
    incidentReport:
      raw.latest_report?.rationale ??
      `Case ${raw.id}: ${raw.classification} with status ${raw.status}. Run analysis to generate a Nemotron report.`,
    rationale: raw.latest_report?.rationale ?? "",
    missingData: raw.missing_signals ?? [],
    tools: [],
    nearestUnits: [],
  };

  return {
    id: `RC-1107-${String(raw.id).padStart(3, "0")}`,
    backendId: raw.id,
    robotId: raw.robot_id,
    sectorId: raw.sector,
    zone,
    locationSource: locSource,
    lat: raw.location?.lat ?? 0,
    lon: raw.location?.lng ?? 0,
    classification: raw.classification === "unknown" ? "object" : raw.classification,
    status: raw.status === "dispatched" || raw.status === "resolved" ? "resolved" : raw.status,
    confidence: {
      label: raw.confidence >= 0.9 ? "high" : raw.confidence >= 0.6 ? "medium" : "low",
      evidence: raw.signals ?? [],
    } as RescueCase["confidence"],
    needs: raw.urgent_reasons ?? [],
    sensors: {
      temperatureC: sensorField(t?.temperature_c),
      irTriggered: sensorField(t?.infrared_triggered),
      waterDetected: sensorField(t?.water_detected),
      motionDetected: sensorField(t?.motion_detected),
      accel: sensorField(t?.accelerometer),
      gyro: sensorField(t?.gyroscope),
      anomalyAreaCm2: sensorField(t?.anomaly_size_cm2 ?? null),
    },
    questionnaire,
    detectedAt: raw.created_at,
    events: [],
    report,
  } as unknown as RescueCaseWithBackendId;
}

const adaptCases = (raw: unknown): RescueCaseWithBackendId[] => {
  const arr = raw as { value?: BackendCase[] } | BackendCase[];
  const list = Array.isArray(arr) ? arr : (arr.value ?? []);
  return list.map(adaptOneCase);
};

const adaptReport = (raw: unknown): NemotronReport => {
  const body = raw as BackendAnalyzeResponse;
  const r = body.report;
  const log = body.tool_log ?? [];
  const now = new Date().toISOString();
  return {
    generatedAt: now,
    incidentReport: r?.rationale ?? "Analysis complete.",
    rationale: r?.rationale ?? "",
    missingData: [],
    tools: log.map((e) => ({
      at: now,
      tool: `${e.agent}:${e.tool}`,
      summary: e.thought ?? "(no reasoning summary)",
      status: "ok" as const,
    })),
    nearestUnits: (r?.nearest_relevant_units ?? []).map((u) => ({
      id: u.unit_id,
      type: u.unit_type as "EMS" | "FIRE" | "SAR",
      distanceKm: u.distance_km,
      availability: undefined,
    })),
  } as unknown as NemotronReport;
};

const adaptRobots = (_raw: unknown): Robot[] => buildRobots();
const adaptSectors = (_raw: unknown): Sector[] => buildSectors();
const adaptUnits = (_raw: unknown): ResponseUnit[] => {
  const seen = new Map<string, ResponseUnit>();
  buildCases().forEach((c) => c.report.nearestUnits.forEach((u) => seen.set(u.id, u)));
  return [...seen.values()];
};

const delay = (ms: number) => new Promise((r) => setTimeout(r, ms));

// --- public API ---

export const reachApi = {
  async getRobots(): Promise<Robot[]> {
    return DEMO_MODE ? buildRobots() : adaptRobots(await getJson("/api/robots"));
  },
  async getCases(): Promise<RescueCase[]> {
    return DEMO_MODE ? buildCases() : adaptCases(await getJson("/api/cases"));
  },
  async getSectors(): Promise<Sector[]> {
    return DEMO_MODE ? buildSectors() : adaptSectors(await getJson("/api/sectors"));
  },
  async getUnits(): Promise<ResponseUnit[]> {
    if (!DEMO_MODE) return adaptUnits(await getJson("/api/units"));
    const seen = new Map<string, ResponseUnit>();
    buildCases().forEach((c) => c.report.nearestUnits.forEach((u) => seen.set(u.id, u)));
    return [...seen.values()];
  },
  async analyzeCase(id: string, current: NemotronReport): Promise<NemotronReport> {
    if (!DEMO_MODE) {
      // id looks like "RC-1107-002". Look up the real backend integer.
      const all = (await this.getCases()) as RescueCaseWithBackendId[];
      const match = all.find((c) => c.id === id);
      const backendId = match?.backendId ?? Number(id.replace(/^RC-1107-/, "")) ?? 0;
      return adaptReport(await getJson(`/api/cases/${backendId}/analyze`, { method: "POST" }));
    }
    await delay(1400);
    const now = new Date().toISOString();
    return {
      ...current,
      generatedAt: now,
      tools: [
        ...current.tools,
        { at: now, tool: "classify_detection", summary: "Re-evaluated with latest telemetry (demo)", status: "ok" },
        { at: now, tool: "query_nearby_units", summary: "Unit distances refreshed (demo)", status: "ok" },
        { at: now, tool: "summarize_report", summary: "Report regenerated (demo)", status: "ok" },
      ],
    };
  },
};