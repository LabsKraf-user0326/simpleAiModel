import os
import pytest


@pytest.fixture(scope="session")
def base_url() -> str:
    """Where the API is running. Override with PREDICT_API_URL."""
    return os.environ.get("PREDICT_API_URL", "http://localhost:5000").rstrip("/")
