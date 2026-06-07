"""FastAPI server.

  GET  /                -> the 150+1 frontend (place 150plus1.html in ../web/)
  GET  /api/latest.json -> latest model output
  POST /api/rebuild     -> trigger a rebuild (guard with a token in production)

Run:  uvicorn api.server:app --reload --port 8000
"""
import json
import os

from fastapi import FastAPI, HTTPException, Header
from fastapi.responses import JSONResponse, FileResponse
from fastapi.staticfiles import StaticFiles

from pipeline.build_model import build

HERE = os.path.dirname(__file__)
LATEST = os.path.join(HERE, "latest.json")
WEB_DIR = os.path.join(HERE, "..", "web")
REBUILD_TOKEN = os.environ.get("REBUILD_TOKEN", "")

app = FastAPI(title="150+1 model API")


@app.get("/api/latest.json")
def latest():
    if not os.path.exists(LATEST):
        raise HTTPException(404, "Δεν υπάρχει ακόμα έξοδος — τρέξτε build_model.")
    with open(LATEST, encoding="utf-8") as f:
        return JSONResponse(json.load(f))


@app.post("/api/rebuild")
def rebuild(x_token: str = Header(default="")):
    if REBUILD_TOKEN and x_token != REBUILD_TOKEN:
        raise HTTPException(401, "unauthorized")
    out = build()
    return {"ok": True, "generated_at": out["generated_at"]}


# Serve the frontend. Put 150plus1.html as web/index.html so it loads at "/".
# StaticFiles(html=True) automatically serves index.html at the root.
if os.path.isdir(WEB_DIR):
    app.mount("/", StaticFiles(directory=WEB_DIR, html=True), name="web")
