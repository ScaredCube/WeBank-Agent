"""Conservative extraction of an explicit CNY amount from the CURRENT user request.

This is an additional server-side constraint for typed account+contact references,
not an authorization to execute transactions. Ambiguous wording fails closed.
"""
from decimal import Decimal
import re

_VERBS = ("转账", "汇款", "打款")
# Reject an explicit negation in the same clause as the transaction verb.
# Intent ambiguity fails closed: the user can clarify rather than create a
# financial action on the basis of a loose keyword match.
_NEGATED_REQUEST = re.compile(r"(?:不|无|别|取消|停止|拒绝|禁止)[^，。；;]{0,24}(?:转账|汇款|打款)")


def is_transfer_request(text: str) -> bool:
    return any(verb in text for verb in _VERBS) and _NEGATED_REQUEST.search(text) is None


_AMOUNTS = re.compile(
    r"(?<![\d.])([0-9]+(?:\.[0-9]{1,2})?)\s*(元|块|角|分)(?![\d.])"
)
_FEN = {"元": 100, "块": 100, "角": 10, "分": 1}


def requested_transfer_amount_fen(text: str) -> int | None:
    if not is_transfer_request(text):
        return None
    amounts = list(_AMOUNTS.finditer(text))
    if len(amounts) != 1:
        return None
    # Reject signed amounts, including separated minus signs like '- 1元'.
    if text[:amounts[0].start()].rstrip().endswith(('-', '−', '－')):
        return None
    value = Decimal(amounts[0].group(1)) * _FEN[amounts[0].group(2)]
    if value != value.to_integral_value():
        return None
    fen = int(value)
    return fen if 0 < fen <= 100_000_000_000 else None


_TYPED_INTENT_PREFIX = re.compile(
    r"^\s*(?:转账|收款|申购|赎回|转换)金额\s*[：:]\s*(.*)$"
)


def requested_intent_amount_fen(text: str) -> int | None:
    """Parse the CNY-only amount following the verified drag-intent prefix.

    The user may append a note after the amount (for example
    "转账金额：500块，还钱"). Accept a single explicit unit-bearing amount in
    that remainder, but keep a unit-less "500" ambiguous and fail closed.
    """
    match = _TYPED_INTENT_PREFIX.match(text)
    if match is None:
        return requested_amount_fen(text)
    return requested_amount_fen(match.group(1))


def requested_amount_fen(text: str) -> int | None:
    """One explicit CNY amount in the current user text; ambiguous input fails closed."""
    if not isinstance(text, str):
        return None
    amounts = list(_AMOUNTS.finditer(text))
    if len(amounts) != 1:
        return None
    if text[:amounts[0].start()].rstrip().endswith(("-", "负")):
        return None
    value = Decimal(amounts[0].group(1)) * _FEN[amounts[0].group(2)]
    if value != value.to_integral_value():
        return None
    fen = int(value)
    return fen if 0 < fen <= 100_000_000_000 else None
