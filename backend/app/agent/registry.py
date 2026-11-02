from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Awaitable, Callable


class RiskLevel(str, Enum):
    GREEN = "green"
    YELLOW = "yellow"
    RED = "red"


class ToolExecutionMode(str, Enum):
    """Distinguishes ordinary session-based Tools from bank action preparation."""
    STANDARD = "standard"
    PREPARE = "prepare"


@dataclass(frozen=True)
class ToolSpec:
    name: str
    description: str
    parameters: dict[str, Any]
    risk: RiskLevel
    handler: Callable[..., Awaitable[Any]] | None = None
    execution: ToolExecutionMode = ToolExecutionMode.STANDARD

    def to_openai_schema(self) -> dict[str, Any]:
        return {
            "type": "function",
            "function": {
                "name": self.name,
                "description": self.description,
                "parameters": self.parameters,
            },
        }


class ToolRegistry:
    def __init__(self) -> None:
        self._tools: dict[str, ToolSpec] = {}

    def register(self, spec: ToolSpec) -> None:
        self._tools[spec.name] = spec

    def get(self, name: str) -> ToolSpec | None:
        return self._tools.get(name)

    def definitions(self) -> list[dict[str, Any]]:
        return [spec.to_openai_schema() for spec in self._tools.values()]


registry = ToolRegistry()
