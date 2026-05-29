# Smart Todo Demo Script

## Run

```bash
cd /Users/ams/Desktop/simpleAiModel
.venv/bin/python app.py
```

Open: http://127.0.0.1:5000/

## Demo Order

1. Open `data/tasks.csv` and show labeled examples.
2. Open `train.py` and explain TF-IDF plus Logistic Regression.
3. Open `app.py` and explain `/health` and `/predict`.
4. Open the dashboard and try:
   - `Resolve P0 incident on checkout API`
   - `Prepare quarterly business review deck`
   - `Read newsletter from cloud provider`
5. Run Phase 3 tests from the dashboard:
   - `Run tests (original API)`
   - `Run tests (mutated API -> :5001)`
6. Mention Phase 2 load testing requires `k6`; show `reports/analysis.md` if k6 is not installed.
   If you need to demo a private API, paste that curl only during the live demo
   and keep private URLs or tokens out of committed files.

## Closing Line

This project demonstrates the full mini lifecycle of an AI API: dataset, training,
serving, dashboard interaction, performance-test hooks, and resilient API tests.
