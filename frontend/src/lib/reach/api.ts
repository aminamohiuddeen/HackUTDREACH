// API adapter for the FastAPI backend.
// Every request carries the user's Supabase access token as a Bearer header;
// the backend verifies it on all rescue-data endpoints.
// The adapt* functions below map the actual backend response shape.
import { supabase } from "@/integrations/supabase/client";
import { buildCases, buildRobots, buildSectors } from "./mock-data";
import type {
  CaseStatus,
  Classification,
  NemotronReport,
  QuestionAnswer,
  RescueCase,
  ResponseUnit,
  Robot,
  Sector,
  TimelineEvent,
  Zone,
} from "./types";

const API_BASE = (import.meta.env["VITE_REACH_API_BASE"] as string | undefined) ?? "";
export const DEMO_MODE = API_BASE === "";

async function getJson(path: string, init?: RequestInit): Promise<unknown> {
  const headers = new Headers(init?.headers);
  headers.set("Accept", "application/json");
  if (init?.method === "POST") headers.set("Content-Type", "application/json");
  const { data, error } = await supabase.auth.getSession();
  if (error || !data.session) throw new Error("Your session has expired. Please sign in again.");
  headers.set("Authorization", `Bearer ${data.session.access_token}`);
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
    // distance_mi from the miles-aware backend; distance_km kept for older backends.
    nearest_relevant_units: { unit_id: string; name: string; unit_type: string; distance_mi?: number; distance_km?: number }[];
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

const CLASSIFICATIONS: readonly Classification[] = ["likely_person", "possible_person", "object"];
const STATUSES: readonly CaseStatus[] = ["ranked", "verify", "cleared", "not_ranked", "resolved"];

/** Map any backend classification string onto the frontend enum ("unknown" etc. → object). */
function toClassification(v: string | null | undefined, fallback: Classification): Classification {
  if (v === "unknown") return "object";
  return CLASSIFICATIONS.includes(v as Classification) ? (v as Classification) : fallback;
}

/** Map any backend status string onto the frontend enum, so STATUS_META lookups never miss. */
function toStatus(v: string | null | undefined, fallback: CaseStatus): CaseStatus {
  if (v === "dispatched" || v === "resolved") return "resolved";
  if (v === "unverified") return "verify";
  return STATUSES.includes(v as CaseStatus) ? (v as CaseStatus) : fallback;
}

/**
 * Fields derived from the latest telemetry row and survey. GET /api/cases (CaseOut) omits
 * telemetry/surveys, so these come back "unavailable" until GET /api/cases/{id} (CaseDetail) is fetched.
 */
type TelemetryFields = Pick<RescueCase, "sensors" | "questionnaire" | "questionnaireMeta" | "zone" | "locationSource">;

function adaptTelemetryFields(raw: Pick<BackendCase, "telemetry" | "surveys">): TelemetryFields {
  const t = raw.telemetry?.[raw.telemetry.length - 1];
  const latestSurvey = raw.surveys?.[raw.surveys.length - 1];
  const answers = latestSurvey?.answers ?? {};

  const questionnaire: QuestionAnswer[] | null = latestSurvey
    ? [
        { questionId: 1, question: "Injured?", answer: answers["injured"] ?? "—" },
        { questionId: 2, question: "Trapped?", answer: answers["trapped"] ?? "—" },
        { questionId: 3, question: "Breathing difficulty?", answer: answers["breathing_difficulty"] ?? "—" },
        { questionId: 4, question: "Others present?", answer: answers["others_present"] ?? "—" },
        { questionId: 5, question: "Need immediate help?", answer: answers["immediate_help"] ?? "—" },
      ]
    : null;

  return {
    sensors: {
      temperatureC: sensorField(t?.temperature_c),
      irTriggered: sensorField(t?.infrared_triggered),
      motionDetected: sensorField(t?.motion_detected),
      accel: sensorField(t?.accelerometer),
      gyro: sensorField(t?.gyroscope),
      anomalyAreaCm2: sensorField(t?.anomaly_size_cm2 ?? null),
    },
    questionnaire,
    questionnaireMeta: latestSurvey
      ? { receivedAt: latestSurvey.timestamp, total: raw.surveys?.length ?? 1 }
      : undefined,
    zone: (t?.location_zone ?? "unknown") as Zone,
    locationSource: t?.location?.source === "operator" ? "operator" : "gps",
  };
}

function adaptOneCase(raw: BackendCase): RescueCaseWithBackendId {
  const { sensors, questionnaire, zone, locationSource: locSource } = adaptTelemetryFields(raw);
  const latest = raw.latest_report ?? null;

  // Prefer the latest Nemotron report's verdict when present; fall back to the case row.
  const caseClassification = toClassification(raw.classification, "object");
  const caseStatus = toStatus(raw.status, "verify");
  const classification = toClassification(latest?.classification, caseClassification);
  const status = toStatus(latest?.status, caseStatus);

  const report: NemotronReport = {
    generatedAt: latest?.created_at ?? raw.updated_at,
    incidentReport: latest?.rationale ?? `Pending analysis for ${classification}.`,
    rationale: latest?.rationale ?? "",
    missingData: raw.missing_signals ?? [],
    tools: [],
    nearestUnits: [],
  };

  const events: TimelineEvent[] = [
    { id: `${raw.id}-created`, at: raw.created_at, actor: "system", title: "Case created", detail: "Telemetry received" },
  ];
  if (latest) {
    events.push({ id: `${raw.id}-report-${latest.report_id}`, at: latest.created_at, actor: "nemotron", title: "Nemotron report generated" });
  }

  return {
    id: `RC-1107-${String(raw.id).padStart(3, "0")}`,
    backendId: raw.id,
    robotId: raw.robot_id,
    sectorId: raw.sector,
    zone,
    locationSource: locSource,
    lat: raw.location?.lat ?? 0,
    lon: raw.location?.lng ?? 0,
    classification,
    status,
    environmentalWarning: null,
    // The frontend never shows a numeric confidence; evidence is the backend's signal list.
    source: raw.source === "hardware" ? "hardware" : raw.source === "simulator" ? "simulator" : undefined,
    confidence: {
      label: "Not calibrated",
      score: typeof raw.confidence === "number" && Number.isFinite(raw.confidence) ? raw.confidence : null,
      evidence: [...(raw.signals ?? []), ...(latest?.classification ? [`Nemotron: ${latest.classification}`] : [])],
    },
    // Safe defaults: the backend does not compute these scores.
    environmentScore: null,
    healthScore: null,
    needs: raw.urgent_reasons ?? [],
    sensors,
    questionnaire,
    uncertaintyReasons: [...(raw.missing_signals ?? []), ...(latest?.rationale_conflict ?? [])],
    // Only VERIFY cases enter the human verification queue.
    verification: status === "verify" ? "pending" : null,
    dispatchedUnit: undefined,
    detectedAt: raw.created_at,
    events,
    report,
  };
}

const adaptCases = (raw: unknown): RescueCaseWithBackendId[] => {
  const arr = raw as { value?: BackendCase[] } | BackendCase[];
  const list = Array.isArray(arr) ? arr : (arr.value ?? []);
  return list.map(adaptOneCase);
};

const KM_TO_MI = 0.621371;
/** Prefer the backend's distance_mi; convert distance_km from older backends. Rounded to 0.1 mi. */
function toMiles(u: { distance_mi?: number; distance_km?: number }): number {
  const mi = typeof u.distance_mi === "number" ? u.distance_mi : typeof u.distance_km === "number" ? u.distance_km * KM_TO_MI : 0;
  return Math.round(mi * 10) / 10;
}

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
      distanceMi: toMiles(u),
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
  /**
   * Fetches GET /api/cases/{id} (CaseDetail) for the telemetry/survey-derived fields that the
   * list endpoint omits. Returns only those fields, to merge into the stored case.
   */
  async getCaseDetail(id: string): Promise<Partial<RescueCase>> {
    if (DEMO_MODE) return {}; // mock cases already carry full details
    const backendId = Number(id.replace(/^RC-1107-/, ""));
    if (!Number.isFinite(backendId)) return {};
    // Only the latest telemetry row is shown; a live hardware case gains one every few seconds.
    const raw = (await getJson(`/api/cases/${backendId}?telemetry_limit=1`)) as BackendCase;
    return adaptTelemetryFields(raw);
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