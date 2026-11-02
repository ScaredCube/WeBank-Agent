"""Synthetic-only FastAPI SSE disconnect fixture; real HTTP, DB and bank reads.

Launch in a dedicated process/port. Never use production credentials, real
accounts or payment/prepare tools in this fixture. The provider and guard are
offline deterministic and the bank's real read Tool stays enabled.
"""
import asyncio
import base64
import json
import os
import tempfile
from pathlib import Path
import secrets
import sys

base = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(base))
scratch = Path(tempfile.mkdtemp(prefix="xiaowe-sse-network-"))
os.environ["DATABASE_URL"] = "sqlite:///" + (scratch / "synthetic.sqlite").as_posix()
os.environ["JWT_SECRET"] = secrets.token_hex(40)
os.environ["DATA_ENCRYPTION_KEY"] = base64.urlsafe_b64encode(os.urandom(32)).decode()
os.environ["DATA_HMAC_KEY"] = base64.urlsafe_b64encode(os.urandom(32)).decode()
os.environ["LLM_API_KEY"] = ""
os.environ["DEMO_USERNAME"] = "demo"
os.environ["DEMO_PASSWORD"] = "demo123"
os.environ["DEMO_MULTI_ASSETS"] = "false"
os.environ["GENERATIVE_UI_ENABLED"] = "false"
os.environ["CORS_ORIGINS"] = "http://127.0.0.1:5187,http://localhost:5187"

from app.agent import loop as agent_loop
from app.agent.llm import LLMChunk
from app.main import app

metrics = {"read_bill_event_count": 0, "agent_turn_count": 0, "halt_count": 0}


class ScriptedReadProvider:
    mode = "openai"

    async def stream(self, messages, tools=None):
        if tools is None:
            yield LLMChunk(content=json.dumps({"narrative": "该账单是模拟银行账单。"}, ensure_ascii=False))
            return
        if not any(m.get("role") == "tool" for m in messages):
            yield LLMChunk(tool_calls=[{
                "id": "synthetic_read_bill_1", "type": "function",
                "function": {"name": "get_monthly_bill", "arguments": '{"month":"2026-10"}'},
            }])
        else:
            yield LLMChunk(content="模拟账单已查询。")


agent_loop.get_llm = lambda: ScriptedReadProvider()
original_stream = agent_loop.AgentLoop.stream


async def paused_after_real_bill(self, *args, **kwargs):
    metrics["agent_turn_count"] += 1
    async for event in original_stream(self, *args, **kwargs):
        yield event
        if event.type == "bill_result":
            metrics["read_bill_event_count"] += 1
            metrics["halt_count"] += 1
            # Intentionally ensure the browser can abort *after* Tool evidence
            # crosses the SSE boundary but *before* assistant completion.
            await asyncio.sleep(30)


agent_loop.AgentLoop.stream = paused_after_real_bill


@app.get("/__e2e/sse-fixture-status", include_in_schema=False)
def fixture_status():
    return {**metrics, "synthetic_only": True}


if __name__ == "__main__":
    import uvicorn
    print("SYNTHETIC_SSE_FIXTURE_PORT=8193", flush=True)
    uvicorn.run(app, host="127.0.0.1", port=8193, log_level="warning")
