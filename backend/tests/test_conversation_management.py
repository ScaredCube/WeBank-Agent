"""Conversation title management must not alter banking history or other users' data."""
from app.models import Conversation
from app.db.session import get_engine
from sqlmodel import Session


def test_rename_conversation_is_persisted_and_does_not_change_messages(client, auth_headers):
    original = client.post('/api/chat/conversations', headers=auth_headers, json={}).json()
    cid = original['id']
    rename = client.patch(f'/api/chat/conversations/{cid}', headers=auth_headers,
                          json={'title': '  本月收支比较  '})
    assert rename.status_code == 200
    assert rename.json()['title'] == '本月收支比较'
    assert rename.headers['cache-control'] == 'no-store'
    listing = client.get('/api/chat/conversations', headers=auth_headers).json()
    assert any(item['id'] == cid and item['title'] == '本月收支比较' for item in listing)
    assert client.get(f'/api/chat/conversations/{cid}/messages', headers=auth_headers).json() == []
    with Session(get_engine()) as session:
        assert session.get(Conversation, cid).title == '本月收支比较'


def test_rename_unauthorized_or_invalid_title(client, auth_headers):
    cid = client.post('/api/chat/conversations', headers=auth_headers, json={}).json()['id']
    assert client.patch(f'/api/chat/conversations/{cid}', json={'title': '测试'}).status_code == 401
    assert client.patch('/api/chat/conversations/999999', headers=auth_headers,
                        json={'title': '越权'}).status_code == 404
    for title in ['', '   ', 'a' * 61]:
        assert client.patch(f'/api/chat/conversations/{cid}', headers=auth_headers,
                            json={'title': title}).status_code == 422
    assert client.get('/api/chat/conversations', headers=auth_headers).json()[0]['title'] == '新对话'
