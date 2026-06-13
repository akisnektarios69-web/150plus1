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
from pipeline.normalize import normalize_all
from pipeline.economy import fetch_economy, health_index
from pipeline.sentiment import run_sentiment
from pipeline.quality import aggregate_quality
from pipeline.constituencies import fetch_2023, allocate_constituencies
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


def make_report(results, agg, econ, H, quality):
    """Αυτόματο ημερήσιο δελτίο 5-6 προτάσεων στα ελληνικά."""
    ps = results["parties"]
    first = max(ps, key=lambda p: p["mean_seats"])
    second = sorted(ps, key=lambda p: -p["mean_seats"])[1]
    ss = results["self_sufficiency"] * 100
    feas = [c for c in results["coalitions"] if c.get("feasible")]
    mom = agg["momentum"]
    from config import PARTIES as _P
    movers = sorted(range(len(mom)), key=lambda i: -abs(mom[i]))[:2]
    mom_txt = ", ".join(f"{_P[i]['short']} {'+' if mom[i]>=0 else ''}{mom[i]:.1f}"
                        for i in movers if abs(mom[i]) >= 0.3)
    lines = [
        f"Η εικόνα σήμερα: πρώτο κόμμα η {first['short']} με εκτίμηση "
        f"{first['pct']:.1f}% και {first['mean_seats']:.0f} έδρες "
        f"(εύρος 90%: {first['low90']}–{first['high90']}), "
        f"δεύτερο η {second['short']} με {second['pct']:.1f}%.",
        f"Η πιθανότητα αυτοδυναμίας διαμορφώνεται στο {ss:.0f}%."
        + (" Καμία μονοκομματική πλειοψηφία δεν προκύπτει στα τρέχοντα δεδομένα."
           if ss < 5 else ""),
    ]
    if feas:
        c = feas[0]
        lines.append(
            f"Ισχυρότερος πολιτικά εφικτός σχηματισμός: "
            f"{'+'.join(c['labels'])} με {c['mean_seats']:.0f} έδρες "
            f"και πιθανότητα πλειοψηφίας {c['p_majority']*100:.0f}%.")
    mm = results.get("majority_math") or {}
    if mm.get("majority_need_pct"):
        lines.append(
            f"Με «χαμένη ψήφο» {mm['wasted_share']:.1f}%, το κατώφλι αυτοδυναμίας "
            f"διαμορφώνεται στο {mm['majority_need_pct']:.1f}% — το πρώτο κόμμα "
            f"απέχει {mm['majority_gap']:.1f} μονάδες.")
    if mom_txt:
        lines.append(f"Δυναμική 30 ημερών: {mom_txt} μονάδες.")
    lines.append(
        f"Ποιότητα τεκμηρίωσης: {quality['evidence_quality'].lower()} "
        f"(συμφωνία εταιρειών {int((quality['agreement_index'] or 0)*100)}%, "
        f"{quality['n_last_30d']} μετρήσεις στο 30ήμερο).")
    if H < -0.15:
        lines.append("Το οικονομικό κλίμα παραμένει επιβαρυντικό για το κυβερνών κόμμα.")
    elif H > 0.15:
        lines.append("Το οικονομικό κλίμα λειτουργεί υποστηρικτικά για το κυβερνών κόμμα.")
    return " ".join(lines)


def build(half_life=HALF_LIFE_DAYS, apply_fund=True):
    print("1) Ingesting polls …")
    polls = ingest()
    print(f"   total {len(polls)} polls after dedupe")
    polls = normalize_all(polls)
    n_norm = sum(1 for p in polls if p.get("normalized"))
    if n_norm:
        print(f"   αναγωγή πρόθεσης→εκτίμησης σε {n_norm} μετρήσεις")

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

    print("7) Κατανομή ανά εκλογική περιφέρεια …")
    const_block = None
    try:
        base2023 = fetch_2023()
        if base2023:
            rep = [round(p["mean_seats"]) for p in results["parties"]]
            d = 300 - sum(rep)
            rep[max(range(len(rep)), key=lambda i: rep[i])] += d
            const_block = allocate_constituencies(base2023, eff, rep)
            print(f"  · {len(const_block['constituencies'])} περιφέρειες (βάση 2023)")
        else:
            print("  · χωρίς δεδομένα 2023 — παραλείπεται (fail-safe)")
    except Exception as e:
        print(f"  · FAILED ({e}) — παραλείπεται (fail-safe)")

    report = make_report(results, agg, econ, H, quality)

    out = {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "report_el": report,
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
        "constituencies": const_block,
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
