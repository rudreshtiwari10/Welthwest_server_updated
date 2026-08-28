"""
Experiment registry (spec §34).

Every run stores enough to be reproduced exactly and compared against another.
Storage is best-effort: MongoDB when the app's database is reachable, with an
in-process ring buffer as the fallback so the compare/clone features still work
in local development.

A run is keyed by its config fingerprint. Re-running the same configuration
returns the same run_id — which is the reproducibility guarantee made visible.
"""

from __future__ import annotations

import logging
import threading
from collections import OrderedDict
from datetime import datetime

logger = logging.getLogger(__name__)

_MEMORY_LIMIT = 60
_memory: "OrderedDict[str, dict]" = OrderedDict()
_lock = threading.Lock()


def _summary(report: dict) -> dict:
    """The compact row shown in the run list and the compare view."""
    run = report.get("run", {})
    head = report.get("headline", {})
    return {
        "run_id": run.get("run_id"),
        "strategy_name": run.get("strategy_name"),
        "strategy_hash": run.get("strategy_hash"),
        "engine_version": run.get("engine_version"),
        "data_version": run.get("data_version"),
        "symbols": run.get("symbols"),
        "timeframe": run.get("timeframe"),
        "start": run.get("start"), "end": run.get("end"),
        "cost_schedule": run.get("cost_schedule"),
        "intrabar_policy": run.get("intrabar_policy"),
        "seed": run.get("seed"),
        "initial_capital": run.get("initial_capital"),
        "net_cagr": head.get("net_cagr"),
        "gross_cagr": head.get("gross_cagr"),
        "max_drawdown": head.get("max_drawdown"),
        "sharpe": head.get("sharpe"),
        "total_trades": head.get("total_trades"),
        "quality_score": head.get("quality_score"),
        "confidence_label": head.get("confidence_label"),
        "created_at": datetime.utcnow().isoformat(timespec="seconds") + "Z",
    }


def _collection():
    """Return the Mongo collection, or None if the database is unavailable."""
    try:
        from database import db
        return db.backtest_india_runs
    except Exception:
        return None


def record_run(report: dict) -> None:
    row = _summary(report)
    row["config"] = report.get("run", {}).get("config")

    with _lock:
        _memory[row["run_id"]] = row
        while len(_memory) > _MEMORY_LIMIT:
            _memory.popitem(last=False)

    col = _collection()
    if col is None:
        return
    try:
        col.update_one({"run_id": row["run_id"]}, {"$set": row}, upsert=True)
    except Exception as exc:
        logger.debug("backtest_india: registry persist skipped (%s)", exc)


def list_runs(limit: int = 25, user_id: str = None) -> list:
    col = _collection()
    if col is not None:
        try:
            query = {"user_id": user_id} if user_id else {}
            rows = list(col.find(query, {"_id": 0, "config": 0})
                        .sort("created_at", -1).limit(limit))
            if rows:
                return rows
        except Exception as exc:
            logger.debug("backtest_india: registry read skipped (%s)", exc)
    with _lock:
        return list(reversed(list(_memory.values())))[:limit]


def get_run(run_id: str) -> dict:
    col = _collection()
    if col is not None:
        try:
            row = col.find_one({"run_id": run_id}, {"_id": 0})
            if row:
                return row
        except Exception:
            pass
    with _lock:
        return _memory.get(run_id, {})


def compare(run_id_a: str, run_id_b: str) -> dict:
    """
    Spec §34 — "compare two runs". Reports which config fields differ, so a
    user can see that a result changed because the cost schedule changed and
    not because the signal did.
    """
    a, b = get_run(run_id_a), get_run(run_id_b)
    if not a or not b:
        return {"available": False, "reason": "one or both runs are no longer in the registry"}

    cfg_a = a.get("config") or {}
    cfg_b = b.get("config") or {}
    diffs = []
    for key in sorted(set(cfg_a) | set(cfg_b)):
        va, vb = cfg_a.get(key), cfg_b.get(key)
        if va != vb:
            diffs.append({"field": key, "a": va, "b": vb})

    metric_keys = ("net_cagr", "gross_cagr", "max_drawdown", "sharpe",
                   "total_trades", "quality_score", "confidence_label")
    metric_diff = [
        {"metric": k, "a": a.get(k), "b": b.get(k),
         "delta": (round(a[k] - b[k], 6)
                   if isinstance(a.get(k), (int, float)) and isinstance(b.get(k), (int, float))
                   else None)}
        for k in metric_keys
    ]

    return {
        "available": True,
        "a": {k: v for k, v in a.items() if k != "config"},
        "b": {k: v for k, v in b.items() if k != "config"},
        "config_differences": diffs,
        "metric_differences": metric_diff,
        "reading": (
            "Identical configs must produce identical metrics. If the configs differ "
            "in exactly one field, every metric change is attributable to that field."
            if len(diffs) <= 1 else
            f"{len(diffs)} config fields differ, so metric changes cannot be attributed "
            "to any single one. Clone a run and change one variable at a time."
        ),
    }
