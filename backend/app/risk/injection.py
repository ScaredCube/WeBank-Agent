import re
import unicodedata
from dataclasses import dataclass
from typing import Any

from app.agent.registry import ToolSpec

_CONTROL_CHARS = re.compile(r"[\x00-\x08\x0b\x0c\x0e-\x1f\x7f]")
_MAX_ARGUMENT_LENGTH = 1000

_PATTERNS: tuple[tuple[str, re.Pattern[str]], ...] = (
    ("instruction_override", re.compile(
        r"(忽略|无视|忘记|忘掉|跳过|绕过|不要遵守|不必遵守|无需遵守|别遵守).{0,20}"
        r"(之前|以上|上面|前面|系统|所有|全部|任何|安全|权限|银行|工具)?"
        r"(指令|规则|提示词|提示|设定|限制|约束|要求|政策|白名单|审计|风险等级|风控等级)"
    )),
    ("instruction_override", re.compile(
        r"(ignore|disregard|forget|override|bypass).{0,30}"
        r"(previous|prior|above|system|developer|all|any|safety|security)?\s*"
        r"(instruction|instructions|prompt|prompts|rule|rules|policy|policies|guardrail|guardrails|whitelist|audit)"
    )),
    ("verification_bypass", re.compile(
        r"(绕过|关闭|禁用|跳过|取消|不要|无需|不用|别).{0,16}"
        r"(风控|风险控制|风险等级|风控等级|权限|验证|确认|审计|安全机制|安全规则|二次确认|双因素|短信验证|密码验证|"
        r"risk\s*control|verification|confirmation|audit|security|2fa|mfa)"
    )),
    ("risk_tampering", re.compile(
        r"(设置|改为|改成|改称|调成|调为|设为|降低|降级|覆盖|篡改|修改).{0,12}"
        r"(风险等级|风控等级|风险级别|风险).{0,12}(绿色|绿|低风险|自动执行|无需确认|不确认|免确认)"
    )),
    ("risk_tampering", re.compile(
        r"(风险等级|风控等级|风险级别).{0,12}"
        r"(改为|改成|改称|调成|调为|设为|设置|降低|降级|覆盖|篡改|修改).{0,8}"
        r"(绿色|绿|低风险|自动执行|无需确认|不确认|免确认)"
    )),
    ("risk_tampering", re.compile(
        r"(set|change|lower|downgrade|override).{0,20}"
        r"(risk\s*level|risk).{0,20}(green|low\s*risk|auto|without\s*confirmation)"
    )),
    ("jailbreak", re.compile(
        r"(jailbreak|dan\s*mode|developer\s*mode|god\s*mode|unrestricted\s*mode|"
        r"越狱|开发者模式|上帝模式|无限制模式|不受限制模式)"
    )),
    ("role_override", re.compile(
        r"(你现在是|从现在开始你是|你的新身份是|扮演|假装你是|你不再是|"
        r"act\s+as|you\s+are\s+now|from\s+now\s+on\s+you\s+are).{0,24}"
        r"(管理员|系统|开发者|root|admin|superuser|无限制|jailbroken|银行工作人员|客服|dan|unrestricted)"
    )),
    ("role_override", re.compile(
        r"(我是|这里是|作为).{0,8}(管理员|系统管理员|超级管理员|银行管理员|root|admin|superuser)"
    )),
    ("prompt_exfiltration", re.compile(
        r"(泄露|显示|输出|告诉我|发给我|给我看|查询|查看|获取|"
        r"reveal|show|print|output|tell\s+me|give\s+me).{0,16}"
        r"(系统提示词|系统提示|隐藏提示|内部规则|内部指令|"
        r"system\s+prompt|hidden\s+prompt|developer\s+message|internal\s+instructions)"
    )),
    ("prompt_exfiltration", re.compile(
        r"(系统提示词|系统提示|隐藏提示|内部规则|system\s+prompt|hidden\s+prompt)"
        r".{0,8}(是什么|内容|原文)"
    )),
    ("prompt_exfiltration", re.compile(
        r"(系统提示词|系统提示|隐藏提示|内部规则|内部指令|system\s+prompt|hidden\s+prompt)"
        r".{0,12}(发给我|给我|告诉我|显示|输出|泄露|reveal|show|print|output|give\s+me|tell\s+me)"
    )),
    ("role_boundary_marker", re.compile(
        r"(<\|im_start\|>|<\|im_end\|>|<\|system\|>|<\s*/?\s*system\s*>|<<\s*/?\s*sys\s*>>|"
        r"\[/?inst\]|###\s*system|begin\s+system|end\s+system)"
    )),
)


@dataclass(frozen=True)
class InjectionDecision:
    blocked: bool
    categories: tuple[str, ...] = ()


def _normalise(text: str) -> str:
    normalised = unicodedata.normalize("NFKC", text)
    normalised = "".join(ch for ch in normalised if unicodedata.category(ch) != "Cf")
    return re.sub(r"\s+", " ", normalised).strip().lower()


def detect_injection(text: str) -> InjectionDecision:
    if not isinstance(text, str) or not text.strip():
        return InjectionDecision(False)
    normalised = _normalise(text)
    categories = tuple(name for name, pattern in _PATTERNS if pattern.search(normalised))
    return InjectionDecision(bool(categories), categories)


def validate_tool_arguments(spec: ToolSpec | None, arguments: dict[str, Any]) -> str | None:
    if spec is None:
        return "工具不可用"
    properties = spec.parameters.get("properties", {})
    if not isinstance(properties, dict):
        return "工具参数无效"
    allowed = set(properties)
    for key, value in arguments.items():
        if not isinstance(key, str) or key not in allowed:
            return "工具参数不在白名单内"
        if value is None:
            continue
        if type(value) not in (str, int, float, bool):
            return "工具参数类型无效"
        if isinstance(value, str):
            if len(value) > _MAX_ARGUMENT_LENGTH:
                return "工具参数过长"
            if _CONTROL_CHARS.search(value):
                return "工具参数包含非法字符"
    return None
