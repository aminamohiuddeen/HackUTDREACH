import { describe, expect, it } from "vitest";
import { classify } from "./classify";
import { buildCases, buildSectors, SCENARIOS } from "./mock-data";
import { applyVerification } from "./store";
import type { SensorSnapshot } from "./types";

const na = { value: null, source: "unavailable" as const };
const base: SensorSnapshot = {
  temperatureC: { value: 22, source: "sensor" },
  irTriggered: { value: false, source: "sensor" },
  motionDetected: { value: false, source: "sensor" },
  accel: na, gyro: na, anomalyAreaCm2: na,
};

describe("classification rules", () => {
  it("IR alone never confirms a person", () => {
    const r = classify({ sensors: { ...base, irTriggered: { value: true, source: "sensor" } }, zone: "road", questionnaire: null });
    expect(r.classification).toBe("object");
    expect(r.status).toBe("not_ranked");
  });

  it("each demo scenario gets its required classification and status", () => {
    const cases = buildCases();
    const get = (k: keyof typeof SCENARIOS) => cases.find((c) => c.id === SCENARIOS[k].caseId)!;
    expect([get("object_cleared").classification, get("object_cleared").status]).toEqual(["object", "cleared"]);
    expect([get("survivor_ranked").classification, get("survivor_ranked").status]).toEqual(["likely_person", "ranked"]);
    expect([get("verify_residential").classification, get("verify_residential").status]).toEqual(["possible_person", "verify"]);
    expect(get("hot_object").classification).toBe("object");
    expect(get("hot_object").status).toBe("not_ranked");
    expect(get("hot_object").environmentalWarning).not.toBeNull();
  });

  it("never fabricates numeric confidence", () => {
    buildCases().forEach((c) => expect(["Not calibrated", "Unknown"]).toContain(c.confidence.label));
  });
});

describe("verification", () => {
  it("ruling out a detection does not change sector coverage", () => {
    const before = buildSectors().find((s) => s.id === "D3")!.coverage;
    const c = buildCases().find((x) => x.status === "verify")!;
    const after = applyVerification(c, "ruled_out", "", "2026-11-07T23:00:00Z");
    expect(after.verification).toBe("ruled_out");
    expect(buildSectors().find((s) => s.id === "D3")!.coverage).toBe(before);
  });

  it("'still needs verification' keeps the case open", () => {
    const c = buildCases().find((x) => x.status === "verify")!;
    expect(applyVerification(c, "needs_verification", "", "2026-11-07T23:00:00Z").status).toBe("verify");
  });
});
