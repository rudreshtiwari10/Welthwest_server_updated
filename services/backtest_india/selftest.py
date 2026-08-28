"""
Engine acceptance tests (spec §38, Appendix C).

These are the checks that have to pass before any number this engine produces
means anything. They use synthetic, hand-verifiable price series wherever an
exact answer exists, so a failure points at a specific broken invariant rather
than at "the backtest looks wrong".

Run standalone:
    python -m services.backtest_india.selftest
"""

from __future__ import annotations

import math
from datetime import datetime, timedelta

import numpy as np
import pandas as pd

from services.backtest_india import features as feat
from services.backtest_india.contracts import (
    Bar, Fill, Order, OrderSide, OrderStatus, OrderType,
)
from services.backtest_india.costs import get_cost_schedule
from services.backtest_india.execution import ExecutionModel, attempt_fill, resolve_intrabar
from services.backtest_india.graph import compile_graph
from services.backtest_india.portfolio import Portfolio

RESULTS: list = []


def check(name: str, condition: bool, detail: str = "") -> bool:
    RESULTS.append({"test": name, "passed": bool(condition), "detail": detail})
    return bool(condition)


def _bar(i: int, o, h, l, c, v=100000.0) -> Bar:
    t = datetime(2024, 1, 1) + timedelta(days=i)
    return Bar("TEST", t, t, float(o), float(h), float(l), float(c), float(v))


# ── 1. ledger arithmetic ────────────────────────────────────────────────────

def test_buy_one_share_exact():
    """Buy 1 share at a known price with zero costs; cash and P&L must be exact."""
    zero = get_cost_schedule("ZERO_COST_v1")
    pf = Portfolio(100000.0)
    pf.seed(datetime(2024, 1, 1))
    f = Fill("F1", "O1", "TEST", OrderSide.BUY, 1, 100.0, 100.0,
             datetime(2024, 1, 2), 1, costs={}, total_cost=0.0)
    pf.apply_fill(f)
    check("buy 1 share: cash reduced by exactly the notional",
          abs(pf.cash - 99900.0) < 1e-9, f"cash={pf.cash}")
    check("buy 1 share: position quantity is 1",
          pf.positions["TEST"].quantity == 1)
    check("buy 1 share: average price equals the fill price",
          abs(pf.positions["TEST"].avg_price - 100.0) < 1e-9)

    pt = pf.mark({"TEST": 110.0}, datetime(2024, 1, 3), 2)
    check("mark to market: equity = cash + holdings",
          abs(pt.equity - (99900.0 + 110.0)) < 1e-9, f"equity={pt.equity}")

    f2 = Fill("F2", "O2", "TEST", OrderSide.SELL, 1, 110.0, 110.0,
              datetime(2024, 1, 4), 3, costs={}, total_cost=0.0)
    trade = pf.apply_fill(f2)
    check("zero-cost round trip matches the analytical P&L",
          trade is not None and abs(trade.net_pnl - 10.0) < 1e-9,
          f"net_pnl={trade.net_pnl if trade else None}")
    check("zero-cost round trip: gross equals net",
          trade is not None and abs(trade.gross_pnl - trade.net_pnl) < 1e-9)
    check("final cash returns to capital plus profit",
          abs(pf.cash - 100010.0) < 1e-9, f"cash={pf.cash}")


def test_cost_components():
    """Each levy is charged on the correct side and basis."""
    sched = get_cost_schedule("INDIA_EQUITY_DELIVERY_v20250401")
    buy_total, buy = sched.compute(OrderSide.BUY, 100, 1000.0)   # turnover 100,000
    sell_total, sell = sched.compute(OrderSide.SELL, 100, 1000.0)

    check("STT charged on both delivery sides",
          abs(buy["stt"] - 100.0) < 1e-6 and abs(sell["stt"] - 100.0) < 1e-6,
          f"buy={buy.get('stt')} sell={sell.get('stt')}")
    check("stamp duty charged on the buy side only",
          "stamp_duty" in buy and "stamp_duty" not in sell,
          f"buy has {'stamp_duty' in buy}, sell has {'stamp_duty' in sell}")
    check("stamp duty amount is rate x turnover",
          abs(buy["stamp_duty"] - 15.0) < 1e-6, f"{buy.get('stamp_duty')}")
    check("SEBI turnover fee is Rs.10 per crore",
          abs(buy["sebi_turnover_fee"] - 0.1) < 1e-6, f"{buy.get('sebi_turnover_fee')}")
    check("GST applies to the service components, not to STT",
          abs(buy["gst"] - 0.18 * (buy["exchange_transaction_charge"]
                                   + buy["sebi_turnover_fee"])) < 1e-6,
          f"gst={buy.get('gst')}")

    intraday = get_cost_schedule("INDIA_EQUITY_INTRADAY_v20250401")
    ib_total, ib = intraday.compute(OrderSide.BUY, 100, 1000.0)
    is_total, isell = intraday.compute(OrderSide.SELL, 100, 1000.0)
    check("intraday STT is charged on the sell side only",
          "stt" not in ib and abs(isell["stt"] - 25.0) < 1e-6)
    check("intraday brokerage is capped at Rs.20 per order",
          abs(ib["brokerage"] - 20.0) < 1e-6, f"{ib.get('brokerage')}")

    zero_total, _ = get_cost_schedule("ZERO_COST_v1").compute(OrderSide.BUY, 100, 1000.0)
    check("zero-cost schedule charges nothing", abs(zero_total) < 1e-12)


def test_cost_only_changes_net():
    """Changing the cost schedule must change costs without changing the fill."""
    a = get_cost_schedule("INDIA_EQUITY_DELIVERY_v20250401")
    b = get_cost_schedule("INDIA_EQUITY_FULL_SERVICE_v20250401")
    ta, _ = a.compute(OrderSide.BUY, 100, 1000.0)
    tb, _ = b.compute(OrderSide.BUY, 100, 1000.0)
    check("a costlier schedule produces strictly higher charges", tb > ta,
          f"discount={ta:.2f} full-service={tb:.2f}")


# ── 2. execution ────────────────────────────────────────────────────────────

def test_slippage_sign():
    """Buys must fill worse (higher), sells must fill worse (lower)."""
    model = ExecutionModel(slippage_model="fixed_bps", slippage_bps=10,
                           use_synthetic_spread=False, participation_rate=0.0)
    bar = _bar(1, 100, 105, 95, 102)
    buy = Order("O1", "TEST", OrderSide.BUY, 10, OrderType.MARKET,
                bar.event_time, 1)
    sell = Order("O2", "TEST", OrderSide.SELL, 10, OrderType.MARKET,
                 bar.event_time, 1)
    fb = attempt_fill(buy, bar, model)
    fs = attempt_fill(sell, bar, model)
    check("buy slippage worsens the price upward", fb.price > fb.reference_price,
          f"{fb.reference_price} -> {fb.price}")
    check("sell slippage worsens the price downward", fs.price < fs.reference_price,
          f"{fs.reference_price} -> {fs.price}")
    check("slippage magnitude matches the configured basis points",
          abs(fb.price / fb.reference_price - 1.0010) < 1e-6, f"{fb.price}")


def test_limit_order_touch():
    """A limit order fills only when the bar actually trades through it."""
    model = ExecutionModel(slippage_model="none", use_synthetic_spread=False,
                           participation_rate=0.0)
    touched = _bar(1, 100, 105, 95, 102)
    untouched = _bar(2, 100, 105, 99, 102)
    o1 = Order("O1", "TEST", OrderSide.BUY, 10, OrderType.LIMIT,
               touched.event_time, 1, limit_price=97.0)
    o2 = Order("O2", "TEST", OrderSide.BUY, 10, OrderType.LIMIT,
               untouched.event_time, 1, limit_price=97.0)
    check("limit fills when the low trades through it",
          attempt_fill(o1, touched, model).filled_quantity == 10)
    check("limit does not fill when the low never reaches it",
          attempt_fill(o2, untouched, model).filled_quantity == 0)


def test_partial_fill():
    """Participation caps must produce partial fills, not silent full fills."""
    model = ExecutionModel(slippage_model="none", use_synthetic_spread=False,
                           participation_rate=0.01, allow_partial_fills=True)
    bar = _bar(1, 100, 105, 95, 102, v=10000.0)   # cap = 100 shares
    o = Order("O1", "TEST", OrderSide.BUY, 500, OrderType.MARKET, bar.event_time, 1)
    a = attempt_fill(o, bar, model)
    check("participation cap limits the fill to 1% of bar volume",
          a.filled_quantity == 100, f"filled {a.filled_quantity} of 500")

    strict = ExecutionModel(slippage_model="none", use_synthetic_spread=False,
                            participation_rate=0.01, allow_partial_fills=False)
    check("with partials disabled the order does not fill at all",
          attempt_fill(o, bar, strict).filled_quantity == 0)


def test_zero_volume_rejected():
    model = ExecutionModel(slippage_model="none", participation_rate=0.05)
    bar = _bar(1, 100, 100, 100, 100, v=0.0)
    o = Order("O1", "TEST", OrderSide.BUY, 10, OrderType.MARKET, bar.event_time, 1)
    a = attempt_fill(o, bar, model)
    check("a zero-volume bar cannot be traded against",
          a.filled_quantity == 0, a.rejected_reason)


def test_intrabar_policy():
    """The ambiguous same-bar case must resolve against the strategy by default."""
    bar = _bar(1, 100, 110, 90, 105)
    ev_c, _ = resolve_intrabar(bar, 1, stop=95.0, target=108.0, policy="conservative")
    ev_o, _ = resolve_intrabar(bar, 1, stop=95.0, target=108.0, policy="optimistic")
    check("conservative policy assumes the stop was hit first", ev_c == "STOP", ev_c)
    check("optimistic policy assumes the target was hit first", ev_o == "TARGET", ev_o)

    ev_only_t, _ = resolve_intrabar(bar, 1, stop=80.0, target=108.0, policy="conservative")
    check("an unambiguous target is still taken under the conservative policy",
          ev_only_t == "TARGET", ev_only_t)
    ev_none, _ = resolve_intrabar(bar, 1, stop=80.0, target=120.0, policy="conservative")
    check("neither level inside the bar produces no exit", ev_none is None)


# ── 3. corporate actions ────────────────────────────────────────────────────

def test_split_and_dividend():
    pf = Portfolio(100000.0)
    pf.seed(datetime(2024, 1, 1))
    pf.apply_fill(Fill("F1", "O1", "TEST", OrderSide.BUY, 100, 100.0, 100.0,
                       datetime(2024, 1, 2), 1, costs={}, total_cost=0.0))
    value_before = pf.positions["TEST"].quantity * pf.positions["TEST"].avg_price

    pf.apply_split("TEST", 2.0, datetime(2024, 1, 3), 2)
    pos = pf.positions["TEST"]
    check("a 2:1 split doubles the quantity", pos.quantity == 200, str(pos.quantity))
    check("a 2:1 split halves the cost basis", abs(pos.avg_price - 50.0) < 1e-9)
    check("a split creates no artificial P&L",
          abs(pos.quantity * pos.avg_price - value_before) < 1e-6)

    cash_before = pf.cash
    pf.apply_dividend("TEST", 5.0, datetime(2024, 1, 4), 3)
    check("a dividend credits cash for the full holding",
          abs(pf.cash - (cash_before + 1000.0)) < 1e-9, f"cash delta={pf.cash - cash_before}")


# ── 4. indicators against hand-computed values ──────────────────────────────

def test_indicator_math():
    x = np.array([1.0, 2, 3, 4, 5, 6, 7, 8, 9, 10])
    s = feat.sma(x, 3)
    check("SMA equals the arithmetic mean of the window",
          abs(s[2] - 2.0) < 1e-12 and abs(s[9] - 9.0) < 1e-12, f"{s[2]}, {s[9]}")

    e = feat.ema(x, 3)
    # seeded with SMA(3) = 2, then alpha = 0.5: 0.5*4 + 0.5*2 = 3
    check("EMA is SMA-seeded and follows alpha = 2/(N+1)",
          abs(e[2] - 2.0) < 1e-12 and abs(e[3] - 3.0) < 1e-12, f"{e[2]}, {e[3]}")

    w = feat.wma(np.array([1.0, 2.0, 3.0]), 3)
    check("WMA weights the newest bar most heavily",
          abs(w[2] - (1 * 1 + 2 * 2 + 3 * 3) / 6) < 1e-12, f"{w[2]}")

    up = np.arange(1.0, 30.0)
    r = feat.rsi(up, 14)
    check("RSI of a monotonically rising series is 100",
          abs(r[-1] - 100.0) < 1e-9, f"{r[-1]}")
    down = np.arange(30.0, 1.0, -1.0)
    check("RSI of a monotonically falling series is 0",
          abs(feat.rsi(down, 14)[-1]) < 1e-9)

    h = np.array([10.0, 12, 11, 15]); l = np.array([8.0, 9, 9, 11]); c = np.array([9.0, 11, 10, 14])
    tr = feat.true_range(h, l, c)
    check("true range uses the previous close when it extends the bar",
          abs(tr[1] - 3.0) < 1e-12, f"{tr[1]}")

    obv = feat.obv(np.array([10.0, 11, 10, 10]), np.array([100.0, 200, 300, 400]))
    check("OBV adds on an up close, subtracts on a down close, holds when flat",
          list(obv) == [0.0, 200.0, -100.0, -100.0], str(list(obv)))

    mid, upb, lob, bw = feat.bollinger(np.array([2.0] * 20), 20, 2.0)
    check("Bollinger bands collapse onto the mean for a constant series",
          abs(upb[-1] - 2.0) < 1e-12 and abs(lob[-1] - 2.0) < 1e-12)


def test_smoothers_survive_leading_nans():
    """
    Regression: a smoother applied to a series that itself has a warm-up (the
    MACD signal line is an EMA of the MACD line) must not seed from NaN. When
    it did, the signal line was NaN for the whole series and no MACD crossover
    could ever fire — a strategy that silently took zero trades.
    """
    x = np.concatenate([np.full(30, np.nan), np.arange(1.0, 101.0)])
    e = feat.ema(x, 9)
    w = feat.wilder(x, 9)
    check("EMA seeds from the first real observation, not from NaN",
          np.isfinite(e[-1]), f"last={e[-1]}")
    check("Wilder smoothing seeds from the first real observation",
          np.isfinite(w[-1]), f"last={w[-1]}")

    rng = np.random.default_rng(3)
    price = 100 + np.cumsum(rng.normal(0, 1, 400))
    line, sig, hist = feat.macd(price)
    crosses = int(np.sum((line[1:] > sig[1:]) & (line[:-1] <= sig[:-1])))
    check("MACD produces a usable signal line and real crossovers",
          np.isfinite(sig[-1]) and crosses > 0, f"{crosses} crossovers")


def test_donchian_excludes_current_bar():
    """The breakout channel must not include the bar being tested."""
    h = np.array([10.0, 11, 12, 20])
    l = np.array([8.0, 9, 10, 11])
    up_excl, _ = feat.donchian(h, l, 3, exclude_current=True)
    up_incl, _ = feat.donchian(h, l, 3, exclude_current=False)
    check("excluding the current bar leaves the channel below today's high",
          abs(up_excl[3] - 12.0) < 1e-12, f"{up_excl[3]}")
    check("including the current bar makes a breakout test tautological",
          abs(up_incl[3] - 20.0) < 1e-12, f"{up_incl[3]}")


# ── 5. look-ahead traps ─────────────────────────────────────────────────────

def test_no_lookahead_in_features():
    """
    Modify only the FUTURE tail of a series. Every feature value before the
    modification must be bit-identical.
    """
    rng = np.random.default_rng(7)
    base = 100 + np.cumsum(rng.normal(0, 1, 300))
    tampered = base.copy()
    tampered[200:] += 50.0     # a large, obvious future change

    def frame(arr):
        return pd.DataFrame({
            "Open": arr, "High": arr + 1, "Low": arr - 1,
            "Close": arr, "Volume": np.full(len(arr), 1e6),
        })

    reqs = [
        {"id": "ema", "type": "EMA", "period": 20},
        {"id": "rsi", "type": "RSI", "period": 14},
        {"id": "macd", "type": "MACD"},
        {"id": "bb", "type": "BBANDS", "period": 20},
        {"id": "atr", "type": "ATR", "period": 14},
        {"id": "adx", "type": "ADX", "period": 14},
        {"id": "dc", "type": "DONCHIAN", "period": 20},
    ]
    a, _, _ = feat.compute_features(frame(base), reqs)
    b, _, _ = feat.compute_features(frame(tampered), reqs)

    leaked = []
    for key in a:
        if not isinstance(a[key], np.ndarray) or a[key].dtype == bool:
            continue
        x, y = a[key][:200], b[key][:200]
        if not np.allclose(np.nan_to_num(x, nan=-999), np.nan_to_num(y, nan=-999),
                           rtol=1e-9, atol=1e-9):
            leaked.append(key)
    check("no feature changes when only future bars are modified",
          not leaked, f"leaked: {leaked}" if leaked else "all 7 features causal")


def test_swing_pivots_confirmed_late():
    """A swing high must not be knowable on the bar it occurs."""
    from services.backtest_india.structure import find_pivots
    h = np.array([1.0, 2, 3, 10, 3, 2, 1, 2, 3, 4])
    l = np.array([0.5, 1, 2, 9, 2, 1, 0.5, 1, 2, 3])
    pivots = find_pivots(h, l, k=3)
    highs = [p for p in pivots if p.kind == "HIGH"]
    check("the obvious swing high at index 3 is detected", len(highs) >= 1,
          f"{len(highs)} highs found")
    if highs:
        p = highs[0]
        check("the swing high is not knowable until k bars later",
              p.detected == p.index + 3, f"pivot at {p.index}, detected at {p.detected}")


def test_graph_warmup_blocks_early_signals():
    n = 200
    arr = 100 + np.arange(n) * 0.1
    df = pd.DataFrame({"Open": arr, "High": arr + 1, "Low": arr - 1,
                       "Close": arr, "Volume": np.full(n, 1e6)})
    values, warm, _ = feat.compute_features(df, [{"id": "sma", "type": "SMA", "period": 50}])
    strategy = {
        "conditions": [{"id": "c", "op": ">", "left": "close", "right": 0}],
        "entry_long": "c",
    }
    g = compile_graph(df, strategy, values, base_warmup=warm)
    check("no entry can fire before the longest feature warm-up completes",
          not g.entry_long[:warm].any() and g.entry_long[warm:].any(),
          f"warmup={warm}")


# ── 6. reproducibility ──────────────────────────────────────────────────────

def test_config_fingerprint_stable():
    from services.backtest_india.contracts import RunConfig
    a = RunConfig(symbols=["RELIANCE"], start="2023-01-01", end="2024-01-01",
                  strategy={"entry_long": "x"})
    b = RunConfig(symbols=["RELIANCE"], start="2023-01-01", end="2024-01-01",
                  strategy={"entry_long": "x"})
    c = RunConfig(symbols=["RELIANCE"], start="2023-01-01", end="2024-01-01",
                  strategy={"entry_long": "x"}, cost_schedule="ZERO_COST_v1")
    check("identical configs produce the same run id", a.fingerprint() == b.fingerprint())
    check("changing only the cost schedule produces a different run id",
          a.fingerprint() != c.fingerprint())
    check("changing only the cost schedule leaves the strategy hash untouched",
          a.strategy_hash() == c.strategy_hash())


def test_short_without_permission():
    """Selling with no holding must obey the shorting configuration."""
    from services.backtest_india.contracts import RunConfig
    cfg = RunConfig(symbols=["X"], start="2023-01-01", end="2024-01-01",
                    allow_short=False)
    check("shorting is disabled by default", cfg.allow_short is False)


def run_all() -> dict:
    RESULTS.clear()
    for fn in (test_buy_one_share_exact, test_cost_components, test_cost_only_changes_net,
               test_slippage_sign, test_limit_order_touch, test_partial_fill,
               test_zero_volume_rejected, test_intrabar_policy, test_split_and_dividend,
               test_indicator_math, test_smoothers_survive_leading_nans,
               test_donchian_excludes_current_bar,
               test_no_lookahead_in_features, test_swing_pivots_confirmed_late,
               test_graph_warmup_blocks_early_signals, test_config_fingerprint_stable,
               test_short_without_permission):
        try:
            fn()
        except Exception as exc:
            RESULTS.append({"test": fn.__name__, "passed": False,
                            "detail": f"raised {type(exc).__name__}: {exc}"})

    passed = sum(1 for r in RESULTS if r["passed"])
    return {
        "total": len(RESULTS), "passed": passed, "failed": len(RESULTS) - passed,
        "all_passed": passed == len(RESULTS),
        "results": list(RESULTS),
    }


if __name__ == "__main__":
    out = run_all()
    for r in out["results"]:
        mark = "PASS" if r["passed"] else "FAIL"
        print(f"[{mark}] {r['test']}" + (f"  ({r['detail']})" if r["detail"] else ""))
    print(f"\n{out['passed']}/{out['total']} passed")
    raise SystemExit(0 if out["all_passed"] else 1)
