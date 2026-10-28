"""Conservative masking for user-controlled and legacy text."""
import re
import unicodedata
from datetime import datetime

from sqlmodel import Session
from app.services.vault import create_temporary

_CANDIDATE = re.compile(r"(?<!\d)\d(?:[\s\-()./·,，:：_]*\d){9,}(?!\d)")
_CHINESE_DIGITS = "零〇一二三四五六七八九幺"
_CHINESE_CANDIDATE = re.compile(r"[零〇一二三四五六七八九幺](?:[\s\-()./·,，:：_]*[零〇一二三四五六七八九幺]){9,}")


def _normalise(text: str) -> str:
    return "".join(str(unicodedata.digit(ch)) if ch.isdecimal() else ch
                   for ch in text if unicodedata.category(ch) != "Cf")


def _digits(value: str) -> str:
    return "".join(str(unicodedata.digit(ch)) for ch in value if ch.isdecimal())


def _luhn(digits: str) -> bool:
    total = 0
    for i, ch in enumerate(reversed(digits)):
        n = int(ch) * (2 if i % 2 else 1)
        total += n - 9 if n > 9 else n
    return total % 10 == 0


def mask_text(text: str) -> str:
    masked = _CHINESE_CANDIDATE.sub("[敏感号码已隐藏]", _normalise(text))
    masked = _CANDIDATE.sub("[敏感号码已隐藏]", masked)
    if sum(ch.isdecimal() or ch in _CHINESE_DIGITS for ch in masked) >= 10:
        masked = re.sub(r"[\d零〇一二三四五六七八九幺]", "*", masked)
    return masked


def mask_value(value):
    if isinstance(value, str):
        return mask_text(value)
    if isinstance(value, list):
        return [mask_value(item) for item in value]
    if isinstance(value, dict):
        result = {}
        for key, item in value.items():
            safe_key = mask_text(key) if isinstance(key, str) else key
            if (key in {"created_at", "updated_at", "expires_at", "confirmed_at", "occurred_at", "completed_at"}
                    and isinstance(item, str) and re.fullmatch(
                        r"\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}(?:\.\d{1,6})?(?:Z|[+-]\d{2}:\d{2})?", item)):
                try:
                    datetime.fromisoformat(item.replace("Z", "+00:00"))
                except ValueError:
                    pass
                else:
                    result[safe_key] = item
                    continue
            result[safe_key] = mask_value(item)
        return result
    return value


def redact_input(session: Session, user_id: int, text: str, scope: str) -> tuple[str, str, bool]:
    normalized, chinese_count = _CHINESE_CANDIDATE.subn("[敏感号码已隐藏]", _normalise(text))
    parts_display: list[str] = []
    parts_model: list[str] = []
    cursor = 0
    uncertain = bool(chinese_count)
    for match in _CANDIDATE.finditer(normalized):
        parts_display.append(normalized[cursor:match.start()])
        parts_model.append(normalized[cursor:match.start()])
        number = _digits(match.group())
        parts_display.append("[敏感号码已隐藏]")
        if re.fullmatch(r"1[3-9][0-9]{9}", number):
            parts_model.append(create_temporary(session, user_id, "phone_input", number, scope))
        elif 16 <= len(number) <= 19 and _luhn(number):
            parts_model.append(create_temporary(session, user_id, "card_input", number, scope))
        else:
            parts_model.append("[敏感号码已隐藏]")
            uncertain = True
        cursor = match.end()
    parts_display.append(normalized[cursor:])
    parts_model.append(normalized[cursor:])
    display = "".join(parts_display)
    model = "".join(parts_model)
    if sum(ch.isdecimal() or ch in _CHINESE_DIGITS for ch in display) >= 10:
        uncertain = True
        display = re.sub(r"[\d零〇一二三四五六七八九幺]", "*", display)
        model = re.sub(r"[\d零〇一二三四五六七八九幺]", "*", model)
    return display, model, uncertain
