"""
Minimal test backend for the Rescue Pod.

  pip install fastapi uvicorn
  uvicorn server:app --host 0.0.0.0 --port 8000

Then, in a second Terminal tab, expose it publicly:
  brew install cloudflared
  cloudflared tunnel --url http://localhost:8000

Copy the https://....trycloudflare.com URL it prints into SERVER in
rescue_pod.ino. Keep both tabs open; the URL changes if you restart the tunnel.
"""
import datetime
import json

from fastapi import FastAPI, Request

app = FastAPI()
latest_telemetry = {}
cases = []


@app.post("/telemetry")
async def telemetry(req: Request):
    data = await req.json()
    data["received_at"] = datetime.datetime.now().isoformat()
    latest_telemetry[data.get("unit_id", "unknown")] = data
    print("TELEMETRY", data.get("sensors"))
    return {"ok": True}


@app.post("/case")
async def new_case(req: Request):
    data = await req.json()
    data["received_at"] = datetime.datetime.now().isoformat()
    cases.append(data)
    print("\n=== NEW CASE ===\n" + json.dumps(data, indent=2))
    # NEXT: send `data` to the Nemotron agent (risk level, nearest unit,
    # gear list), then write the result to Supabase for the Lovable dashboard.
    return {"ok": True}


@app.get("/state")
def state():
    return {"latest_telemetry": latest_telemetry, "cases": cases}

from fastapi.middleware.cors import CORSMiddleware
app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_methods=["*"], allow_headers=["*"])

from fastapi.middleware.cors import CORSMiddleware
app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_methods=["*"], allow_headers=["*"])
