"""Presentation boundary for assistant text without authenticated Tool results.

The LLM can converse and ask for clarification, but cannot self-attest to
balances, transactions, completed actions or privileged system information.
Trusted financial values remain exclusively in bank Tool result renderers.
This is defense-in-depth, not a general semantic fact verifier.
"""
import re

from app.services.redaction import mask_text

_NO_VERIFIED_DATA = "我还没有查到可靠的银行数据。你可以选择对应账户或银行卡，让我为你查询。"
_NO_UNSUPPORTED_ACTION = "这项操作尚未完成。如需办理，请先提供必要信息，之后会进入独立的核对与确认流程。"
_NO_TEXT = "可以告诉我你想了解什么，或者选择一项银行服务。"

_INTERNAL = re.compile(
    r"(?:system_prompt|guard_system_prompt|account_token|source_token|"
    r"target_token|recipient_contact_token|confirmation_token|"
    r"api[_ -]?key|bearer\s+\S+|\[以下是服务端验证的金融对象)",
    re.IGNORECASE,
)
# These are disallowed even if a model claims it has used a bank tool.
_ACTION_COMPLETION = re.compile(
    r"(?:已|已经|成功|刚刚|替你|帮你).{0,12}"
    r"(?:转账|汇款|扣款|支付|挂失|冻结|申购|赎回|取消订阅|成交|执行完|办理成功)"
    r"|(?:转账|汇款|扣款|支付|挂失|申购|赎回).{0,12}(?:成功|完成|已执行|已处理)"
)
# Never display model-authored user-scoped account values as verified results.
_BANK_FACT = re.compile(
    r"(?:你|您|本人的|该|这张|你的|您的|账户|银行卡).{0,16}"
    r"(?:余额(?:是|为|有|剩余|：|:)|交易(?:记录|明细|成功)|"
    r"消费(?:了|金额|总计)|收益(?:是|为|达到)|状态(?:为|是)|"
    r"欠款(?:为|是)|账单(?:金额|共计|总计))"
    r"|(?:余额|账单|收支|交易|持仓).{0,12}"
    r"(?:¥|￥|\d[\d,.]*\s*(?:元|分|万)|一(?:百|千|万)|两(?:百|千|万))"
)
_AMOUNT_CLAIM = re.compile(
    r"(?:¥|￥)\s*\d|\d[\d,.]*\s*(?:元|万元|万块|人民币)"
)
_UNVERIFIED_LOOKUP = re.compile(
    r"(?:已经?查(?:到|询)|查到您的|根据您的账户|系统显示|记录显示|数据库显示)"
)
_MAX_REPLY_CHARS = 1200


def tool_free_reply(raw_content: str) -> str:
    """Release only non-transactional conversational text; fail closed otherwise.

    This text is buffered until a model round finishes, never streamed as raw
    deltas. No trusted financial values are ever sourced from this branch.
    """
    reply = mask_text(raw_content.strip())
    if not reply:
        return _NO_TEXT
    if len(reply) > _MAX_REPLY_CHARS or _INTERNAL.search(reply):
        return _NO_TEXT
    if _ACTION_COMPLETION.search(reply):
        return _NO_UNSUPPORTED_ACTION
    if _BANK_FACT.search(reply) or _AMOUNT_CLAIM.search(reply) or _UNVERIFIED_LOOKUP.search(reply):
        return _NO_VERIFIED_DATA
    return reply
