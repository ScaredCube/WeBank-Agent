"""SSE disruptions preserve trustworthy partial evidence with request identity.

A partial snapshot is never a completed Agent task and cannot replay tools.
"""
import asyncio

from sqlmodel import Session, select

from app.agent.loop import AgentEvent
from app.agent.tool_executor import VerifiedToolContext
from app.db.session import get_engine
from app.models import Account, ChatSubmission, User
from app.services.chat_submissions import claim_submission
from app.services.chat_turn import ChatTurn, stream_chat_turn
from tests.test_ui_chat_roundtrip import bill


def _create_request(client, auth_headers, request_id: str):
    cid = client.post("/api/chat/conversations", headers=auth_headers, json={}).json()["id"]
    with Session(get_engine()) as db:
        user = db.exec(select(User).where(User.username == "demo")).one()
        account = db.exec(select(Account).where(Account.user_id == user.id)).first()
        attempt, created = claim_submission(
            db, user_id=user.id, conversation_id=cid, request_id=request_id,
            payload_digest="a-fixed-fingerprint",
        )
        assert created
        return cid, attempt.id, user.id, account.id


def _turn(cid: int, sid: int, uid: int, aid: int):
    return ChatTurn(conversation_id=cid, submission_id=sid,
                    history=[], original_request="查询并分析本月消费",
                    verified=VerifiedToolContext(user_id=uid, verified_account_id=aid))


def test_connection_interruption_after_bill_keeps_request_linked_partial(
    client, auth_headers,
):
    cid, sid, uid, aid = _create_request(client, auth_headers, "v2-interrupt-bill")
    calls = []

    class Loop:
        async def stream(self, *args, **kwargs):
            calls.append("tool")
            yield AgentEvent("bill_result", {
                "data": bill("2026-10", 12000, 6000),
                "trusted_metadata": {"account_id": aid},
            })
            yield AgentEvent("delta", {"text": "this text must never arrive"})

    async def run():
        checked = 0
        async def disconnected():
            nonlocal checked
            checked += 1
            return checked > 1
        frames = []
        try:
            async for event in stream_chat_turn(_turn(cid, sid, uid, aid), Loop(),
                                                disconnected, lambda value: value):
                frames.append(event)
        except asyncio.CancelledError:
            pass
        return frames

    frames = asyncio.run(run())
    assert [e["type"] for e in frames] == ["bill_result"]
    assert len(calls) == 1
    status = client.get(
        f"/api/chat/conversations/{cid}/requests/v2-interrupt-bill",
        headers=auth_headers,
    ).json()
    assert status["state"] == "interrupted"
    assert status["message"] is None
    assert status["partial_message"]["bill_result"]["consumption_fen"] == 12000
    assert status["partial_message"]["content"]
    with Session(get_engine()) as db:
        attempt = db.get(ChatSubmission, sid)
        assert attempt.assistant_message_id == status["partial_message"]["id"]
    rows = client.get(f"/api/chat/conversations/{cid}/messages",headers=auth_headers).json()
    assert len(rows) == 1 and rows[0]["bill_result"]["consumption_fen"] == 12000


def test_unexpected_failure_after_bill_preserves_snapshot_as_failed_partial(
    client, auth_headers,
):
    cid, sid, uid, aid = _create_request(client, auth_headers, "v2-crashed-bill")

    class Loop:
        async def stream(self, *args, **kwargs):
            yield AgentEvent("bill_result", {
                "data": bill("2026-10", 12000, 6000),
                "trusted_metadata": {"account_id": aid},
            })
            raise RuntimeError("secret diagnostic intentionally excluded")

    async def run():
        async def connected():
            return False
        return [event async for event in stream_chat_turn(
            _turn(cid, sid, uid, aid), Loop(), connected, lambda value: value
        )]

    frames = asyncio.run(run())
    assert [e["type"] for e in frames] == ["bill_result", "error"]
    assert "secret diagnostic" not in str(frames)
    assert "核对历史" in frames[-1]["message"]
    status = client.get(
        f"/api/chat/conversations/{cid}/requests/v2-crashed-bill",
        headers=auth_headers,
    ).json()
    assert status["state"] == "failed"
    assert status["message"] is None
    partial = status["partial_message"]
    assert partial["bill_result"]["consumption_fen"] == 12000
    assert "部分查询已取得可信结果" in partial["content"]
    with Session(get_engine()) as db:
        assert db.get(ChatSubmission, sid).assistant_message_id == partial["id"]


def test_failed_submission_without_saved_reply_has_no_partial(client, auth_headers):
    cid, sid, uid, aid = _create_request(client, auth_headers, "v2-failure-empty")

    class Loop:
        async def stream(self, *args, **kwargs):
            raise RuntimeError("simulated provider failure")
            yield AgentEvent("delta", {"text": "never"})

    async def run():
        async def connected(): return False
        return [event async for event in stream_chat_turn(
            _turn(cid, sid, uid, aid), Loop(), connected, lambda value: value
        )]

    last = asyncio.run(run())[-1]
    assert last["type"] == "error"
    assert last["message"] == "服务出现异常，请稍后再试。"
    status = client.get(
        f"/api/chat/conversations/{cid}/requests/v2-failure-empty",
        headers=auth_headers,
    ).json()
    assert status["state"] == "failed"
    assert status["partial_message"] is None
