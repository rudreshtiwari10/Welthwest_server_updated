"""
Tool base class and ToolResult contract.

Every agent tool extends Tool and implements execute(). The registry
auto-generates the JSON schema that gets sent to the LLM for function-calling.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Any, Optional


@dataclass
class ToolResult:
    """Standardized result from a tool execution."""
    success: bool = True
    data: Any = None
    error: Optional[str] = None
    display_hint: str = "text"  # "text", "table", "chart", "card"

    def to_content(self) -> str:
        """Serialize to a string the LLM can reason over."""
        if not self.success:
            return f"Tool error: {self.error}"
        if isinstance(self.data, str):
            return self.data
        import json
        try:
            return json.dumps(self.data, default=str, indent=2)
        except Exception:
            return str(self.data)


class Tool(ABC):
    """
    Abstract agent tool. Subclasses define:
      - name: unique identifier (used in function-calling)
      - description: what the tool does (sent to LLM)
      - parameters: JSON-schema dict describing expected args
      - execute(**kwargs) -> ToolResult
    """

    name: str = ""
    description: str = ""
    parameters: dict = {}

    @abstractmethod
    def execute(self, **kwargs) -> ToolResult:
        """Run the tool with the given arguments. Must not raise — return ToolResult with error instead."""
        raise NotImplementedError

    def to_schema(self) -> dict:
        """Return the JSON schema declaration for LLM function-calling."""
        return {
            "name": self.name,
            "description": self.description,
            "parameters": self.parameters,
        }
