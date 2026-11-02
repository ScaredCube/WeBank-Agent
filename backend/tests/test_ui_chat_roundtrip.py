"""Real HTTP/SSE and persistence with isolated deterministic Agent/Composer doubles."""
import json

from sqlmodel import Session, select

from app.agent.loop import AgentEvent
from app.core.config import settings
from app.db.session import get_engine
from app.models import Account, MessageResult, User
from tests.test_trusted_ui_results import bill


def events(response):
    assert response.status_code == 200, response.text
    return [json.loads(line[6:]) for line in response.text.splitlines() if line.startswith('data: ')]


def install(monkeypatch, *, currency="CNY", include_metadata=True):
    calls = {'agent': 0, 'composer': 0, 'context': [], 'fallback': False}
    async def stream(self, history, user_id, **kwargs):
        calls['agent'] += 1
        calls['context'].append({'kwargs': kwargs, 'history': history})
        with Session(get_engine()) as db:
            account = db.exec(select(Account).where(Account.user_id == user_id)).first()
            account_id = account.id
        month = '2026-10' if calls['agent'] == 1 else '2026-09'
        bill_data = bill(month, 12000 if month.endswith('10') else 9000, 6000 if month.endswith('10') else 3000)
        bill_data['currency'] = currency
        event_data = {'data': bill_data}
        if include_metadata:
            event_data['trusted_metadata'] = {'account_id': account_id}
        yield AgentEvent('bill_result', event_data)
        yield AgentEvent('delta', {'text': '查询已完成。'})

    class Composer:
        async def compose(self, *, question, catalog, context=None):
            calls['composer'] += 1
            # The result must already be durable before generation begins.
            with Session(get_engine()) as db:
                assert db.exec(select(MessageResult)).first() is not None
            if calls['fallback']:
                return None
            data = next((d for d in catalog['datasets'] if d['kind'] == 'comparison'), catalog['datasets'][0])
            return {'root': 'root', 'elements': {'root': {
                'type': 'ComparisonTable' if data['kind'] == 'comparison' else 'CategoryBarChart',
                'props': {'dataset_ref': data['dataset_ref']},
            }}}
    monkeypatch.setattr('app.agent.loop.AgentLoop.stream', stream)
    monkeypatch.setattr('app.services.chat_turn.get_ui_composer', lambda: Composer())
    return calls


def test_chat_view_multiturn_is_durable_and_retry_does_not_recompose(client, auth_headers, monkeypatch):
    calls = install(monkeypatch)
    cid = client.post('/api/chat/conversations', headers=auth_headers, json={}).json()['id']
    url = f'/api/chat/conversations/{cid}/messages'
    first = events(client.post(url, headers=auth_headers, json={'content': '看2026年10月消费结构', 'request_id': 'ui-read-0001'}))
    view = next(e['view'] for e in first if e['type'] == 'ui_view')
    assert next(e['message'] for e in first if e['type'] == 'done')['ui_view'] == view
    assert [e['type'] for e in first].index('bill_result') < [e['type'] for e in first].index('ui_view')
    category_id = next(iter(view['trusted_data']['datasets'].values()))['rows'][0]['id']
    selected = client.post(f"/api/views/{view['view_id']}/interactions", headers=auth_headers,
        json={'event_id': 'select-category-01', 'base_revision': 1,
              'action': 'select_category', 'value': category_id}).json()
    assert selected['revision'] == 2
    payload = {'content': '和上个月相比呢', 'request_id': 'ui-read-0002',
               'view_context': {'view_id': view['view_id'], 'revision': 2}}
    second = events(client.post(url, headers=auth_headers, json=payload))
    new_view = next(e['view'] for e in second if e['type'] == 'ui_view')
    assert new_view['view_id'] == view['view_id'] and new_view['revision'] == 3
    comparison = next(d for d in new_view['trusted_data']['datasets'].values() if d['kind'] == 'comparison')
    assert any(row.get('metric') == '餐饮' and row.get('delta_fen') == 3000 for row in comparison['rows'])
    assert '餐饮' in calls['context'][1]['history'][-1]['content']
    assert calls['context'][1]['kwargs']['verified_account_token'] is not None
    assert client.get(f"/api/views/{view['view_id']}?revision=1", headers=auth_headers).json() == view
    retry = events(client.post(url, headers=auth_headers, json=payload))
    assert retry[-1]['message']['ui_view'] == new_view
    assert calls['agent'] == 2 and calls['composer'] == 2
    changed = {**payload, 'view_context': {'view_id': view['view_id'], 'revision': 1}}
    assert client.post(url, headers=auth_headers, json=changed).status_code == 409
    history = client.get(url, headers=auth_headers).json()
    rows = history if isinstance(history, list) else history['items']
    assert next(m['ui_view'] for m in rows if m['role'] == 'assistant')['revision'] == 1


def test_tool_free_view_followup_persists_the_exact_context_revision(client, auth_headers, monkeypatch):
    from app.agent.llm import LLMChunk
    from app.agent.loop import AgentLoop

    original_stream = AgentLoop.stream
    calls = install(monkeypatch)
    cid = client.post('/api/chat/conversations', headers=auth_headers, json={}).json()['id']
    url = f'/api/chat/conversations/{cid}/messages'
    first = events(client.post(url, headers=auth_headers,
        json={'content': '看2026年10月消费结构', 'request_id': 'ui-context-first-01'}))
    initial_view = next(event['view'] for event in first if event['type'] == 'ui_view')
    category_id = next(iter(initial_view['trusted_data']['datasets'].values()))['rows'][0]['id']
    selected = client.post(f"/api/views/{initial_view['view_id']}/interactions",
        headers=auth_headers,
        json={'event_id': 'ui-context-select-01', 'base_revision': 1,
              'action': 'select_category', 'value': category_id}).json()
    assert selected['revision'] == 2
    dataset = next(dataset for dataset in selected['trusted_data']['datasets'].values()
                   if dataset['kind'] == 'categories')
    row = next(row for row in dataset['rows'] if row['id'] == category_id)
    label = row['label']
    whole, cents = divmod(row['amount_fen'], 100)
    expected_amount = f'{whole:,}.{cents:02d}'

    class Provider:
        calls = 0
        async def stream(self, messages, tools=None):
            self.calls += 1
            yield LLMChunk(content='这个回答不应调用模型')

    provider = Provider()
    monkeypatch.setattr(AgentLoop, 'stream', original_stream)
    monkeypatch.setattr('app.api.routes.chat.AgentLoop', lambda: AgentLoop(llm=provider))
    second = events(client.post(url, headers=auth_headers, json={
        'content': '这个分类有什么值得注意？',
        'view_context': {'view_id': selected['view_id'], 'revision': selected['revision']},
        'request_id': 'ui-context-followup-01',
    }))
    message = next(event['message'] for event in second if event['type'] == 'done')
    assert provider.calls == 1  # V2 may independently phrase a verified view follow-up.
    assert message['ui_view'] == selected
    assert label in message['content'] and expected_amount in message['content']
    assert f"{row['count']} 笔" in message['content']
    assert message['ui_view']['revision'] == 2

    history = client.get(url, headers=auth_headers).json()
    rows = history if isinstance(history, list) else history['items']
    assistant = [row for row in rows if row['role'] == 'assistant']
    assert assistant[-1]['ui_view'] == selected


def test_chat_composer_failure_keeps_durable_financial_result(client, auth_headers, monkeypatch):
    calls = install(monkeypatch)
    calls['fallback'] = True
    cid = client.post('/api/chat/conversations', headers=auth_headers, json={}).json()['id']
    url = f'/api/chat/conversations/{cid}/messages'
    output = events(client.post(url, headers=auth_headers,
        json={'content': '看看本月消费', 'request_id': 'ui-fallback-0001'}))
    assert {'type': 'ui_status', 'status': 'fallback'} in output
    message = output[-1]['message']
    assert message['ui_view'] is None and message['bill_result']['consumption_fen'] == 12000
    assert calls['composer'] == 1


def test_invalid_composed_reference_logs_safe_reason_and_falls_back(client, auth_headers, monkeypatch, caplog):
    install(monkeypatch)
    class InvalidComposer:
        async def compose(self, **kwargs):
            return {'root': 'root', 'elements': {'root': {
                'type': 'CategoryBarChart', 'props': {'dataset_ref': 'untrusted-private-reference'},
            }}}
    monkeypatch.setattr('app.services.chat_turn.get_ui_composer', lambda: InvalidComposer())
    cid = client.post('/api/chat/conversations', headers=auth_headers, json={}).json()['id']
    output = events(client.post(f'/api/chat/conversations/{cid}/messages', headers=auth_headers,
        json={'content': '分析消费', 'request_id': 'ui-invalid-ref-01'}))
    assert {'type': 'ui_status', 'status': 'fallback'} in output
    assert output[-1]['message']['bill_result'] is not None
    assert 'dataset reference does not exist' in caplog.text
    assert 'untrusted-private-reference' not in caplog.text


def test_verified_bill_still_composes_after_later_agent_error(client, auth_headers, monkeypatch):
    calls = install(monkeypatch)

    async def partial_stream(self, history, user_id, **kwargs):
        with Session(get_engine()) as db:
            account = db.exec(select(Account).where(Account.user_id == user_id)).first()
            account_id = account.id
        yield AgentEvent('bill_result', {'data': bill('2026-10', 12000, 6000),
                                        'trusted_metadata': {'account_id': account_id}})
        yield AgentEvent('error', {'message': '后续步骤失败'})

    monkeypatch.setattr('app.agent.loop.AgentLoop.stream', partial_stream)
    cid = client.post('/api/chat/conversations', headers=auth_headers, json={}).json()['id']
    output = events(client.post(f'/api/chat/conversations/{cid}/messages', headers=auth_headers,
        json={'content': '分析消费', 'request_id': 'ui-partial-error-01'}))
    view = next(event['view'] for event in output if event['type'] == 'ui_view')
    message = next(event['message'] for event in output if event['type'] == 'done')
    assert '部分查询已完成' in message['content']
    assert message['bill_result']['consumption_fen'] == 12000
    assert message['ui_view'] == view and calls['composer'] == 1


def test_verified_selected_account_fills_missing_internal_result_provenance(client, auth_headers, monkeypatch):
    install(monkeypatch, include_metadata=False)
    with Session(get_engine()) as db:
        user = db.exec(select(User).where(User.username == 'demo')).one()
        account = db.exec(select(Account).where(Account.user_id == user.id)).first()
        account_id = account.id
    cid = client.post('/api/chat/conversations', headers=auth_headers, json={}).json()['id']
    output = events(client.post(f'/api/chat/conversations/{cid}/messages', headers=auth_headers,
        json={'content': '分析2026年10月消费分类',
              'references': [{'kind': 'account', 'id': account_id}]}))

    view = next(event['view'] for event in output if event['type'] == 'ui_view')
    assert view['trusted_data']['datasets']
    assert output[-1]['message']['bill_result']


def test_view_link_failure_falls_back_to_saved_bank_result(client, auth_headers, monkeypatch):
    install(monkeypatch)
    from app.services import chat_turn
    actual = chat_turn.finalize_assistant

    def fail_view_binding(*args, **kwargs):
        if kwargs.get('view') is not None:
            raise RuntimeError('view binding failed')
        return actual(*args, **kwargs)

    monkeypatch.setattr(chat_turn, 'finalize_assistant', fail_view_binding)
    cid = client.post('/api/chat/conversations', headers=auth_headers, json={}).json()['id']
    output = events(client.post(f'/api/chat/conversations/{cid}/messages', headers=auth_headers,
        json={'content': '分析本月消费', 'request_id': 'link-fail-0001'}))
    assert not any(event['type'] == 'ui_view' for event in output)
    assert {'type': 'ui_status', 'status': 'fallback'} in output
    assert output[-1]['type'] == 'done' and output[-1]['message']['bill_result']


def test_cancelled_composer_keeps_saved_reply_replayable(client, auth_headers, monkeypatch):
    import asyncio
    from app.agent.tool_executor import VerifiedToolContext
    from app.services.chat_submissions import claim_submission
    from app.services.chat_turn import ChatTurn, stream_chat_turn
    from app.models import ChatSubmission

    cid = client.post('/api/chat/conversations', headers=auth_headers, json={}).json()['id']
    with Session(get_engine()) as db:
        user = db.exec(select(User).where(User.username == 'demo')).one()
        account = db.exec(select(Account).where(Account.user_id == user.id)).first()
        uid, aid = user.id, account.id
        submission, _ = claim_submission(db, user_id=uid, conversation_id=cid,
            request_id='cancel-compose-001', payload_digest='digest')
        sid = submission.id

    class Loop:
        async def stream(self, *args, **kwargs):
            yield AgentEvent('bill_result', {'data': bill('2026-10', 12000, 6000),
                                            'trusted_metadata': {'account_id': aid}})
            yield AgentEvent('delta', {'text': '查询完成'})
    class Composer:
        async def compose(self, **kwargs):
            raise asyncio.CancelledError()
    monkeypatch.setattr('app.services.chat_turn.get_ui_composer', lambda: Composer())

    async def run():
        async def connected(): return False
        turn = ChatTurn(conversation_id=cid, submission_id=sid, history=[],
                        original_request='分析消费', verified=VerifiedToolContext(user_id=uid))
        try:
            async for _ in stream_chat_turn(turn, Loop(), connected, lambda event: event):
                pass
        except asyncio.CancelledError:
            pass
    asyncio.run(run())
    with Session(get_engine()) as db:
        row = db.get(ChatSubmission, sid)
        assert row.state == 'completed' and row.assistant_message_id is not None
    status = client.get(f'/api/chat/conversations/{cid}/requests/cancel-compose-001', headers=auth_headers).json()
    assert status['message']['bill_result']['consumption_fen'] == 12000


def test_disabled_composer_preserves_results_and_existing_view_history(client, auth_headers, monkeypatch):
    monkeypatch.setattr(settings, "generative_ui_enabled", True)
    calls = install(monkeypatch)
    cid = client.post('/api/chat/conversations', headers=auth_headers, json={}).json()['id']
    url = f'/api/chat/conversations/{cid}/messages'
    first = events(client.post(url, headers=auth_headers,
        json={'content': '看2026年10月消费结构', 'request_id': 'ui-enabled-0001'}))
    first_view = next(e['view'] for e in first if e['type'] == 'ui_view')

    monkeypatch.setattr(settings, "generative_ui_enabled", False)
    second = events(client.post(url, headers=auth_headers,
        json={'content': '和上个月相比呢', 'request_id': 'ui-disabled-0002',
              'view_context': {'view_id': first_view['view_id'], 'revision': 1}}))
    second_message = next(e['message'] for e in second if e['type'] == 'done')

    assert {'type': 'ui_status', 'status': 'fallback'} in second
    assert not any(e == {'type': 'ui_status', 'status': 'composing'} for e in second)
    assert second_message['ui_view'] is None
    assert second_message['bill_result']['consumption_fen'] == 9000
    assert calls['composer'] == 1
    assert client.get(f"/api/views/{first_view['view_id']}?revision=1",
                      headers=auth_headers).json() == first_view

    history = client.get(url, headers=auth_headers).json()
    rows = history if isinstance(history, list) else history['items']
    assistants = [row for row in rows if row['role'] == 'assistant']
    assert assistants[0]['ui_view'] == first_view
    assert assistants[1]['ui_view'] is None
    assert assistants[1]['bill_result']['consumption_fen'] == 9000
    with Session(get_engine()) as db:
        assert len(db.exec(select(MessageResult)).all()) == 2


def test_non_cny_bill_keeps_fixed_result_but_uses_ui_fallback(client, auth_headers, monkeypatch):
    calls = install(monkeypatch, currency="USD")
    cid = client.post('/api/chat/conversations', headers=auth_headers, json={}).json()['id']
    url = f'/api/chat/conversations/{cid}/messages'
    output = events(client.post(url, headers=auth_headers,
        json={'content': 'show my monthly bill', 'request_id': 'ui-usd-fallback-01'}))
    message = next(e['message'] for e in output if e['type'] == 'done')

    assert {'type': 'ui_status', 'status': 'fallback'} in output
    assert not any(e['type'] == 'ui_view' for e in output)
    assert message['bill_result']['currency'] == 'USD'
    assert message['ui_view'] is None
    assert calls['composer'] == 0

    history = client.get(url, headers=auth_headers).json()
    rows = history if isinstance(history, list) else history['items']
    assistant = next(row for row in rows if row['role'] == 'assistant')
    assert assistant['bill_result']['currency'] == 'USD'
    assert assistant['ui_view'] is None
