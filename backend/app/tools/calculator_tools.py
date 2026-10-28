import ast
import math
import time
from typing import Any

from pydantic import BaseModel, ConfigDict, Field, ValidationError

MAX_EXPRESSION_LENGTH = 200
MAX_NODES = 100
MAX_SECONDS = 0.05
MAX_INT_BITS = 512
MAX_FLOAT_ABS = 1e15
MAX_EXPONENT = 64

_BIN_OPS = (ast.Add, ast.Sub, ast.Mult, ast.Div, ast.FloorDiv, ast.Mod, ast.Pow)
_UNARY_OPS = (ast.UAdd, ast.USub)


class CalculationError(ValueError):
    pass


class CalculateArguments(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)
    expression: str = Field(min_length=1, max_length=MAX_EXPRESSION_LENGTH)


def _check_number(value: Any) -> int | float:
    if type(value) is int:
        if value.bit_length() > MAX_INT_BITS:
            raise CalculationError("结果超出范围")
        return value
    if type(value) is float:
        if not math.isfinite(value) or abs(value) > MAX_FLOAT_ABS:
            raise CalculationError("结果超出范围")
        return value
    raise CalculationError("仅支持数字和基本运算")


def _eval(node: ast.AST, deadline: float) -> int | float:
    if time.monotonic() > deadline:
        raise CalculationError("计算超时")
    if isinstance(node, ast.Expression):
        return _eval(node.body, deadline)
    if isinstance(node, ast.Constant):
        return _check_number(node.value)
    if isinstance(node, ast.UnaryOp) and isinstance(node.op, _UNARY_OPS):
        value = _eval(node.operand, deadline)
        return _check_number(value if isinstance(node.op, ast.UAdd) else -value)
    if isinstance(node, ast.BinOp) and isinstance(node.op, _BIN_OPS):
        left = _eval(node.left, deadline)
        right = _eval(node.right, deadline)
        if isinstance(node.op, (ast.Div, ast.FloorDiv, ast.Mod)) and right == 0:
            raise CalculationError("除数不能为零")
        if isinstance(node.op, ast.Pow) and abs(right) > MAX_EXPONENT:
            raise CalculationError("指数过大")
        try:
            if isinstance(node.op, ast.Add):
                value = left + right
            elif isinstance(node.op, ast.Sub):
                value = left - right
            elif isinstance(node.op, ast.Mult):
                value = left * right
            elif isinstance(node.op, ast.Div):
                value = left / right
            elif isinstance(node.op, ast.FloorDiv):
                value = left // right
            elif isinstance(node.op, ast.Mod):
                value = left % right
            else:
                value = left ** right
        except (ArithmeticError, ValueError):
            raise CalculationError("计算失败") from None
        return _check_number(value)
    raise CalculationError("仅支持数字和基本运算")


def evaluate_expression(expression: str, max_seconds: float = MAX_SECONDS) -> int | float:
    if not isinstance(expression, str) or not expression or len(expression) > MAX_EXPRESSION_LENGTH:
        raise CalculationError("表达式无效或过长")
    try:
        tree = ast.parse(expression, mode="eval")
    except (SyntaxError, ValueError, MemoryError, RecursionError):
        raise CalculationError("表达式无效") from None
    if sum(1 for _ in ast.walk(tree)) > MAX_NODES:
        raise CalculationError("表达式过于复杂")
    return _eval(tree, time.monotonic() + max_seconds)


async def calculate(*, user_id: int, session: Any = None, **arguments: Any) -> dict:
    try:
        args = CalculateArguments.model_validate(arguments)
        value = evaluate_expression(args.expression)
    except ValidationError:
        return {"ok": False, "data": None, "error": "计算参数无效"}
    except CalculationError as exc:
        return {"ok": False, "data": None, "error": str(exc)}
    return {"ok": True, "data": {"result": value, "kind": "int" if type(value) is int else "float"},
            "error": None}
