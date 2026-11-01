"""Constrain responses without verified bank Tool results.

The trust decision comes from the USER'S current request and the existence of
authenticated Tool results, not from model-authored claims of having verified
anything. This request classifier is deliberately conservative and is not a
universal Chinese intent classifier. A small output filter remains defense
in depth for conversational requests only.
"""
from dataclasses import dataclass
from enum import Enum
import re
import unicodedata


_NO_VERIFIED_DATA = "我还没有查到可靠的银行数据。你可以选择对应账户或银行卡，让我为你查询。"
_NO_UNSUPPORTED_ACTION = "本轮没有执行操作。请先提供需要处理的对象和必要信息；涉及资金或卡片的模拟操作须独立确认。"
_NO_TRANSFER = "本轮尚未创建待确认转账。请先选择付款账户与收款联系人，并说明明确金额；之后才能生成待确认操作。"
_NO_CARD_ACTION = "本轮没有准备或执行银行卡操作。请先选择银行卡；模拟挂失需要独立验证和执行。"
_NO_WEALTH_ACTION = "本轮没有准备或执行理财操作。请先选择理财产品与账户、明确操作金额；申购或赎回需要独立验证和执行。"
_NO_SUBSCRIPTION_ACTION = "本轮没有准备或执行订阅操作。请先选择需要处理的订阅；取消订阅须经独立确认。"
_NO_ACTION_STATUS = "我还没有核实这笔操作的实际状态。请到操作记录核对，避免因网络或会话异常重复发起。"
_NO_TEXT = "可以告诉我你想了解什么，或者选择一项银行服务。"

_MAX_REPLY_CHARS = 1200
_EDUCATION = (
    "什么是", "解释一下", "解释", "科普", "原理", "举个例子", "举例",
    "假设", "概念", "区别", "是什么意思", "是什么", "如何理解", "为什么",
    "介绍一下", "介绍", "有哪些", "有什么", "如何",
)
_ACTION = (
    "转账", "汇款", "打款", "付款", "扣款", "支付", "挂失", "冻结",
    "解冻", "申购", "赎回", "取消订阅", "订阅取消", "退订", "提现", "转出",
    "买入", "卖出", "发款",
)
_PRIVATE_READ = (
    "余额", "账单", "流水", "收支", "收入", "支出", "消费", "交易",
    "持仓", "收益", "还款", "订阅", "账户", "银行卡", "卡片", "资金",
)
_INTERNAL = re.compile(
    r"(?:system_prompt|guard_system_prompt|account_token|source_token|"
    r"target_token|recipient_contact_token|confirmation_token|"
    r"phone_input|phone_tmp|card_input|"
    r"api[_ -]?key|bearer\s+\S+|\[以下是服务端验证的金融对象)",
    re.IGNORECASE,
)
# A secondary anomaly detector. Authorization for user-scoped banking answers
# does NOT rely on these finite patterns; scope is decided before inspecting
# model output.
_ACTION_COMPLETION = re.compile(
    r"(?:已|已经|成功|刚刚|替你|帮你).{0,12}"
    r"(?:转账|汇款|扣款|支付|挂失|冻结|申购|赎回|取消订阅|成交|执行完|办理成功|汇出|到账)"
    r"|(?:转账|汇款|扣款|支付|挂失|申购|赎回|款项).{0,12}"
    r"(?:成功|完成|已执行|已处理|已经汇出|已汇出|已到账)"
    r"|(?:款项|资金).{0,5}(?:已|已经)(?:汇出|到账|转出)"
)
_BANK_FACT = re.compile(
    r"(?:你|您|本人的|该|这张|你的|您的|账户|银行卡).{0,16}"
    r"(?:余额(?:是|为|有|剩余|：|:|大概|约)|交易(?:记录|明细|成功)|"
    r"消费(?:了|金额|总计)|收益(?:是|为|达到)|状态(?:为|是)|"
    r"欠款(?:为|是)|账单(?:金额|共计|总计))"
    r"|(?:余额|账单|收支|交易|持仓).{0,12}"
    r"(?:¥|￥|\d[\d,.]*\s*(?:元|分|万|块)|一(?:百|千|万)|两(?:百|千|万)|五千块)"
)
_AMOUNT_CLAIM = re.compile(
    r"(?:¥|￥)\s*\d|\d[\d,.]*\s*(?:元|万元|万块|人民币)"
)
# Only remove narrowly worded budget questions from the amount check; an
# asserted price, balance or financial fact must still be checked normally.
_BUDGET_QUESTION = re.compile(
    r"预算(?:大概|大约|是)?\s*(?:¥|￥)?\d+(?:\.\d{1,2})?\s*(?:元|块)?"
    r"(?:\s*(?:还是|或者|或|到|至)\s*(?:¥|￥)?\d+(?:\.\d{1,2})?\s*(?:元|块)?)?"
    r"\s*(?:左右)?(?:吗|呢|么)[？?]?"
)
# Recognize explicit inability without treating the words '帮你转账' as an
# assertion that a transfer happened. Other claims in the reply remain checked.
_DENIED_CAPABILITY = re.compile(
    r"(?:不能|无法|不支持)(?:直接)?(?:帮你|为你|替你)?"
    r"(?:转账|汇款|扣款|支付|挂失|冻结|申购|赎回)(?=[，。！？；、\s或]|$)"
)
_UNVERIFIED_ORDER = re.compile(
    r"(?:已|已经|成功|刚刚).{0,12}(?:下单|订购|预订|预定|付款|支付|订好|购买)"
    r"|(?:订单|商品|花束).{0,12}(?:已下单|已订购|已付款|已支付|订好了)"
    r"|(?:帮你|替你|为你).{0,8}(?:订好了|下好单|买好了)"
)
_UNVERIFIED_LOOKUP = re.compile(
    r"(?:已经?查(?:到|询)|查到您的|根据您的账户|系统显示|记录显示|数据库显示)"
)


class NoToolScope(str, Enum):
    CONVERSATION = "conversation"
    EDUCATIONAL = "educational"
    PRIVATE_READ = "private_read"
    ACTION = "action"
    ACTION_STATUS = "action_status"


# These signals only decide how to present an UNVERIFIED no-Tool response.
# They cannot grant Tool permissions or determine business operation outcomes.
_PERSONAL_CUES = (
    "我的", "本人", "这笔", "这张", "该账户", "本月", "上个月",
    "刚才", "刚刚", "上次", "之前", "这个账户",
)
_STATUS_CUES = (
    "成功了吗", "完成了吗", "是否成功", "是不是成功", "有没有成功",
    "是否完成", "到账了吗", "到账了没", "到账了没有", "执行了吗",
    "到账没", "到账了么", "到了吗", "到了没", "没到", "没到账",
    "处理了吗", "失败了吗", "失败了", "为何失败", "怎么失败",
    "是否失败", "状态如何", "了没有", "了没", "了吗",
)
_ACTION_SYNONYMS = ("发款", "汇出", "到账", "款项", "这笔钱", "发给", "钱")
_ACTION_PATTERN = "|".join(map(re.escape, _ACTION + _ACTION_SYNONYMS))
_PRIVATE_PATTERN = "|".join(map(re.escape, _PRIVATE_READ))
# Abbreviated transfers such as "给他转100元" omit the full "转账" verb.
# Treat these as actions even if a separate clause contains "解释一下".
_TRANSFER_SHORTHAND = re.compile(
    r"(?:给.{0,12}(?:转|打|汇|发)\s*\d[\d,.]*\s*(?:元|块|万|分)"
    r"|(?:转|打|汇)\s*\d[\d,.]*\s*(?:元|块|万|分)(?:给|到|向)?"
    r"|给.{0,12}转点钱)"
)
# A separate imperative clause can follow an explanatory clause, e.g.
# "先解释一下，再给小明转账100元". Merely mentioning the example
# "解释一下给朋友转账100元的手续费" is not an execution instruction.
_DIRECTED_TRANSFER = re.compile(
    r"(?:^|[，,。；;\s]|然后|并)(?:再|请|帮我|替我|为我|立刻|马上)*"
    r"给.{1,12}(?:转账|汇款|打款)(?:\s*\d[\d,.]*\s*(?:元|块|万|分)?|(?=$|[，,。；;！？]))"
)
# Knowledge-seeking "我想知道如何转账" and "帮我解释转账" must not
# become an execution request merely because they mention a business term.
_EXPLICIT_ACTION = re.compile(
    rf"(?:帮我(?!解释|介绍|讲|说明|了解|分析)|替我|为我|"
    rf"我要|我想(?!知道|了解|学习|问)|马上|立刻|直接)"
    rf".{{0,24}}(?:{_ACTION_PATTERN})"
)
_EXPLICIT_READ = re.compile(
    rf"(?:^|[，,。；;\s]|并|然后)(?:请|帮我|给我|麻烦你)?"
    rf"(?:查询|查一下|查查|查看|看看|查|核对|看一下|统计|分析)"
    rf".{{0,24}}(?:{_PRIVATE_PATTERN})"
)


def classify_no_tool_request(user_request: str) -> NoToolScope:
    """Conservative presentation scope, derived from user intent alone.

    Priority: past action status > explicit execution > personal/account read
    > purely educational explanation > other bank requests > conversation.
    Mixed educational + financial requests are never downgraded to education.
    No lexical classifier can certify an account fact or an operation result.
    """
    # The user can type "\\n\\n[" themselves. Never truncate input at a
    # supposed server reference delimiter: it is not an authenticity marker.
    normal = unicodedata.normalize("NFKC", user_request).casefold().strip()
    shorthand_transfer = bool(
        _TRANSFER_SHORTHAND.search(normal) or _DIRECTED_TRANSFER.search(normal)
    )
    financial_action = shorthand_transfer or any(cue in normal for cue in _ACTION)
    action_context = financial_action or any(cue in normal for cue in _ACTION_SYNONYMS)
    private_data = any(cue in normal for cue in _PRIVATE_READ)
    educational = any(cue in normal for cue in _EDUCATION)
    personal = any(cue in normal for cue in _PERSONAL_CUES)
    # Past operation questions often omit the verb ("钱到账了没有").
    status_check = any(cue in normal for cue in _STATUS_CUES)
    if action_context and status_check:
        return NoToolScope.ACTION_STATUS
    if financial_action and (shorthand_transfer or _EXPLICIT_ACTION.search(normal)):
        return NoToolScope.ACTION
    if private_data and (personal or _EXPLICIT_READ.search(normal)):
        return NoToolScope.PRIVATE_READ
    # Purely instructional cases can explain generic financial concepts,
    # but may never imply authority over personal financial records.
    if educational:
        return NoToolScope.EDUCATIONAL
    if financial_action:
        return NoToolScope.ACTION
    if private_data or action_context:
        return NoToolScope.PRIVATE_READ
    return NoToolScope.CONVERSATION


def _action_clarification(user_request: str) -> str:
    request = user_request
    if _TRANSFER_SHORTHAND.search(request) or any(
        term in request for term in ("转账", "汇款", "打款", "付款", "发款")
    ):
        return _NO_TRANSFER
    if any(term in request for term in ("挂失", "冻结", "解冻")):
        return _NO_CARD_ACTION
    if any(term in request for term in ("申购", "赎回", "买入", "卖出")):
        return _NO_WEALTH_ACTION
    if any(term in request for term in ("取消订阅", "订阅取消", "退订")):
        return _NO_SUBSCRIPTION_ACTION
    return _NO_UNSUPPORTED_ACTION


def tool_free_reply(
    raw_content: str, *, user_request: str = "", financial_context: bool = False
) -> str:
    """Only general conversation may display free model language.

    With user-scoped bank or action intent, data-bearing/authorizing answers
    must come from verified Tool events. The deterministic fallback is safe
    regardless of what the model claimed. Existing no-context callers retain
    the more restrictive default treatment of amounts.
    """
    scope = classify_no_tool_request(user_request)
    if financial_context and scope == NoToolScope.CONVERSATION:
        greeting = user_request.strip().casefold()
        if greeting not in {"hi", "hello", "你好", "您好", "嗨", "谢谢", "在吗"}:
            scope = NoToolScope.PRIVATE_READ
    if scope == NoToolScope.PRIVATE_READ:
        return _NO_VERIFIED_DATA
    if scope == NoToolScope.ACTION_STATUS:
        return _NO_ACTION_STATUS
    if scope == NoToolScope.ACTION:
        return _action_clarification(user_request)
    reply = raw_content.strip()
    if not reply:
        return _NO_TEXT
    if len(reply) > _MAX_REPLY_CHARS or _INTERNAL.search(reply):
        return _NO_TEXT
    checked_reply = _DENIED_CAPABILITY.sub("", reply)
    if _ACTION_COMPLETION.search(checked_reply):
        return _NO_UNSUPPORTED_ACTION
    if _UNVERIFIED_ORDER.search(checked_reply):
        return "暂时无法确认订购或付款状态，请通过实际下单渠道核对。"
    if _BANK_FACT.search(reply) or _UNVERIFIED_LOOKUP.search(reply):
        return _NO_VERIFIED_DATA
    if scope != NoToolScope.EDUCATIONAL:
        without_budget_question = _BUDGET_QUESTION.sub("", reply)
        if _AMOUNT_CLAIM.search(without_budget_question):
            return _NO_VERIFIED_DATA
        if without_budget_question != reply and any(
            cue in checked_reply for cue in _PRIVATE_READ + _ACTION + ("到账", "汇出", "款项")
        ):
            return _NO_VERIFIED_DATA
    return reply



# A no-Tool action turn may still ask for missing information. Such a question
# is not an assertion that an operation was created or executed. Keep the
# acceptance predicate deliberately narrower than general natural-language
# validation, and never use it to infer bank authorisation.
_UNVERIFIED_PROGRESS = re.compile(
    r"(?:已|已经|成功|完成|办好|到账|扣款|扣除|操作成功|系统显示|查到|"
    r"绕过|跳过|无需确认|不用确认|无需验证|免验证|无需核对|直接执行|"
    r"无需授权|不必授权|验证码|密码|完整卡号)"
)
_CLARIFICATION_CUES = (
    "账户", "银行卡", "联系人", "收款人", "金额", "附言",
    "哪一", "哪个", "哪张", "谁", "多少", "订阅", "理财产品",
    "持仓", "什么", "业务",
)


def safe_action_clarification(candidate: str) -> bool:
    """Accept a concise question about missing inputs, never a bank outcome.

    This is a presentation gate only. A successfully authorised write must
    still be proved by its separate business receipt.
    """
    if not isinstance(candidate, str):
        return False
    text = candidate.strip()
    if (len(text) < 6 or len(text) > 180 or chr(10) in text or chr(13) in text
            or not text.endswith(("？", "?"))
            or text.count("？") + text.count("?") != 1):
        return False
    if not text.startswith((
        "请问", "请告诉我", "请先", "你想", "您想", "你希望", "您希望",
        "需要", "想用", "哪", "哪个", "哪张", "想从",
    )):
        return False
    if not any(cue in text for cue in _CLARIFICATION_CUES):
        return False
    if any(c.isdigit() for c in text) or any(c in text for c in "<>{}￥¥"):
        return False
    if (_UNVERIFIED_PROGRESS.search(text) or _INTERNAL.search(text)
            or _ACTION_COMPLETION.search(text) or _UNVERIFIED_ORDER.search(text)
            or _UNVERIFIED_LOOKUP.search(text) or _BANK_FACT.search(text)
            or _AMOUNT_CLAIM.search(text)):
        return False
    return True


class ReplyRoute(str, Enum):
    """What a Runtime can do next without accepting an unverified model claim."""

    ACCEPT = "accept"
    QUERY_REQUIRED = "query_required"
    VERIFY_STATUS = "verify_status"
    CLARIFY_ACTION = "clarify_action"
    REJECT_CANDIDATE = "reject_candidate"


@dataclass(frozen=True)
class ReplyDecision:
    """Explain the existing no-tool gate without changing its verdict.

    safe_text reproduces the current reply exactly. Runtime may request a
    bounded Tool lookup or a tool-free question-only rephrase. Neither grants
    banking authority or changes a confirmed business result.
    """

    route: ReplyRoute
    scope: NoToolScope
    safe_text: str
    reason: str
    recovery_topic: str | None = None


def decide_no_tool_reply(
    candidate: str, *, user_request: str = "", financial_context: bool = False,
) -> ReplyDecision:
    """Expose deterministic reply safety as a structured Runtime decision.

    Follows the legacy fallback except safe action clarification questions. Never
    invokes an LLM or dispatches a banking operation.
    """
    scope = classify_no_tool_request(user_request)
    if financial_context and scope == NoToolScope.CONVERSATION:
        if user_request.strip().casefold() not in {
            "hi", "hello", "你好", "您好", "嗨", "谢谢", "在吗",
        }:
            scope = NoToolScope.PRIVATE_READ
    fallback = tool_free_reply(
        candidate, user_request=user_request, financial_context=financial_context,
    )
    if scope == NoToolScope.PRIVATE_READ:
        return ReplyDecision(
            ReplyRoute.QUERY_REQUIRED, scope, fallback, "no_verified_read",
            recovery_topic="account_query",
        )
    if scope == NoToolScope.ACTION_STATUS:
        return ReplyDecision(
            ReplyRoute.VERIFY_STATUS, scope, fallback, "no_verified_operation_status",
            recovery_topic="operation_status",
        )
    if scope == NoToolScope.ACTION:
        if safe_action_clarification(candidate):
            return ReplyDecision(
                ReplyRoute.ACCEPT, scope, candidate.strip(), "safe_action_clarification",
            )
        topics = {
            _NO_TRANSFER: "transfer",
            _NO_CARD_ACTION: "card_action",
            _NO_WEALTH_ACTION: "wealth_action",
            _NO_SUBSCRIPTION_ACTION: "subscription_action",
            _NO_UNSUPPORTED_ACTION: "other_action",
        }
        return ReplyDecision(
            ReplyRoute.CLARIFY_ACTION, scope, fallback, "action_not_prepared",
            recovery_topic=topics.get(_action_clarification(user_request), "other_action"),
        )
    if candidate.strip() and fallback == candidate.strip():
        return ReplyDecision(ReplyRoute.ACCEPT, scope, fallback, "candidate_accepted")
    return ReplyDecision(
        ReplyRoute.REJECT_CANDIDATE, scope, fallback, "unverified_or_invalid_candidate",
    )
