import os
import base64
import tempfile
from pathlib import Path

db_path = Path(tempfile.gettempdir()) / "bank_agent_test.db"
if db_path.exists():
    db_path.unlink()

os.environ["DATABASE_URL"] = f"sqlite:///{db_path.as_posix()}"
os.environ["LLM_API_KEY"] = ""
# Most regression tests use deterministic model doubles; dedicated grounding
# tests enable the reviewer explicitly.
os.environ["REPLY_GROUNDING_ENABLED"] = "false"
os.environ["JWT_SECRET"] = "test-secret-with-enough-length-123456"
os.environ["DATA_ENCRYPTION_KEY"] = base64.urlsafe_b64encode(b"a" * 32).decode()
os.environ["DATA_HMAC_KEY"] = base64.urlsafe_b64encode(b"b" * 32).decode()
os.environ["DEMO_USERNAME"] = "demo"
os.environ["DEMO_PASSWORD"] = "demo123"
# Most regression tests assume the original single-account fixture. Matrix tests
# create the second account/holding explicitly.
os.environ["DEMO_MULTI_ASSETS"] = "false"

import pytest
from fastapi.testclient import TestClient
from sqlmodel import SQLModel

from app.agent.llm import LLMChunk
from app.db.session import get_engine
from app.main import app


class TestProvider:
    """Deterministic text-only model double; never used in production."""

    mode = "test"
    model = "test"

    async def stream(self, messages, tools=None):
        yield LLMChunk(content="已收到。")
        yield LLMChunk(finish_reason="stop")


@pytest.fixture(autouse=True)
def test_llm(monkeypatch):
    provider = TestProvider()
    monkeypatch.setattr("app.agent.llm.validate_llm_config", lambda: None)
    monkeypatch.setattr("app.agent.loop.get_llm", lambda: provider)
    monkeypatch.setattr("app.agent.guard.get_llm", lambda: provider)
    monkeypatch.setattr("app.agent.ui_composer.get_llm", lambda: provider)
    monkeypatch.setattr("app.agent.loop.get_guard", lambda: None)


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
