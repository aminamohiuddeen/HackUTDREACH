// Frontend domain types for REACH. These describe what the UI needs; the FastAPI
// response schema is not final, so api.ts maps backend payloads into these shapes.

/** Where a value came from. "unavailable" means no value exists — never guess one. */
export type Provenance = "sensor" | "manual" | "unavailable";

export interface Reading<T> {
  value: T | null;
  source: Provenance;
}

export interface Vec3 {
  x: number;
  y: number;
  z: number;
}

export type Zone = "residential" | "industrial" | "road" | "unknown";
export type LocationSource = "gps" | "operator";
export type ConnectionStatus = "online" | "degraded" | "offline";
/** Where a case's data came from: the backend simulator or a physical rescue pod. */
export type DataSource = "simulator" | "hardware";

export interface QuestionAnswer {
  questionId: number;
  question: string;
  answer: string | null; // null = not answered
}

export interface SensorSnapshot {
  temperatureC: Reading<number>;
  irTriggered: Reading<boolean>;
  waterDetected: Reading<boolean>;
  motionDetected: Reading<boolean>;
  accel: Reading<Vec3>;
  gyro: Reading<Vec3>;
  anomalyAreaCm2: Reading<number>;
}

export interface Robot {
  id: string;
  connection: ConnectionStatus;
  timestamp: string; // ISO
  sectorId: string;
  lat: number;
  lon: number;
  locationSource: LocationSource;
  zone: Zone;
  sensors: SensorSnapshot;
  questionnaire: QuestionAnswer[] | null; // null = no OLED session
}

export type Classification = "likely_person" | "possible_person" | "object";
/** not_ranked: hot object that must not be ranked as a victim. resolved: a human marked the case done. */
export type CaseStatus = "ranked" | "verify" | "cleared" | "not_ranked" | "resolved";
/** 0–100 condition score. Higher = better. null = unknown/not applicable — never fabricated. */
export type Score = number | null;
export type VerificationOutcome =
  | "pending"
  | "needs_verification"
  | "person_confirmed"
  | "ruled_out";

export interface Confidence {
  /** Never a fabricated number. */
  label: "Not calibrated" | "Unknown";
  evidence: string[];
  /** Backend classifier confidence, 0–1, when the backend supplies one. Never fabricated. */
  score?: number | null | undefined;
}

export type UnitType = "EMS" | "FIRE" | "SAR";
export interface ResponseUnit {
  id: string;
  type: UnitType;
  distanceMi: number;
  availability?: string | undefined; // only shown if the backend supplies it
}

export type EventActor = "robot" | "nemotron" | "operator" | "system";
export interface TimelineEvent {
  id: string;
  at: string; // ISO
  actor: EventActor;
  title: string;
  detail?: string | undefined;
}

export interface ToolStep {
  at: string;
  tool: string;
  summary: string;
  status: "ok" | "partial" | "skipped";
}

export interface NemotronReport {
  generatedAt: string;
  incidentReport: string;
  rationale: string;
  missingData: string[];
  tools: ToolStep[];
  nearestUnits: ResponseUnit[];
}

export type ScenarioKey = "object_cleared" | "survivor_ranked" | "verify_residential" | "hot_object";

export interface RescueCase {
  id: string;
  scenario?: ScenarioKey | undefined;
  /** Set for live backend cases; absent for demo seed data. */
  source?: DataSource | undefined;
  detectedAt: string;
  robotId: string;
  sectorId: string;
  lat: number;
  lon: number;
  locationSource: LocationSource;
  zone: Zone;
  classification: Classification;
  status: CaseStatus;
  environmentalWarning: string | null;
  confidence: Confidence;
  /** How intact/safe the environment is (structure, water, heat). */
  environmentScore: Score;
  /** Survivor health condition, derived from questionnaire answers. null when no person is confirmed. */
  healthScore: Score;
  needs: string[];
  sensors: SensorSnapshot;
  questionnaire: QuestionAnswer[] | null;
  uncertaintyReasons: string[];
  verification: VerificationOutcome | null; // null when the case never entered VERIFY
  /** Set only when a human operator confirms a unit to send. REACH never dispatches itself. */
  dispatchedUnit?: { unitId: string; at: string } | undefined;
  report: NemotronReport;
  events: TimelineEvent[];
}

export type SectorCoverage = "unsearched" | "partial" | "searched";
export interface Sector {
  id: string; // e.g. "C4"
  row: number;
  col: number;
  zone: Zone;
  coverage: SectorCoverage; // tracked independently from detection classification
  lastSweep: string | null;
}
