"""Synthetic market factors: multivariate Student-t (nu=4) innovations with GARCH(1,1) per factor (alpha=0.08, beta=0.90), block correlations.
Orders of magnitude are public ones, presented as such and not as a calibration. The true conditional law is kept (sigma_t, nu) for the benchmark."""
from datetime import date

import numpy as np
import pandas as pd

from riskreport import calendar as cal

EQ = [f"EQ{i}" for i in range(1, 9)]
OPT_UND = EQ[:4]
IV = [f"IV_{u}" for u in OPT_UND]
FX = ["EURUSD", "EURGBP", "EURJPY"]
YLD = ["DE2Y", "DE5Y", "DE10Y", "FR10Y", "IT10Y"]
FACTORS = EQ + ["IDX"] + FX + YLD + IV
KIND = {**{f: "logret" for f in EQ + ["IDX"] + FX}, **{f: "bp" for f in YLD}, **{f: "volpt" for f in IV}}
NU, ALPHA, BETA = 4, 0.08, 0.90

EQ_VOL = np.array([0.18, 0.22, 0.25, 0.28, 0.30, 0.33, 0.36, 0.38])
START = {**dict(zip(EQ, [42, 68, 95, 120, 150, 185, 60, 210], strict=True)), "IDX": 4500.0, "EURUSD": 1.08, "EURGBP": 0.86, "EURJPY": 162.0,
         "DE2Y": 2.3, "DE5Y": 2.5, "DE10Y": 2.7, "FR10Y": 3.2, "IT10Y": 3.7, **dict(zip(IV, EQ_VOL[:4], strict=True))}
# unconditional daily vol of the increment, in the native unit of KIND
SIG = np.concatenate([EQ_VOL / np.sqrt(252), [0.16 / np.sqrt(252)], [0.07, 0.06, 0.09] / np.sqrt(252), [4.5, 4.5, 4.5, 4.5, 5.5], [0.010] * 4])


def correlation():
    n = len(FACTORS)
    i = {f: k for k, f in enumerate(FACTORS)}
    C = np.eye(n)

    def put(a, b, r):
        C[i[a], i[b]] = C[i[b], i[a]] = r
    for a in EQ:
        for b in EQ:
            if a < b:
                put(a, b, 0.45)
        put(a, "IDX", 0.75)
    for a in FX:
        for b in FX:
            if a < b:
                put(a, b, 0.35)
        for e in EQ + ["IDX"]:
            put(a, e, 0.10)
    for a in YLD:
        for b in YLD:
            if a < b:
                put(a, b, 0.80 if a[:2] == b[:2] else 0.70)
        for e in EQ + ["IDX"]:
            put(a, e, 0.15)
    for a in IV:
        for b in IV:
            if a < b:
                put(a, b, 0.50)
        for e in EQ + ["IDX"]:
            put(a, e, -0.45)
        put(a, a[3:], -0.70)
        for y in YLD:
            put(a, y, -0.05)
    w, V = np.linalg.eigh(C)
    C = (V * np.clip(w, 1e-4, None)) @ V.T  # nearest PSD
    d = np.sqrt(np.diag(C))
    return C / np.outer(d, d)


def simulate(seed=42, n_days=750, asof=date(2026, 10, 30), burn=250):
    """Returns (levels DataFrame indexed by TARGET2 date, true conditional daily sigma DataFrame of the increments)."""
    rng = np.random.default_rng(seed)
    n = len(FACTORS)
    L = np.linalg.cholesky(correlation())
    T = n_days + burn
    z = rng.standard_normal((T, n)) @ L.T
    z *= np.sqrt((NU - 2) / rng.chisquare(NU, size=(T, 1)))  # common chi2 -> multivariate t, unit variance
    w = SIG**2 * (1 - ALPHA - BETA)
    h = np.tile(SIG**2, (T, 1))
    inc = np.zeros((T, n))
    for t in range(T):
        if t:
            h[t] = w + ALPHA * inc[t - 1] ** 2 + BETA * h[t - 1]
        inc[t] = np.sqrt(h[t]) * z[t]
    inc, h = inc[burn:], h[burn:]
    lev = np.zeros((n_days, n))
    x = np.array([START[f] for f in FACTORS], float)
    for t in range(n_days):
        for k, f in enumerate(FACTORS):
            kd = KIND[f]
            if kd == "logret":
                x[k] *= np.exp(inc[t, k])
            elif kd == "bp":
                x[k] += inc[t, k] / 100 + 0.01 * (START[f] - x[k])  # mild mean reversion keeps yields in a plausible range
            else:
                x[k] = max(0.01, x[k] + inc[t, k] + 0.02 * (START[f] - x[k]))
        lev[t] = x
    idx = pd.to_datetime(cal.business_days(asof, n_days))
    return pd.DataFrame(lev, idx, FACTORS), pd.DataFrame(np.sqrt(h), idx, FACTORS)
