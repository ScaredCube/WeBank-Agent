import base64
import json
from concurrent.futures import ThreadPoolExecutor

from sqlmodel import Session, select

from app.core.config import settings
from app.core.security import create_access_token
from app.db.session import get_engine
from app.models import Account, Card, User, ViewRevision
from app.services.view_service import create_or_append_view
from tests.test_trusted_ui_results import result


def setup_view(client, headers):
    cid = client.post('/api/chat/conversations', headers=headers, json={}).json()['id']
    with Session(get_engine()) as db:
        user = db.exec(select(User).where(User.username == 'demo')).one()
        account = db.exec(select(Account).where(Account.user_id == user.id)).first()
        uid, aid = user.id, account.id
    return create_or_append_view(user_id=uid, conversation_id=cid,
        results=[result('bill-oct', '2026-10', 12000, aid)],
        spec={'root': 'm', 'elements': {'m': {'type': 'CategoryBarChart',
              'props': {'dataset_ref': 'bill-oct:categories'}}}})


def test_view_history_idempotency_conflicts_and_encryption(client, auth_headers):
    view = setup_view(client, auth_headers)
    url = f'/api/views/{view.view_id}'
    first = client.get(url, headers=auth_headers)
    assert first.status_code == 200 and first.headers['cache-control'] == 'no-store'
    assert first.json()['revision'] == 1
    action = {'event_id': 'event-select-01', 'base_revision': 1,
              'action': 'select_category', 'value': view.trusted_data.datasets['bill-oct:categories'].rows[0].id}
    updated = client.post(url + '/interactions', headers=auth_headers, json=action)
    assert updated.status_code == 200 and updated.json()['revision'] == 2
    assert client.post(url + '/interactions', headers=auth_headers, json=action).json() == updated.json()
    assert client.post(url + '/interactions', headers=auth_headers,
                       json={**action, 'value': 'missing'}).status_code == 409
    assert client.post(url + '/interactions', headers=auth_headers,
                       json={**action, 'event_id': 'another-event'}).status_code == 409
    assert client.get(url + '?revision=1', headers=auth_headers).json() == first.json()
    assert client.get(url, headers=auth_headers).json()['revision'] == 2
    assert client.get(url + '?revision=999', headers=auth_headers).status_code == 404
    with Session(get_engine()) as db:
        stored = db.exec(select(ViewRevision).where(ViewRevision.view_id == view.view_id)).all()
        assert len(stored) == 2
        assert {row.key_version for row in stored} == {settings.data_encryption_key_version}
        for row in stored:
            assert '餐饮' not in row.ciphertext and 'consumption_fen' not in row.ciphertext


def test_view_history_remains_readable_after_encryption_key_rotation(client, auth_headers, monkeypatch):
    view = setup_view(client, auth_headers)
    old_version = settings.data_encryption_key_version
    old_key = settings.data_encryption_key
    rotated_version = 'test-v2'
    rotated_key = base64.urlsafe_b64encode(b'c' * 32).decode()
    monkeypatch.setattr(settings, 'data_encryption_key_version', rotated_version)
    monkeypatch.setattr(settings, 'data_encryption_key', rotated_key)
    monkeypatch.setattr(
        settings, 'data_encryption_previous_keys', json.dumps({old_version: old_key}),
    )

    url = f'/api/views/{view.view_id}'
    restored = client.get(url, headers=auth_headers)
    assert restored.status_code == 200
    assert restored.json()['revision'] == 1
    updated = client.post(url + '/interactions', headers=auth_headers, json={
        'event_id': 'rotation-sort-01', 'base_revision': 1,
        'action': 'set_sort', 'value': 'amount_desc',
    })
    assert updated.status_code == 200 and updated.json()['revision'] == 2

    with Session(get_engine()) as db:
        rows = db.exec(select(ViewRevision).where(
            ViewRevision.view_id == view.view_id,
        ).order_by(ViewRevision.revision)).all()
        assert [row.key_version for row in rows] == [old_version, rotated_version]

    monkeypatch.setattr(settings, 'data_encryption_previous_keys', '{}')
    assert client.get(url + '?revision=1', headers=auth_headers).status_code == 404


def test_view_owner_and_invalid_actions(client, auth_headers):
    view = setup_view(client, auth_headers)
    url = f'/api/views/{view.view_id}'
    with Session(get_engine()) as db:
        other = User(username='other', password_hash='test-unused')
        db.add(other); db.commit(); db.refresh(other)
        token = create_access_token(str(other.id))
    foreign = {'Authorization': f'Bearer {token}'}
    action = {'event_id': 'event-select-01', 'base_revision': 1,
              'action': 'select_category', 'value': 'missing'}
    assert client.get(url, headers=foreign).status_code == 404
    assert client.post(url + '/interactions', headers=foreign, json=action).status_code == 404
    assert client.post(url + '/interactions', headers=auth_headers, json=action).status_code == 422
    assert client.post(url + '/interactions', headers=auth_headers,
                       json={**action, 'action': 'execute_transfer'}).status_code == 422


def test_chat_rejects_card_from_different_view_account(client, auth_headers):
    view = setup_view(client, auth_headers)
    with Session(get_engine()) as db:
        user = db.exec(select(User).where(User.username == 'demo')).one()
        other = Account(user_id=user.id, name='另一账户', masked_number='****7777',
                        currency='CNY', balance_fen=0)
        db.add(other); db.flush()
        card = Card(account_id=other.id, status='active')
        db.add(card); db.commit(); db.refresh(card)
        card_id = card.id
    response = client.post(f'/api/chat/conversations/{view.conversation_id}/messages',
                           headers=auth_headers, json={
        'content': '看看这张卡', 'references': [{'kind': 'card', 'id': card_id}],
        'view_context': {'view_id': view.view_id, 'revision': 1},
    })
    assert response.status_code == 400


def test_concurrent_view_updates_only_one_revision_wins(client, auth_headers):
    view = setup_view(client, auth_headers)
    url = f'/api/views/{view.view_id}/interactions'
    def update(index):
        return client.post(url, headers=auth_headers, json={
            'event_id': f'concurrent-{index}', 'base_revision': 1,
            'action': 'set_sort', 'value': 'amount_desc' if index == 0 else 'amount_asc',
        }).status_code
    with ThreadPoolExecutor(max_workers=2) as pool:
        statuses = list(pool.map(update, range(2)))
    assert sorted(statuses) == [200, 409]
