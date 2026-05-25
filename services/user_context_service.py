"""
user_context_service — persistent per-user money profile, goals, and portfolio.

Single MongoDB collection `welth_user_context`, keyed by user_id. Stores:
  - profile:  age / income / dependents / tax-regime preference / risk profile
  - goals:    list of named savings/investment goals with targets and progress
  - portfolio: list of manually-entered holdings (equity, MF, FD, PPF, etc.)

This is the moat layer — every personalized agent answer is grounded in this.
"""

import logging
import uuid
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from pymongo import ASCENDING

from database import get_db


logger = logging.getLogger(__name__)


# ---- Constants -------------------------------------------------------------

VALID_REGIMES = ("old", "new", "auto")
VALID_RISK = ("conservative", "moderate", "aggressive")
VALID_CITY = ("metro", "tier1", "tier2", "tier3")
VALID_GOAL_TYPES = ("retirement", "house", "education", "emergency", "vehicle", "vacation", "wedding", "custom")
VALID_ASSET_TYPES = ("equity", "equity_mf", "debt_mf", "hybrid_mf", "etf", "fd", "rd", "ppf", "epf", "nps", "ssy", "gold", "bond", "real_estate", "cash", "other")


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _collection():
    db = get_db()
    coll = db.welth_user_context
    # Ensure index — idempotent.
    try:
        coll.create_index([("user_id", ASCENDING)], unique=True, name="user_id_unique")
    except Exception:
        pass
    return coll


def _empty_doc(user_id: str) -> Dict[str, Any]:
    return {
        "user_id": user_id,
        "profile": {},
        "goals": [],
        "portfolio": {"holdings": [], "last_updated": None},
        "created_at": _now(),
        "updated_at": _now(),
    }


def _scrub_id(doc: Dict[str, Any]) -> Dict[str, Any]:
    if doc and "_id" in doc:
        doc.pop("_id")
    return doc


# ---- Profile ---------------------------------------------------------------

def get_profile(user_id: str) -> Dict[str, Any]:
    doc = _collection().find_one({"user_id": user_id}) or {}
    return doc.get("profile") or {}


def upsert_profile(user_id: str, profile: Dict[str, Any]) -> Dict[str, Any]:
    """Replace profile fields. Validates the small enum set."""
    p = {}
    if "age" in profile and profile["age"] is not None:
        age = int(profile["age"])
        if age < 0 or age > 120:
            raise ValueError("age must be between 0 and 120")
        p["age"] = age
    if "annual_income" in profile and profile["annual_income"] is not None:
        inc = float(profile["annual_income"])
        if inc < 0:
            raise ValueError("annual_income must be ≥ 0")
        p["annual_income"] = inc
    if "is_salaried" in profile:
        p["is_salaried"] = bool(profile["is_salaried"])
    if "city_tier" in profile and profile["city_tier"]:
        if profile["city_tier"] not in VALID_CITY:
            raise ValueError(f"city_tier must be one of {VALID_CITY}")
        p["city_tier"] = profile["city_tier"]
    if "dependents" in profile and profile["dependents"] is not None:
        p["dependents"] = max(0, int(profile["dependents"]))
    if "tax_regime_pref" in profile and profile["tax_regime_pref"]:
        if profile["tax_regime_pref"] not in VALID_REGIMES:
            raise ValueError(f"tax_regime_pref must be one of {VALID_REGIMES}")
        p["tax_regime_pref"] = profile["tax_regime_pref"]
    if "risk_profile" in profile and profile["risk_profile"]:
        if profile["risk_profile"] not in VALID_RISK:
            raise ValueError(f"risk_profile must be one of {VALID_RISK}")
        p["risk_profile"] = profile["risk_profile"]
    if "marital_status" in profile and profile["marital_status"]:
        p["marital_status"] = profile["marital_status"]

    coll = _collection()
    coll.update_one(
        {"user_id": user_id},
        {
            "$set": {
                "profile": p,
                "updated_at": _now(),
            },
            "$setOnInsert": {
                "user_id": user_id,
                "goals": [],
                "portfolio": {"holdings": [], "last_updated": None},
                "created_at": _now(),
            },
        },
        upsert=True,
    )
    return p


# ---- Goals -----------------------------------------------------------------

def get_goals(user_id: str) -> List[Dict[str, Any]]:
    doc = _collection().find_one({"user_id": user_id}) or {}
    return doc.get("goals") or []


def add_goal(user_id: str, goal: Dict[str, Any]) -> Dict[str, Any]:
    goal_type = goal.get("type") or "custom"
    if goal_type not in VALID_GOAL_TYPES:
        raise ValueError(f"goal type must be one of {VALID_GOAL_TYPES}")
    name = (goal.get("name") or "").strip()
    if not name:
        raise ValueError("goal name is required")
    target_amount = float(goal.get("target_amount") or 0)
    if target_amount <= 0:
        raise ValueError("target_amount must be > 0")
    target_year = int(goal.get("target_year") or 0)
    if target_year < 1900 or target_year > 2200:
        raise ValueError("target_year must be a sensible year")

    new_goal = {
        "id": uuid.uuid4().hex[:12],
        "type": goal_type,
        "name": name,
        "target_amount": target_amount,
        "target_year": target_year,
        "current_progress": float(goal.get("current_progress") or 0),
        "monthly_sip": float(goal.get("monthly_sip") or 0),
        "expected_return_pct": float(goal.get("expected_return_pct") or 12.0),
        "created_at": _now(),
    }

    _collection().update_one(
        {"user_id": user_id},
        {
            "$push": {"goals": new_goal},
            "$set": {"updated_at": _now()},
            "$setOnInsert": {
                "user_id": user_id,
                "profile": {},
                "portfolio": {"holdings": [], "last_updated": None},
                "created_at": _now(),
            },
        },
        upsert=True,
    )
    return new_goal


def update_goal(user_id: str, goal_id: str, updates: Dict[str, Any]) -> bool:
    set_ops = {"updated_at": _now()}
    for k in ("name", "target_amount", "target_year", "current_progress", "monthly_sip", "expected_return_pct"):
        if k in updates:
            set_ops[f"goals.$[g].{k}"] = updates[k]
    res = _collection().update_one(
        {"user_id": user_id},
        {"$set": set_ops},
        array_filters=[{"g.id": goal_id}],
    )
    return res.matched_count > 0


def delete_goal(user_id: str, goal_id: str) -> bool:
    res = _collection().update_one(
        {"user_id": user_id},
        {
            "$pull": {"goals": {"id": goal_id}},
            "$set": {"updated_at": _now()},
        },
    )
    return res.modified_count > 0


# ---- Portfolio -------------------------------------------------------------

def get_portfolio(user_id: str) -> Dict[str, Any]:
    doc = _collection().find_one({"user_id": user_id}) or {}
    return doc.get("portfolio") or {"holdings": [], "last_updated": None}


def replace_portfolio(user_id: str, holdings: List[Dict[str, Any]]) -> Dict[str, Any]:
    """Replace the entire holdings list. Simpler than per-item add/edit/delete for MVP."""
    cleaned = []
    for h in holdings or []:
        asset_type = (h.get("asset_type") or "other").strip().lower()
        if asset_type not in VALID_ASSET_TYPES:
            raise ValueError(f"asset_type must be one of {VALID_ASSET_TYPES}")
        symbol = (h.get("symbol") or "").strip().upper()
        name = (h.get("name") or symbol or "Untitled").strip()
        quantity = float(h.get("quantity") or 0)
        avg_buy_price = float(h.get("avg_buy_price") or 0)
        if quantity < 0 or avg_buy_price < 0:
            raise ValueError("quantity and avg_buy_price must be ≥ 0")
        cleaned.append({
            "id": h.get("id") or uuid.uuid4().hex[:12],
            "asset_type": asset_type,
            "symbol": symbol,
            "name": name,
            "quantity": quantity,
            "avg_buy_price": avg_buy_price,
            "buy_date": h.get("buy_date") or "",
            "notes": (h.get("notes") or "").strip(),
        })

    portfolio = {"holdings": cleaned, "last_updated": _now()}
    _collection().update_one(
        {"user_id": user_id},
        {
            "$set": {"portfolio": portfolio, "updated_at": _now()},
            "$setOnInsert": {
                "user_id": user_id,
                "profile": {},
                "goals": [],
                "created_at": _now(),
            },
        },
        upsert=True,
    )
    return portfolio


def analyze_portfolio(user_id: str) -> Dict[str, Any]:
    """
    Static analysis on the saved portfolio: total invested, asset-class breakdown,
    top holdings by invested amount, concentration flags. Live price fetching is
    deferred — this works on the saved buy-price snapshot.
    """
    pf = get_portfolio(user_id)
    holdings = pf.get("holdings") or []
    if not holdings:
        return {
            "summary": {
                "holding_count": 0,
                "total_invested": 0,
            },
            "asset_class_breakdown": [],
            "top_holdings": [],
            "concentration_flags": ["Portfolio is empty — add holdings to get analysis."],
        }

    by_class: Dict[str, float] = {}
    enriched = []
    for h in holdings:
        invested = h["quantity"] * h["avg_buy_price"]
        enriched.append({**h, "invested": round(invested, 2)})
        by_class[h["asset_type"]] = by_class.get(h["asset_type"], 0) + invested

    total_invested = sum(by_class.values())

    asset_class_breakdown = [
        {
            "asset_type": k,
            "invested": round(v, 2),
            "pct": round(v / total_invested * 100, 1) if total_invested else 0,
        }
        for k, v in sorted(by_class.items(), key=lambda kv: kv[1], reverse=True)
    ]

    top_holdings = sorted(enriched, key=lambda h: h["invested"], reverse=True)[:5]
    top_holdings = [
        {
            "name": h["name"],
            "symbol": h["symbol"],
            "asset_type": h["asset_type"],
            "invested": h["invested"],
            "pct_of_portfolio": round(h["invested"] / total_invested * 100, 1) if total_invested else 0,
        }
        for h in top_holdings
    ]

    flags: List[str] = []
    for h in top_holdings:
        if h["pct_of_portfolio"] > 25:
            flags.append(
                f"{h['name']} is {h['pct_of_portfolio']}% of the portfolio — "
                "above the typical 25% single-name concentration threshold."
            )
    equity_pct = sum(b["pct"] for b in asset_class_breakdown if b["asset_type"] in ("equity", "equity_mf", "etf"))
    if equity_pct > 90:
        flags.append(f"{equity_pct:.0f}% in equity — heavy concentration; review against risk profile and time horizon.")
    elif equity_pct < 20 and total_invested > 0:
        flags.append(f"Only {equity_pct:.0f}% in equity — review against long-term inflation-beating return needs.")

    return {
        "summary": {
            "holding_count": len(holdings),
            "total_invested": round(total_invested, 2),
        },
        "asset_class_breakdown": asset_class_breakdown,
        "top_holdings": top_holdings,
        "concentration_flags": flags,
    }


def get_full_context(user_id: str) -> Dict[str, Any]:
    """Return the full document (profile + goals + portfolio) for one shot."""
    doc = _collection().find_one({"user_id": user_id})
    if not doc:
        return _scrub_id(_empty_doc(user_id))
    return _scrub_id(doc)
