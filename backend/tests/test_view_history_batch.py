from sqlalchemy import event
from sqlmodel import Session, select

from app.db.session import get_engine
from app.models import Account, Message, MessageView, User, UIView, ViewRevision
from app.services import view_service
from app.services.view_service import create_or_append_view
from tests.test_trusted_ui_results import result


def _new_view(client, headers, result_ref, conversation_id=None):
    if conversation_id is None:
        conversation_id = client.post(
            "/api/chat/conversations", headers=headers, json={},
        ).json()["id"]
    with Session(get_engine()) as db:
        user = db.exec(select(User).where(User.username == "demo")).one()
        account = db.exec(select(Account).where(Account.user_id == user.id)).first()
        user_id, account_id = user.id, account.id
    view = create_or_append_view(
        user_id=user_id,
        conversation_id=conversation_id,
        results=[result(result_ref, "2026-10", 12000, account_id)],
        spec={
            "root": "chart",
            "elements": {
                "chart": {
                    "type": "CategoryBarChart",
                    "props": {"dataset_ref": f"{result_ref}:categories"},
                },
            },
        },
    )
    return conversation_id, view


def _load_views(session, messages):
    loader = getattr(view_service, "load_views_for_messages", None)
    assert callable(loader), "batch historical view loader has not been implemented"
    return loader(session, messages)


def test_history_view_readback_uses_chunked_joins_and_returns_each_bound_view(client, auth_headers):
    conversation_id, view = _new_view(client, auth_headers, "bill-history-batch")
    engine = get_engine()
    statements = []

    with Session(engine, expire_on_commit=False) as db:
        messages = [
            Message(conversation_id=conversation_id, role="assistant", content=f"reply {index}")
            for index in range(205)
        ]
        db.add_all(messages)
        db.commit()
        db.add_all([
            MessageView(message_id=message.id, view_id=view.view_id, revision=view.revision)
            for message in messages
        ])
        db.commit()
        history = db.exec(select(Message).where(
            Message.conversation_id == conversation_id,
        ).order_by(Message.id)).all()

        def record_statement(connection, cursor, statement, parameters, context, executemany):
            if statement.lstrip().upper().startswith("SELECT"):
                statements.append(statement.lower())

        event.listen(engine, "before_cursor_execute", record_statement)
        try:
            restored = _load_views(db, history)
        finally:
            event.remove(engine, "before_cursor_execute", record_statement)

    assert len(restored) == 205
    assert all(item.view_id == view.view_id and item.revision == 1
               for item in restored.values())
    assert len(statements) == 2
    for table in ("messageview", "message", "viewrevision", "uiview", "conversation"):
        assert sum(table in statement for statement in statements) == 2


def test_history_view_readback_skips_bad_or_misbound_views_without_losing_valid_siblings(
    client, auth_headers,
):
    conversation_id, good_view = _new_view(
        client, auth_headers, "bill-history-good",
    )
    _, corrupt_view = _new_view(
        client, auth_headers, "bill-history-corrupt", conversation_id,
    )
    _, wrong_owner_view = _new_view(
        client, auth_headers, "bill-history-wrong-owner", conversation_id,
    )
    wrong_conversation_id = client.post(
        "/api/chat/conversations", headers=auth_headers, json={},
    ).json()["id"]

    with Session(get_engine()) as db:
        good_message = Message(
            conversation_id=conversation_id, role="assistant", content="good view",
        )
        corrupt_message = Message(
            conversation_id=conversation_id, role="assistant", content="damaged view",
        )
        misbound_message = Message(
            conversation_id=wrong_conversation_id, role="assistant", content="wrong conversation",
        )
        wrong_owner_message = Message(
            conversation_id=conversation_id, role="assistant", content="wrong view owner",
        )
        user_message = Message(
            conversation_id=conversation_id, role="user", content="not an assistant view",
        )
        db.add_all([
            good_message, corrupt_message, misbound_message,
            wrong_owner_message, user_message,
        ])
        db.commit()
        foreign_user = User(username="view-owner-mismatch", password_hash="hash")
        db.add(foreign_user)
        db.commit()
        wrong_owner_row = db.get(UIView, wrong_owner_view.view_id)
        wrong_owner_row.user_id = foreign_user.id
        db.add(wrong_owner_row)
        db.commit()
        db.add_all([
            MessageView(message_id=good_message.id,
                        view_id=good_view.view_id, revision=good_view.revision),
            MessageView(message_id=corrupt_message.id,
                        view_id=corrupt_view.view_id, revision=corrupt_view.revision),
            MessageView(message_id=misbound_message.id,
                        view_id=good_view.view_id, revision=good_view.revision),
            MessageView(message_id=wrong_owner_message.id,
                        view_id=wrong_owner_view.view_id, revision=wrong_owner_view.revision),
            MessageView(message_id=user_message.id,
                        view_id=good_view.view_id, revision=good_view.revision),
        ])
        corrupt_revision = db.get(
            ViewRevision, (corrupt_view.view_id, corrupt_view.revision),
        )
        corrupt_revision.ciphertext = "not-an-encrypted-view-snapshot"
        db.add(corrupt_revision)
        db.commit()
        history = db.exec(select(Message).where(
            Message.id.in_([
                good_message.id, corrupt_message.id,
                misbound_message.id, wrong_owner_message.id, user_message.id,
            ]),
        )).all()

        restored = _load_views(db, history)

    assert set(restored) == {good_message.id}
    assert restored[good_message.id].view_id == good_view.view_id
