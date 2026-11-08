# REACH Triage Protocols

Plain-text reference for responders and the REACH agents. These rules mirror
`agents/classifier.py`. If the two disagree, the code is authoritative and this
file must be updated. REACH flags cases for human review. It never diagnoses
injuries and never dispatches units on its own.

## 1. Escalating an IR anomaly to VERIFY

An infrared trigger is a lead, not a finding. Escalate to **VERIFY** when:

- `infrared_triggered` is true **and** `anomaly_size_cm2` is human-sized
  (400–8000 cm²) **and** at least one other signal agrees (residential zone or
  motion), with no survey response yet; or
- `infrared_triggered` is true but `anomaly_size_cm2` is missing. The size is
  unknown, so the case cannot be cleared.

A VERIFY case waits up to 5 minutes (soft window) for a survey response. A late
response still counts. VERIFY cases are **never ranked**: a responder or a
survey response must confirm first.

## 2. Residential vs. industrial zone weighting

- **Residential** counts as one corroborating signal, because people are expected there.
- **Industrial / road** add no signal. Hot machinery, engines and pipes often
  trigger IR, so an IR hit in these zones needs motion or a survey to move up.
- **Unknown zone** adds no signal and is listed under `missing_signals`.
  Unknown is not treated as safe.

## 3. Signals required for likely_person

Corroborating signals:

1. IR triggered **and** anomaly 400–8000 cm²
2. Motion detected
3. Location zone = residential
4. Survey response (at least one answer that is not "unknown")

| Evidence | Classification | Status |
|---|---|---|
| Survey response (alone or with anything else) | likely_person | ranked |
| ≥2 sensor signals, no survey | possible_person | verify |
| IR fired, anomaly size missing | possible_person | verify |
| Exactly 1 sensor signal, no survey | object | unverified |
| No signals at all | object | cleared |
| No telemetry and no survey | unknown | verify |

IR on its own can **never** produce likely_person or ranked.

## 4. Unit type mapping

Responders pick the unit. REACH suggests, humans assign (`assigned_unit_id` is
human-entered only).

- **SAR**: person trapped, under debris, or location unconfirmed (VERIFY cases
  that need eyes on).
- **EMS**: person reachable and reporting injury, breathing difficulty, or
  asking for immediate help.
- **FIRE**: active heat source, structural hazard, or industrial-zone thermal
  anomaly; also forcible entry for trapped persons.

When trapped and injured are both "yes", consider SAR + EMS together.

## 5. Urgent review triggers from survey answers

Flag the case `urgent` (a review priority, not a diagnosis) if any of these is "yes":

- `injured`
- `trapped`
- `breathing_difficulty`
- `immediate_help`

`others_present = yes` does not mark the case urgent on its own, but responders
should expect more than one person at the location. Urgent ranked cases sort
above non-urgent ones; more "yes" answers sort higher.

## 6. When data is missing

- Missing is **unknown**, never safe. Unanswered survey questions default to
  "unknown", not "no".
- A survey where every answer is "unknown" means nobody responded. It does not
  count as a survey response.
- `anomaly_size_cm2` missing with IR triggered means VERIFY, not cleared.
- No telemetry and no survey means classification `unknown`, status `verify`.
- Every gap is listed in the case's `missing_signals` so responders can see
  what still needs checking.
- Vital-sign fields (`heart_rate_bpm`, `spo2_percent`) are recorded and shown,
  but never interpreted into a diagnosis.

## 7. Operator overrides

- `dispatched` and `resolved` are set by responders and are not overwritten
  by new sensor data. The classification keeps updating underneath.
- After a case is `resolved`, new data from the same robot and sector opens a
  new case.
- `cleared` set by a responder is an explicit human action. New data will
  re-evaluate the case automatically.
