import type { RescueCase, Score } from "./types";

export type ScoreBand = "good" | "fair" | "poor" | "unknown";

/** Band a 0–100 condition score for display. null is never guessed — it bands as unknown. */
export function scoreBand(score: Score): ScoreBand {
  if (score == null) return "unknown";
  if (score >= 70) return "good";
  if (score >= 40) return "fair";
  return "poor";
}

/** Actionable cases a manager must look at first: ranked people + pending VERIFY. */
export function priorityRank(c: RescueCase): number {
  if (c.status === "ranked") {
    const h = c.healthScore;
    if (h != null && h < 40) return 0;
    if (h != null && h < 70) return 1;
    return 2;
  }
  if (c.status === "verify" && c.verification === "pending") return 3;
  return 9;
}

/** Cases needing a response decision, sorted by urgency then detection time. */
export function needsResponse(cases: RescueCase[]): RescueCase[] {
  return cases
    .filter((c) => priorityRank(c) < 9)
    .sort((a, b) => priorityRank(a) - priorityRank(b) || a.detectedAt.localeCompare(b.detectedAt));
}
