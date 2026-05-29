"""Train the task-priority classifier and save it to disk."""
from __future__ import annotations

from pathlib import Path

import joblib
import pandas as pd
from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.linear_model import LogisticRegression
from sklearn.metrics import classification_report, accuracy_score
from sklearn.model_selection import train_test_split
from sklearn.pipeline import Pipeline

DATA_PATH = Path(__file__).parent / "data" / "tasks.csv"
MODEL_PATH = Path(__file__).parent / "model.joblib"
LABELS = ["High", "Medium", "Low"]


def build_pipeline() -> Pipeline:
    return Pipeline(
        [
            (
                "tfidf",
                TfidfVectorizer(
                    lowercase=True,
                    ngram_range=(1, 2),
                    min_df=1,
                    sublinear_tf=True,
                ),
            ),
            (
                "clf",
                LogisticRegression(
                    max_iter=1000,
                    class_weight="balanced",
                    C=4.0,
                ),
            ),
        ]
    )


def main() -> None:
    df = pd.read_csv(DATA_PATH)
    df["task"] = df["task"].astype(str).str.strip()
    df["priority"] = df["priority"].astype(str).str.strip()

    X_train, X_test, y_train, y_test = train_test_split(
        df["task"],
        df["priority"],
        test_size=0.2,
        random_state=42,
        stratify=df["priority"],
    )

    pipeline = build_pipeline()
    pipeline.fit(X_train, y_train)

    y_pred = pipeline.predict(X_test)
    acc = accuracy_score(y_test, y_pred)
    print(f"Held-out accuracy: {acc:.3f}")
    print(classification_report(y_test, y_pred, labels=LABELS, zero_division=0))

    if acc < 0.70:
        print(f"WARNING: accuracy {acc:.3f} is below the 0.70 target.")

    # Refit on full dataset before saving so the shipped model uses all examples.
    final = build_pipeline()
    final.fit(df["task"], df["priority"])
    joblib.dump(final, MODEL_PATH)
    print(f"Saved model to {MODEL_PATH}")


if __name__ == "__main__":
    main()
