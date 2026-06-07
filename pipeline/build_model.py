"""Build the model: ingest -> aggregate -> fundamentals -> simulate -> write JSON.

Run manually:   python -m pipeline.build_model
Output:         api/latest.json   (the contract the frontend reads)
                api/archive/<timestamp>.json
"""
import json
import os
from datetime import datetime, timezone

from config import PKEYS, HALF_LIFE_DAYS
from pipeline.ingest_polls import ingest
from pipeline.aggregate import build_aggregate
from pipeline.economy import fetch_economy, health_index
from pipeline.sentiment import run_sentiment
from pipeline.quality import aggregate_quality
from pipeline.simulate import simulate

API_DIR = os.path.join(os.path.dirname(__file__), "..", "api")
ARCHIVE_DIR = os.path.join(API_DIR, "archive")


def apply_fundamentals(base, momentum, sentiment, econ):
    """Blend polls + momentum + economy into the effective starting point.

    Kept deliberately gentle: polls are the backbone, fundamentals only steer.
    """
    H = health_index(econ)
    fi = max(range(len(base)), key=lambda i: base[i])
    eff = []
    for i, p in enumerate(base):
        v = p + momentum[i] * 0.25 + sentiment.get(PKEYS[i], 0.0) * 0.6
        if i == fi:
            v += H * 3.0
        else:
            v -= H * 3.0 / (len(base) - 1)
        eff.append(max(0.0, round(v, 2)))
    return eff, H


def build(half_life=HALF_LIFE_DAYS, apply_fund=True):
    print("1) Ingesting polls …")
    polls = ingest()
    print(f"   total {len(polls)} polls after dedupe")

    print("2) Aggregating (time × √sample × reliability) …")
    agg = build_aggregate(polls, half_life)

    print("3) Economy …")
    econ = fetch_economy()

    print("4) News sentiment …")
    sentiment = run_sentiment()

    base = agg["base_pct"]
    if apply_fund:
        eff, H = apply_fundamentals(base, agg["momentum"], sentiment, econ)
    else:
        eff, H = base, health_index(econ)

    print("5) Monte Carlo …")
    results = simulate(eff, vol_mult=agg["volatility"])

    print("6) Ποιοτική αξιολόγηση δημοσκοπήσεων …")
    quality = aggregate_quality(polls, agg["reliability"], agg["reference_date"])

    out = {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "reference_date": agg["reference_date"].date().isoformat(),
        "half_life_days": half_life,
        "polls": [{
            "date": p["date"].date().isoformat(),
            "pollster": p["pollster"],
            "sample": p["sample"],
            "reliability": p.get("reliability"),
            "vals": {PKEYS[i]: p["vals"][i] for i in range(len(PKEYS))},
        } for p in polls],
        "reliability": {k: round(v, 3) for k, v in agg["reliability"].items()},
        "econ": econ,
        "health_index": H,
        "sentiment": sentiment,
        "quality": quality,
        "base_pct": {PKEYS[i]: base[i] for i in range(len(PKEYS))},
        "effective_pct": {PKEYS[i]: eff[i] for i in range(len(PKEYS))},
        "results": results,
    }

    os.makedirs(ARCHIVE_DIR, exist_ok=True)
    with open(os.path.join(API_DIR, "latest.json"), "w", encoding="utf-8") as f:
        json.dump(out, f, ensure_ascii=False, indent=2)
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    with open(os.path.join(ARCHIVE_DIR, f"{stamp}.json"), "w", encoding="utf-8") as f:
        json.dump(out, f, ensure_ascii=False, indent=2)

    print(f"\n✓ wrote api/latest.json  ·  first party {results['parties'][0]['short']} "
          f"≈ {results['parties'][0]['mean_seats']} έδρες  ·  "
          f"P(αυτοδυναμία)={results['self_sufficiency']*100:.1f}%")
    return out


if __name__ == "__main__":
    build()
