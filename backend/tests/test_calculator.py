import asyncio
import json

import pytest
from sqlmodel import Session, select

from app.agent.llm import LLMChunk
from app.agent.registry import RiskLevel
from app.db.session import get_engine
from app.models import AuditLog
from app.tools.calculator_tools import (
    CalculationError,
    calculate,
    evaluate_expression,
)
from app.tools.register import create_agent_registry


def _events(response):
    return [json.loads(line[6:]) for line in response.text.splitlines() if line.startswith("data: ")]


@pytest.mark.parametrize("expression,expected", [
    ("1+2", 3),
    ("2 * (3 + 4)", 14),
    ("-5 + 2", -3),
    ("+4", 4),
    ("7 // 2", 3),
    ("7 % 4", 3),
    ("2 ** 10", 1024),
    ("10 / 4", 2.5),
    ("1.5 + 2.5", 4.0),
])
def test_calculator_accepts_basic_arithmetic(expression, expected):
    assert evaluate_expression(expression) == expected


@pytest.mark.parametrize("expression", [
    "a + 1",
    "__import__('os')",
    "open('x')",
    "(1).__class__",
    "[1, 2]",
    "1 if 1 else 2",
    "True",
    "1j",
    "sum([1, 2])",
    "lambda: 1",
])
def test_calculator_rejects_code_and_non_numeric_nodes(expression):
    with pytest.raises(CalculationError, match="仅支持数字和基本运算"):
        evaluate_expression(expression)


@pytest.mark.parametrize("expression,message", [
    ("", "表达式无效或过长"),
    ("1 + ", "表达式无效"),
    ("1/0", "除数不能为零"),
    ("2 ** 1000", "指数过大"),
    ("1e309", "结果超出范围"),
    ("9" * 300, "表达式无效或过长"),
])
def test_calculator_rejects_invalid_or_unsafe_values(expression, message):
    with pytest.raises(CalculationError, match=message):
        evaluate_expression(expression)


def test_calculator_rejects_too_many_nodes_and_times_out():
    with pytest.raises(CalculationError, match="表达式过于复杂"):
        evaluate_expression("1+" * 60 + "1")
    with pytest.raises(CalculationError, match="计算超时"):
        evaluate_expression("1+1", max_seconds=-1)


def test_calculator_tool_validates_arguments_and_returns_fixed_errors():
    assert asyncio.run(calculate(user_id=1, expression="2+3")) == {
        "ok": True, "data": {"result": 5, "kind": "int"}, "error": None,
    }
    assert asyncio.run(calculate(user_id=1, expression="1/0"))["error"] == "除数不能为零"
    assert asyncio.run(calculate(user_id=1, expression="a+1"))["error"] == "仅支持数字和基本运算"
    assert asyncio.run(calculate(user_id=1, expression=123))["error"] == "计算参数无效"
    assert asyncio.run(calculate(user_id=1, expression="1+1", extra=1))["error"] == "计算参数无效"


def test_calculator_is_registered_as_green_tool():
    spec = create_agent_registry().get("calculate")
    assert spec is not None and spec.risk == RiskLevel.GREEN
    assert spec.parameters["properties"]["expression"]["type"] == "string"


def test_chat_renders_calculator_result_not_model_text(client, auth_headers, monkeypatch):
    class CalcLLM:
        calls = 0

        async def stream(self, messages, tools=None):
            self.calls += 1
            if self.calls == 1:
                yield LLMChunk(tool_calls=[{"id": "calc", "type": "function", "function": {
                    "name": "calculate", "arguments": '{"expression": "2+3*4"}',
                }}])
            else:
                yield LLMChunk(content="计算结果是 14。")

    monkeypatch.setattr("app.agent.loop.get_llm", lambda: CalcLLM())
    conversation = client.post("/api/chat/conversations", json={}, headers=auth_headers).json()
    response = client.post(f"/api/chat/conversations/{conversation['id']}/messages",
                           json={"content": "计算 2+3*4"}, headers=auth_headers)
    assert response.status_code == 200
    assert "计算结果是 14。" in response.text
    with Session(get_engine()) as session:
        logs = session.exec(select(AuditLog)).all()
        assert any(entry.event_type == "tool_called" and entry.tool == "calculate" for entry in logs)
        assert any(entry.event_type == "tool_result" and entry.tool == "calculate" for entry in logs)
        assert any(entry.event_type == "risk_assessed" and entry.tool == "calculate"
                   and entry.risk_level == "green" for entry in logs)


def test_chat_rejects_calculator_user_id_override(client, auth_headers, monkeypatch):
    class CalcLLM:
        calls = 0

        async def stream(self, messages, tools=None):
            self.calls += 1
            if self.calls == 1:
                yield LLMChunk(tool_calls=[{"id": "calc", "type": "function", "function": {
                    "name": "calculate", "arguments": '{"expression": "1+1", "user_id": 2}',
                }}])
            else:
                yield LLMChunk(content="查询参数无效。")

    monkeypatch.setattr("app.agent.loop.get_llm", lambda: CalcLLM())
    conversation = client.post("/api/chat/conversations", json={}, headers=auth_headers).json()
    response = client.post(f"/api/chat/conversations/{conversation['id']}/messages",
                           json={"content": "计算 1+1"}, headers=auth_headers)
    assert "查询参数无效" in response.text
    assert "计算结果" not in response.text
