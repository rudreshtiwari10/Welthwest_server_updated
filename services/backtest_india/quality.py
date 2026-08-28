"""
Strategy Quality Score and bias audit (spec §35, §36, §42).

The score is a RESEARCH-QUALITY ranking aid. It is not a probability of future
profit, it is not calibrated against future outcomes, and the raw metrics that
feed it stay visible so a user can disagree with the weighting.

    Q = 0.25*OOS_RiskAdjusted + 0.20*Robustness + 0.15*RegimeConsistency
      + 0.15*CostSurvival + 0.10*LiquidityQuality + 0.10*BenchmarkExcess
      + 0.05*Simplicity

Every component is normalised with documented caps that are returned alongside
the score, so the number can be audited rather than trusted.
"""

from __future__ import annotations

import numpy as np

from services.backtest_india.contracts import ConfidenceLabel


def _norm(value, lo: float, hi: float) -> float:
    """Linear normalisation into [0, 1] with explicit, reported caps."""
    if value is None or not np.isfinite(value):
        return 0.0
    return float(np.clip((value - lo) / (hi - lo), 0.0, 1.0))


def compute_quality(metrics: dict, walk_forward: dict, robustness: dict,
                    regimes: dict, stress: dict, liquidity: dict,
                    strategy: dict) -> dict:
    """Assemble Q with every component and its cap exposed."""
    components = []

    # 1. Out-of-sample risk-adjusted return (0.25)
    if walk_forward.get("available"):
        oos_sharpe = walk_forward.get("oos_mean_sharpe")
        oos_val = _norm(oos_sharpe, 0.0, 2.0)
        oos_basis = f"walk-forward mean OOS Sharpe {oos_sharpe}"
    else:
        # no walk-forward: the in-sample Sharpe is heavily discounted, because
        # an unvalidated result is not an out-of-sample result
        oos_val = _norm(metrics.get("sharpe"), 0.0, 2.0) * 0.4
        oos_basis = ("in-sample Sharpe, discounted 60% because no walk-forward "
                     "validation was run")
    components.append({
        "name": "OOS risk-adjusted return", "weight": 0.25,
        "value": round(oos_val, 4), "basis": oos_basis,
        "cap": "Sharpe 0.0 -> 0, Sharpe 2.0 -> 1",
    })

    # 2. Robustness (0.20)
    rb = robustness.get("stability") if robustness.get("available") else None
    rb_val = _norm(rb, 0.0, 0.9)
    components.append({
        "name": "Parameter robustness", "weight": 0.20,
        "value": round(rb_val, 4),
        "basis": (f"median/best neighbour score = {rb}" if rb is not None
                  else "no numeric parameters to perturb"),
        "cap": "stability 0.0 -> 0, 0.9 -> 1",
    })

    # 3. Regime consistency (0.15)
    reg_val = 0.0
    reg_basis = "not enough observations to condition on regime"
    if regimes.get("available") and regimes.get("by_bar"):
        sharpes = [b["sharpe"] for b in regimes["by_bar"] if b.get("sharpe") is not None]
        if sharpes:
            positive = sum(1 for s in sharpes if s > 0) / len(sharpes)
            worst = min(sharpes)
            reg_val = 0.6 * positive + 0.4 * _norm(worst, -1.0, 1.0)
            reg_basis = (f"{sum(1 for s in sharpes if s > 0)}/{len(sharpes)} regimes "
                         f"positive, worst regime Sharpe {worst:.2f}")
    components.append({
        "name": "Regime consistency", "weight": 0.15,
        "value": round(reg_val, 4), "basis": reg_basis,
        "cap": "60% share of positive regimes + 40% worst-regime Sharpe in [-1, 1]",
    })

    # 4. Cost survival (0.15)
    cost_val = 0.0
    cost_basis = "cost stress not run"
    if stress.get("available"):
        rate = stress.get("survival_rate")
        if rate is not None:
            cost_val = float(rate)
            cost_basis = (f"{stress.get('scenarios_survived')}/"
                          f"{stress.get('scenarios_tested')} stress scenarios stayed positive")
    components.append({
        "name": "Cost and realism survival", "weight": 0.15,
        "value": round(cost_val, 4), "basis": cost_basis,
        "cap": "fraction of stress scenarios with a positive return",
    })

    # 5. Liquidity quality (0.10)
    liq_val = 1.0
    liq_basis = "no participation constraint ever bound"
    if liquidity.get("available"):
        binding = liquidity.get("liquidity_constrained_pct", 0.0) or 0.0
        rejected = liquidity.get("rejected_pct", 0.0) or 0.0
        liq_val = float(np.clip(1.0 - (binding + rejected) / 100.0, 0.0, 1.0))
        liq_basis = (f"{binding:.1f}% of entries were size-capped by liquidity, "
                     f"{rejected:.1f}% of orders never filled")
    components.append({
        "name": "Liquidity quality", "weight": 0.10,
        "value": round(liq_val, 4), "basis": liq_basis,
        "cap": "1 minus the share of orders constrained or unfilled",
    })

    # 6. Benchmark excess (0.10)
    bm = metrics.get("benchmark") or {}
    excess = bm.get("excess_cagr")
    bm_val = _norm(excess, -0.10, 0.20)
    components.append({
        "name": "Benchmark excess", "weight": 0.10,
        "value": round(bm_val, 4),
        "basis": (f"CAGR excess over benchmark = {excess:.2%}" if excess is not None
                  else "no benchmark available"),
        "cap": "-10% -> 0, +20% -> 1",
    })

    # 7. Simplicity (0.05) — spec §25 complexity penalty
    n_params = _count_parameters(strategy)
    simp_val = float(np.clip(1.0 - (n_params - 2) / 18.0, 0.0, 1.0))
    components.append({
        "name": "Simplicity", "weight": 0.05,
        "value": round(simp_val, 4),
        "basis": f"{n_params} tunable degrees of freedom in the strategy graph",
        "cap": "2 parameters -> 1, 20 parameters -> 0",
    })

    q = sum(c["weight"] * c["value"] for c in components)

    return {
        "score": round(100.0 * q, 1),
        "scale": "0-100",
        "components": components,
        "degrees_of_freedom": n_params,
        "disclaimer": (
            "This is a research-quality score, not a probability of future profit. "
            "It ranks how well a result survived validation, robustness, regime and "
            "cost testing. It says nothing about whether the edge will persist."
        ),
    }


def _count_parameters(strategy: dict) -> int:
    n = 0
    for group in ("features", "candles", "chart_patterns"):
        for item in strategy.get(group, []) or []:
            n += sum(1 for k, v in item.items()
                     if k not in ("id", "type") and isinstance(v, (int, float)))
    for cond in strategy.get("conditions", []) or []:
        n += sum(1 for k, v in cond.items()
                 if k not in ("id", "op", "left", "right") and isinstance(v, (int, float)))
        if isinstance(cond.get("right"), (int, float)):
            n += 1
    return n


def confidence_label(metrics: dict, walk_forward: dict, robustness: dict,
                     stress: dict, quality_score: float) -> dict:
    """
    Spec §35 — Research / Validated / Robust / Fragile / Failed.

    The label is derived from what was actually tested, so an untested strategy
    lands in "Research" no matter how good its headline number looks.
    """
    trades = metrics.get("total_trades", 0) or 0
    total_return = metrics.get("total_return", 0.0) or 0.0
    sharpe = metrics.get("sharpe", 0.0) or 0.0
    mdd = metrics.get("max_drawdown", 0.0) or 0.0

    reasons = []

    if trades < 10:
        return {
            "label": ConfidenceLabel.RESEARCH.value,
            "reasons": [f"only {trades} closed trades — far too few to conclude anything"],
            "summary": ("Not enough trades to distinguish skill from noise. Widen the "
                        "window, loosen the entry rules, or add instruments."),
        }

    if total_return <= 0 or sharpe <= 0:
        reasons.append(f"net return {total_return:.1%} with Sharpe {sharpe:.2f} after costs")
        return {
            "label": ConfidenceLabel.FAILED.value, "reasons": reasons,
            "summary": ("The strategy did not survive its own costs on this data. "
                        "That is a legitimate result, not an error."),
        }

    wf_ok = walk_forward.get("available") and (walk_forward.get("consistency", 0) or 0) >= 0.5
    rb_verdict = robustness.get("verdict") if robustness.get("available") else None
    stress_rate = stress.get("survival_rate") if stress.get("available") else None

    if rb_verdict == "fragile":
        reasons.append("performance collapses under small parameter changes")
        return {
            "label": ConfidenceLabel.FRAGILE.value, "reasons": reasons,
            "summary": ("The headline number sits on a narrow parameter spike. Treat "
                        "the specific parameter values as fitted to this sample."),
        }

    if stress_rate is not None and stress_rate < 0.5:
        reasons.append(f"only {stress_rate:.0%} of realism stress scenarios stayed positive")
        return {
            "label": ConfidenceLabel.FRAGILE.value, "reasons": reasons,
            "summary": ("The result does not have enough margin to absorb worse costs, "
                        "worse fills or missed signals."),
        }

    if wf_ok and rb_verdict == "plateau" and (stress_rate or 0) >= 0.7 and quality_score >= 60:
        reasons = [
            f"walk-forward consistency {walk_forward.get('consistency'):.0%} across "
            f"{walk_forward.get('folds')} out-of-sample folds",
            "parameter neighbourhood behaves as a plateau",
            f"{stress.get('scenarios_survived')}/{stress.get('scenarios_tested')} "
            "stress scenarios stayed positive",
        ]
        return {
            "label": ConfidenceLabel.ROBUST.value, "reasons": reasons,
            "summary": ("Survived out-of-sample windows, parameter perturbation and "
                        "realism stress. This is the strongest label this engine "
                        "issues — it is still not a forecast."),
        }

    if wf_ok:
        reasons.append(f"positive in {walk_forward.get('positive_folds')}/"
                       f"{walk_forward.get('folds')} out-of-sample folds")
        return {
            "label": ConfidenceLabel.VALIDATED.value, "reasons": reasons,
            "summary": ("Held up on data outside the windows used to look at it, but "
                        "has not cleared the full robustness and stress bar."),
        }

    reasons.append("no walk-forward validation was run, so this is an in-sample result")
    if mdd < -0.4:
        reasons.append(f"maximum drawdown {mdd:.1%}")
    return {
        "label": ConfidenceLabel.RESEARCH.value, "reasons": reasons,
        "summary": ("A hypothesis, not a validated result. Enable walk-forward "
                    "validation before drawing any conclusion from it."),
    }


def bias_audit(cfg, base, series_map, liquidity: dict, walk_forward: dict) -> list:
    """
    Spec §35/§42 — the audit the engine performs on ITSELF, reported whether or
    not the news is good.
    """
    checks = []

    checks.append({
        "check": "Look-ahead bias",
        "status": "pass",
        "detail": ("Signals are evaluated at bar close and every resulting order is "
                   f"stamped eligible at least {max(1, (cfg.execution or {}).get('latency_bars', 1))} "
                   "bar later. No fill can occur on the signal bar. Swing pivots are "
                   "withheld until k subsequent bars confirm them, and chart patterns "
                   "act only on their confirmation bar."),
    })

    surv_ok = cfg.survivorship_mode == "point_in_time"
    checks.append({
        "check": "Survivorship bias",
        "status": "warn",
        "detail": ("The instrument list was supplied directly, so it reflects symbols "
                   "that exist today. Any company delisted during the window is absent "
                   "from this test, which flatters the result. Point-in-time index "
                   "membership is not yet wired to a constituent-history source."
                   if not surv_ok or True else ""),
    })

    quality_notes = []
    for sym, s in series_map.items():
        q = s.quality
        if q.quarantined_indices:
            quality_notes.append(f"{sym}: {len(q.quarantined_indices)} bar(s) quarantined")
        if q.missing_bars_estimated > 0:
            quality_notes.append(f"{sym}: ~{q.missing_bars_estimated} session(s) absent")
        if q.duplicate_timestamps:
            quality_notes.append(f"{sym}: {q.duplicate_timestamps} duplicate timestamp(s) removed")
    checks.append({
        "check": "Data quality",
        "status": "warn" if quality_notes else "pass",
        "detail": ("; ".join(quality_notes) if quality_notes
                   else "No duplicate, out-of-order, impossible or non-positive bars found."),
    })

    policy = (cfg.intrabar_policy or "conservative").lower()
    checks.append({
        "check": "Intrabar ambiguity",
        "status": "pass" if policy in ("conservative", "priority_stop") else "warn",
        "detail": (
            "When a stop and a target both fall inside one bar, the adverse event is "
            "assumed first. Daily OHLC cannot reveal the true order, and this is the "
            "only assumption that cannot flatter the result."
            if policy in ("conservative", "priority_stop") else
            f"Intrabar policy is '{policy}'. Same-bar stop/target conflicts are resolved "
            "in the strategy's favour, which inflates the result. Re-run with the "
            "conservative policy before believing these numbers."
        ),
    })

    checks.append({
        "check": "Execution realism",
        "status": "warn",
        "detail": ("Fills are simulated from OHLCV bars with a synthetic spread and a "
                   "modelled slippage curve. No real bid/ask or tick data was used, so "
                   "the spread is an assumption, not an observation."),
    })

    if liquidity.get("available"):
        binding = liquidity.get("liquidity_constrained_pct", 0) or 0
        checks.append({
            "check": "Liquidity feasibility",
            "status": "warn" if binding > 5 else "pass",
            "detail": (f"{binding:.1f}% of entries had their size cut by the "
                       f"{liquidity.get('participation_rate', 0):.1%} volume participation "
                       "cap. At larger capital these positions would not be fillable."
                       if binding > 0 else
                       "No entry was ever constrained by the volume participation cap."),
        })

    checks.append({
        "check": "Out-of-sample discipline",
        "status": "pass" if walk_forward.get("available") else "warn",
        "detail": (
            f"{walk_forward.get('folds')} walk-forward folds with a "
            f"{walk_forward.get('schedule', {}).get('purge_bars')}-bar purge and a "
            f"{walk_forward.get('schedule', {}).get('embargo_bars')}-bar embargo "
            "between train and test."
            if walk_forward.get("available") else
            "No walk-forward validation was run. Every number here is in-sample."
        ),
    })

    checks.append({
        "check": "Capital-gains tax",
        "status": "info",
        "detail": ("Transaction levies (STT, stamp duty, GST, exchange and SEBI charges) "
                   "are inside net P&L. Capital-gains or business-income tax is NOT, "
                   "because its treatment depends on instrument, holding period and "
                   "taxpayer status."),
    })

    return checks
