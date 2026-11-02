import asyncio
from app.agent.llm import LLMChunk
from app.agent.ui_composer import UIComposer


class Provider:
    mode = "openai"

    def __init__(self, text='{"view_data":{"metrics":{},"datasets":{}},"spec":{"root":"root","elements":{}}}', tool=False):
        self.text, self.tool, self.calls, self.messages = text, tool, 0, None

    async def stream(self, messages, tools=None):
        assert tools is None
        self.calls += 1
        self.messages = messages
        yield LLMChunk(content=self.text, tool_calls=[{}] if self.tool else None)


def run(composer):
    return asyncio.run(composer.compose(question="消费结构", catalog={"metrics": ["m"]}))


def test_composer_uses_generated_catalog_once_and_no_tools():
    provider = Provider()
    assert run(UIComposer(provider=provider)) == {
        "view_data": {"metrics": {}, "datasets": {}},
        "spec": {"root": "root", "elements": {}},
    }
    assert provider.calls == 1
    assert "metric_ref" in provider.messages[0]["content"]
    assert "消费结构" in provider.messages[-1]["content"]


def test_composer_rejects_invalid_outputs_without_repair():
    for text, tool in [
        ('not json', False), ('[]', False),
        ('{"view_data":1,"spec":{"root":"r","elements":{}}}', False),
        ('{}', True), ('x' * 131073, False),
        ('{"view_data":{},"spec":{"root":"r","elements":{},"state":{}}}', False),
    ]:
        provider = Provider(text, tool)
        assert run(UIComposer(provider=provider)) is None
        assert provider.calls == 1


def test_composer_missing_catalog_fails_closed(tmp_path):
    provider = Provider()
    assert run(UIComposer(provider=provider, prompt_path=tmp_path / "missing")) is None
    assert provider.calls == 0


def test_composer_timeout_cancels_stream_without_retry():
    class Slow(Provider):
        cancelled = False

        async def stream(self, messages, tools=None):
            self.calls += 1
            try:
                await asyncio.sleep(5)
                yield LLMChunk(content="{}")
            finally:
                self.cancelled = True

    provider = Slow()
    assert run(UIComposer(provider=provider, timeout_seconds=0.01)) is None
    assert provider.calls == 1 and provider.cancelled


def test_composer_logs_only_a_safe_failure_category(caplog):
    secret_like_output = 'private-model-output-not-json'
    assert run(UIComposer(provider=Provider(secret_like_output))) is None
    assert 'ui composer fallback: invalid_json' in caplog.text
    assert secret_like_output not in caplog.text
