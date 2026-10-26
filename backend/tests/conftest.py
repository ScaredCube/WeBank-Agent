import os
import tempfile
from pathlib import Path

db_path = Path(tempfile.gettempdir()) / "bank_agent_test.db"
if db_path.exists():
    db_path.unlink()

os.environ["DATABASE_URL"] = f"sqlite:///{db_path.as_posix()}"
os.environ["LLM_API_KEY"] = ""
os.environ["JWT_SECRET"] = "test-secret-with-enough-length-123456"
os.environ["DEMO_USERNAME"] = "demo"
os.environ["DEMO_PASSWORD"] = "demo123"

import pytest
from fastapi.testclient import TestClient
from sqlmodel import SQLModel

from app.db.session import get_engine
from app.main import app


@pytest.fixture
def client():
    SQLModel.metadata.drop_all(get_engine())
    with TestClient(app) as test_client:
        yield test_client
    SQLModel.metadata.drop_all(get_engine())


@pytest.fixture
def auth_headers(client):
    response = client.post(
        "/api/auth/login",
        json={"username": "demo", "password": "demo123"},
    )
    assert response.status_code == 200
    token = response.json()["access_token"]
    return {"Authorization": f"Bearer {token}"}
