"""A drop-in replacement for app.py that renames the response fields.

`priority`   -> `level`
`confidence` -> `score`

Used to verify that the self-healing tests survive a real API rename.

Run:
    python tests/mutated_app.py            # default port 5001
    PORT=5050 python tests/mutated_app.py  # override
"""
from __future__ import annotations

import os
from pathlib import Path

import joblib
from flask import Flask, jsonify, request

MODEL_PATH = Path(__file__).resolve().parents[1] / "model.joblib"

app = Flask(__name__)
_model = joblib.load(MODEL_PATH)


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

    # NOTE: deliberately renamed to simulate an API drift.
    return jsonify(
        {
            "level": classes[best_index],
            "score": round(float(probabilities[best_index]), 4),
        }
    )


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=int(os.environ.get("PORT", "5001")))
