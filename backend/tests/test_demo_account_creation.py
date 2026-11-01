"""Account creation is only possible in the explicitly enabled simulated bank."""
from sqlmodel import Session, select

from app.core.config import settings
from app.db.session import get_engine
from app.models import Account, Card, AuditLog


def test_create_demo_account_is_authenticated_and_zero_balance(client, auth_headers):
    assert client.post('/api/bank/accounts/demo', json={'name': '备用账户'}).status_code == 401
    first = client.post('/api/bank/accounts/demo', headers=auth_headers,
                        json={'name': '我的备用账户'})
    assert first.status_code == 201
    data = first.json()
    assert data['name'] == '我的备用账户'
    assert data['balance_fen'] == 0
    assert data['card_status'] == 'missing'
    assert data['can_transfer'] is False
    assert data['masked_number'].startswith('**** ')
    assert first.headers['cache-control'] == 'no-store'
    with Session(get_engine()) as session:
        saved = session.get(Account, data['account_id'])
        assert saved is not None and saved.balance_fen == 0
        assert session.exec(select(Card).where(Card.account_id == saved.id)).first() is None
        assert session.exec(select(AuditLog).where(AuditLog.user_id == saved.user_id, AuditLog.event_type == 'demo_account_created')).first() is not None
    again = client.post('/api/bank/accounts/demo', headers=auth_headers,
                        json={'name': '第三个账户'})
    assert again.status_code == 201
    assert again.json()['account_id'] > data['account_id']
    assert len(client.get('/api/bank/dashboard', headers=auth_headers).json()['accounts']) == 3


def test_demo_creation_disabled_and_input_restricted(client, auth_headers, monkeypatch):
    assert client.post('/api/bank/accounts/demo', headers=auth_headers,
                       json={'name': '<script>alert(1)</script>'}).status_code == 422
    monkeypatch.setattr(settings, 'debug', False)
    response = client.post('/api/bank/accounts/demo', headers=auth_headers,
                           json={'name': '新账户'})
    assert response.status_code == 404
