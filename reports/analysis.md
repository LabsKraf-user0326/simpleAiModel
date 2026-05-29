# Phase 2 — Performance Analysis

Target: Flask `app.py` running the TF-IDF + LogisticRegression model on `POST /predict`.
Host: local machine, single Flask dev-server process (single-threaded WSGI).
Tool: `k6 v1.4.2`.

## Test 1 — Ramp-up (1 → 10 → 50 VUs)

| Stat | Value |
|---|---|
| Total requests | **21,964** |
| Failed | **0 (0.00%)** |
| Throughput | ~110 req/s |
| Duration avg / p90 / p95 / max | **5.7 ms / 11.4 ms / 14.1 ms / 44.7 ms** |
| Threshold `p(95) < 1500ms` | ✅ pass |
| Threshold `http_req_failed < 2%` | ✅ pass |

### When does response time increase?
Latency stays essentially flat across the three load stages. p95 never crosses ~14 ms even at 50 VUs with 200 ms of think-time between calls. The model itself is the bottleneck candidate, and it isn't being stressed at this rate — a single TF-IDF transform + logistic regression `predict_proba` is sub-millisecond, and Flask's per-request overhead dominates.

### Does the server start failing?
No. Zero failed requests across the full run. With 200 ms of think-time, 50 sustained VUs produce only ~250 concurrent requests/second, well within what a single-threaded WSGI loop can handle when each request finishes in single-digit milliseconds.

**Takeaway:** the API comfortably handles 50 sustained users at this request shape. To find the real ceiling we'd need to remove think-time or push VUs higher.

## Test 2 — Spike (5 → 100 VUs almost instantly → 5)

| Stat | Value |
|---|---|
| Total requests | **62,408** |
| Failed | **24,831 (39.79%)** |
| Throughput | ~446 req/s |
| Duration of successful requests avg / p90 / p95 / max | **2.6 ms / 5.4 ms / 9.9 ms / 137 ms** |
| Errors in the 45 s recovery window after the spike | **0** |
| Threshold `http_req_failed < 20%` | ❌ **fail** (39.79%) |
| Threshold `p(95) < 5000ms` | ✅ pass |

### Does the server crash?
The Flask process kept running, but ~40% of requests during the burst window failed. The failure shape is telling:
- Successful responses are still very fast (p95 ~10 ms).
- The k6 `http_req_blocked` max jumped to **19.5 s** — i.e. connections sitting in OS backlog waiting to be accepted.

That points to **TCP accept-queue saturation in the single-threaded dev server**, not slow inference. The model isn't the problem; the WSGI loop can only accept one connection at a time, and 100 simultaneous VUs overrun the listen backlog.

### Does it recover afterward?
Yes — cleanly. The script tagged any failure during the 45-second recovery window (load back at 5 VUs) with a `recovery_errors` counter. That counter never fired, meaning **0 failures after the burst ended**. The server returned to the same sub-10 ms p95 it had during the ramp-up test.

## Summary

| Behavior | Observed |
|---|---|
| Knee of the latency curve | Not reached at 50 sustained VUs |
| Failure mode under spike | ~40% requests dropped at the TCP/accept layer |
| Recovery | Immediate; no degradation after load drops |
| Bottleneck identified | Single-threaded WSGI server, **not** the ML model |

## What would move the needle

These aren't part of Phase 2 deliverables, but they're the obvious next moves if you wanted the API to survive a 100-VU spike:

1. **Run with gunicorn**: `gunicorn -w 4 -k gthread --threads 4 app:app` — gives 16 concurrent workers and a real accept loop instead of the dev server.
2. **Increase the OS listen backlog** (`SOMAXCONN`) if running behind a load balancer.
3. **Cache predictions** for repeated task strings — model inference is fast, but skipping it for hot inputs would push the ceiling further.

## How to reproduce

```bash
# In one terminal — keep API running
python app.py

# In another
k6 run k6/ramp-up.js
k6 run k6/spike.js
```

Output lands in `reports/`:
- `ramp-up-summary.{json,txt}`
- `spike-summary.{json,txt}`
- this file
