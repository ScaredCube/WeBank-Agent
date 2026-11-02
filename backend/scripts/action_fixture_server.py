"""Isolated E2E fixture: deterministic model Tool call, real Agent/HTTP/DB.

Never use in production; only the explicit synthetic-bank E2E runner imports it.
"""
import json
import os
import re

from app.agent.llm import LLMChunk
from app.agent.guard import GuardVerdict
import app.agent.loop as loop
from app.main import app


class FixtureTransferModel:
    def __init__(self):
        self.prepared = False

    async def stream(self, messages, tools=None):
        if self.prepared or tools is None:
            yield LLMChunk(content="已准备待确认转账，请在固定弹窗中核对。")
            return
        if not any(t["function"]["name"] == "prepare_transfer" for t in (tools or [])):
            raise RuntimeError("Fixture requires the real registered transfer Tool")
        self.prepared = True
        user_message = next(
            m["content"] for m in reversed(messages) if m.get("role") == "user"
        )
        phone = re.search(r"<PHONE_TMP_[^>]+>", user_message)
        if phone is None:
            raise RuntimeError("Chat route did not provide verified temporary phone reference")
        # A safe edit test sends a fresh message requesting 2 yuan.
        # Amount is derived from the CURRENT user instruction, not the old
        # action or its confirmation token.
        amount_fen = 200 if re.search(r"转账\s*2\s*元", user_message) else 100
        arguments = {
            "recipient_name": "模拟收款人",
            "amount_fen": amount_fen,
            "target_token": phone.group(),
            # Deliberately omit source_token: it must come from selected account.
        }
        yield LLMChunk(tool_calls=[{
            "id": "fixture_call", "type": "function",
            "function": {"name": "prepare_transfer",
                         "arguments": json.dumps(arguments, ensure_ascii=False)},
        }])


loop.get_llm = lambda: FixtureTransferModel()
loop.get_guard = lambda: None


if os.environ.get('BANK_AGENT_ACTION_E2E_FACE') == '1':
    class FixtureEscalatingGuard:
        async def review(self, call):
            # Synthetic, isolated negative Guard verdict. The real risk engine
            # must still demand both code and face before execution.
            if call.tool != 'prepare_transfer':
                return GuardVerdict(True, 'allowed')
            return GuardVerdict(False, 'rejected')

    loop.get_guard = lambda: FixtureEscalatingGuard()
