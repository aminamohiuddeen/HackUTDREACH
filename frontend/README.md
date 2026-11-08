# REACH Mission Control

Build a premium, functional, visually exceptional first-responder dashboard called REACH (Rescue, Evaluation, Assistance, Coordination, and Hope).

REACH is a disaster search-and-rescue platform. A remote-controlled robot collects environmental sensor readings, including temperature, infrared, water, movement, acceleration, and orientation. An OLED screen allows a survivor to answer five predefined questions.

A separate Python FastAPI backend receives data, applies classification rules, and uses NVIDIA Nemotron to organize rescue reports and retrieve nearby relevant emergency response units.

I am responsible for the frontend. Other teammates are building the backend and hardware.

Build ONLY the React frontend using TypeScript, Tailwind CSS, shadcn/ui, and Lucide icons.

## Visual direction

Make this look like a world-class emergency operations command center with the visual quality of a premium modern software product.

Use:
- Background: #0B1220
- Panel background: #151F30
- Primary blue: #3B82F6
- Warning amber: #F59E0B
- Critical red: #EF4444
- Success green: #22C55E
- Off-white accessible text
- Inter for interface text
- JetBrains Mono for technical values, coordinates, and case IDs

Create a highly intentional visual hierarchy with beautiful typography, generous but efficient spacing, refined sensor cards, subtle borders, tasteful animations, carefully styled hover states, and excellent alignment.

Use a fixed left navigation sidebar and a professional mission status header.

Avoid neon effects, excessive gradients, generic chatbot layouts, and decorative charts that provide no operational value.

## Main pages

### 1. Mission Overview

Create a polished command center overview with:
- Active cases
- Cases requiring urgent human review
- Possible-person detections awaiting verification
- Survey-confirmed person cases
- Cleared detection cases
- Unsearched sectors
- Active robot status
- Recent alerts
- Recent Nemotron reports
- A prominent, interactive disaster-zone sector grid

Include useful charts showing recent environmental readings and case status distribution.

### 2. Robot Monitor

Display live-style telemetry cards:
- Robot ID
- Connection status
- Timestamp
- Temperature (°C)
- Infrared trigger
- Water detection
- Motion detection
- Accelerometer X/Y/Z
- Gyroscope X/Y/Z
- Latitude and longitude
- Location source: GPS or operator
- Zone: residential, industrial, road, unknown
- Anomaly area (cm²), if available
- Latest OLED questionnaire answers

Distinguish actual readings, manually entered estimates, and unavailable information.

Do not implement cameras or computer vision.

### 3. Rescue Cases

Build a professional, searchable case-management interface.

Every case should display:
- Case ID
- Detection time
- Robot ID
- Sector
- Location
- Classification: likely_person, possible_person, object
- Confidence, with evidence or an unknown value
- Status: ranked, verify, cleared
- Risk level, distinct from classification confidence
- Reported needs
- Sensor readings
- Questionnaire answers
- Nemotron rationale
- Nearest relevant response units

Include a beautiful case-detail panel showing all evidence chronologically.

### 4. VERIFY Queue

Make this one of the standout features of the entire product.

Display ambiguous detections that need human investigation.

Show:
- Case location
- IR data
- Motion and anomaly measurements
- Surrounding location zone
- Questionnaire availability
- Missing evidence
- Reason the case remains uncertain
- Human verification controls
- Timeline of investigation events

Allow an operator to record:
- Still needs verification
- Person confirmed
- Detection ruled out

A detection being ruled out must NOT automatically mark the whole sector as searched or safe.

Never automatically close cases.

### 5. Nemotron Mission Intelligence

Create an AI mission-operations interface showing:
- Incident report
- Classification
- Confidence
- Status
- Risk level
- Needs
- Rationale
- Missing data
- Tool execution timeline
- Nearest relevant units for human consideration

Nearest relevant units must show:
- Unit ID
- Type: EMS, FIRE, or SAR
- Distance in kilometers
- Availability if supplied

The AI must NEVER select, assign, or dispatch a unit.

Use the exact label:
"Nearest Relevant Units (Human Decision Required)"

Do not add any proposed-assignment interface.

## Classification behavior

Provide four clearly labeled simulated scenarios:

1. Object / Cleared:
No confirmed survivor evidence. Classification object, status cleared.

2. Survivor / Ranked:
Valid survivor questionnaire received. Classification likely_person, status ranked.

3. Unresponsive Residential Anomaly / VERIFY:
IR triggered, residential zone, human-sized anomaly, no survey response. Classification possible_person, status verify.

4. Hot Object / Not Ranked:
Elevated temperature or IR activity, without corroborating evidence of a person. Do not classify it as a survivor or rank it as a victim. Use a distinct environmental-warning indicator where appropriate.

IR alone must never confirm a person.

Do not fabricate precise AI confidence scores. Use "Not calibrated" or "Unknown" for confidence if unsupported.

Ensure detection classification and search-sector coverage are tracked separately.

## Data and architecture

Use simulated frontend data initially.

Create reusable TypeScript types, mock services, and a separate API adapter for future FastAPI integration.

Expected backend endpoints include:
- GET /api/robots
- GET /api/cases
- GET /api/sectors
- GET /api/units
- POST /api/cases/{id}/analyze

The actual backend schema will be supplied later. Do not assume undocumented response fields.

Use a clear demo-mode indicator.

All navigation, case filters, scenario selection controls, verification interactions, and tabs must function using local state.

Do not connect Supabase or build a separate backend.

Do not expose API credentials in frontend code.

This is a real working dashboard prototype, not a static landing page.

Prioritize beautiful UI, clear decision support, accessible visual hierarchy, and operational trustworthiness.

This project was built with [Lovable](https://lovable.dev).

## Build with Lovable

Continue developing this project in the [Lovable editor](https://lovable.dev/projects/e15909ff-46aa-450b-99d2-0af63edee2ac).

- **Ship faster**: describe what you want to build and Lovable handles the code.
- **Stay in sync**: every change made in Lovable is committed straight to this repository.
- **Full ownership**: this code is yours. Push to `main` on GitHub and your changes sync back into Lovable, ready for your next prompt.

## Development

Prefer working locally? You need Node.js and npm — [install with nvm](https://github.com/nvm-sh/nvm#installing-and-updating).

```sh
git clone <this-repository-url>
cd <repository-name>
npm i
npm run dev
```
