"""
backtest_india — WelthWest Realistic Hybrid Backtesting Engine (v2).

A completely independent, event-driven research and execution simulator built
to the specification in backtest.md. It shared no code with the legacy
`services/backtesting_engine.py` (removed — the old /api/backtesting/*
endpoints and their engine were retired in favor of this one) or with
`services/simple_backtest_service.py`, which is unrelated and still used by
the Finance AI chat assistant.

Canonical pipeline (spec §2):

    Universe -> Point-in-Time Data -> Corporate Actions -> Feature Layer
      -> Pattern Layer -> Strategy Graph -> Signal -> Risk/Sizing -> Order
      -> Latency Queue -> Execution/Fills -> Costs & Taxes -> Portfolio Ledger
      -> Equity Curve -> Diagnostics -> Validation -> Robustness -> Report

Public entry points:

    from services.backtest_india import run_backtest, ENGINE_VERSION
    result = run_backtest(config_dict)

Everything else (indicator catalogue, pattern catalogue, cost schedules,
presets) is exposed through the catalogue helpers so the API layer never has
to reach into internals.
"""

ENGINE_VERSION = "2.0.0"

from services.backtest_india.contracts import (
    RunConfig,
    Bar,
    Order,
    Fill,
    Trade,
    Position,
    OrderSide,
    OrderType,
    OrderStatus,
    ExitReason,
    RealismLevel,
    IntrabarPolicy,
)
from services.backtest_india.engine import run_backtest, run_single_pass
from services.backtest_india.catalogue import (
    indicator_catalogue,
    candle_catalogue,
    structure_catalogue,
    chart_pattern_catalogue,
    sizing_catalogue,
    execution_catalogue,
    full_catalogue,
)
from services.backtest_india.costs import list_cost_schedules, get_cost_schedule
from services.backtest_india.presets import list_presets, get_preset

__all__ = [
    "ENGINE_VERSION",
    "run_backtest",
    "run_single_pass",
    "RunConfig",
    "Bar",
    "Order",
    "Fill",
    "Trade",
    "Position",
    "OrderSide",
    "OrderType",
    "OrderStatus",
    "ExitReason",
    "RealismLevel",
    "IntrabarPolicy",
    "indicator_catalogue",
    "candle_catalogue",
    "structure_catalogue",
    "chart_pattern_catalogue",
    "sizing_catalogue",
    "execution_catalogue",
    "full_catalogue",
    "list_cost_schedules",
    "get_cost_schedule",
    "list_presets",
    "get_preset",
]
