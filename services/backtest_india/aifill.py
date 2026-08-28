"""
AI-assisted pipeline fill for Backtest India.

A user who does not write strategy graphs answers a short interview; an LLM
turns those answers into a complete, valid configuration for the same engine
the manual builder feeds. Nothing here is required — the manual path is
untouched and this module is never imported by the engine itself.

Two things make the output trustworthy rather than plausible-looking:

  1. The prompt is built from the LIVE catalogue, so the model can only name
     indicators, patterns and operators that actually exist.
  2. Every candidate graph is statically validated AND dry-run against real
     bars to count entry signals. A graph that would fire zero trades is sent
     back to the model with that fact and a instruction to loosen it.

Step 2 is the point. "No trades were generated" is the single most common way
a hand-built strategy fails here, and it is exactly the failure an LLM is most
prone to reproduce — it will happily AND together four rare conditions.
"""

from __future__ import annotations

import json
import logging
import os
import re
from datetime import date, timedelta
from typing import Any, Dict, List, Optional, Tuple

import requests

logger = logging.getLogger(__name__)

# How many entry signals we consider "enough to read" over the window.
MIN_SIGNALS = 8
# The dry run only ever touches one instrument, so it stays cheap.
VERIFY_TIMEOUT_BARS = 20_000
LLM_TIMEOUT = 60


# ── Interview ───────────────────────────────────────────────────────────────
#
# Deliberately fixed rather than model-generated: it is instant, costs nothing,
# and asks the same thing every time so the prompt below can rely on the shape.

INTERVIEW: List[Dict[str, Any]] = [
    {
        "key": "idea",
        "type": "text",
        "question": "Describe the strategy you have in mind, in your own words.",
        "hint": ("Plain English is fine — \"buy strong stocks when they dip\" or "
                 "\"trade breakouts out of quiet periods\". Leave it blank and we "
                 "will build something sensible from your other answers."),
        "placeholder": "e.g. I want to buy when a stock pulls back but is still in an uptrend",
        "required": False,
    },
    {
        "key": "goal",
        "type": "choice",
        "question": "What are you trying to find out?",
        "options": [
            {"value": "learn", "label": "I am learning how backtesting works"},
            {"value": "steady", "label": "Whether a steady, low-drama strategy works"},
            {"value": "growth", "label": "Whether an aggressive strategy beats the index"},
            {"value": "idea", "label": "Whether the specific idea above holds up"},
        ],
        "required": True,
    },
    {
        "key": "holding",
        "type": "choice",
        "question": "How long should a typical trade last?",
        "options": [
            {"value": "days", "label": "A few days"},
            {"value": "weeks", "label": "A few weeks"},
            {"value": "months", "label": "Months"},
            {"value": "unsure", "label": "I am not sure — you decide"},
        ],
        "required": True,
    },
    {
        "key": "risk",
        "type": "choice",
        "question": "How much of a losing streak could you actually sit through?",
        "options": [
            {"value": "low", "label": "Very little — protect the capital first"},
            {"value": "medium", "label": "A normal amount of ups and downs"},
            {"value": "high", "label": "A lot, if the upside is bigger"},
        ],
        "required": True,
    },
    {
        "key": "symbols",
        "type": "symbols",
        "question": "Which instruments should we test?",
        "hint": "Leave empty and we will pick a few liquid, well-known names.",
        "required": False,
    },
    {
        "key": "capital",
        "type": "number",
        "question": "How much capital should the simulation start with?",
        "default": 1_000_000,
        "required": False,
    },
    {
        "key": "experience",
        "type": "choice",
        "question": "How familiar are you with technical indicators?",
        "options": [
            {"value": "none", "label": "Not at all — keep it simple"},
            {"value": "some", "label": "I know the common ones"},
            {"value": "lots", "label": "Very — feel free to get specific"},
        ],
        "required": True,
    },
]


def interview() -> List[Dict[str, Any]]:
    return INTERVIEW


# ── Prompt ──────────────────────────────────────────────────────────────────

SYSTEM_PROMPT = """\
You configure backtests for an Indian-equity research simulator. You translate \
a non-expert's description into a complete, valid engine configuration.

You MUST reply with a single JSON object and nothing else. No prose, no \
markdown fences, no commentary outside the JSON.

THE MOST IMPORTANT RULE
The configuration must actually generate trades. A strategy that fires zero or \
a handful of entries over the whole window is useless and is treated as a \
failure. Concretely:
  - Use at most 2-3 conditions in an entry rule.
  - Never AND together several individually-rare events (a specific candlestick \
    pattern AND an RSI extreme AND a crossover on the same bar will almost \
    never fire).
  - When you want two things to be true "around the same time" rather than on \
    the identical bar, wrap the rarer one in WITHIN_LAST with bars 3-10.
  - Prefer state conditions (price above a moving average, RSI below 45) over \
    instant conditions (an exact crossover) as the primary filter.
  - Aim for roughly 20-100 entry signals over a 5-year daily window.

OUTPUT SCHEMA
{
  "strategy_name": "short human name",
  "strategy": {
    "features":   [{"id":"ema20","type":"EMA","period":20,"source":"close"}],
    "candles":    [{"id":"bull_eng","type":"ENGULFING_BULL"}],
    "conditions": [{"id":"trend","op":">","left":"ema20","right":"ema50"}],
    "entry_long": <expression>,
    "exit_long":  <expression>
  },
  "settings": {
    "symbols": ["RELIANCE"],
    "timeframe": "1d",
    "years_back": 5,
    "initial_capital": 1000000,
    "risk": {...}, "sizing": {...},
    "max_concurrent_positions": 5, "max_position_weight": 0.25,
    "allow_short": false,
    "walk_forward": true, "run_stress": false,
    "run_parameters": false, "run_controls": true
  },
  "explanation": "2-3 sentences a beginner understands. No jargon.",
  "stage_notes": {
    "input": "one line", "strategy": "one line",
    "risk": "one line", "sizing": "one line"
  }
}

EXPRESSIONS
An expression is either a condition id ("trend"), or an object:
  {"op":"AND","args":[<expr>,<expr>]}          logic: AND OR NOT XOR
  {"op":"WITHIN_LAST","bars":5,"args":[<expr>]} temporal
Every id referenced by a condition or expression must be defined above it.
Condition operands are either a defined id, a raw price field \
(close/open/high/low/volume/hl2/typical) or a plain number.

RISK OBJECT
{"stop_type":"atr","stop_atr_multiple":2.0,
 "target_type":"r_multiple","target_r":2.5,
 "trailing_enabled":true,"trailing_atr_multiple":3.0,
 "breakeven_enabled":false,"breakeven_trigger_r":1.0,
 "time_stop_bars":0,"cooldown_bars":3,
 "portfolio_max_drawdown":0,"max_consecutive_losses":0}

SIZING OBJECT
{"model":"risk_per_trade","fraction":0.005}

Every strategy needs an exit_long as well as an entry_long. Give the trade a \
way out that is not only the stop: a trend break or a crossover back the other \
way works well.
"""


def _compact_catalogue() -> str:
    """The vocabulary the model is allowed to use, as compactly as possible."""
    from services.backtest_india.catalogue import full_catalogue

    cat = full_catalogue()

    def keys(items, k="key"):
        return ", ".join(str(i.get(k)) for i in items or [])

    indicators = []
    for spec in cat.get("indicators", []):
        params = ",".join(spec.get("params", {}).keys())
        outputs = spec.get("outputs") or []
        out = f" -> {'.'.join([spec['key'].lower()]) if len(outputs) == 1 else '/'.join(outputs)}"
        indicators.append(f"{spec['key']}({params}){out if len(outputs) > 1 else ''}")

    ops = cat.get("operators", {})
    risk = cat.get("risk_rules", {})

    return "\n".join([
        "INDICATORS (type -> params): " + "; ".join(indicators),
        "CANDLE PATTERNS: " + keys(cat.get("candles")),
        "CHART PATTERNS: " + keys(cat.get("chart_patterns")),
        "STRUCTURE OUTPUTS (usable directly as ids): " + keys(cat.get("structure_outputs")),
        "COMPARATORS: " + ", ".join(ops.get("comparators", [])),
        "LOGIC: " + ", ".join(ops.get("logic", [])),
        "TEMPORAL: " + ", ".join(ops.get("temporal", [])),
        "SIZING MODELS: " + keys(cat.get("sizing_models")),
        "STOP TYPES: " + keys(risk.get("stop_types")),
        "TARGET TYPES: " + keys(risk.get("target_types")),
        "TIMEFRAMES: " + keys(cat.get("timeframes")),
        "UNIVERSE: " + ", ".join(u["symbol"] for u in cat.get("universe", [])[:40]),
    ])


def _user_prompt(answers: Dict[str, Any]) -> str:
    lines = ["The user answered an interview. Build their configuration.", ""]
    labels = {q["key"]: q["question"] for q in INTERVIEW}
    for key, label in labels.items():
        val = answers.get(key)
        if val in (None, "", []):
            continue
        if isinstance(val, list):
            val = ", ".join(str(v) for v in val)
        lines.append(f"{label}\n  -> {val}")
    lines += ["", "AVAILABLE VOCABULARY (use nothing outside this):", _compact_catalogue()]
    return "\n".join(lines)


# ── LLM transport ───────────────────────────────────────────────────────────
#
# Same providers and preference order the rest of the app already uses, so this
# feature needs no new keys. Each is tried until one returns usable JSON.

def _scrub(text: str) -> str:
    """
    Strip anything that looks like an API key out of a message.

    Provider errors routinely quote the request URL or headers, and one of
    those (Gemini's) used to carry the key in a query string. This runs over
    every message that can reach a client or a log line.
    """
    out = str(text)
    for env in ("OPENROUTER_API_KEY", "GEMINI_API_KEY", "OPENAI_API_KEY",
                "CLAUDE_API_KEY", "ANTHROPIC_API_KEY"):
        val = (os.environ.get(env) or "").strip()
        if len(val) > 8:
            out = out.replace(val, "***")
    out = re.sub(r"(key=)[A-Za-z0-9_\-]{8,}", r"\1***", out)
    out = re.sub(r"\b(sk-[A-Za-z0-9_\-]{8,})", "***", out)
    return out


def _openrouter(messages: List[Dict], key: str) -> str:
    model = os.environ.get("BACKTEST_AI_MODEL", "anthropic/claude-sonnet-5")
    r = requests.post(
        "https://openrouter.ai/api/v1/chat/completions",
        headers={"Authorization": f"Bearer {key}", "Content-Type": "application/json"},
        json={"model": model, "messages": messages,
              "max_tokens": 2500, "temperature": 0.4,
              "response_format": {"type": "json_object"}},
        timeout=LLM_TIMEOUT,
    )
    r.raise_for_status()
    return r.json()["choices"][0]["message"]["content"]


def _openai(messages: List[Dict], key: str) -> str:
    r = requests.post(
        "https://api.openai.com/v1/chat/completions",
        headers={"Authorization": f"Bearer {key}", "Content-Type": "application/json"},
        json={"model": os.environ.get("BACKTEST_AI_OPENAI_MODEL", "gpt-4o-mini"),
              "messages": messages, "max_tokens": 2500, "temperature": 0.4,
              "response_format": {"type": "json_object"}},
        timeout=LLM_TIMEOUT,
    )
    r.raise_for_status()
    return r.json()["choices"][0]["message"]["content"]


def _gemini(messages: List[Dict], key: str) -> str:
    # Key goes in a header, never the query string: request URLs end up inside
    # exception messages, which are logged and shown to the user.
    model = os.environ.get("BACKTEST_AI_GEMINI_MODEL", "gemini-2.0-flash")
    prompt = "\n\n".join(m["content"] for m in messages)
    r = requests.post(
        f"https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent",
        headers={"x-goog-api-key": key, "Content-Type": "application/json"},
        json={"contents": [{"parts": [{"text": prompt}]}],
              "generationConfig": {"temperature": 0.4, "maxOutputTokens": 2500,
                                   "response_mime_type": "application/json"}},
        timeout=LLM_TIMEOUT,
    )
    r.raise_for_status()
    return r.json()["candidates"][0]["content"]["parts"][0]["text"]


def _claude(messages: List[Dict], key: str) -> str:
    system = next((m["content"] for m in messages if m["role"] == "system"), "")
    rest = [m for m in messages if m["role"] != "system"]
    r = requests.post(
        "https://api.anthropic.com/v1/messages",
        headers={"x-api-key": key, "anthropic-version": "2023-06-01",
                 "Content-Type": "application/json"},
        json={"model": os.environ.get("BACKTEST_AI_CLAUDE_MODEL", "claude-sonnet-4-5"),
              "system": system, "messages": rest, "max_tokens": 2500,
              "temperature": 0.4},
        timeout=LLM_TIMEOUT,
    )
    r.raise_for_status()
    return r.json()["content"][0]["text"]


def _providers() -> List[Tuple[str, Any, str]]:
    out = []
    for name, env, fn in (
        ("openrouter", "OPENROUTER_API_KEY", _openrouter),
        ("gemini", "GEMINI_API_KEY", _gemini),
        ("openai", "OPENAI_API_KEY", _openai),
        ("claude", "CLAUDE_API_KEY", _claude),
    ):
        key = (os.environ.get(env) or "").strip()
        if key:
            out.append((name, fn, key))
    return out


def ai_available() -> bool:
    return bool(_providers())


def _call_llm(messages: List[Dict]) -> Tuple[str, str]:
    """Returns (raw_text, provider_name). Raises if every provider fails."""
    errors = []
    for name, fn, key in _providers():
        try:
            return fn(messages, key), name
        except Exception as exc:            # noqa: BLE001 - try the next provider
            safe = _scrub(exc)
            logger.warning("backtest-india ai-fill: %s failed: %s", name, safe)
            errors.append(f"{name}: {safe}")
    raise RuntimeError(_scrub("No AI provider could be reached. " + " | ".join(errors)))


def _parse_json(raw: str) -> Dict[str, Any]:
    """Models still fence their JSON sometimes, even when told not to."""
    text = raw.strip()
    if text.startswith("```"):
        text = re.sub(r"^```[a-zA-Z]*\s*|\s*```$", "", text).strip()
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        start, end = text.find("{"), text.rfind("}")
        if start >= 0 and end > start:
            return json.loads(text[start:end + 1])
        raise


# ── Verification ────────────────────────────────────────────────────────────

def count_signals(strategy: Dict[str, Any], symbol: str, start: str, end: str,
                  timeframe: str) -> Optional[int]:
    """
    Dry-run the graph against one instrument and count entry signals.

    Returns None when the check could not run (no data, fetch failure) — an
    inconclusive check must never be reported as "zero trades".
    """
    try:
        from services.backtest_india.datafeed import load_instrument
        from services.backtest_india.engine import prepare_instrument, PERIODS_PER_YEAR

        series = load_instrument(symbol, start, end, timeframe)
        if series is None or len(series.analysis) == 0:
            return None
        plan = prepare_instrument(series, strategy, PERIODS_PER_YEAR.get(timeframe, 252))
        return int(plan.entry_long.sum()) + int(plan.entry_short.sum())
    except Exception as exc:                # noqa: BLE001 - verification is best-effort
        logger.info("backtest-india ai-fill: signal check skipped (%s)", exc)
        return None


# ── Assembly ────────────────────────────────────────────────────────────────

def _window(years_back: Any) -> Tuple[str, str]:
    try:
        n = max(1, min(15, int(years_back)))
    except (TypeError, ValueError):
        n = 5
    end = date.today()
    return (end - timedelta(days=int(n * 365.25))).isoformat(), end.isoformat()


def _clean_settings(raw: Dict[str, Any], answers: Dict[str, Any]) -> Dict[str, Any]:
    """Keep only keys the page understands, coerced to the right types."""
    s: Dict[str, Any] = {}

    symbols = raw.get("symbols") or answers.get("symbols") or []
    if isinstance(symbols, str):
        symbols = [x.strip() for x in symbols.split(",") if x.strip()]
    symbols = [str(x).strip().upper() for x in symbols][:8]
    if symbols:
        s["symbols"] = symbols

    start, end = _window(raw.get("years_back", 5))
    s["start"], s["end"] = start, end

    if raw.get("timeframe"):
        s["timeframe"] = str(raw["timeframe"])
    if raw.get("benchmark"):
        s["benchmark"] = str(raw["benchmark"])

    for key, cast in (("initial_capital", float),
                      ("max_concurrent_positions", int),
                      ("max_position_weight", float)):
        if raw.get(key) is not None:
            try:
                s[key] = cast(raw[key])
            except (TypeError, ValueError):
                pass

    for key in ("allow_short", "walk_forward", "run_stress",
                "run_parameters", "run_controls"):
        if isinstance(raw.get(key), bool):
            s[key] = raw[key]

    if isinstance(raw.get("risk"), dict):
        s["risk"] = raw["risk"]
    if isinstance(raw.get("sizing"), dict):
        s["sizing"] = raw["sizing"]

    # The interview's own capital answer wins — the user typed it explicitly.
    if answers.get("capital"):
        try:
            s["initial_capital"] = float(answers["capital"])
        except (TypeError, ValueError):
            pass

    return s


def generate(answers: Dict[str, Any], verify: bool = True) -> Dict[str, Any]:
    """
    Run the interview answers through the model and return a config the page
    can apply directly. Raises RuntimeError when no provider is reachable.
    """
    from services.backtest_india.graph import validate_graph

    messages = [
        {"role": "system", "content": SYSTEM_PROMPT},
        {"role": "user", "content": _user_prompt(answers)},
    ]

    attempts: List[Dict[str, Any]] = []
    payload: Dict[str, Any] = {}
    provider = ""
    signals: Optional[int] = None
    warnings: List[str] = []

    # Two attempts: the first as asked, the second with whatever went wrong fed
    # back in. Most "no trades" graphs are fixed by the second pass.
    for attempt in range(2):
        raw, provider = _call_llm(messages)
        try:
            payload = _parse_json(raw)
        except Exception:                   # noqa: BLE001
            attempts.append({"attempt": attempt + 1, "error": "unparseable JSON"})
            messages.append({"role": "assistant", "content": raw[:2000]})
            messages.append({"role": "user", "content":
                             "That was not valid JSON. Reply with the JSON object only."})
            continue

        strategy = payload.get("strategy") or {}
        problems = validate_graph(strategy)
        if problems:
            attempts.append({"attempt": attempt + 1, "problems": problems})
            messages.append({"role": "assistant", "content": json.dumps(payload)[:2000]})
            messages.append({"role": "user", "content":
                             "The engine rejected that graph:\n- "
                             + "\n- ".join(problems)
                             + "\nFix these and reply with the corrected JSON only."})
            continue

        if not verify:
            break

        settings = _clean_settings(payload.get("settings") or {}, answers)
        probe = (settings.get("symbols") or ["RELIANCE"])[0]
        signals = count_signals(strategy, probe, settings["start"], settings["end"],
                                settings.get("timeframe", "1d"))

        if signals is None:
            warnings.append(
                "The signal check could not run (market data was unavailable), so the "
                "trade count is unverified.")
            break

        if signals >= MIN_SIGNALS:
            break

        attempts.append({"attempt": attempt + 1, "signals": signals})
        if attempt == 0:
            messages.append({"role": "assistant", "content": json.dumps(payload)[:2000]})
            messages.append({"role": "user", "content": (
                f"That configuration produced only {signals} entry signals on {probe} "
                f"over the whole window — far too few to draw any conclusion. The rules "
                f"are too restrictive. Loosen them: drop the rarest condition entirely, "
                f"widen any thresholds, and wrap anything that must coincide in "
                f"WITHIN_LAST with 5-10 bars. Reply with the corrected JSON only.")})
        else:
            warnings.append(
                f"Even after loosening, this fires only {signals} entry signals on "
                f"{probe}. Widen the window or simplify the entry rule further.")

    if not payload.get("strategy"):
        raise RuntimeError("The AI did not return a usable strategy. Please try again.")

    settings = _clean_settings(payload.get("settings") or {}, answers)

    return {
        "strategy": payload["strategy"],
        "strategy_name": str(payload.get("strategy_name") or "AI strategy")[:80],
        "settings": settings,
        "explanation": str(payload.get("explanation") or ""),
        "stage_notes": payload.get("stage_notes") or {},
        "signals_found": signals,
        "warnings": warnings,
        "provider": provider,
        "attempts": attempts,
    }
