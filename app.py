"""Flask API + unified dashboard for all three phases.

Routes:
  Phase 1: GET /, GET /health, POST /predict
  Phase 2: POST /api/run/load   (custom load test, streamed via SSE-style chunks)
  Phase 3: GET  /api/run/tests, GET /api/run/tests-mutated  (Server-Sent Events)

The single Flask process serves the model + drives k6 + drives pytest, so a
learner can demo every phase from one URL: http://localhost:5000/
"""
from __future__ import annotations

import json
import os
import re
import shutil
import socket
import subprocess
import sys
import threading
import time
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

import joblib
from flask import (
    Flask,
    Response,
    jsonify,
    render_template,
    request,
    stream_with_context,
)

PROJECT_ROOT = Path(__file__).parent.resolve()
MODEL_PATH   = PROJECT_ROOT / "model.joblib"
K6_DIR       = PROJECT_ROOT / "k6"
TESTS_DIR    = PROJECT_ROOT / "tests"
REPORTS_DIR  = PROJECT_ROOT / "reports"
PY           = sys.executable

app = Flask(__name__)
_model = joblib.load(MODEL_PATH)


# ---------- Phase 1 ----------

@app.get("/")
def dashboard():
    return render_template("dashboard.html")


@app.get("/health")
def health():
    return jsonify({"status": "ok"})


@app.post("/predict")
def predict():
    payload = request.get_json(silent=True) or {}
    task = payload.get("task")
    if not isinstance(task, str) or not task.strip():
        return jsonify({"error": "Request body must include a non-empty 'task' string."}), 400

    text = task.strip()
    probabilities = _model.predict_proba([text])[0]
    classes = list(_model.classes_)
    best_index = int(probabilities.argmax())

    return jsonify(
        {
            "priority": classes[best_index],
            "confidence": round(float(probabilities[best_index]), 4),
        }
    )


# ---------- Shared streaming helpers ----------

def _sse(event_type: str, **fields) -> str:
    return f"data: {json.dumps({'type': event_type, **fields})}\n\n"


def _wait_for_health(url: str, timeout: float = 5.0) -> bool:
    deadline = time.time() + timeout
    while time.time() < deadline:
        try:
            urlopen(url, timeout=0.5).read()
            return True
        except Exception:
            time.sleep(0.2)
    return False


def _find_free_port() -> int:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.bind(("127.0.0.1", 0))
        return int(s.getsockname()[1])


def _stream_subprocess(cmd: list[str], env: dict[str, str] | None = None):
    """Yield decoded text fragments as the subprocess emits them.
    Splits on both '\\n' and '\\r' so k6's progress bar shows up live.
    Final yield is a dict {'exit_code': N, 'proc': <Popen>}."""
    try:
        proc = subprocess.Popen(
            cmd,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            env=env,
            bufsize=0,
            cwd=str(PROJECT_ROOT),
        )
    except OSError as exc:
        yield f"ERROR: failed to start {' '.join(cmd)!r}: {exc}"
        yield {"exit_code": 127}
        return
    buf = b""
    try:
        while True:
            chunk = proc.stdout.read(256)
            if not chunk:
                break
            buf += chunk
            while True:
                idx_n = buf.find(b"\n")
                idx_r = buf.find(b"\r")
                indices = [i for i in (idx_n, idx_r) if i >= 0]
                if not indices:
                    break
                idx = min(indices)
                line, buf = buf[:idx], buf[idx + 1 :]
                yield line.decode("utf-8", errors="replace")
        if buf:
            yield buf.decode("utf-8", errors="replace")
    finally:
        try:
            proc.wait(timeout=10)
        except subprocess.TimeoutExpired:
            proc.kill()
            proc.wait()
        yield {"exit_code": proc.returncode}


# ---------- Phase 3 — fixed SSE scenarios (pytest) ----------

FIXED_SCENARIOS: dict[str, dict] = {
    "tests": {
        "label": "pytest against original API",
        "build_cmd": lambda: [
            PY, "-m", "pytest", "tests/", "-v",
            "--log-cli-level=WARNING", "--color=no",
        ],
    },
    "tests-mutated": {
        "label": "pytest against mutated API (renamed fields)",
        "build_cmd": None,  # special — see below
    },
}


@app.get("/api/run/<kind>")
def run_fixed_scenario(kind):
    if kind not in FIXED_SCENARIOS:
        return jsonify({"error": f"unknown scenario {kind!r}"}), 400
    scenario = FIXED_SCENARIOS[kind]

    def generate():
        yield _sse("start", scenario=kind, label=scenario["label"])
        mutated_proc: subprocess.Popen | None = None
        try:
            if kind == "tests-mutated":
                port = _find_free_port()
                base_url = f"http://127.0.0.1:{port}"
                yield _sse("info", text=f"Starting mutated server on :{port} ...")
                try:
                    mutated_proc = subprocess.Popen(
                        [PY, str(TESTS_DIR / "mutated_app.py")],
                        stdout=subprocess.PIPE,
                        stderr=subprocess.STDOUT,
                        env={**os.environ, "PORT": str(port)},
                        cwd=str(PROJECT_ROOT),
                    )
                except OSError as exc:
                    yield _sse("error", text=f"Could not start mutated server: {exc}")
                    yield _sse("end", exit_code=127)
                    return
                if not _wait_for_health(f"{base_url}/health", timeout=10.0):
                    output = ""
                    if mutated_proc.poll() is not None:
                        try:
                            output = (mutated_proc.stdout.read() or b"").decode("utf-8", errors="replace")
                        except Exception:
                            output = ""
                    detail = f" Mutated server output: {output.strip()}" if output.strip() else ""
                    yield _sse("error", text=f"Mutated server did not come up in time on :{port}.{detail}")
                    yield _sse("end", exit_code=-1)
                    return
                yield _sse("info", text=f"Mutated server up on :{port}. Running pytest ...")
                env = {**os.environ, "PREDICT_API_URL": base_url}
                cmd = [
                    PY, "-m", "pytest", "tests/", "-v",
                    "--log-cli-level=WARNING", "--color=no",
                ]
            else:
                cmd = scenario["build_cmd"]()
                env = None

            yield _sse("info", text=f"$ {' '.join(cmd)}")
            for item in _stream_subprocess(cmd, env=env):
                if isinstance(item, dict):
                    yield _sse("end", exit_code=item["exit_code"])
                else:
                    yield _sse("line", text=item)
        finally:
            if mutated_proc is not None:
                try:
                    mutated_proc.terminate()
                    mutated_proc.wait(timeout=5)
                except Exception:
                    mutated_proc.kill()

    return Response(
        stream_with_context(generate()),
        mimetype="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )


# ---------- Phase 2 — custom load test ----------

_DURATION_RE = re.compile(r"^\s*(?:(\d+)\s*h)?\s*(?:(\d+)\s*m)?\s*(?:(\d+)\s*s?)?\s*$")


def _validate_duration(d: str) -> bool:
    if not isinstance(d, str) or not d.strip():
        return False
    m = _DURATION_RE.match(d)
    if not m:
        return False
    return any(g is not None for g in m.groups())


def _duration_seconds(d: str) -> int:
    m = _DURATION_RE.match(d)
    if not m:
        return 0
    h, mm, ss = (int(g) if g else 0 for g in m.groups())
    return h * 3600 + mm * 60 + ss


def _percentile(sorted_values: list[float], pct: float) -> float | None:
    if not sorted_values:
        return None
    if len(sorted_values) == 1:
        return sorted_values[0]
    pos = (len(sorted_values) - 1) * pct
    lo = int(pos)
    hi = min(lo + 1, len(sorted_values) - 1)
    frac = pos - lo
    return sorted_values[lo] * (1 - frac) + sorted_values[hi] * frac


def _validate_load_config(cfg: dict) -> tuple[bool, str]:
    url = cfg.get("url")
    if not isinstance(url, str) or not url.strip():
        return False, "url is required"
    if not (url.startswith("http://") or url.startswith("https://")):
        return False, "url must start with http:// or https://"
    method = (cfg.get("method") or "GET").upper()
    if method not in {"GET", "POST", "PUT", "PATCH", "DELETE", "HEAD", "OPTIONS"}:
        return False, f"unsupported method {method!r}"
    headers = cfg.get("headers") or {}
    if not isinstance(headers, dict):
        return False, "headers must be an object"
    stages = cfg.get("stages")
    if not isinstance(stages, list) or not stages:
        return False, "stages must be a non-empty array"
    for i, s in enumerate(stages):
        if not isinstance(s, dict):
            return False, f"stages[{i}] must be an object"
        if not _validate_duration(s.get("duration", "")):
            return False, f"stages[{i}].duration is invalid (use '30s', '2m', '1m30s')"
        try:
            t = int(s.get("target"))
        except (TypeError, ValueError):
            return False, f"stages[{i}].target must be an integer"
        if t < 0 or t > 5000:
            return False, f"stages[{i}].target {t} is out of range"
    return True, ""


def _parse_summary(path: Path) -> dict | None:
    """Read k6's JSON summary and slim it to what the UI needs."""
    try:
        raw = json.loads(path.read_text())
    except Exception:
        return None
    metrics = raw.get("metrics", {})

    def pluck(name, *fields):
        m = metrics.get(name, {})
        vals = m.get("values", {})
        return {f: vals.get(f) for f in fields}

    slim = {
        "metrics": {
            "http_reqs":        {"values": pluck("http_reqs", "count", "rate")},
            "http_req_failed":  {"values": pluck("http_req_failed", "rate", "passes", "fails")},
            "http_req_duration":{"values": pluck("http_req_duration",
                                                  "avg", "med", "p(90)", "p(95)", "p(99)", "max", "min")},
        },
        "thresholds_passed": all(
            not t.get("ok") is False
            for m in metrics.values()
            for t in (m.get("thresholds") or {}).values()
            if isinstance(t, dict)
        ),
    }
    return slim


def _request_once(url: str, method: str, headers: dict, body: str) -> tuple[float, bool, str]:
    data = None if method in {"GET", "HEAD"} else body.encode("utf-8")
    req = Request(url, data=data, headers={str(k): str(v) for k, v in headers.items()}, method=method)
    start = time.perf_counter()
    try:
        with urlopen(req, timeout=10) as resp:
            resp.read()
            status = getattr(resp, "status", 200)
    except HTTPError as exc:
        try:
            exc.read()
        except Exception:
            pass
        status = exc.code
        return (time.perf_counter() - start) * 1000, False, str(status)
    except URLError as exc:
        return (time.perf_counter() - start) * 1000, False, exc.reason.__class__.__name__
    except Exception as exc:
        return (time.perf_counter() - start) * 1000, False, exc.__class__.__name__
    return (time.perf_counter() - start) * 1000, 200 <= status < 300, str(status)


def _write_fallback_summary(summary: dict, lines: list[str]) -> None:
    REPORTS_DIR.mkdir(exist_ok=True)
    (REPORTS_DIR / "load-summary.json").write_text(json.dumps(summary, indent=2), encoding="utf-8")
    (REPORTS_DIR / "load-summary.txt").write_text("\n".join(lines) + "\n", encoding="utf-8")


def _python_load_runner(
    url: str,
    method: str,
    headers: dict,
    body: str,
    stages: list[dict],
    think_ms: int,
    p95: int,
    failmax: float,
):
    latencies: list[float] = []
    failures = 0
    status_counts: dict[str, int] = {}
    lock = threading.Lock()
    started = time.perf_counter()
    think_s = max(think_ms, 0) / 1000

    yield "k6 is not installed; using built-in Python fallback load runner."

    for idx, stage in enumerate(stages, start=1):
        duration = _duration_seconds(stage["duration"])
        target = int(stage["target"])
        if duration <= 0:
            yield f"stage {idx}/{len(stages)} skipped: invalid duration {stage['duration']!r}"
            continue
        if target <= 0:
            yield f"stage {idx}/{len(stages)}: target 0 VUs for {duration}s"
            time.sleep(duration)
            continue

        stop_at = time.perf_counter() + duration
        yield f"stage {idx}/{len(stages)}: {target} workers for {duration}s"

        def worker():
            nonlocal failures
            while time.perf_counter() < stop_at:
                latency, ok, status = _request_once(url, method, headers, body)
                with lock:
                    latencies.append(latency)
                    status_counts[status] = status_counts.get(status, 0) + 1
                    if not ok:
                        failures += 1
                if think_s:
                    time.sleep(think_s)

        with ThreadPoolExecutor(max_workers=target) as pool:
            futures = [pool.submit(worker) for _ in range(target)]
            for future in futures:
                future.result()

        with lock:
            total = len(latencies)
            yield f"stage {idx}/{len(stages)} complete: {total} total requests, {failures} failures"

    elapsed = max(time.perf_counter() - started, 0.001)
    sorted_latencies = sorted(latencies)
    total = len(sorted_latencies)
    passes = total - failures
    fail_rate = failures / total if total else 0.0
    avg = sum(sorted_latencies) / total if total else None
    p95_value = _percentile(sorted_latencies, 0.95)
    thresholds_passed = (p95_value or 0) < p95 and fail_rate < failmax
    summary = {
        "metrics": {
            "http_reqs": {"values": {"count": total, "rate": total / elapsed}},
            "http_req_failed": {"values": {"rate": fail_rate, "passes": passes, "fails": failures}},
            "http_req_duration": {
                "values": {
                    "avg": avg,
                    "med": _percentile(sorted_latencies, 0.50),
                    "p(90)": _percentile(sorted_latencies, 0.90),
                    "p(95)": p95_value,
                    "p(99)": _percentile(sorted_latencies, 0.99),
                    "max": max(sorted_latencies) if total else None,
                    "min": min(sorted_latencies) if total else None,
                }
            },
        },
        "thresholds_passed": thresholds_passed,
        "status_counts": status_counts,
        "runner": "python-fallback",
    }
    report_lines = [
        "Python fallback load summary",
        f"target: {method} {url}",
        f"requests: {total}",
        f"failures: {failures} ({fail_rate:.2%})",
        f"throughput: {total / elapsed:.2f} req/s",
        f"p95 latency: {p95_value:.2f} ms" if p95_value is not None else "p95 latency: n/a",
        f"thresholds passed: {thresholds_passed}",
    ]
    _write_fallback_summary(summary, report_lines)
    for line in report_lines:
        yield line
    yield {"summary": summary}
    yield {"exit_code": 0 if thresholds_passed else 1}


@app.post("/api/run/load")
def run_load():
    cfg = request.get_json(silent=True) or {}
    ok, why = _validate_load_config(cfg)
    if not ok:
        return jsonify({"error": why}), 400

    url     = cfg["url"]
    method  = (cfg.get("method") or "GET").upper()
    headers = cfg.get("headers") or {}
    body    = cfg.get("body") or ""
    stages  = [{"duration": s["duration"], "target": int(s["target"])} for s in cfg["stages"]]
    think   = int(cfg.get("think_ms") or 100)
    p95     = int(cfg.get("p95_threshold") or 5000)
    failmax = float(cfg.get("fail_threshold") or 0.5)

    env = {
        **os.environ,
        "TARGET_URL":     url,
        "METHOD":         method,
        "HEADERS_JSON":   json.dumps(headers),
        "BODY":           body,
        "STAGES_JSON":    json.dumps(stages),
        "THINK_MS":       str(think),
        "P95_THRESHOLD":  str(p95),
        "FAIL_THRESHOLD": str(failmax),
    }
    k6_bin = shutil.which("k6")
    cmd = [k6_bin or "k6", "run", str(K6_DIR / "load.js")]

    total_secs = 0
    for s in stages:
        m = _DURATION_RE.match(s["duration"])
        if m:
            h, mm, ss = (int(g) if g else 0 for g in m.groups())
            total_secs += h * 3600 + mm * 60 + ss
    peak_vus = max((s["target"] for s in stages), default=0)

    def generate():
        yield _sse("start",
                   scenario="load",
                   label=f"k6 load test against {url}  ·  ~{total_secs}s  ·  peak {peak_vus} VUs")
        if not k6_bin:
            fallback_exit = 1
            for item in _python_load_runner(url, method, headers, body, stages, think, p95, failmax):
                if isinstance(item, dict) and "summary" in item:
                    meta = f"{method} {url} · peak {peak_vus} workers · ~{total_secs}s · python fallback"
                    yield _sse("summary", data=item["summary"], meta=meta)
                elif isinstance(item, dict):
                    fallback_exit = item["exit_code"]
                else:
                    yield _sse("line", text=item)
            yield _sse("end", exit_code=fallback_exit)
            return
        yield _sse("info", text=f"$ {' '.join(cmd)}")
        REPORTS_DIR.mkdir(exist_ok=True)
        summary_path = REPORTS_DIR / "load-summary.json"
        try:
            summary_path.unlink()
        except FileNotFoundError:
            pass

        exit_code = None
        try:
            for item in _stream_subprocess(cmd, env=env):
                if isinstance(item, dict):
                    exit_code = item["exit_code"]
                else:
                    yield _sse("line", text=item)
        finally:
            summary = _parse_summary(summary_path) if summary_path.exists() else None
            if summary:
                meta = f"{method} {url} · peak {peak_vus} VUs · ~{total_secs}s"
                yield _sse("summary", data=summary, meta=meta)
            yield _sse("end", exit_code=exit_code if exit_code is not None else -1)

    return Response(
        stream_with_context(generate()),
        mimetype="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5000, threaded=True)
