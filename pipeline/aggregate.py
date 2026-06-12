"""Poll aggregation layer.

Weight of each poll = time_decay  ×  sqrt(sample / 1000)  ×  reliability
  * time_decay   : 0.5 ** (age_in_days / HALF_LIFE_DAYS)
  * reliability  : taken from the poll if provided, else inferred automatically
                   from the pollster's average deviation from the local
                   consensus (a "house effect" / accuracy proxy).

Also derives:
  * 30-day momentum (news-sentiment proxy from data)
  * per-party volatility multiplier feeding the simulation's sigma.
"""
from datetime import timedelta
import math
from pipeline.quality import _method_score

from config import PKEYS, HALF_LIFE_DAYS


def _time_weight(poll_date, ref_date, half_life):
    age = max(0.0, (ref_date - poll_date).total_seconds() / 86400.0)
    return 0.5 ** (age / half_life)


def compute_reliability(polls, half_life=HALF_LIFE_DAYS):
    """Lower reliability for pollsters that deviate more from local consensus."""
    house = {}
    for p in polls:
        wsum = 0.0
        agg = [0.0] * len(PKEYS)
        for q in polls:
            if q is p:
                continue
            w = (0.5 ** (abs((p["date"] - q["date"]).days) / half_life)) * math.sqrt((q["sample"] or 900) / 1000)
            wsum += w
            for i, v in enumerate(q["vals"]):
                agg[i] += v * w
        if wsum <= 0:
            continue
        agg = [v / wsum for v in agg]
        mad = sum(abs(v - agg[i]) for i, v in enumerate(p["vals"])) / len(PKEYS)
        house.setdefault(p["pollster"], []).append(mad)
    rel = {}
    for k, devs in house.items():
        m = sum(devs) / len(devs)
        rel[k] = max(0.4, 1.0 / (1.0 + 0.45 * m))
    return rel


def aggregate_at(polls, ref_date, rel_map, half_life=HALF_LIFE_DAYS):
    n = len(PKEYS)
    wsum = [0.0] * n          # ανά κόμμα: το 0 σε παλιά μέτρηση = «δεν μετρήθηκε»
    agg = [0.0] * n
    any_w = 0.0
    for p in polls:
        if p["date"] > ref_date:
            continue
        wr = p["reliability"] if p.get("reliability") is not None else rel_map.get(p["pollster"], 1.0)
        w = (_time_weight(p["date"], ref_date, half_life)
             * math.sqrt((p["sample"] or 900) / 1000) * wr
             * _method_score(p.get("method")))
        if w <= 0:
            continue
        any_w += w
        for i, v in enumerate(p["vals"]):
            if v > 0:
                agg[i] += v * w
                wsum[i] += w
    if any_w <= 0:
        return None
    return [(agg[i] / wsum[i] if wsum[i] > 0 else 0.0) for i in range(n)]


def compute_volatility(polls, ref_date, rel_map, half_life=HALF_LIFE_DAYS):
    agg = aggregate_at(polls, ref_date, rel_map, half_life)
    if agg is None:
        return None
    recent = [p for p in polls if (ref_date - p["date"]).days <= 60]
    out = []
    for i in range(len(PKEYS)):
        if len(recent) > 1:
            s2 = sum((p["vals"][i] - agg[i]) ** 2 for p in recent) / len(recent)
            sd = math.sqrt(s2)
        else:
            sd = 1.2
        out.append(max(0.7, min(2.2, sd / 1.2)))
    return out


def build_aggregate(polls, half_life=HALF_LIFE_DAYS):
    """Returns dict with base percentages, 30d momentum, volatility, reliability."""
    polls = sorted(polls, key=lambda p: p["date"])
    rel_map = compute_reliability(polls, half_life)
    ref = polls[-1]["date"]
    base = aggregate_at(polls, ref, rel_map, half_life)
    past = aggregate_at(polls, ref - timedelta(days=30), rel_map, half_life)
    momentum = [round(base[i] - past[i], 1) for i in range(len(PKEYS))] if past else [0.0] * len(PKEYS)
    vol = compute_volatility(polls, ref, rel_map, half_life)
    return {
        "reference_date": ref,
        "base_pct": [round(v, 1) for v in base],
        "momentum": momentum,
        "volatility": vol,
        "reliability": rel_map,
    }
