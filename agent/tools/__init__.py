"""
Tool registry — auto-discovers and registers all agent tools.

Usage:
    from agent.tools import get_tool_registry
    registry = get_tool_registry()
    schemas = registry.get_schemas()      # for LLM function-calling
    result = registry.execute("get_stock_quote", symbol="RELIANCE")
"""

from __future__ import annotations

import logging
from typing import Optional

from agent.tools.base import Tool, ToolResult

logger = logging.getLogger(__name__)


class ToolRegistry:
    """Registry of available agent tools."""

    def __init__(self):
        self._tools: dict[str, Tool] = {}

    def register(self, tool: Tool) -> None:
        if tool.name in self._tools:
            logger.warning("Tool %s already registered, overwriting", tool.name)
        self._tools[tool.name] = tool

    def get(self, name: str) -> Optional[Tool]:
        return self._tools.get(name)

    def execute(self, name: str, **kwargs) -> ToolResult:
        tool = self._tools.get(name)
        if tool is None:
            return ToolResult(success=False, error=f"Unknown tool: {name!r}")
        try:
            return tool.execute(**kwargs)
        except Exception as e:
            logger.error("Tool %s raised: %s", name, e)
            return ToolResult(success=False, error=f"Tool execution failed")

    def get_schemas(self) -> list[dict]:
        """Return JSON schemas for all registered tools (for LLM function-calling)."""
        return [t.to_schema() for t in self._tools.values()]

    def list_tools(self) -> list[str]:
        return sorted(self._tools.keys())

    def __len__(self) -> int:
        return len(self._tools)


# ---- Singleton registry with all tools loaded ------------------------------

_registry: Optional[ToolRegistry] = None


def get_tool_registry() -> ToolRegistry:
    """Return the global tool registry with all tools registered."""
    global _registry
    if _registry is not None:
        return _registry

    _registry = ToolRegistry()

    # Import and register all tools.
    from agent.tools.quote import GetStockQuoteTool
    from agent.tools.history import GetPriceHistoryTool
    from agent.tools.indicators import ComputeIndicatorTool
    from agent.tools.fundamentals import GetFundamentalsTool
    from agent.tools.resolve_symbol import ResolveSymbolTool
    from agent.tools.explain_concept import ExplainConceptTool
    from agent.tools.index import GetIndexQuoteTool
    from agent.tools.feature_promoter import SuggestFeatureTool

    for tool_cls in [
        GetStockQuoteTool,
        GetPriceHistoryTool,
        ComputeIndicatorTool,
        GetFundamentalsTool,
        ResolveSymbolTool,
        ExplainConceptTool,
        GetIndexQuoteTool,
        SuggestFeatureTool,
    ]:
        _registry.register(tool_cls())

    logger.info("Tool registry loaded: %d tools", len(_registry))
    return _registry


__all__ = ["Tool", "ToolResult", "ToolRegistry", "get_tool_registry"]
