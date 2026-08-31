"""
API surface for the backtest_india engine (WelthWest Backtesting v2).

This is now the only backtesting engine — the legacy /api/backtesting/*
endpoints, the old Beta page, and services/backtesting_engine.py were
retired. Nothing in this module ever imported from that file or from
services/simple_backtest_service.py (still used elsewhere, by Finance AI).

Routes
------
GET  /api/backtest-india/health            engine + data-source status
GET  /api/backtest-india/catalogue         everything the builder UI renders from
GET  /api/backtest-india/presets           ready-made strategy graphs
GET  /api/backtest-india/presets/<key>     one preset, fully expanded
GET  /api/backtest-india/cost-schedules    versioned Indian charge schedules
POST /api/backtest-india/validate          static graph check, no data fetched
POST /api/backtest-india/run               the full experiment
POST /api/backtest-india/pattern-lab       forward-outcome study (separate path)
GET  /api/backtest-india/runs              experiment registry
GET  /api/backtest-india/runs/<run_id>     one registry entry
GET  /api/backtest-india/compare           diff two runs
GET  /api/backtest-india/selftest          the engine's own acceptance suite
"""

from __future__ import annotations

import functools
import logging
import os
import time

from flask import Blueprint, g, jsonify, request

from middleware.feature_limit import feature_limit

logger = logging.getLogger(__name__)

backtest_india_bp = Blueprint("backtest_india", __name__,
                              url_prefix="/api/backtest-india")

# Guard-rails so a single request cannot pin a worker.
MAX_SYMBOLS = 8
MAX_ROBUSTNESS_VARIANTS = 24


# ── Access gate ─────────────────────────────────────────────────────────────
#
# /run and /pattern-lab would normally sit behind feature_limit('backtest-beta'),
# which enforces sign-in AND the daily quota.
#
# LOGIN IS CURRENTLY DISABLED FOR THIS PAGE. Both endpoints are open to anyone
# who can reach them — no user id, no quota — because the page is still being
# built out and signing in on every run got in the way.
#
# >>> TO PUT LOGIN BACK: change OPEN_ACCESS_BY_DEFAULT to False. <<<
# That single line is the whole switch. Alternatively, leave it as-is and set
# the env var BACKTEST_INDIA_OPEN_ACCESS=false, which overrides the default and
# is the safer option for a deployed environment.
#
# The value is resolved per request, so nothing is baked in at import time.

OPEN_ACCESS_BY_DEFAULT = True

_TRUTHY = {"1", "true", "yes", "on"}
_FALSY = {"0", "false", "no", "off"}


def open_access_enabled() -> bool:
    """True when /run and /pattern-lab skip auth and quota entirely."""
    raw = os.environ.get("BACKTEST_INDIA_OPEN_ACCESS", "").strip().lower()
    if raw in _TRUTHY:
        return True
    if raw in _FALSY:
        return False
    return OPEN_ACCESS_BY_DEFAULT


def metered(feature_key: str):
    """feature_limit, unless open access is on (which it currently is)."""
    gated = feature_limit(feature_key)

    def decorator(fn):
        wrapped = gated(fn)

        @functools.wraps(fn)
        def dispatch(*args, **kwargs):
            if open_access_enabled():
                logger.warning(
                    "backtest-india: %s served WITHOUT login or quota — open access "
                    "is on. Set OPEN_ACCESS_BY_DEFAULT=False (or the env var "
                    "BACKTEST_INDIA_OPEN_ACCESS=false) to require sign-in again.",
                    request.path,
                )
                return fn(*args, **kwargs)
            return wrapped(*args, **kwargs)

        return dispatch

    return decorator


def _fail(message: str, status: int = 400, **extra):
    payload = {"success": False, "error": message}
    payload.update(extra)
    return jsonify(payload), status


# ── Metadata (public, cheap) ────────────────────────────────────────────────

@backtest_india_bp.route("/health", methods=["GET"])
def health():
    from services.backtest_india import ENGINE_VERSION
    return jsonify({
        "success": True,
        "engine": "backtest_india",
        "engine_version": ENGINE_VERSION,
        "status": "ready",
        "open_access": open_access_enabled(),
        "realism_level": 3,
        "realism_note": ("OHLCV bars with a synthetic spread, modelled slippage, "
                         "volume participation caps and execution latency. No tick "
                         "or order-book data."),
    }), 200


@backtest_india_bp.route("/catalogue", methods=["GET"])
def catalogue():
    try:
        from services.backtest_india.catalogue import full_catalogue
        payload = full_catalogue()
        # lets the builder tell the user whether a run will ask them to sign in
        payload["open_access"] = open_access_enabled()
        return jsonify({"success": True, "catalogue": payload}), 200
    except Exception as exc:
        logger.error("backtest-india catalogue failed: %s", exc, exc_info=True)
        return _fail("Could not build the strategy catalogue.", 500)


@backtest_india_bp.route("/presets", methods=["GET"])
def presets():
    from services.backtest_india.presets import list_presets
    return jsonify({"success": True, "presets": list_presets()}), 200


@backtest_india_bp.route("/presets/<key>", methods=["GET"])
def preset_detail(key: str):
    from services.backtest_india.presets import get_preset
    try:
        return jsonify({"success": True, "preset": get_preset(key)}), 200
    except KeyError as exc:
        return _fail(str(exc), 404)


@backtest_india_bp.route("/cost-schedules", methods=["GET"])
def cost_schedules():
    from services.backtest_india.costs import list_cost_schedules
    return jsonify({"success": True, "schedules": list_cost_schedules()}), 200


@backtest_india_bp.route("/validate", methods=["POST"])
def validate():
    """Static strategy-graph check. Fetches no data, so it is instant."""
    from services.backtest_india.graph import validate_graph
    data = request.get_json(silent=True) or {}
    strategy = data.get("strategy") or {}
    problems = validate_graph(strategy)
    return jsonify({
        "success": True,
        "valid": not problems,
        "problems": problems,
    }), 200


# ── The run (gated + metered) ──────────────────────────────────────────────

@backtest_india_bp.route("/run", methods=["POST"])
@metered("backtest-beta")
def run():
    """Execute a full experiment and return the complete report."""
    data = request.get_json(silent=True)
    if not isinstance(data, dict):
        return _fail("Request body must be a JSON object.")

    symbols = data.get("symbols")
    if isinstance(symbols, str):
        symbols = [s.strip() for s in symbols.split(",") if s.strip()]
    if not symbols:
        return _fail("Select at least one instrument to test.")
    if len(symbols) > MAX_SYMBOLS:
        return _fail(f"A single run is limited to {MAX_SYMBOLS} instruments. "
                     f"You selected {len(symbols)}.")
    data["symbols"] = symbols

    if not data.get("start") or not data.get("end"):
        return _fail("Both a start and an end date are required.")
    if str(data["start"]) >= str(data["end"]):
        return _fail("The start date must fall before the end date.")

    if not (data.get("strategy") or {}).get("entry_long") and \
       not (data.get("strategy") or {}).get("entry_short"):
        return _fail("The strategy has no entry rule. Load a preset or add one "
                     "in the builder.")

    try:
        capital = float(data.get("initial_capital", 1_000_000))
    except (TypeError, ValueError):
        return _fail("Initial capital must be a number.")
    if capital <= 0:
        return _fail("Initial capital must be greater than zero.")
    data["initial_capital"] = capital

    rob = dict(data.get("robustness") or {})
    rob["max_variants"] = min(int(rob.get("max_variants", 8)), MAX_ROBUSTNESS_VARIANTS)
    data["robustness"] = rob

    started = time.time()
    try:
        from services.backtest_india import run_backtest
        report = run_backtest(data)
    except ValueError as exc:
        return _fail(str(exc), 400)
    except Exception as exc:
        logger.error("backtest-india run failed: %s", exc, exc_info=True)
        return _fail("The backtest could not be completed. "
                     f"Reason: {exc}", 500)

    # feature_limit stashes the quota on `g` and mirrors it in X-RateLimit-*
    # headers; surface it in the body so the page can show it without reading
    # headers through the fetch wrapper.
    remaining = getattr(g, "usage_remaining", None)
    if remaining is not None:
        report["usage"] = {
            "feature": getattr(g, "feature_key", "backtest-beta"),
            "remaining": remaining,
            "limit": getattr(g, "usage_limit", None),
        }
    report["server_runtime_seconds"] = round(time.time() - started, 2)
    return jsonify(report), 200


@backtest_india_bp.route("/pattern-lab", methods=["POST"])
@metered("backtest-beta")
def pattern_lab():
    """
    Forward-outcome study. Deliberately a separate endpoint from /run: pattern
    performance analysis and live signal generation are kept physically apart.
    """
    data = request.get_json(silent=True) or {}
    symbol = data.get("symbol")
    if not symbol:
        return _fail("A symbol is required.")
    if not data.get("start") or not data.get("end"):
        return _fail("Both a start and an end date are required.")

    try:
        from services.backtest_india.patternlab import study
        result = study(
            symbol=symbol, start=data["start"], end=data["end"],
            timeframe=data.get("timeframe", "1d"),
            exchange=data.get("exchange", "NSE"),
            pattern_types=data.get("patterns"),
            include_chart_patterns=bool(data.get("include_chart_patterns", True)),
        )
    except Exception as exc:
        logger.error("backtest-india pattern lab failed: %s", exc, exc_info=True)
        return _fail(f"The pattern study could not be completed. Reason: {exc}", 500)

    return jsonify({"success": True, "study": result}), 200


# ── Experiment registry ────────────────────────────────────────────────────

@backtest_india_bp.route("/runs", methods=["GET"])
def runs():
    from services.backtest_india.registry import list_runs
    limit = min(int(request.args.get("limit", 25)), 100)
    return jsonify({"success": True, "runs": list_runs(limit)}), 200


@backtest_india_bp.route("/runs/<run_id>", methods=["GET"])
def run_detail(run_id: str):
    from services.backtest_india.registry import get_run
    row = get_run(run_id)
    if not row:
        return _fail("That run is no longer in the registry.", 404)
    return jsonify({"success": True, "run": row}), 200


@backtest_india_bp.route("/compare", methods=["GET"])
def compare_runs():
    from services.backtest_india.registry import compare
    a, b = request.args.get("a"), request.args.get("b")
    if not a or not b:
        return _fail("Provide two run ids as ?a=<run_id>&b=<run_id>.")
    return jsonify({"success": True, "comparison": compare(a, b)}), 200


# ── AI-assisted fill (optional; the manual builder never touches this) ──────

@backtest_india_bp.route("/ai-fill/interview", methods=["GET"])
def ai_fill_interview():
    """The questions the assistant asks. Static, so it is free and instant."""
    from services.backtest_india.aifill import ai_available, interview
    return jsonify({
        "success": True,
        "available": ai_available(),
        "questions": interview(),
    }), 200


@backtest_india_bp.route("/ai-fill", methods=["POST"])
@metered("backtest-beta")
def ai_fill():
    """
    Turn interview answers into a complete pipeline configuration.

    The response is a proposal, not an applied change — the page shows it to
    the user and only writes it into the builder if they accept.
    """
    from services.backtest_india.aifill import ai_available, generate

    if not ai_available():
        return _fail("The AI assistant is not configured on this server. "
                     "Set OPENROUTER_API_KEY, GEMINI_API_KEY, OPENAI_API_KEY or "
                     "CLAUDE_API_KEY to enable it.", 503)

    data = request.get_json(silent=True)
    if not isinstance(data, dict):
        return _fail("Request body must be a JSON object.")

    answers = data.get("answers")
    if not isinstance(answers, dict) or not answers:
        return _fail("Answer at least one question before asking the assistant.")

    started = time.time()
    try:
        result = generate(answers, verify=bool(data.get("verify", True)))
    except RuntimeError as exc:
        # Already scrubbed of credentials by aifill, but never assume.
        from services.backtest_india.aifill import _scrub
        return _fail(_scrub(exc), 502)
    except Exception as exc:
        from services.backtest_india.aifill import _scrub
        logger.error("backtest-india ai-fill failed: %s", _scrub(exc), exc_info=True)
        return _fail("The assistant could not build a configuration. "
                     f"Reason: {_scrub(exc)}", 500)

    result["success"] = True
    result["server_runtime_seconds"] = round(time.time() - started, 2)
    return jsonify(result), 200


@backtest_india_bp.route("/selftest", methods=["GET"])
def selftest():
    """
    The engine's own acceptance suite (spec §38). Exposed so the numbers this
    engine produces can be audited rather than trusted.
    """
    try:
        from services.backtest_india.selftest import run_all
        return jsonify({"success": True, "selftest": run_all()}), 200
    except Exception as exc:
        logger.error("backtest-india selftest failed: %s", exc, exc_info=True)
        return _fail("The self-test suite could not be run.", 500)
