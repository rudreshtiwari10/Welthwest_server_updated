"""
Indicator / feature library (spec §7, §30, §31).

Every function here is written from the formula in the specification — nothing
is imported from `ta`, `talib` or the legacy engine. Each returns a numpy array
aligned 1:1 with the input frame, NaN during warm-up, and each is registered
with its declared warm-up length so the engine can refuse to trade before a
feature is mathematically defined.

Convention: functions take the *analysis* (adjusted) frame. They never see the
future — every value at index i depends only on rows <= i.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Callable, Optional

import numpy as np
import pandas as pd


# ── Primitive smoothers ─────────────────────────────────────────────────────

def sma(x: np.ndarray, n: int) -> np.ndarray:
    """SMA_N(t) = sum_{i=0}^{N-1} P_{t-i} / N."""
    return pd.Series(x).rolling(n, min_periods=n).mean().to_numpy()


def _first_valid(x: np.ndarray) -> int:
    """Index of the first non-NaN observation, or -1 if the series is empty of them.

    Recursive smoothers are frequently applied to a series that itself has a
    warm-up (the MACD signal line is an EMA of the MACD line). Seeding from
    index 0 in that case would seed from NaN and poison the entire output, so
    every smoother here starts at the first real observation.
    """
    valid = np.flatnonzero(~np.isnan(x))
    return int(valid[0]) if len(valid) else -1


def ema(x: np.ndarray, n: int) -> np.ndarray:
    """EMA_N(t) = a*P_t + (1-a)*EMA_{t-1}, a = 2/(N+1).

    Seeded with the SMA of the first N valid observations so the series is
    stable and reproducible rather than dependent on the first data point.
    """
    x = np.asarray(x, dtype=float)
    out = np.full(len(x), np.nan)
    start = _first_valid(x)
    if start < 0 or len(x) - start < n:
        return out
    alpha = 2.0 / (n + 1.0)
    seed_end = start + n
    prev = float(np.nanmean(x[start:seed_end]))
    out[seed_end - 1] = prev
    for i in range(seed_end, len(x)):
        if np.isnan(x[i]):
            out[i] = prev
            continue
        prev = alpha * x[i] + (1 - alpha) * prev
        out[i] = prev
    return out


def wilder(x: np.ndarray, n: int) -> np.ndarray:
    """Wilder's smoothing: EMA with alpha = 1/N. Canonical for RSI/ATR/ADX."""
    x = np.asarray(x, dtype=float)
    out = np.full(len(x), np.nan)
    start = _first_valid(x)
    if start < 0 or len(x) - start < n:
        return out
    seed_end = start + n
    prev = float(np.nanmean(x[start:seed_end]))
    out[seed_end - 1] = prev
    for i in range(seed_end, len(x)):
        v = 0.0 if np.isnan(x[i]) else x[i]
        prev = prev + (v - prev) / n
        out[i] = prev
    return out


def wma(x: np.ndarray, n: int) -> np.ndarray:
    """WMA_N = sum(w_i * P_i) / sum(w_i), w_i = N-i (most recent weighted N)."""
    x = np.asarray(x, dtype=float)
    w = np.arange(n, 0, -1, dtype=float)[::-1]   # oldest .. newest ascending
    denom = w.sum()
    out = np.full(len(x), np.nan)
    for i in range(n - 1, len(x)):
        out[i] = float(np.dot(x[i - n + 1: i + 1], w) / denom)
    return out


def dema(x: np.ndarray, n: int) -> np.ndarray:
    """DEMA = 2*EMA(P) - EMA(EMA(P))."""
    e1 = ema(x, n)
    return 2 * e1 - ema(e1, n)


def tema(x: np.ndarray, n: int) -> np.ndarray:
    """TEMA = 3*EMA - 3*EMA(EMA) + EMA(EMA(EMA))."""
    e1 = ema(x, n)
    e2 = ema(e1, n)
    e3 = ema(e2, n)
    return 3 * e1 - 3 * e2 + e3


def hma(x: np.ndarray, n: int) -> np.ndarray:
    """Hull MA = WMA(2*WMA(n/2) - WMA(n), sqrt(n))."""
    half = max(1, int(n / 2))
    root = max(1, int(np.sqrt(n)))
    return wma(2 * wma(x, half) - wma(x, n), root)


# ── True range family ───────────────────────────────────────────────────────

def true_range(h: np.ndarray, l: np.ndarray, c: np.ndarray) -> np.ndarray:
    """TR = max(H-L, |H-C_prev|, |L-C_prev|)."""
    prev = np.roll(c, 1)
    prev[0] = c[0]
    return np.maximum.reduce([h - l, np.abs(h - prev), np.abs(l - prev)])


def atr(h, l, c, n: int = 14) -> np.ndarray:
    """ATR_N = WilderEMA(TR, N)."""
    return wilder(true_range(h, l, c), n)


def natr(h, l, c, n: int = 14) -> np.ndarray:
    """Normalised ATR = ATR / Close."""
    with np.errstate(divide="ignore", invalid="ignore"):
        return atr(h, l, c, n) / np.asarray(c, dtype=float)


# ── Trend ───────────────────────────────────────────────────────────────────

def macd(x: np.ndarray, fast: int = 12, slow: int = 26, signal: int = 9):
    """MACD = EMA_fast - EMA_slow; Signal = EMA(MACD); Hist = MACD - Signal."""
    line = ema(x, fast) - ema(x, slow)
    sig = ema(line, signal)
    return line, sig, line - sig


def adx(h, l, c, n: int = 14):
    """
    Wilder ADX. +DM = max(H-H_prev,0) when up-move dominates, else 0; -DM
    mirrored. +DI = 100*Wilder(+DM)/ATR; DX = 100*|+DI - -DI|/(+DI + -DI);
    ADX = Wilder(DX).
    """
    h = np.asarray(h, float); l = np.asarray(l, float); c = np.asarray(c, float)
    up = np.diff(h, prepend=h[0])
    dn = -np.diff(l, prepend=l[0])
    plus_dm = np.where((up > dn) & (up > 0), up, 0.0)
    minus_dm = np.where((dn > up) & (dn > 0), dn, 0.0)
    atr_n = atr(h, l, c, n)
    with np.errstate(divide="ignore", invalid="ignore"):
        pdi = 100.0 * wilder(plus_dm, n) / atr_n
        mdi = 100.0 * wilder(minus_dm, n) / atr_n
        dx = 100.0 * np.abs(pdi - mdi) / (pdi + mdi)
    return wilder(dx, n), pdi, mdi


def supertrend(h, l, c, n: int = 10, mult: float = 3.0):
    """Supertrend line and direction (+1 up-trend, -1 down-trend)."""
    h = np.asarray(h, float); l = np.asarray(l, float); c = np.asarray(c, float)
    a = atr(h, l, c, n)
    mid = (h + l) / 2.0
    upper, lower = mid + mult * a, mid - mult * a
    line = np.full(len(c), np.nan)
    direction = np.zeros(len(c))
    fu, fl = upper.copy(), lower.copy()
    for i in range(1, len(c)):
        if np.isnan(a[i]):
            continue
        fu[i] = min(upper[i], fu[i - 1]) if c[i - 1] <= fu[i - 1] else upper[i]
        fl[i] = max(lower[i], fl[i - 1]) if c[i - 1] >= fl[i - 1] else lower[i]
        if c[i] > fu[i - 1]:
            direction[i] = 1
        elif c[i] < fl[i - 1]:
            direction[i] = -1
        else:
            direction[i] = direction[i - 1] or 1
        line[i] = fl[i] if direction[i] == 1 else fu[i]
    return line, direction


def ichimoku(h, l, c, tenkan: int = 9, kijun: int = 26, senkou_b: int = 52):
    """Tenkan/Kijun/SenkouA/SenkouB. Senkou spans are shifted FORWARD (+kijun),
    which is safe — they describe future plot positions from past data."""
    hs, ls = pd.Series(h), pd.Series(l)
    tk = ((hs.rolling(tenkan).max() + ls.rolling(tenkan).min()) / 2).to_numpy()
    kj = ((hs.rolling(kijun).max() + ls.rolling(kijun).min()) / 2).to_numpy()
    sa = pd.Series((tk + kj) / 2).shift(kijun).to_numpy()
    sb = pd.Series(((hs.rolling(senkou_b).max() + ls.rolling(senkou_b).min()) / 2)).shift(kijun).to_numpy()
    return tk, kj, sa, sb


def aroon(h, l, n: int = 25):
    """Aroon Up/Down: 100*(N - bars since N-period extreme)/N."""
    hs, ls = pd.Series(h), pd.Series(l)
    up = hs.rolling(n + 1).apply(lambda w: 100.0 * (n - (len(w) - 1 - int(np.argmax(w)))) / n, raw=True)
    dn = ls.rolling(n + 1).apply(lambda w: 100.0 * (n - (len(w) - 1 - int(np.argmin(w)))) / n, raw=True)
    return up.to_numpy(), dn.to_numpy()


# ── Momentum / oscillators ──────────────────────────────────────────────────

def rsi(x: np.ndarray, n: int = 14) -> np.ndarray:
    """RSI = 100 - 100/(1+RS), RS = Wilder(AvgGain)/Wilder(AvgLoss)."""
    x = np.asarray(x, float)
    d = np.diff(x, prepend=x[0])
    gain = wilder(np.where(d > 0, d, 0.0), n)
    loss = wilder(np.where(d < 0, -d, 0.0), n)
    out = np.full(len(x), np.nan)
    valid = ~np.isnan(gain) & ~np.isnan(loss)
    rs = np.divide(gain, loss, out=np.full(len(x), np.inf), where=(loss > 0) & valid)
    out[valid] = 100.0 - 100.0 / (1.0 + rs[valid])
    out[valid & (loss <= 0)] = 100.0
    return out


def stochastic(h, l, c, k: int = 14, d: int = 3, smooth: int = 3):
    """%K = 100*(C-LL_N)/(HH_N-LL_N) smoothed; %D = SMA(%K, d)."""
    hh = pd.Series(h).rolling(k).max().to_numpy()
    ll = pd.Series(l).rolling(k).min().to_numpy()
    rng = hh - ll
    with np.errstate(divide="ignore", invalid="ignore"):
        raw_k = 100.0 * (np.asarray(c, float) - ll) / rng
    raw_k = np.where(rng == 0, 50.0, raw_k)
    k_line = sma(raw_k, smooth) if smooth > 1 else raw_k
    return k_line, sma(k_line, d)


def williams_r(h, l, c, n: int = 14) -> np.ndarray:
    """%R = -100*(HH_N - C)/(HH_N - LL_N)."""
    hh = pd.Series(h).rolling(n).max().to_numpy()
    ll = pd.Series(l).rolling(n).min().to_numpy()
    rng = hh - ll
    with np.errstate(divide="ignore", invalid="ignore"):
        out = -100.0 * (hh - np.asarray(c, float)) / rng
    return np.where(rng == 0, -50.0, out)


def roc(x: np.ndarray, n: int = 12) -> np.ndarray:
    """ROC_N = 100*(C/C_{t-N} - 1)."""
    s = pd.Series(x)
    return (100.0 * (s / s.shift(n) - 1.0)).to_numpy()


def cci(h, l, c, n: int = 20) -> np.ndarray:
    """CCI = (TP - SMA(TP,N)) / (0.015 * MeanDeviation_N), TP = (H+L+C)/3."""
    tp = (np.asarray(h, float) + np.asarray(l, float) + np.asarray(c, float)) / 3.0
    ma = sma(tp, n)
    md = pd.Series(tp).rolling(n).apply(lambda w: np.mean(np.abs(w - w.mean())), raw=True).to_numpy()
    with np.errstate(divide="ignore", invalid="ignore"):
        return (tp - ma) / (0.015 * md)


def awesome_oscillator(h, l) -> np.ndarray:
    """AO = SMA5(median price) - SMA34(median price)."""
    mp = (np.asarray(h, float) + np.asarray(l, float)) / 2.0
    return sma(mp, 5) - sma(mp, 34)


def trix(x: np.ndarray, n: int = 15) -> np.ndarray:
    """TRIX = 100 * rate-of-change of a triple-smoothed EMA (1-bar ROC)."""
    e3 = ema(ema(ema(x, n), n), n)
    s = pd.Series(e3)
    return (100.0 * (s / s.shift(1) - 1.0)).to_numpy()


# ── Volatility ──────────────────────────────────────────────────────────────

def bollinger(x: np.ndarray, n: int = 20, k: float = 2.0):
    """middle = SMA_N; upper/lower = middle +/- k*sigma_N; bandwidth normalised."""
    mid = sma(x, n)
    sd = pd.Series(x).rolling(n, min_periods=n).std(ddof=0).to_numpy()
    up, lo = mid + k * sd, mid - k * sd
    with np.errstate(divide="ignore", invalid="ignore"):
        bw = (up - lo) / mid
    return mid, up, lo, bw


def keltner(h, l, c, n: int = 20, mult: float = 2.0):
    """Keltner channel: EMA(close) +/- mult * ATR."""
    mid = ema(np.asarray(c, float), n)
    a = atr(h, l, c, n)
    return mid, mid + mult * a, mid - mult * a


def donchian(h, l, n: int = 20, exclude_current: bool = True):
    """
    Donchian upper = HH_N, lower = LL_N.

    exclude_current=True shifts the window back one bar so a breakout trigger
    compares today's close against a channel that did NOT include today's own
    high — the spec's default and the difference between a real breakout test
    and a tautology.
    """
    hs, ls = pd.Series(h), pd.Series(l)
    if exclude_current:
        hs, ls = hs.shift(1), ls.shift(1)
    return hs.rolling(n).max().to_numpy(), ls.rolling(n).min().to_numpy()


def historical_volatility(c: np.ndarray, n: int = 20, periods_per_year: int = 252):
    """Annualised std of log returns over N bars."""
    lr = np.diff(np.log(np.asarray(c, float)), prepend=np.log(c[0]))
    return pd.Series(lr).rolling(n).std(ddof=1).to_numpy() * np.sqrt(periods_per_year)


# ── Volume / flow ───────────────────────────────────────────────────────────

def obv(c: np.ndarray, v: np.ndarray) -> np.ndarray:
    """OBV_t = OBV_{t-1} +V_t if C up, -V_t if C down, unchanged if equal."""
    c = np.asarray(c, float); v = np.asarray(v, float)
    d = np.sign(np.diff(c, prepend=c[0]))
    return np.cumsum(d * v)


def vwap(h, l, c, v, session_reset: Optional[np.ndarray] = None) -> np.ndarray:
    """
    VWAP = sum(TP*V)/sum(V). Price proxy is the typical price, stated
    explicitly per spec §7. `session_reset` is a boolean array marking the
    first bar of each session; without it the VWAP is cumulative.
    """
    tp = (np.asarray(h, float) + np.asarray(l, float) + np.asarray(c, float)) / 3.0
    v = np.asarray(v, float)
    if session_reset is None:
        cv = np.cumsum(v)
        with np.errstate(divide="ignore", invalid="ignore"):
            return np.cumsum(tp * v) / cv
    out = np.full(len(tp), np.nan)
    num = den = 0.0
    for i in range(len(tp)):
        if session_reset[i]:
            num = den = 0.0
        num += tp[i] * v[i]
        den += v[i]
        out[i] = num / den if den > 0 else np.nan
    return out


def cmf(h, l, c, v, n: int = 20) -> np.ndarray:
    """MFM = ((C-L)-(H-C))/(H-L); CMF_N = sum(MFM*V)/sum(V)."""
    h = np.asarray(h, float); l = np.asarray(l, float)
    c = np.asarray(c, float); v = np.asarray(v, float)
    rng = h - l
    with np.errstate(divide="ignore", invalid="ignore"):
        mfm = ((c - l) - (h - c)) / rng
    mfm = np.where(rng == 0, 0.0, mfm)
    num = pd.Series(mfm * v).rolling(n).sum().to_numpy()
    den = pd.Series(v).rolling(n).sum().to_numpy()
    with np.errstate(divide="ignore", invalid="ignore"):
        return num / den


def mfi(h, l, c, v, n: int = 14) -> np.ndarray:
    """Money Flow Index — RSI-style ratio of positive to negative money flow."""
    tp = (np.asarray(h, float) + np.asarray(l, float) + np.asarray(c, float)) / 3.0
    raw = tp * np.asarray(v, float)
    d = np.diff(tp, prepend=tp[0])
    pos = pd.Series(np.where(d > 0, raw, 0.0)).rolling(n).sum().to_numpy()
    neg = pd.Series(np.where(d < 0, raw, 0.0)).rolling(n).sum().to_numpy()
    with np.errstate(divide="ignore", invalid="ignore"):
        ratio = pos / neg
    out = 100.0 - 100.0 / (1.0 + ratio)
    return np.where(neg == 0, 100.0, out)


def volume_zscore(v: np.ndarray, n: int = 20) -> np.ndarray:
    """(V - mean_N(V)) / std_N(V)."""
    s = pd.Series(np.asarray(v, float))
    m = s.rolling(n).mean()
    sd = s.rolling(n).std(ddof=0)
    return ((s - m) / sd.replace(0, np.nan)).to_numpy()


# ── Statistical / structural features ───────────────────────────────────────

def linreg_slope(x: np.ndarray, n: int = 20):
    """beta = sum((i-ibar)(y-ybar)) / sum((i-ibar)^2), plus R^2 = 1 - SSE/SST."""
    y = np.asarray(x, float)
    idx = np.arange(n, dtype=float)
    ix = idx - idx.mean()
    denom = float((ix ** 2).sum())
    slope = np.full(len(y), np.nan)
    r2 = np.full(len(y), np.nan)
    for i in range(n - 1, len(y)):
        w = y[i - n + 1: i + 1]
        if np.isnan(w).any():
            continue
        wy = w - w.mean()
        b = float((ix * wy).sum() / denom)
        pred = b * ix
        sse = float(((wy - pred) ** 2).sum())
        sst = float((wy ** 2).sum())
        slope[i] = b
        r2[i] = 1.0 - sse / sst if sst > 0 else np.nan
    return slope, r2


def zscore(x: np.ndarray, n: int = 20) -> np.ndarray:
    """Time-series z-score: (x_t - mean_N)/std_N."""
    s = pd.Series(np.asarray(x, float))
    return ((s - s.rolling(n).mean()) / s.rolling(n).std(ddof=0).replace(0, np.nan)).to_numpy()


def rolling_percentile(x: np.ndarray, n: int = 100) -> np.ndarray:
    """Empirical percentile (0-100) of x_t within the previous N observations."""
    s = pd.Series(np.asarray(x, float))
    return s.rolling(n).apply(
        lambda w: 100.0 * float((w[:-1] <= w[-1]).sum()) / max(1, len(w) - 1), raw=True
    ).to_numpy()


def highest(x: np.ndarray, n: int, exclude_current: bool = True) -> np.ndarray:
    s = pd.Series(np.asarray(x, float))
    if exclude_current:
        s = s.shift(1)
    return s.rolling(n).max().to_numpy()


def lowest(x: np.ndarray, n: int, exclude_current: bool = True) -> np.ndarray:
    s = pd.Series(np.asarray(x, float))
    if exclude_current:
        s = s.shift(1)
    return s.rolling(n).min().to_numpy()


def rolling_beta(r: np.ndarray, rb: np.ndarray, n: int = 60):
    """Rolling beta and correlation vs a benchmark return series."""
    a, b = pd.Series(r), pd.Series(rb)
    cov = a.rolling(n).cov(b)
    var = b.rolling(n).var(ddof=1)
    corr = a.rolling(n).corr(b)
    return (cov / var.replace(0, np.nan)).to_numpy(), corr.to_numpy()


# ── Registry ────────────────────────────────────────────────────────────────

@dataclass
class FeatureSpec:
    """Everything the UI and the engine need to know about one feature."""
    key: str
    label: str
    category: str
    params: dict                # name -> default
    outputs: list               # output series names
    warmup: Callable            # params -> int
    description: str
    fn: Callable                # (frame, **params) -> dict[name, ndarray]


def _c(df): return df["Close"].to_numpy(dtype=float)
def _h(df): return df["High"].to_numpy(dtype=float)
def _l(df): return df["Low"].to_numpy(dtype=float)
def _o(df): return df["Open"].to_numpy(dtype=float)
def _v(df): return df["Volume"].to_numpy(dtype=float)


def _src(df, source: str):
    m = {"close": _c, "open": _o, "high": _h, "low": _l}
    if source == "hl2":
        return (_h(df) + _l(df)) / 2
    if source in ("typical", "hlc3"):
        return (_h(df) + _l(df) + _c(df)) / 3
    return m.get(source, _c)(df)


FEATURES: dict[str, FeatureSpec] = {}


def _reg(spec: FeatureSpec):
    FEATURES[spec.key] = spec
    return spec


_reg(FeatureSpec("SMA", "Simple Moving Average", "trend",
                 {"period": 20, "source": "close"}, ["value"],
                 lambda p: int(p["period"]),
                 "Arithmetic mean of the last N closes.",
                 lambda df, period=20, source="close": {"value": sma(_src(df, source), int(period))}))

_reg(FeatureSpec("EMA", "Exponential Moving Average", "trend",
                 {"period": 20, "source": "close"}, ["value"],
                 lambda p: int(p["period"]) * 2,
                 "Exponentially weighted mean, alpha = 2/(N+1), SMA-seeded.",
                 lambda df, period=20, source="close": {"value": ema(_src(df, source), int(period))}))

_reg(FeatureSpec("WMA", "Weighted Moving Average", "trend",
                 {"period": 20, "source": "close"}, ["value"],
                 lambda p: int(p["period"]),
                 "Linearly weighted mean, weight N for the newest bar.",
                 lambda df, period=20, source="close": {"value": wma(_src(df, source), int(period))}))

_reg(FeatureSpec("DEMA", "Double EMA", "trend",
                 {"period": 20, "source": "close"}, ["value"],
                 lambda p: int(p["period"]) * 3,
                 "2*EMA - EMA(EMA); reduces EMA lag.",
                 lambda df, period=20, source="close": {"value": dema(_src(df, source), int(period))}))

_reg(FeatureSpec("TEMA", "Triple EMA", "trend",
                 {"period": 20, "source": "close"}, ["value"],
                 lambda p: int(p["period"]) * 4,
                 "3*EMA - 3*EMA(EMA) + EMA(EMA(EMA)).",
                 lambda df, period=20, source="close": {"value": tema(_src(df, source), int(period))}))

_reg(FeatureSpec("HMA", "Hull Moving Average", "trend",
                 {"period": 20, "source": "close"}, ["value"],
                 lambda p: int(p["period"]) * 2,
                 "WMA(2*WMA(n/2) - WMA(n), sqrt(n)).",
                 lambda df, period=20, source="close": {"value": hma(_src(df, source), int(period))}))

_reg(FeatureSpec("MACD", "MACD", "trend",
                 {"fast": 12, "slow": 26, "signal": 9}, ["macd", "signal", "hist"],
                 lambda p: int(p["slow"]) * 2 + int(p["signal"]),
                 "EMA(fast) - EMA(slow), with its own EMA signal line and histogram.",
                 lambda df, fast=12, slow=26, signal=9: dict(
                     zip(("macd", "signal", "hist"), macd(_c(df), int(fast), int(slow), int(signal))))))

_reg(FeatureSpec("ADX", "ADX / DMI", "trend",
                 {"period": 14}, ["adx", "plus_di", "minus_di"],
                 lambda p: int(p["period"]) * 3,
                 "Wilder trend-strength index with +DI/-DI directional components.",
                 lambda df, period=14: dict(
                     zip(("adx", "plus_di", "minus_di"), adx(_h(df), _l(df), _c(df), int(period))))))

_reg(FeatureSpec("SUPERTREND", "Supertrend", "trend",
                 {"period": 10, "multiplier": 3.0}, ["line", "direction"],
                 lambda p: int(p["period"]) * 3,
                 "ATR-banded trend line; direction flips on band breach.",
                 lambda df, period=10, multiplier=3.0: dict(
                     zip(("line", "direction"), supertrend(_h(df), _l(df), _c(df), int(period), float(multiplier))))))

_reg(FeatureSpec("ICHIMOKU", "Ichimoku", "trend",
                 {"tenkan": 9, "kijun": 26, "senkou_b": 52},
                 ["tenkan", "kijun", "senkou_a", "senkou_b"],
                 lambda p: int(p["senkou_b"]) + int(p["kijun"]),
                 "Tenkan/Kijun midpoints plus forward-shifted cloud spans.",
                 lambda df, tenkan=9, kijun=26, senkou_b=52: dict(
                     zip(("tenkan", "kijun", "senkou_a", "senkou_b"),
                         ichimoku(_h(df), _l(df), _c(df), int(tenkan), int(kijun), int(senkou_b))))))

_reg(FeatureSpec("AROON", "Aroon", "trend",
                 {"period": 25}, ["up", "down"],
                 lambda p: int(p["period"]) + 1,
                 "Bars elapsed since the N-period high/low, scaled 0-100.",
                 lambda df, period=25: dict(zip(("up", "down"), aroon(_h(df), _l(df), int(period))))))

_reg(FeatureSpec("RSI", "RSI (Wilder)", "momentum",
                 {"period": 14, "source": "close"}, ["value"],
                 lambda p: int(p["period"]) * 3,
                 "100 - 100/(1+RS) using Wilder-smoothed average gain/loss.",
                 lambda df, period=14, source="close": {"value": rsi(_src(df, source), int(period))}))

_reg(FeatureSpec("STOCH", "Stochastic", "momentum",
                 {"k_period": 14, "d_period": 3, "smooth": 3}, ["k", "d"],
                 lambda p: int(p["k_period"]) + int(p["d_period"]) + int(p["smooth"]),
                 "%K position of close within the N-bar range; %D its SMA.",
                 lambda df, k_period=14, d_period=3, smooth=3: dict(
                     zip(("k", "d"), stochastic(_h(df), _l(df), _c(df), int(k_period), int(d_period), int(smooth))))))

_reg(FeatureSpec("WILLR", "Williams %R", "momentum",
                 {"period": 14}, ["value"],
                 lambda p: int(p["period"]),
                 "-100 * (HH - C)/(HH - LL); mirrors Stochastic %K.",
                 lambda df, period=14: {"value": williams_r(_h(df), _l(df), _c(df), int(period))}))

_reg(FeatureSpec("ROC", "Rate of Change", "momentum",
                 {"period": 12, "source": "close"}, ["value"],
                 lambda p: int(p["period"]) + 1,
                 "Percentage change over N bars.",
                 lambda df, period=12, source="close": {"value": roc(_src(df, source), int(period))}))

_reg(FeatureSpec("CCI", "Commodity Channel Index", "momentum",
                 {"period": 20}, ["value"],
                 lambda p: int(p["period"]),
                 "Typical-price deviation scaled by mean absolute deviation.",
                 lambda df, period=20: {"value": cci(_h(df), _l(df), _c(df), int(period))}))

_reg(FeatureSpec("AO", "Awesome Oscillator", "momentum",
                 {}, ["value"], lambda p: 34,
                 "SMA5 minus SMA34 of the median price.",
                 lambda df: {"value": awesome_oscillator(_h(df), _l(df))}))

_reg(FeatureSpec("TRIX", "TRIX", "momentum",
                 {"period": 15}, ["value"],
                 lambda p: int(p["period"]) * 4,
                 "1-bar rate of change of a triple-smoothed EMA, in percent.",
                 lambda df, period=15: {"value": trix(_c(df), int(period))}))

_reg(FeatureSpec("ATR", "Average True Range", "volatility",
                 {"period": 14}, ["value", "normalized"],
                 lambda p: int(p["period"]) * 2,
                 "Wilder-smoothed true range, plus ATR/Close.",
                 lambda df, period=14: {"value": atr(_h(df), _l(df), _c(df), int(period)),
                                        "normalized": natr(_h(df), _l(df), _c(df), int(period))}))

_reg(FeatureSpec("BBANDS", "Bollinger Bands", "volatility",
                 {"period": 20, "k": 2.0, "source": "close"},
                 ["middle", "upper", "lower", "bandwidth"],
                 lambda p: int(p["period"]),
                 "SMA +/- k standard deviations, with normalised bandwidth.",
                 lambda df, period=20, k=2.0, source="close": dict(
                     zip(("middle", "upper", "lower", "bandwidth"),
                         bollinger(_src(df, source), int(period), float(k))))))

_reg(FeatureSpec("KELTNER", "Keltner Channel", "volatility",
                 {"period": 20, "multiplier": 2.0}, ["middle", "upper", "lower"],
                 lambda p: int(p["period"]) * 2,
                 "EMA centre line with ATR-scaled bands.",
                 lambda df, period=20, multiplier=2.0: dict(
                     zip(("middle", "upper", "lower"),
                         keltner(_h(df), _l(df), _c(df), int(period), float(multiplier))))))

_reg(FeatureSpec("DONCHIAN", "Donchian Channel", "volatility",
                 {"period": 20, "exclude_current": 1}, ["upper", "lower"],
                 lambda p: int(p["period"]) + 1,
                 "N-bar highest high / lowest low; excludes the current bar by "
                 "default so breakout tests are not self-referential.",
                 lambda df, period=20, exclude_current=1: dict(
                     zip(("upper", "lower"), donchian(_h(df), _l(df), int(period), bool(int(exclude_current)))))))

_reg(FeatureSpec("HVOL", "Historical Volatility", "volatility",
                 {"period": 20, "periods_per_year": 252}, ["value"],
                 lambda p: int(p["period"]) + 1,
                 "Annualised standard deviation of log returns.",
                 lambda df, period=20, periods_per_year=252: {
                     "value": historical_volatility(_c(df), int(period), int(periods_per_year))}))

_reg(FeatureSpec("OBV", "On-Balance Volume", "volume",
                 {}, ["value"], lambda p: 1,
                 "Running volume total signed by the close-to-close direction.",
                 lambda df: {"value": obv(_c(df), _v(df))}))

_reg(FeatureSpec("VWAP", "VWAP (cumulative)", "volume",
                 {}, ["value"], lambda p: 1,
                 "Typical-price volume-weighted average price over the window.",
                 lambda df: {"value": vwap(_h(df), _l(df), _c(df), _v(df))}))

_reg(FeatureSpec("CMF", "Chaikin Money Flow", "volume",
                 {"period": 20}, ["value"],
                 lambda p: int(p["period"]),
                 "Volume-weighted money-flow multiplier over N bars.",
                 lambda df, period=20: {"value": cmf(_h(df), _l(df), _c(df), _v(df), int(period))}))

_reg(FeatureSpec("MFI", "Money Flow Index", "volume",
                 {"period": 14}, ["value"],
                 lambda p: int(p["period"]) + 1,
                 "RSI-style ratio of positive to negative money flow.",
                 lambda df, period=14: {"value": mfi(_h(df), _l(df), _c(df), _v(df), int(period))}))

_reg(FeatureSpec("VOLZ", "Volume Z-Score", "volume",
                 {"period": 20}, ["value"],
                 lambda p: int(p["period"]),
                 "Standardised volume relative to its own N-bar history.",
                 lambda df, period=20: {"value": volume_zscore(_v(df), int(period))}))

_reg(FeatureSpec("LINREG", "Linear Regression Slope", "statistical",
                 {"period": 20, "source": "close"}, ["slope", "r2"],
                 lambda p: int(p["period"]),
                 "OLS slope over N bars and its R-squared fit quality.",
                 lambda df, period=20, source="close": dict(
                     zip(("slope", "r2"), linreg_slope(_src(df, source), int(period))))))

_reg(FeatureSpec("ZSCORE", "Z-Score", "statistical",
                 {"period": 20, "source": "close"}, ["value"],
                 lambda p: int(p["period"]),
                 "Time-series standardisation over a rolling window.",
                 lambda df, period=20, source="close": {"value": zscore(_src(df, source), int(period))}))

_reg(FeatureSpec("PCTRANK", "Rolling Percentile", "statistical",
                 {"period": 100, "source": "close"}, ["value"],
                 lambda p: int(p["period"]),
                 "Empirical percentile of the current value within N history.",
                 lambda df, period=100, source="close": {"value": rolling_percentile(_src(df, source), int(period))}))

_reg(FeatureSpec("HIGHEST", "Highest High", "statistical",
                 {"period": 20, "exclude_current": 1}, ["value"],
                 lambda p: int(p["period"]) + 1,
                 "Rolling maximum, current bar excluded by default.",
                 lambda df, period=20, exclude_current=1: {
                     "value": highest(_h(df), int(period), bool(int(exclude_current)))}))

_reg(FeatureSpec("LOWEST", "Lowest Low", "statistical",
                 {"period": 20, "exclude_current": 1}, ["value"],
                 lambda p: int(p["period"]) + 1,
                 "Rolling minimum, current bar excluded by default.",
                 lambda df, period=20, exclude_current=1: {
                     "value": lowest(_l(df), int(period), bool(int(exclude_current)))}))


# ── Computation driver ──────────────────────────────────────────────────────

def compute_features(df: pd.DataFrame, requests: list) -> tuple[dict, int, list]:
    """
    Compute every requested feature on the analysis frame.

    `requests` is a list of {"id", "type", **params}. Returns
    (values_by_ref, max_warmup, errors) where values_by_ref maps both "id" and
    "id.output" to arrays, so a graph can reference `macd1` (first output) or
    `macd1.signal` explicitly.
    """
    values: dict = {}
    warmups: list = [0]
    errors: list = []

    # raw price/volume series are always addressable
    values["close"] = _c(df); values["open"] = _o(df)
    values["high"] = _h(df); values["low"] = _l(df)
    values["volume"] = _v(df)
    values["hl2"] = (values["high"] + values["low"]) / 2
    values["typical"] = (values["high"] + values["low"] + values["close"]) / 3

    for req in requests or []:
        fid = req.get("id")
        ftype = str(req.get("type", "")).upper()
        spec = FEATURES.get(ftype)
        if not spec:
            errors.append(f"Unknown feature type '{ftype}' (id={fid})")
            continue
        params = {k: v for k, v in req.items() if k in spec.params}
        merged = {**spec.params, **params}
        try:
            out = spec.fn(df, **merged)
        except Exception as exc:
            errors.append(f"Feature '{fid}' ({ftype}) failed: {exc}")
            continue
        for name, arr in out.items():
            values[f"{fid}.{name}"] = arr
        # bare id resolves to the primary output
        primary = spec.outputs[0]
        values[fid] = out[primary]
        try:
            warmups.append(int(spec.warmup(merged)))
        except Exception:
            warmups.append(50)

    return values, max(warmups), errors


def catalogue() -> list:
    """Serialisable description of the whole library for the UI."""
    return [
        {
            "key": s.key, "label": s.label, "category": s.category,
            "params": s.params, "outputs": s.outputs,
            "description": s.description,
        }
        for s in sorted(FEATURES.values(), key=lambda x: (x.category, x.key))
    ]
