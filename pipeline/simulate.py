"""Monte Carlo simulation of seat distributions.

Mirrors the calibrated frontend model:
  * idiosyncratic per-party error  sigma_i = (1.5 + 0.10*p_i) * vol_mult_i
  * correlated national swing       sys ~ N(0, 1.6), scaled by p_i / max(p)
  * sub-3% "others" bucket absorbs the remainder and is re-normalised to 100.
The non-linear first-party bonus is what makes the mean seat count differ from
a single deterministic allocation, so we always report the simulated mean.
"""
import itertools
import numpy as np

from config import PARTIES, PKEYS, SEATS, MAJORITY, N_SIMS, THRESHOLD
from pipeline.electoral_law import allocate, first_party_bonus


def _round_to_sum(vals, target):
    floors = [int(v) for v in vals]
    acc = sum(floors)
    order = sorted(range(len(vals)), key=lambda i: vals[i] - floors[i], reverse=True)
    k = 0
    while acc < target:
        floors[order[k % len(order)]] += 1
        acc += 1
        k += 1
    return floors


def simulate(base_pct, vol_mult=None, n_sims=N_SIMS, seed=None):
    rng = np.random.default_rng(seed)
    n = len(base_pct)
    base = np.array(base_pct, dtype=float)
    others = max(0.0, 100.0 - base.sum())
    if vol_mult is None:
        vol_mult = [1.0] * n
    sigma = np.array([(1.5 + 0.10 * p) * vol_mult[i] for i, p in enumerate(base)])
    first_pct = max(base.max(), 1.0)

    seat_samples = np.zeros((n_sims, n), dtype=int)
    self_suff = 0
    first_seats = np.zeros(n_sims, dtype=int)

    for s in range(n_sims):
        sys = rng.normal(0, 1.6)
        draw = np.maximum(0, base + rng.normal(0, sigma) + sys * 0.6 * (base / first_pct))
        others_d = max(0.0, others + rng.normal(0, 1.2))
        total = draw.sum() + others_d
        if total > 0:
            draw = draw * 100.0 / total
        seats, fi, _ = allocate(draw.tolist())
        seat_samples[s] = seats
        first_seats[s] = seats[fi]
        if max(seats) >= MAJORITY:
            self_suff += 1

    mean_seats = seat_samples.mean(axis=0)
    rep = _round_to_sum(mean_seats.tolist(), SEATS)

    parties = []
    for i, p in enumerate(PARTIES):
        col = seat_samples[:, i]
        parties.append({
            "key": p["key"], "short": p["short"], "name": p["name"], "color": p["color"],
            "pct": round(float(base[i]), 1),
            "mean_seats": round(float(mean_seats[i]), 1),
            "rep_seats": int(rep[i]),
            "low90": int(np.percentile(col, 5)),
            "high90": int(np.percentile(col, 95)),
        })

    coalitions = _coalitions(seat_samples)

    return {
        "parties": parties,
        "self_sufficiency": round(self_suff / n_sims, 4),
        "first_seats_low90": int(np.percentile(first_seats, 5)),
        "first_seats_high90": int(np.percentile(first_seats, 95)),
        "parties_in_parliament": int(sum(1 for p in base if p >= THRESHOLD)),
        "coalitions": coalitions,
        "n_sims": n_sims,
    }


def _coalitions(seat_samples):
    n = seat_samples.shape[1]
    means = seat_samples.mean(axis=0)
    idxs = [i for i in range(n) if means[i] >= 0.5]
    combos = []
    for r in (2, 3):
        combos += list(itertools.combinations(idxs, r))
    evald = []
    for combo in combos:
        tot = seat_samples[:, list(combo)].sum(axis=1)
        mean = float(tot.mean())
        if mean < 120:
            continue
        evald.append({
            "members": [PKEYS[i] for i in combo],
            "labels": [PARTIES[i]["short"] for i in combo],
            "mean_seats": round(mean, 1),
            "p_majority": round(float((tot >= MAJORITY).mean()), 4),
        })
    evald.sort(key=lambda c: (-c["p_majority"], len(c["members"]), -c["mean_seats"]))
    return evald[:6]
