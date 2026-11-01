"""Keyset history, cross-conversation isolation and bounded snapshot queries."""
from sqlalchemy import event
from sqlmodel import Session, select

from app.db.session import get_engine
from app.models import Conversation, Message, MessageResult, User
from app.services.vault import encrypt_result_snapshot


def seeded(client, headers):
    conversation_id = client.post("/api/chat/conversations", json={}, headers=headers).json()["id"]
    with Session(get_engine()) as db:
        rows = [
            Message(conversation_id=conversation_id, role="assistant" if i % 2 else "user",
                    content=f"message-{i:03d}") for i in range(125)
        ]
        db.add_all(rows)
        db.flush()
        for i in (1, 27, 61, 99, 123):
            ciphertext, version = encrypt_result_snapshot({"unexpected": "old-data"})
            db.add(MessageResult(message_id=rows[i].id, kind="card_status",
                                 ciphertext=ciphertext, key_version=version))
        db.commit()
    return conversation_id


def test_history_keyset_pages_and_legacy_compatibility(client, auth_headers):
    conversation_id = seeded(client, auth_headers)
    url = f"/api/chat/conversations/{conversation_id}/messages"
    latest = client.get(url + "?limit=50", headers=auth_headers)
    assert latest.status_code == 200 and latest.headers["cache-control"] == "no-store"
    assert [m["content"] for m in latest.json()] == [f"message-{i:03d}" for i in range(75,125)]
    cursor = latest.json()[0]["id"]
    older = client.get(f"{url}?limit=50&before_id={cursor}", headers=auth_headers)
    assert [m["content"] for m in older.json()] == [f"message-{i:03d}" for i in range(25,75)]
    oldest = client.get(f"{url}?limit=50&before_id={older.json()[0]['id']}", headers=auth_headers)
    assert [m["content"] for m in oldest.json()] == [f"message-{i:03d}" for i in range(25)]
    assert client.get(f"{url}?limit=50&before_id={oldest.json()[0]['id']}",
                      headers=auth_headers).json() == []
    legacy = client.get(url, headers=auth_headers)
    assert len(legacy.json()) == 125
    ids = [m["id"] for m in oldest.json()+older.json()+latest.json()]
    assert len(set(ids)) == 125 and ids == sorted(ids)


def test_paging_requires_valid_cursor_and_bounded_limit(client, auth_headers):
    conversation_id = seeded(client, auth_headers)
    url = f"/api/chat/conversations/{conversation_id}/messages"
    for query in ("limit=0", "limit=101", "before_id=-1", "before_id=1"):
        assert client.get(f"{url}?{query}", headers=auth_headers).status_code == 422


def test_history_snapshot_query_count_does_not_grow_with_assistant_messages(
    client, auth_headers,
):
    conversation_id = seeded(client, auth_headers)
    statements = []
    engine = get_engine()

    # SQLAlchemy emits case-dependent SQL; normalize the inspected statement.
    def count_snapshot(connection, cursor, statement, parameters, context, executemany):
        if "from messageresult" in statement.lower():
            statements.append(statement)

    event.listen(engine, "before_cursor_execute", count_snapshot)
    try:
        response = client.get(f"/api/chat/conversations/{conversation_id}/messages",
                              headers=auth_headers)
    finally:
        event.remove(engine, "before_cursor_execute", count_snapshot)
    assert response.status_code == 200
    assert len(response.json()) == 125
    assert len(statements) == 1, f"Snapshot N+1 regression: {len(statements)} SQL queries"
    # Corrupted / legacy incompatible snapshot still degrades per message, without
    # replacing the persisted assistant text or leaking its encrypted payload.
    assert response.json()[27]["content"] == "message-027"


def test_foreign_conversation_is_not_readable_with_cursor(client, auth_headers):
    own = seeded(client, auth_headers)
    with Session(get_engine()) as db:
        other = User(username="history_other", password_hash="unused")
        db.add(other)
        db.commit()
        db.refresh(other)
        foreign = Conversation(user_id=other.id)
        db.add(foreign)
        db.commit()
        db.refresh(foreign)
    url = f"/api/chat/conversations/{foreign.id}/messages?limit=50&before_id=10000"
    assert client.get(url, headers=auth_headers).status_code == 404
    assert len(client.get(f"/api/chat/conversations/{own}/messages?limit=10",
                          headers=auth_headers).json()) == 10

def test_legacy_long_history_batches_snapshots_below_sqlite_parameter_limit(
    client, auth_headers,
):
    conversation_id = client.post("/api/chat/conversations", json={},
                                  headers=auth_headers).json()["id"]
    with Session(get_engine()) as session:
        session.add_all([
            Message(conversation_id=conversation_id, role="assistant", content="synthetic")
            for _ in range(950)
        ])
        session.commit()
    statements: list[str] = []
    engine = get_engine()

    def collect(connection, cursor, statement, parameters, context, executemany):
        if "from messageresult" in statement.lower():
            statements.append(statement)
            assert len(parameters) <= 400

    event.listen(engine, "before_cursor_execute", collect)
    try:
        result = client.get(f"/api/chat/conversations/{conversation_id}/messages",
                            headers=auth_headers)
    finally:
        event.remove(engine, "before_cursor_execute", collect)
    assert result.status_code == 200
    assert len(result.json()) == 950
    assert len(statements) == 3
