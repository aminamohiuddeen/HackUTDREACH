import { classify } from "./classify";
import type {
  QuestionAnswer,
  Reading,
  RescueCase,
  Robot,
  ScenarioKey,
  Sector,
  SensorSnapshot,
  TimelineEvent,
  Vec3,
  Zone,
  NemotronReport,
  ResponseUnit,
  LocationSource,
} from "./types";

// Fixed mission clock so server and client render identical data.
export const MISSION_START = "2026-11-07T19:30:00Z";
const t = (hhmmss: string) => `2026-11-07T${hhmmss}Z`;

const s = <T,>(value: T): Reading<T> => ({ value, source: "sensor" });
const m = <T,>(value: T): Reading<T> => ({ value, source: "manual" });
const na = <T,>(): Reading<T> => ({ value: null, source: "unavailable" });
const v = (x: number, y: number, z: number): Vec3 => ({ x, y, z });

export const QUESTIONS = [
  "Are you injured?",
  "Can you move on your own?",
  "How many people are with you?",
  "Is it hard to breathe?",
  "Do you need water or medication?",
];

const survey = (answers: (string | null)[]): QuestionAnswer[] =>
  QUESTIONS.map((question, i) => ({ questionId: i + 1, question, answer: answers[i] ?? null }));

export const SCENARIOS: Record<ScenarioKey, { label: string; short: string; caseId: string; summary: string }> = {
  object_cleared: {
    label: "Object / Cleared",
    short: "Cleared",
    caseId: "RC-1107-001",
    summary: "No survivor evidence. Debris pile on road segment.",
  },
  survivor_ranked: {
    label: "Survivor / Ranked",
    short: "Ranked",
    caseId: "RC-1107-002",
    summary: "Valid OLED questionnaire received from survivor.",
  },
  verify_residential: {
    label: "Unresponsive Residential Anomaly / VERIFY",
    short: "VERIFY",
    caseId: "RC-1107-003",
    summary: "IR + human-sized anomaly in residential zone. No survey response.",
  },
  hot_object: {
    label: "Hot Object / Not Ranked",
    short: "Not ranked",
    caseId: "RC-1107-004",
    summary: "Elevated heat and IR with no corroborating person evidence.",
  },
};

interface Seed {
  id: string;
  scenario?: ScenarioKey;
  detectedAt: string;
  robotId: string;
  sectorId: string;
  lat: number;
  lon: number;
  locationSource: LocationSource;
  zone: Zone;
  environmentScore: number;
  healthScore: number | null;
  needs: string[];
  sensors: SensorSnapshot;
  questionnaire: QuestionAnswer[] | null;
  evidence: string[];
  uncertainty: string[];
  report: NemotronReport;
  extraEvents?: TimelineEvent[];
}

const units = (...u: ResponseUnit[]) => u;

const seeds: Seed[] = [
  {
    id: "RC-1107-001",
    scenario: "object_cleared",
    detectedAt: t("21:12:40"),
    robotId: "REACH-01",
    sectorId: "B2",
    lat: 29.76312,
    lon: -95.36844,
    locationSource: "gps",
    zone: "road",
    environmentScore: 84,
    healthScore: null,
    needs: [],
    sensors: {
      temperatureC: s(21.4),
      irTriggered: s(false),
      waterDetected: s(false),
      motionDetected: s(false),
      accel: s(v(0.02, -0.01, 9.79)),
      gyro: s(v(0.4, -0.2, 0.1)),
      anomalyAreaCm2: s(820),
    },
    questionnaire: null,
    evidence: ["IR not triggered", "No motion", "Ambient temperature"],
    uncertainty: [],
    report: {
      generatedAt: t("21:13:22"),
      incidentReport:
        "Robot REACH-01 inspected a debris pile on the Main St road segment (B2). No thermal, motion, or survivor response was recorded. Detection classified as object.",
      rationale:
        "No sensor channel indicated a person: IR inactive, no motion, ambient temperature 21.4 °C, no questionnaire interaction.",
      missingData: [],
      tools: [
        { at: t("21:13:01"), tool: "classify_detection", summary: "Rules → object / cleared", status: "ok" },
        { at: t("21:13:12"), tool: "summarize_report", summary: "Incident report drafted", status: "ok" },
        { at: t("21:13:20"), tool: "query_nearby_units", summary: "Skipped — no person evidence", status: "skipped" },
      ],
      nearestUnits: [],
    },
  },
  {
    id: "RC-1107-002",
    scenario: "survivor_ranked",
    detectedAt: t("21:48:05"),
    robotId: "REACH-01",
    sectorId: "C4",
    lat: 29.76088,
    lon: -95.36219,
    locationSource: "gps",
    zone: "residential",
    environmentScore: 36,
    healthScore: 44,
    needs: ["Medical assessment", "Extraction — immobile", "Water"],
    sensors: {
      temperatureC: s(29.8),
      irTriggered: s(true),
      waterDetected: s(true),
      motionDetected: s(true),
      accel: s(v(0.11, 0.04, 9.81)),
      gyro: s(v(1.2, 0.6, -0.3)),
      anomalyAreaCm2: s(2650),
    },
    questionnaire: survey(["Yes", "No", "2", "No", "Water"]),
    evidence: ["OLED questionnaire answered (5/5)", "IR + motion corroborate"],
    uncertainty: [],
    report: {
      generatedAt: t("21:49:31"),
      incidentReport:
        "Survivor located in collapsed residence, 1400 block Elm (C4). Survivor reports injury, cannot move unaided, one additional person present. Requests water. Standing water detected at robot position.",
      rationale:
        "Questionnaire responses are direct survivor evidence. Health score lowered by reported injury and immobility; environment integrity lowered by standing water and structural collapse.",
      missingData: ["Identity of second occupant", "Structural stability assessment"],
      tools: [
        { at: t("21:48:40"), tool: "classify_detection", summary: "Rules → likely_person / ranked", status: "ok" },
        { at: t("21:48:58"), tool: "extract_needs", summary: "3 needs from questionnaire", status: "ok" },
        { at: t("21:49:10"), tool: "query_nearby_units", summary: "4 units within 6 km", status: "ok" },
        { at: t("21:49:29"), tool: "summarize_report", summary: "Incident report drafted", status: "ok" },
      ],
      nearestUnits: units(
        { id: "EMS-14", type: "EMS", distanceKm: 1.8, availability: "Available" },
        { id: "SAR-03", type: "SAR", distanceKm: 2.4, availability: "On scene — Sector D" },
        { id: "FIRE-22", type: "FIRE", distanceKm: 3.1 },
        { id: "EMS-09", type: "EMS", distanceKm: 5.7, availability: "Available" },
      ),
    },
  },
  {
    id: "RC-1107-003",
    scenario: "verify_residential",
    detectedAt: t("22:06:18"),
    robotId: "REACH-01",
    sectorId: "D3",
    lat: 29.75851,
    lon: -95.36472,
    locationSource: "gps",
    zone: "residential",
    environmentScore: 52,
    healthScore: null,
    needs: ["Unknown — no survivor response"],
    sensors: {
      temperatureC: s(31.2),
      irTriggered: s(true),
      waterDetected: s(false),
      motionDetected: s(false),
      accel: s(v(0.05, 0.02, 9.8)),
      gyro: s(v(0.3, 0.1, 0.0)),
      anomalyAreaCm2: s(2380),
    },
    questionnaire: null,
    evidence: ["IR triggered", "Anomaly 2380 cm² (human-sized)", "Residential zone"],
    uncertainty: [
      "IR alone cannot confirm a person",
      "No questionnaire response — survivor may be unconscious, or no one is present",
      "No motion detected over 4 minutes of observation",
    ],
    report: {
      generatedAt: t("22:07:44"),
      incidentReport:
        "Human-sized thermal anomaly beneath partial roof collapse, 900 block Oak (D3). No response to OLED prompts. No motion observed.",
      rationale:
        "IR activity and anomaly size are consistent with a person but also with warm debris or an animal. Without a questionnaire response or motion, a person cannot be confirmed. Routed to human verification.",
      missingData: ["Questionnaire response", "Motion"],
      tools: [
        { at: t("22:06:50"), tool: "classify_detection", summary: "Rules → possible_person / verify", status: "ok" },
        { at: t("22:07:05"), tool: "flag_missing_data", summary: "4 evidence gaps flagged", status: "partial" },
        { at: t("22:07:22"), tool: "query_nearby_units", summary: "3 units within 5 km", status: "ok" },
        { at: t("22:07:41"), tool: "summarize_report", summary: "Incident report drafted", status: "ok" },
      ],
      nearestUnits: units(
        { id: "SAR-03", type: "SAR", distanceKm: 0.9, availability: "On scene — Sector D" },
        { id: "EMS-14", type: "EMS", distanceKm: 2.2, availability: "Available" },
        { id: "FIRE-22", type: "FIRE", distanceKm: 3.6 },
      ),
    },
    extraEvents: [
      { id: "e3-op1", at: t("22:11:02"), actor: "operator", title: "Operator repositioned robot", detail: "Approached anomaly from north side; access blocked by beam." },
      { id: "e3-r2", at: t("22:14:30"), actor: "robot", title: "OLED prompt repeated", detail: "No response after 3 attempts." },
    ],
  },
  {
    id: "RC-1107-004",
    scenario: "hot_object",
    detectedAt: t("22:19:51"),
    robotId: "REACH-02",
    sectorId: "E5",
    lat: 29.75502,
    lon: -95.35711,
    locationSource: "operator",
    zone: "industrial",
    environmentScore: 18,
    healthScore: null,
    needs: ["Hazard awareness for responders"],
    sensors: {
      temperatureC: s(68.5),
      irTriggered: s(true),
      waterDetected: s(false),
      motionDetected: s(false),
      accel: s(v(0.01, 0.0, 9.8)),
      gyro: s(v(0.1, 0.0, 0.0)),
      anomalyAreaCm2: m(400),
    },
    questionnaire: null,
    evidence: ["Temperature 68.5 °C", "IR triggered", "No motion, no survey"],
    uncertainty: [],
    report: {
      generatedAt: t("22:21:03"),
      incidentReport:
        "Heat source detected at warehouse loading dock (E5), likely a damaged electrical transformer. No indicators of a person. Environmental hazard noted for responders entering the sector.",
      rationale:
        "Elevated temperature and IR are present but uncorroborated: no motion, no questionnaire, small anomaly (operator estimate). Not ranked as a victim. Flagged as an environmental warning.",
      missingData: ["Precise anomaly area (operator estimate only)", "Heat source identification"],
      tools: [
        { at: t("22:20:24"), tool: "classify_detection", summary: "Rules → object / not ranked + heat warning", status: "ok" },
        { at: t("22:20:40"), tool: "query_nearby_units", summary: "FIRE units only (hazard)", status: "ok" },
        { at: t("22:21:01"), tool: "summarize_report", summary: "Incident report drafted", status: "ok" },
      ],
      nearestUnits: units({ id: "FIRE-22", type: "FIRE", distanceKm: 1.4 }, { id: "FIRE-07", type: "FIRE", distanceKm: 4.9, availability: "Available" }),
    },
  },
  {
    id: "RC-1107-005",
    detectedAt: t("22:31:09"),
    robotId: "REACH-02",
    sectorId: "A5",
    lat: 29.76598,
    lon: -95.35902,
    locationSource: "operator",
    zone: "unknown",
    environmentScore: 28,
    healthScore: null,
    needs: ["Unknown"],
    sensors: {
      temperatureC: s(27.1),
      irTriggered: s(true),
      waterDetected: s(true),
      motionDetected: s(true),
      accel: s(v(0.3, -0.2, 9.6)),
      gyro: s(v(4.1, -2.2, 0.8)),
      anomalyAreaCm2: na(),
    },
    questionnaire: null,
    evidence: ["IR triggered", "Motion detected"],
    uncertainty: [
      "Anomaly size unavailable — robot tilted on unstable surface",
      "Zone unknown; location entered by operator",
      "Motion may be from water flow",
    ],
    report: {
      generatedAt: t("22:32:15"),
      incidentReport: "IR and motion detected near flooded underpass (A5). Robot unstable; anomaly measurement failed.",
      rationale: "Two signals present but both have plausible non-human sources (moving water). Requires human verification.",
      missingData: ["Anomaly area", "Questionnaire response", "Zone classification", "GPS fix"],
      tools: [
        { at: t("22:31:40"), tool: "classify_detection", summary: "Rules → possible_person / verify", status: "ok" },
        { at: t("22:31:58"), tool: "flag_missing_data", summary: "4 evidence gaps flagged", status: "partial" },
        { at: t("22:32:12"), tool: "query_nearby_units", summary: "2 units within 5 km", status: "ok" },
      ],
      nearestUnits: units({ id: "SAR-11", type: "SAR", distanceKm: 1.2 }, { id: "EMS-09", type: "EMS", distanceKm: 3.3, availability: "Available" }),
    },
  },
  {
    id: "RC-1107-006",
    detectedAt: t("22:38:47"),
    robotId: "REACH-01",
    sectorId: "F2",
    lat: 29.75204,
    lon: -95.36677,
    locationSource: "gps",
    zone: "residential",
    environmentScore: 76,
    healthScore: 80,
    needs: ["Medical check", "Medication"],
    sensors: {
      temperatureC: s(24.6),
      irTriggered: s(true),
      waterDetected: s(false),
      motionDetected: s(true),
      accel: s(v(0.04, 0.01, 9.8)),
      gyro: s(v(0.6, 0.2, 0.1)),
      anomalyAreaCm2: s(3100),
    },
    questionnaire: survey(["No", "Yes", "1", null, "Medication"]),
    evidence: ["OLED questionnaire answered (4/5)"],
    uncertainty: [],
    report: {
      generatedAt: t("22:40:02"),
      incidentReport: "Ambulatory survivor sheltering in garage, Pine Ct (F2). Not injured; requests medication.",
      rationale: "Questionnaire responses confirm a responsive, ambulatory person.",
      missingData: ["Breathing question unanswered"],
      tools: [
        { at: t("22:39:20"), tool: "classify_detection", summary: "Rules → likely_person / ranked", status: "ok" },
        { at: t("22:39:35"), tool: "extract_needs", summary: "2 needs from questionnaire", status: "ok" },
        { at: t("22:39:50"), tool: "query_nearby_units", summary: "3 units within 6 km", status: "ok" },
      ],
      nearestUnits: units(
        { id: "EMS-21", type: "EMS", distanceKm: 1.1, availability: "Available" },
        { id: "SAR-03", type: "SAR", distanceKm: 3.0 },
        { id: "EMS-14", type: "EMS", distanceKm: 4.6, availability: "Committed" },
      ),
    },
  },
];

function buildEvents(sd: Seed): TimelineEvent[] {
  const base: TimelineEvent[] = [
    { id: `${sd.id}-det`, at: sd.detectedAt, actor: "robot", title: `Detection logged by ${sd.robotId}`, detail: sd.evidence.join(" · ") },
    ...sd.report.tools.map((tool, i) => ({
      id: `${sd.id}-tool-${i}`,
      at: tool.at,
      actor: "nemotron" as const,
      title: tool.tool,
      detail: tool.summary,
    })),
    { id: `${sd.id}-rep`, at: sd.report.generatedAt, actor: "nemotron", title: "Report published", detail: "Awaiting human review" },
    ...(sd.extraEvents ?? []),
  ];
  return base.sort((a, b) => a.at.localeCompare(b.at));
}

export function buildCases(): RescueCase[] {
  return seeds.map((sd) => {
    const r = classify({ sensors: sd.sensors, zone: sd.zone, questionnaire: sd.questionnaire });
    return {
      id: sd.id,
      scenario: sd.scenario,
      detectedAt: sd.detectedAt,
      robotId: sd.robotId,
      sectorId: sd.sectorId,
      lat: sd.lat,
      lon: sd.lon,
      locationSource: sd.locationSource,
      zone: sd.zone,
      classification: r.classification,
      status: r.status,
      environmentalWarning: r.environmentalWarning,
      confidence: {
        label: r.classification === "possible_person" ? "Unknown" : "Not calibrated",
        evidence: sd.evidence,
      },
      environmentScore: sd.environmentScore,
      healthScore: sd.healthScore,
      needs: sd.needs,
      sensors: sd.sensors,
      questionnaire: sd.questionnaire,
      uncertaintyReasons: sd.uncertainty,
      verification: r.status === "verify" ? "pending" : null,
      report: sd.report,
      events: buildEvents(sd),
    };
  });
}

const ROWS = ["A", "B", "C", "D", "E", "F"];
const zoneMap: Zone[][] = [
  ["road", "road", "residential", "residential", "unknown", "unknown"],
  ["road", "road", "residential", "residential", "industrial", "unknown"],
  ["residential", "residential", "residential", "residential", "industrial", "industrial"],
  ["residential", "residential", "residential", "road", "industrial", "industrial"],
  ["residential", "road", "road", "road", "industrial", "industrial"],
  ["residential", "residential", "residential", "road", "unknown", "unknown"],
];
const coverageMap = [
  "SSPPUU",
  "SSSPPU",
  "PSSPUU",
  "PPPUUU",
  "UUPUPU",
  "UPUUUU",
];

export function buildSectors(): Sector[] {
  const out: Sector[] = [];
  ROWS.forEach((r, ri) => {
    for (let c = 0; c < 6; c++) {
      const code = coverageMap[ri]![c];
      out.push({
        id: `${r}${c + 1}`,
        row: ri,
        col: c,
        zone: zoneMap[ri]![c]!,
        coverage: code === "S" ? "searched" : code === "P" ? "partial" : "unsearched",
        lastSweep: code === "U" ? null : t(`2${1 + ((ri + c) % 2)}:${String(10 + ri * 7 + c).padStart(2, "0")}:00`),
      });
    }
  });
  return out;
}

export function buildRobots(): Robot[] {
  const c = buildCases();
  const verify = c.find((x) => x.id === "RC-1107-003")!;
  const hot = c.find((x) => x.id === "RC-1107-004")!;
  return [
    {
      id: "REACH-01",
      connection: "online",
      timestamp: t("22:41:12"),
      sectorId: verify.sectorId,
      lat: verify.lat,
      lon: verify.lon,
      locationSource: "gps",
      zone: verify.zone,
      sensors: verify.sensors,
      questionnaire: null,
    },
    {
      id: "REACH-02",
      connection: "degraded",
      timestamp: t("22:40:55"),
      sectorId: hot.sectorId,
      lat: hot.lat,
      lon: hot.lon,
      locationSource: "operator",
      zone: hot.zone,
      sensors: hot.sensors,
      questionnaire: null,
    },
  ];
}

/** Recent temperature + IR samples for REACH-01 (last 30 min, 1-minute cadence). */
export const TEMP_SERIES = Array.from({ length: 31 }, (_, i) => {
  const minute = 10 + i;
  const base = 22 + Math.sin(i / 4) * 1.6 + (i > 18 && i < 25 ? (i - 18) * 1.4 : 0) + (i >= 25 ? 8 - (i - 25) * 0.6 : 0);
  return {
    time: `22:${String(minute).padStart(2, "0")}`,
    temperature: Math.round(base * 10) / 10,
    ir: i > 19 && i < 27 ? 1 : 0,
  };
});
