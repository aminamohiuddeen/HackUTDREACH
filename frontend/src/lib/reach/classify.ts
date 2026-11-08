import type { CaseStatus, Classification, QuestionAnswer, SensorSnapshot, Zone } from "./types";

/** Anomaly area at or above this is treated as human-sized (frontend demo rule). */
export const HUMAN_SIZED_ANOMALY_CM2 = 1500;
/** Temperature at or above this is an environmental heat warning, not survivor evidence. */
export const HOT_OBJECT_TEMP_C = 45;

export interface ClassifyInput {
  sensors: SensorSnapshot;
  zone: Zone;
  questionnaire: QuestionAnswer[] | null;
}

export interface ClassifyResult {
  classification: Classification;
  status: CaseStatus;
  environmentalWarning: string | null;
  reasons: string[];
}

export function hasValidSurvey(q: QuestionAnswer[] | null): boolean {
  return !!q && q.some((a) => a.answer !== null);
}

/**
 * Demo mirror of the backend rules so simulated cases stay consistent.
 * IR alone never confirms a person.
 */
export function classify({ sensors, zone, questionnaire }: ClassifyInput): ClassifyResult {
  const ir = sensors.irTriggered.value === true;
  const motion = sensors.motionDetected.value === true;
  const area = sensors.anomalyAreaCm2.value;
  const humanSized = area !== null && area >= HUMAN_SIZED_ANOMALY_CM2;
  const temp = sensors.temperatureC.value;
  const hot = temp !== null && temp >= HOT_OBJECT_TEMP_C;

  if (hasValidSurvey(questionnaire)) {
    return {
      classification: "likely_person",
      status: "ranked",
      environmentalWarning: hot ? "Elevated temperature near survivor" : null,
      reasons: ["Survivor answered OLED questionnaire"],
    };
  }

  if (ir && humanSized && (zone === "residential" || motion)) {
    return {
      classification: "possible_person",
      status: "verify",
      environmentalWarning: null,
      reasons: [
        "IR triggered",
        `Human-sized anomaly (${area} cm²)`,
        zone === "residential" ? "Residential zone" : "Motion detected",
        "No questionnaire response",
      ],
    };
  }

  if (ir && motion) {
    return {
      classification: "possible_person",
      status: "verify",
      environmentalWarning: null,
      reasons: ["IR triggered", "Motion detected", "No questionnaire response"],
    };
  }

  if (hot || ir) {
    return {
      classification: "object",
      status: "not_ranked",
      environmentalWarning: hot ? `Heat source ${temp} °C` : "IR activity without corroboration",
      reasons: ["Thermal / IR activity only", "No corroborating person evidence"],
    };
  }

  return {
    classification: "object",
    status: "cleared",
    environmentalWarning: null,
    reasons: ["No survivor evidence"],
  };
}
