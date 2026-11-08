import { createContext, useContext, useEffect, useMemo, useReducer, type ReactNode } from "react";
import { toast } from "sonner";
import { DEMO_MODE, reachApi } from "./api";
import { buildCases, buildRobots, buildSectors, SCENARIOS } from "./mock-data";
import type { NemotronReport, RescueCase, Robot, ScenarioKey, Sector, VerificationOutcome } from "./types";

interface State {
  cases: RescueCase[];
  sectors: Sector[];
  robots: Robot[];
  scenario: ScenarioKey;
}

type Action =
  | { type: "scenario"; key: ScenarioKey }
  | { type: "verify"; caseId: string; outcome: Exclude<VerificationOutcome, "pending">; note: string }
  | { type: "dispatch_unit"; caseId: string; unitId: string }
  | { type: "resolve"; caseId: string }
  | { type: "report"; caseId: string; report: NemotronReport }
  | { type: "load"; cases: RescueCase[] }
  | { type: "update_case_details"; caseId: string; details: Partial<RescueCase> };

const OUTCOME_TITLE: Record<Exclude<VerificationOutcome, "pending">, string> = {
  needs_verification: "Operator: still needs verification",
  person_confirmed: "Operator: person confirmed",
  ruled_out: "Operator: detection ruled out",
};

/** Applies a human verification decision. Never touches sector coverage. */
export function applyVerification(
  c: RescueCase,
  outcome: Exclude<VerificationOutcome, "pending">,
  note: string,
  at: string,
): RescueCase {
  const event = {
    id: `${c.id}-op-${at}`,
    at,
    actor: "operator" as const,
    title: OUTCOME_TITLE[outcome],
    detail: note || undefined,
  };
  const next: RescueCase = { ...c, verification: outcome, events: [...c.events, event] };
  if (outcome === "person_confirmed") {
    next.classification = "likely_person";
    next.status = "ranked";
  } else if (outcome === "ruled_out") {
    next.classification = "object";
    next.status = "cleared";
  } else {
    next.status = "verify";
  }
  return next;
}

function reducer(state: State, a: Action): State {
  switch (a.type) {
    case "scenario": {
      const sc = state.cases.find((c) => c.id === SCENARIOS[a.key].caseId);
      // Scenarios reference mock case IDs; with live backend cases there may be no match.
      if (!sc) return { ...state, scenario: a.key };
      const robots = state.robots.map((r) =>
        r.id === sc.robotId
          ? {
              ...r,
              sectorId: sc.sectorId,
              lat: sc.lat,
              lon: sc.lon,
              zone: sc.zone,
              locationSource: sc.locationSource,
              sensors: sc.sensors,
              questionnaire: sc.questionnaire,
              timestamp: sc.detectedAt,
            }
          : r,
      );
      return { ...state, scenario: a.key, robots };
    }
    case "verify":
      return {
        ...state,
        cases: state.cases.map((c) =>
          c.id === a.caseId ? applyVerification(c, a.outcome, a.note, new Date().toISOString()) : c,
        ),
      };
    case "dispatch_unit": {
      const at = new Date().toISOString();
      return {
        ...state,
        cases: state.cases.map((c) =>
          c.id === a.caseId
            ? {
                ...c,
                dispatchedUnit: { unitId: a.unitId, at },
                events: [
                  ...c.events,
                  { id: `${c.id}-du-${at}`, at, actor: "operator" as const, title: `Operator dispatched ${a.unitId}`, detail: "Unit selection confirmed by a human operator" },
                ],
              }
            : c,
        ),
      };
    }
    case "resolve": {
      const at = new Date().toISOString();
      return {
        ...state,
        cases: state.cases.map((c) =>
          c.id === a.caseId
            ? {
                ...c,
                status: "resolved" as const,
                events: [
                  ...c.events,
                  { id: `${c.id}-rs-${at}`, at, actor: "operator" as const, title: "Operator marked case resolved" },
                ],
              }
            : c,
        ),
      };
    }
    case "report":
      return {
        ...state,
        cases: state.cases.map((c) =>
          c.id === a.caseId
            ? {
                ...c,
                report: a.report,
                events: [
                  ...c.events,
                  { id: `${c.id}-re-${a.report.generatedAt}`, at: a.report.generatedAt, actor: "nemotron", title: "Analysis re-run", detail: "Report regenerated" },
                ],
              }
            : c,
        ),
      };
    case "load":
      // Replace cases wholesale with live backend data; sectors/robots are left as-is.
      return { ...state, cases: a.cases };
    case "update_case_details":
      // Merge detail-only fields (sensors, questionnaire, …) fetched from GET /api/cases/{id}.
      return {
        ...state,
        cases: state.cases.map((c) => (c.id === a.caseId ? { ...c, ...a.details } : c)),
      };
  }
}

interface Ctx extends State {
  dispatch: (a: Action) => void;
}
const ReachContext = createContext<Ctx | null>(null);

export function ReachProvider({ children }: { children: ReactNode }) {
  const [state, dispatch] = useReducer(reducer, undefined, () => ({
    // DEMO_MODE: mock seed. Live mode: start empty and load from the backend on mount.
    cases: DEMO_MODE ? buildCases() : [],
    sectors: buildSectors(),
    robots: buildRobots(),
    scenario: "verify_residential" as ScenarioKey,
  }));
  useEffect(() => {
    if (DEMO_MODE) return;
    let cancelled = false;
    reachApi
      .getCases()
      // GET /api/cases omits telemetry/surveys; fetch each case's detail in parallel so the
      // dashboard, survivor list and case list are populated. A failed detail falls back to the summary.
      .then((cases) =>
        Promise.all(
          cases.map((c) =>
            reachApi
              .getCaseDetail(c.id)
              .then((details) => ({ ...c, ...details }))
              .catch(() => c),
          ),
        ),
      )
      .then((cases) => {
        if (!cancelled) dispatch({ type: "load", cases });
      })
      .catch((e: unknown) => {
        if (!cancelled) toast.error("Could not load cases", { description: e instanceof Error ? e.message : String(e) });
      });
    return () => {
      cancelled = true;
    };
  }, []);
  const value = useMemo(() => ({ ...state, dispatch }), [state]);
  return <ReachContext.Provider value={value}>{children}</ReachContext.Provider>;
}

/**
 * Loads the full case detail (sensors, questionnaire) when a case is opened.
 * No-op in DEMO_MODE, where mock cases already include these fields.
 */
export function useCaseDetail(caseId: string | undefined) {
  const { dispatch } = useReach();
  useEffect(() => {
    if (!caseId || DEMO_MODE) return;
    let cancelled = false;
    reachApi
      .getCaseDetail(caseId)
      .then((details) => {
        if (!cancelled && Object.keys(details).length) dispatch({ type: "update_case_details", caseId, details });
      })
      .catch((e: unknown) => {
        if (!cancelled) toast.error("Could not load case details", { description: e instanceof Error ? e.message : String(e) });
      });
    return () => {
      cancelled = true;
    };
  }, [caseId, dispatch]);
}

export function useReach() {
  const ctx = useContext(ReachContext);
  if (!ctx) throw new Error("useReach must be inside ReachProvider");
  return ctx;
}
