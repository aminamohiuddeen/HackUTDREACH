Python FastAPI backend and NVIDIA Nemotron integration for REACH.

## Run

```bash
cd backend
python -m venv .venv && .venv/Scripts/activate   # Windows; use .venv/bin/activate on macOS/Linux
pip install -r requirements.txt
cp .env.example .env
uvicorn main:app --reload        # http://localhost:8000/docs
pytest                           # tests
python simulator.py --scenario all   # needs the server running
python scripts/reset_db.py           # delete reach.db and reseed (stop the server first)
```

> **Schema change (units now have `lat`/`lng`):** delete backend/reach.db before
> first run after this change. `python scripts/reset_db.py` does this and reseeds
> in one command. `create_all` does not alter existing tables.

Env: `FRONTEND_ORIGIN` (CORS; comma-separated list allowed), `DATABASE_URL`
(default `sqlite:///./reach.db`).
`NVIDIA_API_KEY` / `NVIDIA_MODEL` configure Nemotron (`nemotron.py`). With no key
(or the `.env.example` placeholder), `nemotron.mock_mode()` is true and
`chat_with_tools()` returns a deterministic stub of the same shape.

## Evaluation

`eval.py` generates synthetic scenarios, posts them through the real API against a
scratch SQLite DB (deleted afterwards; `reach.db` is never touched), runs
`/analyze`, and checks the report's classification and status against
`classify_case()`. Two runners per scenario: the built-in mock path, and the live
agent loop driven by a scripted fake model (compliant / override / malformed /
runaway). No NVIDIA calls. Exit code 0 only if every run matches.

```bash
python eval.py                               # 20 scenarios, mock mode
python eval.py --n 100 --json > eval_results.json   # larger run for the slide
python eval.py --n 100 --pitch               # one summary line
python eval.py --check-live                  # demo prep: 3 scenarios on the real model, needs NVIDIA_API_KEY
```

## Data source labelling (simulator vs. hardware)

Every telemetry and survey record carries `source: "simulator" | "hardware"`.
**The default is `simulator`.** Real hardware (ESP32) must opt in on every
request with either:

- header `X-Reach-Source: hardware`, or
- query param `?source=hardware`

## Endpoints

| Method | Path | Notes |
|---|---|---|
| GET | `/health` | `{"status":"ok"}` |
| POST | `/api/telemetry` | ESP32 telemetry; attaches to the robot+sector's open case and reclassifies it |
| POST | `/api/surveys` | Survivor survey answers (`yes`/`no`/`unknown`, missing answers become `unknown`) |
| GET | `/api/robots` | |
| GET | `/api/cases` | `?status=` `?sector=`; ranked first (with `rank`), then verify, unverified, dispatched, cleared, resolved |
| GET | `/api/cases/{id}` | Case + telemetry + surveys |
| PATCH | `/api/cases/{id}` | `status`, `assigned_unit_id`, `notes` (human-entered only) |
| POST | `/api/cases/{id}/analyze` | Runs the classifier + coordinator agents; returns `{report, tool_log, agent_counts, mode, truncated}` (same shape in live and mock mode). Never assigns a unit |
| GET | `/api/sectors` | Seeded S1–S4 |
| GET | `/api/units` | Seeded EMS/FIRE/SAR units |

Telemetry field names are a contract with firmware and the dashboard. See
`schemas.py` and coordinate before renaming. Classification rules are in
`agents/classifier.py` and `protocol_kb/triage_protocols.md`.
