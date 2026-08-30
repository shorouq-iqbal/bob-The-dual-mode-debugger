"""
app.py — HealX FastAPI backend with Server-Sent Events (SSE) streaming.

Start with:
    uvicorn app:app --reload --port 8000
"""

import asyncio
import json
import os
import queue
import threading
from datetime import datetime
from pathlib import Path

from fastapi import FastAPI
from fastapi.responses import FileResponse, HTMLResponse, StreamingResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

# --- App init ---
app = FastAPI(title="HealX Dashboard", version="1.0")

STATIC_DIR = Path(__file__).parent / "static"
STATIC_DIR.mkdir(exist_ok=True)
app.mount("/static", StaticFiles(directory=str(STATIC_DIR)), name="static")

# Global run state — only one concurrent run in demo mode
_run_queue: queue.Queue = queue.Queue(maxsize=500)
_run_active = threading.Event()


class TriggerRequest(BaseModel):
    test_path: str = os.path.join("tests", "test_deterministic_bug.py")


# ---------------------------------------------------------------------------
# SSE helpers
# ---------------------------------------------------------------------------

def _push(event_type: str, data: dict):
    """Push a JSON event into the SSE queue."""
    try:
        _run_queue.put_nowait({"type": event_type, "data": data})
    except queue.Full:
        pass


async def _event_generator():
    """Async generator that yields SSE-formatted events."""
    while True:
        try:
            item = _run_queue.get_nowait()
            payload = json.dumps(item)
            yield f"data: {payload}\n\n"
        except queue.Empty:
            await asyncio.sleep(0.1)


# ---------------------------------------------------------------------------
# Background run worker
# ---------------------------------------------------------------------------

def _run_worker(test_path: str):
    """Runs the full HealX pipeline in a background thread, pushing SSE events."""
    import orchestrator
    import reporter

    triage_results = []
    verdict = None
    result = {}

    try:
        # --- Triage ---
        _push("triage_start", {"test_path": test_path})
        for _ in range(orchestrator.TRIAGE_RUNS):
            passed = orchestrator.run_test(orchestrator.REPO_PATH, test_path)["passed"]
            triage_results.append(passed)
            _push("triage_update", {"results": triage_results})

        if all(r == triage_results[0] for r in triage_results):
            verdict = "MODE_A" if not triage_results[0] else "NO_BUG"
        else:
            verdict = "MODE_B"

        _push("mode_routed", {"verdict": verdict, "results": triage_results})

        if verdict == "NO_BUG":
            _push("completed", {"success": True, "report_path": None, "message": "No bugs found."})
            return

        # --- Event callback for orchestrator ---
        def on_event(kind, data):
            _push(kind, data)
            if kind == "subagent_status":
                _push("subagent_status", data)

        if verdict == "MODE_A":
            result = orchestrator.run_debug_loop(test_path, event_cb=on_event)
        else:
            # Initialise subagent states
            for k in ["timing", "state", "randomness"]:
                _push("subagent_status", {"kind": k, "status": "PENDING"})
            result = orchestrator.run_flakyguard(test_path, event_cb=on_event)

        # --- Diff ready ---
        if result.get("diff"):
            _push("diff_ready", {"diff": result["diff"]})

        # --- Report ---
        report_path = reporter.generate_report(
            test_name=test_path,
            triage_results=triage_results,
            verdict=verdict,
            result=result,
        )

        _push("completed", {
            "success": result.get("success", False),
            "report_path": os.path.basename(report_path),
            "stress_passes": result.get("stress_passes", 0),
            "stress_total": result.get("stress_total", 0),
            "verdict": verdict,
        })

    except Exception as exc:
        _push("error", {"message": str(exc)})
    finally:
        _run_active.clear()


# ---------------------------------------------------------------------------
# Routes
# ---------------------------------------------------------------------------

@app.get("/", response_class=HTMLResponse)
async def index():
    html_path = STATIC_DIR / "index.html"
    if html_path.exists():
        return FileResponse(str(html_path))
    return HTMLResponse("<h1>HealX Dashboard</h1><p>Place index.html in static/</p>")


@app.post("/api/trigger")
async def trigger_run(req: TriggerRequest):
    if _run_active.is_set():
        return {"status": "busy", "message": "A run is already in progress."}
    # Drain previous events
    while not _run_queue.empty():
        try:
            _run_queue.get_nowait()
        except queue.Empty:
            break
    _run_active.set()
    thread = threading.Thread(target=_run_worker, args=(req.test_path,), daemon=True)
    thread.start()
    return {"status": "started", "test_path": req.test_path}


@app.get("/api/stream")
async def stream_events():
    return StreamingResponse(
        _event_generator(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "X-Accel-Buffering": "no",
            "Connection": "keep-alive",
        },
    )


@app.get("/api/status")
async def status():
    return {"active": _run_active.is_set()}


@app.get("/api/report/{filename}")
async def get_report(filename: str):
    path = Path(__file__).parent / filename
    if path.exists() and path.suffix == ".md":
        return FileResponse(str(path), media_type="text/markdown")
    return HTMLResponse("<h1>Report not found</h1>", status_code=404)
