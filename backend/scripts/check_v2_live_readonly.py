"""Live, read-only Agent chat smoke check against synthetic local banking data.

Run only with explicit local .env loaded and an isolated SQLite database.
Never print credentials or raw bank data to stdout.
"""
from __future__ import annotations

import base64
import json
import os
import tempfile
from pathlib import Path
import sys
import uuid

from dotenv import load_dotenv

source_override = os.getenv("XIAOWE_TEST_ENV_FILE")
source = (Path(source_override) if source_override
          else Path(__file__).resolve().parents[1] / ".env")
if source.is_file():
    load_dotenv(source, override=False)
if not os.getenv("LLM_API_KEY"):
    raise RuntimeError("Set a synthetic-only live test LLM key via environment or .env")
os.environ["DATABASE_URL"] = "sqlite:///" + (Path(tempfile.mkdtemp(prefix="xiaowe-v2-live-")) / "synthetic.db").as_posix()
os.environ["JWT_SECRET"] = os.urandom(40).hex()
# Use isolated synthetic vault keys; do not alter project credentials.
os.environ["DATA_ENCRYPTION_KEY"] = base64.urlsafe_b64encode(os.urandom(32)).decode()
os.environ["DATA_HMAC_KEY"] = base64.urlsafe_b64encode(os.urandom(32)).decode()
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from fastapi.testclient import TestClient  # noqa: E402
from app.main import app  # noqa: E402
from app.core.config import settings  # noqa: E402
from app.agent.llm import get_llm_info  # noqa: E402

# Optional development-only instrumentation: log ONLY requested Tool names.
# Never print model text, user payloads, Tool arguments, bank data or keys.
if os.getenv("XIAOWE_TRACE_READ_TOOLS") == "1":
    from app.agent import loop as agent_loop
    original_provider_factory = agent_loop.get_llm

    class ToolNameTrace:
        def __init__(self, inner):
            self.inner = inner
            self.mode = inner.mode

        async def stream(self, messages, tools=None):
            async for chunk in self.inner.stream(messages, tools=tools):
                if chunk.tool_calls:
                    names = [call.get("function", {}).get("name")
                             for call in chunk.tool_calls if isinstance(call, dict)]
                    print("model_requested_tools=", ",".join(str(name) for name in names), flush=True)
                yield chunk

    agent_loop.get_llm = lambda: ToolNameTrace(original_provider_factory())

def events(response):
    parsed = []
    for line in response.text.splitlines():
        if line.startswith("data: "):
            try:
                parsed.append(json.loads(line[6:]))
            except json.JSONDecodeError:
                pass
    return parsed

with TestClient(app) as client:
    login = client.post("/api/auth/login", json={
        "username": settings.demo_username,
        "password": settings.demo_password,
    })
    login.raise_for_status()
    header = {"Authorization": "Bearer " + login.json()["access_token"]}
    dashboard = client.get("/api/bank/dashboard", headers=header)
    dashboard.raise_for_status()
    accounts = dashboard.json().get("accounts", [])
    print("model_mode=", get_llm_info().get("mode"))
    print("synthetic_accounts=", len(accounts))
    conversation = client.post("/api/chat/conversations", headers=header, json={})
    conversation.raise_for_status()
    url = f"/api/chat/conversations/{conversation.json()['id']}/messages"
    prompts = [
        {"content": "你好，简短介绍一下你的银行服务能力"},
        {"content": "分析这个演示活期账户在2026年10月的收支", "references": [
            {"kind": "account", "id": accounts[0]["account_id"]}
        ]},
        {"content": "从刚才的账单中，有哪些支出类别值得关注？"},
    ]
    if os.getenv("XIAOWE_TEST_THREE_READ") == "1":
        triple = {"content": (
            "请查询2026-10的月度账单、最近交易流水，并识别疑似重复订阅"
        ), "references": [{"kind": "account", "id": accounts[0]["account_id"]}]}
        if os.getenv("XIAOWE_ONLY_THREE_READ") == "1":
            prompts = [triple]
        else:
            prompts.append(triple)
    for i, prompt in enumerate(prompts):
        prompt["request_id"] = str(uuid.uuid4())
        try:
            response = client.post(url, headers=header, json=prompt, timeout=40)
            frames = events(response)
            done = next((f for f in reversed(frames) if f.get("type") == "done"), {})
            message = done.get("message") or {}
            print("turn=", i+1, "http=", response.status_code,
                  "event_types=", ",".join(f.get("type", "?") for f in frames),
                  "has_content=", bool(message.get("content")),
                  "content_characters=", len(message.get("content") or ""),
                  "verified_history_followup=", (
                      "根据这段会话此前已核验并保存的账单" in (message.get("content") or "")
                  ) if i == 2 else None,
                  "three_read_complete=", (
                      "三个只读查询目标均已取得可信结果" in (message.get("content") or "")
                  ) if (i == 3 or os.getenv("XIAOWE_ONLY_THREE_READ") == "1") else None,
                  "three_read_missing=", (
                      ",".join(label for label in ("月度账单", "最近交易流水", "疑似周期性扣费识别")
                               if label + "：未取得可信结果" in (message.get("content") or ""))
                  ) if (i == 3 or os.getenv("XIAOWE_ONLY_THREE_READ") == "1") else None,
                  "error=", any(f.get("type") == "error" for f in frames))
        except Exception as error:
            print("turn=", i+1, "exception=", type(error).__name__)
