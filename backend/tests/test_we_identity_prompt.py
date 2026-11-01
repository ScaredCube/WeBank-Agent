"""Identity is a useful service contract, not an unsolicited slogan."""
from app.agent.prompt_assembly import assemble_agent_prompt, assemble_guard_prompt
from app.agent.prompts import SYSTEM_PROMPT
from app.tools.register import create_agent_registry
from app.agent.registry import ToolExecutionMode


def test_we_identity_and_optional_memo_match_the_real_tool_contract():
    text = assemble_agent_prompt().model_messages()[0]["content"]
    assert "小We" in text and "We在你身边" in text
    assert "不要反复自我介绍" in text
    assert "不能自称银行真人客服" in text
    assert "note=\"\"" in text
    assert "附言尚未明确前不要调用准备转账工具" not in text
    transfer = create_agent_registry().get("prepare_transfer")
    assert transfer is not None
    assert transfer.execution == ToolExecutionMode.PREPARE
    assert transfer.parameters["properties"]["note"].get("default") == ""


def test_guard_does_not_depend_on_an_obsolete_hardcoded_readonly_tool_list():
    prompt = assemble_guard_prompt().model_messages()[0]["content"]
    registry = create_agent_registry()
    assert registry.get("get_latest_action_progress") is not None
    assert "风险等级为 green" in prompt
    assert "名称不在某份手写清单中就拒绝" in prompt
    assert "只输出一个 JSON 对象" in prompt
    assert "准备/写操作" in prompt


def test_prompt_describes_new_execution_modes_without_pretending_completion():
    prompt = SYSTEM_PROMPT
    assert "内部转账" in prompt and "收款请求" in prompt
    assert "持仓转换" in prompt
    assert "真实操作回执" in prompt
    assert "查询" in prompt and "分析" in prompt
