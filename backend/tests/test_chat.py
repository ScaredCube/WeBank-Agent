import json


def _sse_payloads(text: str) -> list[dict]:
    payloads = []
    for block in text.replace("\r\n", "\n").split("\n\n"):
        for line in block.split("\n"):
            if line.startswith("data: "):
                payloads.append(json.loads(line[len("data: ") :]))
    return payloads


def test_chat_stream_and_persist(client, auth_headers):
    created = client.post("/api/chat/conversations", json={}, headers=auth_headers)
    assert created.status_code == 201
    conversation_id = created.json()["id"]

    response = client.post(
        f"/api/chat/conversations/{conversation_id}/messages",
        json={"content": "你好，帮我看看这个月的账单"},
        headers=auth_headers,
    )
    assert response.status_code == 200
    payloads = _sse_payloads(response.text)
    types = [payload["type"] for payload in payloads]
    assert "delta" in types
    assert types[-1] == "done"

    streamed = "".join(payload["text"] for payload in payloads if payload["type"] == "delta")
    assert "演示模式" in streamed

    messages = client.get(
        f"/api/chat/conversations/{conversation_id}/messages",
        headers=auth_headers,
    ).json()
    assert [message["role"] for message in messages] == ["user", "assistant"]
    assert messages[1]["content"] == streamed

    conversations = client.get("/api/chat/conversations", headers=auth_headers).json()
    assert conversations[0]["title"].startswith("你好")


def test_chat_requires_auth(client):
    response = client.get("/api/chat/conversations")
    assert response.status_code == 401


def test_chat_rejects_missing_conversation(client, auth_headers):
    response = client.post(
        "/api/chat/conversations/999/messages",
        json={"content": "hello"},
        headers=auth_headers,
    )
    assert response.status_code == 404
