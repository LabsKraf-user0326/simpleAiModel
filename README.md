# Smart Todo APIs

Phase 1 (AI API), Phase 2 (k6 load tests), and Phase 3 (self-healing tests),
all driven from a single Flask process.

## Demo materials

- [Code and dashboard PPT](demo/Smart-Todo-Code-and-Dashboard-Demo.pptx)
- [GitHub-viewable demo walkthrough](demo/DEMO.md)
- [Recorded dashboard demo video](demo/smart-todo-dashboard-demo.mp4)
- [Demo flow video GIF](demo/smart-todo-demo-flow.gif)
- [Presenter script](demo/demo-script.md)

![Smart Todo demo flow](demo/smart-todo-demo-flow.gif)

## Single-server quick start

```bash
python3 -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
python train.py            # produces model.joblib (one-time)
python app.py              # serves everything on :5000
```

Then open **http://localhost:5000/** — the dashboard has:

- **Phase 1**: live prediction widget that hits `POST /predict`.
- **Phase 2**: load-test builder that posts config to `POST /api/run/load`, runs `k6`,
  and streams output back into the page. It includes presets for this local server.
- **Phase 3**: two buttons that run the pytest suite — once against this server,
  once against an auto-spawned mutated server on `:5001`
  (`GET /api/run/tests`, `GET /api/run/tests-mutated`).

Phase 2 results live in [`reports/analysis.md`](reports/analysis.md).

## Phase 1 — AI API

A small text classifier that predicts the priority of a task (`High` / `Medium` / `Low`) and a Flask API that serves it.

## Layout
- `data/tasks.csv` — labeled dataset (200 rows).
- `train.py` — trains a TF-IDF + Logistic Regression pipeline and saves `model.joblib`.
- `app.py` — Flask app exposing `/health` and `/predict`.

## Setup
```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

## Train
```bash
python train.py
```
Prints held-out accuracy + per-class report, then refits on the full dataset and writes `model.joblib`.

## Run the API
```bash
python app.py
```
Listens on `http://localhost:5000`.

## Endpoints

### `GET /health`
```json
{ "status": "ok" }
```

### `POST /predict`
Request:
```json
{ "task": "Fix production bug" }
```
Response:
```json
{ "priority": "High", "confidence": 0.87 }
```

## Quick check
```bash
curl -s http://localhost:5000/health
curl -s -X POST http://localhost:5000/predict \
  -H 'content-type: application/json' \
  -d '{"task": "Fix production bug"}'
```

## Phase 2 — Load tests

Uses [`k6`](https://k6.io) when it is installed (`brew install k6`). If k6 is
not available, the dashboard automatically falls back to a built-in Python load
runner so the demo still produces streamed output and report cards.

From the dashboard you can:

- click **Preset: /predict (this server)** for a local API load test.
- paste your own local/private request into the curl parser when demoing a specific
  external API. Keep tokens and private URLs out of committed files.

You can also run the fixed scripts in another terminal:

```bash
k6 run k6/ramp-up.js   # 1 → 10 → 50 VUs over ~3min 20s
k6 run k6/spike.js     # 5 → 100 VUs burst, then drop back, ~2min 20s
```

Results land in `reports/` as `*-summary.json` (raw) and `*-summary.txt` (k6 text format). The narrative report is `reports/analysis.md`.

Override the target with `BASE_URL`:
```bash
BASE_URL=http://localhost:5000 k6 run k6/ramp-up.js
```

## Phase 3 — Self-healing tests

A pytest suite that survives small API renames. Field lookups go through
`tests/self_healing.py::resolve_field`, which:

1. Tries the canonical field (`priority`, `confidence`)
2. Falls back to known aliases (`level`/`urgency`/...,  `score`/`probability`/...)
3. Logs a WARNING when a fallback was used
4. Raises `FieldNotFound` (and fails the test) if nothing matches

### Run against the live API
```bash
python app.py            # in one terminal
pytest tests/ -v         # in another  → 7 passed, no warnings
```

### Demonstrate self-healing
`tests/mutated_app.py` is a drop-in server that returns `level` + `score`
instead of `priority` + `confidence`, simulating an API rename.

```bash
python tests/mutated_app.py                          # serves on :5001
PREDICT_API_URL=http://localhost:5001 \
  pytest tests/ -v --log-cli-level=WARNING            # 7 passed, with warnings
```

The same tests pass without modification — they just log a warning per renamed field so the drift is visible.
