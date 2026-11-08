import { describe, expect, it } from "vitest";
import { buildCases } from "./mock-data";
import { applyVerification, mergeLiveCases } from "./store";
import type { RescueCase } from "./types";

const base = (): RescueCase => ({ ...buildCases()[0]!, report: { ...buildCases()[0]!.report, tools: [] } });

describe("mergeLiveCases (periodic live refresh)", () => {
  it("takes the backend's latest sensors and adds new cases", () => {
    const prev = [base()];
    const fresh = { ...base(), sensors: { ...base().sensors, motionDetected: { value: true, source: "sensor" as const } } };
    const added = { ...base(), id: "RC-1107-099" };
    const out = mergeLiveCases(prev, [fresh, added]);
    expect(out).toHaveLength(2);
    expect(out[0]!.sensors.motionDetected.value).toBe(true);
    expect(out[1]!.id).toBe("RC-1107-099");
  });

  it("drops cases the backend no longer returns", () => {
    expect(mergeLiveCases([base()], [])).toEqual([]);
  });

  it("keeps an analysis run in this session when the backend has no tool log", () => {
    const analyzed = { ...base(), report: { ...base().report, tools: [{ at: "t", tool: "classifier:get_case_evidence", summary: "s", status: "ok" as const }] } };
    const out = mergeLiveCases([analyzed], [base()]);
    expect(out[0]!.report.tools).toHaveLength(1);
  });

  it("keeps operator decisions, their timeline events and a confirmed unit", () => {
    const decided = { ...applyVerification(base(), "ruled_out", "debris", "2026-11-08T08:00:00Z"), dispatchedUnit: { unitId: "EMS-14", at: "x" } };
    const fresh = { ...base(), status: "verify" as const, classification: "possible_person" as const, verification: "pending" as const };
    const out = mergeLiveCases([decided], [fresh])[0]!;
    expect(out.status).toBe("cleared");
    expect(out.classification).toBe("object");
    expect(out.verification).toBe("ruled_out");
    expect(out.events.some((e) => e.actor === "operator")).toBe(true);
    expect(out.dispatchedUnit?.unitId).toBe("EMS-14");
  });

  it("follows the backend's classification when no operator has decided", () => {
    const fresh = { ...base(), status: "ranked" as const, classification: "likely_person" as const };
    const out = mergeLiveCases([base()], [fresh])[0]!;
    expect(out.status).toBe("ranked");
    expect(out.classification).toBe("likely_person");
  });
});
