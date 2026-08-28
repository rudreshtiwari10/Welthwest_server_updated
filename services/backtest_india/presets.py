"""
Ready-made strategy graphs (spec §40 — the V1 library).

Each preset is a complete, valid strategy graph the UI can load with one click
and then edit. They exist so a user's first run is a working one, and so the
engine has known-shaped inputs for its own smoke tests.

Deliberately included: a preset that is expected to LOSE money after costs.
An engine that can only produce winners is not a research tool.
"""

from __future__ import annotations

import copy


PRESETS = {
    "ema_trend_pullback": {
        "name": "EMA trend + RSI pullback + bullish engulfing",
        "summary": ("The specification's own worked example: trade with the daily "
                    "trend, enter on an oversold pullback confirmed by a bullish "
                    "engulfing candle, risk 0.5% of equity behind a 2x ATR stop."),
        "expectation": "Selective. Expect few trades and long flat stretches.",
        "strategy": {
            "features": [
                {"id": "ema20", "type": "EMA", "period": 20},
                {"id": "ema50", "type": "EMA", "period": 50},
                {"id": "rsi14", "type": "RSI", "period": 14},
                {"id": "atr14", "type": "ATR", "period": 14},
            ],
            "candles": [{"id": "bull_eng", "type": "ENGULFING_BULL"}],
            "conditions": [
                {"id": "trend", "op": ">", "left": "ema20", "right": "ema50"},
                {"id": "pullback", "op": "<", "left": "rsi14", "right": 45},
                {"id": "pattern", "op": "IS_TRUE", "left": "bull_eng"},
                {"id": "trend_break", "op": "CROSS_BELOW", "left": "ema20", "right": "ema50"},
            ],
            "entry_long": {"op": "AND", "args": [
                "trend", {"op": "WITHIN_LAST", "bars": 5, "args": ["pullback"]}, "pattern"]},
            "exit_long": "trend_break",
        },
        "risk": {"stop_type": "atr", "stop_atr_multiple": 2.0,
                 "target_type": "r_multiple", "target_r": 2.5,
                 "trailing_enabled": True, "trailing_atr_multiple": 3.0,
                 "cooldown_bars": 3},
        "sizing": {"model": "risk_per_trade", "fraction": 0.005},
    },

    "donchian_breakout": {
        "name": "Donchian breakout with ADX filter",
        "summary": ("Classic trend following: buy a 20-bar breakout only when ADX "
                    "confirms a trending regime, exit on a 10-bar low. The Donchian "
                    "channel excludes the current bar, so the breakout test is not "
                    "self-referential."),
        "expectation": "Low hit rate, positive expectancy from a few large winners.",
        "strategy": {
            "features": [
                {"id": "dc", "type": "DONCHIAN", "period": 20, "exclude_current": 1},
                {"id": "dc_exit", "type": "DONCHIAN", "period": 10, "exclude_current": 1},
                {"id": "adx", "type": "ADX", "period": 14},
                {"id": "atr14", "type": "ATR", "period": 14},
            ],
            "conditions": [
                {"id": "breakout", "op": ">", "left": "close", "right": "dc.upper"},
                {"id": "trending", "op": ">", "left": "adx.adx", "right": 20},
                {"id": "breakdown", "op": "<", "left": "close", "right": "dc_exit.lower"},
            ],
            "entry_long": {"op": "AND", "args": ["breakout", "trending"]},
            "exit_long": "breakdown",
        },
        "risk": {"stop_type": "atr", "stop_atr_multiple": 2.5, "target_type": "none",
                 "trailing_enabled": True, "trailing_atr_multiple": 3.5},
        "sizing": {"model": "atr_risk", "fraction": 0.0075, "atr_multiple": 2.5},
    },

    "sma_crossover": {
        "name": "SMA 50/200 golden cross",
        "summary": ("The simplest trend rule there is. Included as the baseline any "
                    "more complex strategy has to beat before its complexity is "
                    "worth anything."),
        "expectation": "Few trades, long holds, tracks the underlying closely.",
        "strategy": {
            "features": [
                {"id": "fast", "type": "SMA", "period": 50},
                {"id": "slow", "type": "SMA", "period": 200},
            ],
            "conditions": [
                {"id": "golden", "op": "CROSS_ABOVE", "left": "fast", "right": "slow"},
                {"id": "death", "op": "CROSS_BELOW", "left": "fast", "right": "slow"},
            ],
            "entry_long": "golden", "exit_long": "death",
        },
        "risk": {"stop_type": "percent", "stop_percent": 12.0, "target_type": "none"},
        "sizing": {"model": "percent_equity", "weight": 0.95},
    },

    "bollinger_mean_reversion": {
        "name": "Bollinger mean reversion",
        "summary": ("Buy the lower band, exit at the middle band. Mean reversion is "
                    "where transaction costs do their worst damage — this preset "
                    "exists partly to show that."),
        "expectation": ("High hit rate, small wins. Often turns negative once real "
                        "Indian charges and slippage are applied."),
        "strategy": {
            "features": [
                {"id": "bb", "type": "BBANDS", "period": 20, "k": 2.0},
                {"id": "rsi", "type": "RSI", "period": 14},
                {"id": "atr14", "type": "ATR", "period": 14},
            ],
            "conditions": [
                {"id": "oversold", "op": "<", "left": "close", "right": "bb.lower"},
                {"id": "rsi_low", "op": "<", "left": "rsi", "right": 35},
                {"id": "revert", "op": ">", "left": "close", "right": "bb.middle"},
            ],
            "entry_long": {"op": "AND", "args": ["oversold", "rsi_low"]},
            "exit_long": "revert",
        },
        "risk": {"stop_type": "atr", "stop_atr_multiple": 2.0,
                 "target_type": "none", "time_stop_bars": 15},
        "sizing": {"model": "percent_equity", "weight": 0.25},
    },

    "macd_momentum": {
        "name": "MACD momentum with volume confirmation",
        "summary": ("MACD crossing its signal line above zero, confirmed by a volume "
                    "expansion. Exits on the opposite cross."),
        "expectation": "Moderate frequency; sensitive to the volume threshold.",
        "strategy": {
            "features": [
                {"id": "macd", "type": "MACD", "fast": 12, "slow": 26, "signal": 9},
                {"id": "volz", "type": "VOLZ", "period": 20},
                {"id": "atr14", "type": "ATR", "period": 14},
            ],
            "conditions": [
                {"id": "cross_up", "op": "CROSS_ABOVE", "left": "macd.macd", "right": "macd.signal"},
                {"id": "above_zero", "op": ">", "left": "macd.macd", "right": 0},
                {"id": "vol_ok", "op": ">", "left": "volz", "right": 0.5},
                {"id": "cross_dn", "op": "CROSS_BELOW", "left": "macd.macd", "right": "macd.signal"},
            ],
            "entry_long": {"op": "AND", "args": ["cross_up", "above_zero", "vol_ok"]},
            "exit_long": "cross_dn",
        },
        "risk": {"stop_type": "atr", "stop_atr_multiple": 2.0,
                 "target_type": "r_multiple", "target_r": 2.0,
                 "breakeven_enabled": True, "breakeven_trigger_r": 1.0},
        "sizing": {"model": "risk_per_trade", "fraction": 0.01},
    },

    "structure_breakout_retest": {
        "name": "Confirmed structure break",
        "summary": ("Enter on a break of the last CONFIRMED swing high, filtered by "
                    "structural trend. The swing is withheld until k bars confirm it, "
                    "so this cannot see a pivot before the market did."),
        "expectation": "Low frequency; the confirmation lag deliberately costs entry price.",
        "strategy": {
            "structure": {"pivot_k": 3, "bos_buffer_atr": 0.15, "min_touches": 2},
            "features": [
                {"id": "atr14", "type": "ATR", "period": 14},
                {"id": "ema50", "type": "EMA", "period": 50},
            ],
            "conditions": [
                {"id": "bos", "op": "IS_TRUE", "left": "structure.bos_up"},
                {"id": "uptrend", "op": ">", "left": "close", "right": "ema50"},
                {"id": "bos_down", "op": "IS_TRUE", "left": "structure.bos_down"},
            ],
            "entry_long": {"op": "AND", "args": ["bos", "uptrend"]},
            "exit_long": "bos_down",
        },
        "risk": {"stop_type": "structure", "stop_structure_buffer_atr": 0.5,
                 "target_type": "r_multiple", "target_r": 3.0,
                 "trailing_enabled": True, "trailing_atr_multiple": 3.0},
        "sizing": {"model": "risk_per_trade", "fraction": 0.005},
    },

    "double_bottom_reversal": {
        "name": "Double bottom neckline break",
        "summary": ("A chart-pattern strategy. The pattern is only actionable on its "
                    "confirmation bar — the neckline break — never at the second low, "
                    "which is only knowable in hindsight."),
        "expectation": "Very low frequency. Often too few trades to conclude anything.",
        "strategy": {
            "structure": {"pivot_k": 4},
            "features": [{"id": "atr14", "type": "ATR", "period": 14},
                         {"id": "ema200", "type": "EMA", "period": 200}],
            "chart_patterns": [
                {"id": "dbot", "type": "DOUBLE_BOTTOM", "tol": 0.04,
                 "min_sep": 8, "max_sep": 90, "confirm_horizon": 40},
            ],
            "conditions": [
                {"id": "confirmed", "op": "IS_TRUE", "left": "dbot"},
                {"id": "weak", "op": "<", "left": "close", "right": "ema200"},
            ],
            "entry_long": "confirmed",
            "exit_long": "weak",
        },
        "risk": {"stop_type": "atr", "stop_atr_multiple": 2.5,
                 "target_type": "r_multiple", "target_r": 2.5, "time_stop_bars": 40},
        "sizing": {"model": "percent_equity", "weight": 0.30},
    },
}


def list_presets() -> list:
    return [
        {"key": k, "name": v["name"], "summary": v["summary"],
         "expectation": v["expectation"],
         "features": len(v["strategy"].get("features", [])),
         "uses_candles": bool(v["strategy"].get("candles")),
         "uses_chart_patterns": bool(v["strategy"].get("chart_patterns")),
         "uses_structure": bool(v["strategy"].get("structure")),
         "sizing": v["sizing"], "risk": v["risk"]}
        for k, v in PRESETS.items()
    ]


def get_preset(key: str) -> dict:
    p = PRESETS.get(key)
    if not p:
        raise KeyError(f"Unknown preset '{key}'. Available: {', '.join(PRESETS)}")
    return copy.deepcopy(p)
