"""Isolated E2E fixture: deterministic model Tool call, real Agent/HTTP/DB.

Never use in production; only the explicit synthetic-bank E2E runner imports it.
"""
import json
import re

from app.agent.llm import LLMChunk
import app.agent.loop as loop
from app.main import app


class FixtureTransferModel:
    async def stream(self, messages, tools=None):
        if not any(t["function"]["name"] == "prepare_transfer" for t in (tools or [])):
            raise RuntimeError("Fixture requires the real registered transfer Tool")
        user_message = next(
            m["content"] for m in reversed(messages) if m.get("role") == "user"
        )
        phone = re.search(r"<PHONE_TMP_[^>]+>", user_message)
        if phone is None:
            raise RuntimeError("Chat route did not provide verified temporary phone reference")
        arguments = {
            "recipient_name": "模拟收款人",
            "amount_fen": 100,
            "target_token": phone.group(),
            # Deliberately omit source_token: it must come from selected account.
        }
        yield LLMChunk(tool_calls=[{
            "id": "fixture_call", "type": "function",
            "function": {"name": "prepare_transfer",
                         "arguments": json.dumps(arguments, ensure_ascii=False)},
        }])


loop.get_llm = lambda: FixtureTransferModel()
