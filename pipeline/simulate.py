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

from config import (PARTIES, PKEYS, SEATS, MAJORITY, N_SIMS, THRESHOLD,
                    INCOMPATIBLE_PAIRS, KKE_SOLO)
from pipeline.electoral_law import allocate, first_party_bonus

_INC = {(a, b) for a, b in INCOMPATIBLE_PAIRS} | {(b, a) for a, b in INCOMPATIBLE_PAIRS}


def is_feasible(keys):
    """Πολιτική συμβατότητα ενός συνδυασμού κομμάτων."""
    if KKE_SOLO and "KKE" in keys and len(keys) > 1:
        return False
    for a, b in itertools.combinations(keys, 2):
        if (a, b) in _INC:
            return False
    return True


def banzhaf(seat_samples, feasible_only=True):
    """Δείκτης διαπραγματευτικής ισχύος Banzhaf, μέσος όρος στα σενάρια.

    Για κάθε σενάριο μετράμε σε πόσους (εφικτούς) συνασπισμούς κάθε κόμμα
    είναι «κρίσιμο»: η αποχώρησή του ρίχνει τον συνασπισμό κάτω από 151.
    Επιστρέφει κανονικοποιημένο δείκτη ανά κόμμα (άθροισμα 1).
    """
    n_sims, n = seat_samples.shape
    masks = np.array([[(c >> i) & 1 for i in range(n)]
                      for c in range(1, 2 ** n)], dtype=np.int8)   # (C, n)
    if feasible_only:
        ok = np.array([is_feasible([PKEYS[i] for i in range(n) if m[i]])
                       for m in masks], dtype=bool)
        masks = masks[ok]
    totals = seat_samples @ masks.T                                # (sims, C)
    wins = totals >= MAJORITY
    swings = np.zeros(n)
    for i in range(n):
        has_i = masks[:, i] == 1
        without = totals[:, has_i] - seat_samples[:, [i]]
        swings[i] = (wins[:, has_i] & (without < MAJORITY)).sum()
    s = swings.sum()
    return (swings / s).round(4).tolist() if s > 0 else [0.0] * n


def majority_math(base):
    """Κατώφλι αυτοδυναμίας δεδομένης της «χαμένης ψήφου».

    wasted = λοιπά (εκτός λίστας) + κόμματα της λίστας κάτω του 3%.
    E = 100 - wasted = άθροισμα εγκύρων που μοιράζονται έδρες.
    Λύνουμε αριθμητικά: bonus(nd) + (300 - bonus(nd)) * nd/E >= 151.
    """
    listed = sum(base)
    sub3 = sum(p for p in base if p < THRESHOLD)
    wasted = max(0.0, 100.0 - listed) + sub3
    E = max(1.0, 100.0 - wasted)
    needed = None
    nd = 20.0
    while nd <= E:
        b = first_party_bonus(nd)
        if b + (SEATS - b) * nd / E >= MAJORITY:
            needed = round(nd, 1)
            break
        nd += 0.1
    first = max(base)
    return {
        "wasted_share": round(wasted, 1),
        "majority_need_pct": needed,
        "majority_gap": round(needed - first, 1) if needed else None,
    }


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
        "banzhaf": {PKEYS[i]: v for i, v in enumerate(banzhaf(seat_samples))},
        "majority_math": majority_math(list(base)),
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
        keys = [PKEYS[i] for i in combo]
        evald.append({
            "members": keys,
            "labels": [PARTIES[i]["short"] for i in combo],
            "mean_seats": round(mean, 1),
            "p_majority": round(float((tot >= MAJORITY).mean()), 4),
            "feasible": is_feasible(keys),
        })
    # εφικτοί πρώτοι, μετά κατά πιθανότητα πλειοψηφίας / λιγότερα κόμματα
    evald.sort(key=lambda c: (not c["feasible"], -c["p_majority"],
                              len(c["members"]), -c["mean_seats"]))
    feasible = [c for c in evald if c["feasible"]][:6]
    infeasible = [c for c in evald if not c["feasible"]][:3]
    return feasible + infeasible
