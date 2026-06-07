"""Ποιοτική (μεθοδολογική) αξιολόγηση δημοσκοπήσεων.

Δεν κρίνει το «ποιος προηγείται», αλλά πόσο αξιόπιστο είναι το ΚΑΘΕ εύρημα,
με βάση τα ποιοτικά χαρακτηριστικά της μέτρησης:

  * Επικαιρότητα (recency)      — πόσο πρόσφατη.
  * Επάρκεια δείγματος (sample) — μέγεθος → τυπικό σφάλμα.
  * Μέθοδος (method)            — τηλεφωνική/μικτή/διαδικτυακή/προσωπική.
  * Διαφάνεια (transparency)    — δημοσιοποιεί δείγμα, μέθοδο, εντολέα, αναποφάσιστους;
  * Ιστορική ακρίβεια (house)   — απόκλιση της εταιρείας από τη συναίνεση.

Παράγει per-poll score + συγκεντρωτικούς δείκτες (συμφωνία εταιρειών, όγκος
τεκμηρίωσης, μέση ποιότητα) και ένα συνολικό «δείκτη ποιότητας τεκμηρίωσης»
που λειτουργεί ως προειδοποίηση για το πόσο προσεκτικά να διαβαστούν οι εκτιμήσεις.
"""
import math
import statistics
from datetime import timedelta

# Μέθοδος δειγματοληψίας -> σκορ ποιότητας (πιθανοτική/τηλεφωνική > opt-in online)
METHOD_SCORE = {
    "τηλεφωνική": 1.00, "cati": 1.00, "phone": 1.00,
    "προσωπική": 0.95, "face": 0.95, "f2f": 0.95,
    "μικτή": 0.85, "mixed": 0.85,
    "διαδικτυακή": 0.65, "online": 0.65, "cawi": 0.65, "panel": 0.60,
}


def margin_of_error(sample, p=0.5):
    """95% περιθώριο σφάλματος (απλό τυχαίο δείγμα) σε ποσοστιαίες μονάδες."""
    if not sample or sample <= 0:
        return None
    return round(1.96 * math.sqrt(p * (1 - p) / sample) * 100, 2)


def _method_score(method):
    if not method:
        return 0.5
    return METHOD_SCORE.get(method.strip().lower(), 0.7)


def poll_quality(poll, reliability, ref_date):
    age = max(0.0, (ref_date - poll["date"]).days)
    recency = math.exp(-age / 30.0)                      # 0..1 (μισό βάρος ~21 ημ.)
    sample = poll.get("sample")
    sample_adequacy = min(1.0, math.sqrt((sample or 0) / 1000)) if sample else 0.45
    method = _method_score(poll.get("method"))
    disclosed = sum(1 for f in ("sample", "method", "commissioner", "undecided")
                    if poll.get(f) not in (None, "", "—"))
    transparency = disclosed / 4.0
    accuracy = reliability if reliability is not None else 0.8
    overall = (0.30 * recency + 0.20 * sample_adequacy + 0.20 * method
               + 0.15 * transparency + 0.15 * accuracy)
    flags = []
    if not sample:
        flags.append("δεν δημοσιοποιείται μέγεθος δείγματος")
    if poll.get("undecided") and poll["undecided"] >= 12:
        flags.append("υψηλό ποσοστό αναποφάσιστων")
    if age > 30:
        flags.append("παλαιότερη των 30 ημερών")
    return {
        "date": poll["date"].date().isoformat(),
        "pollster": poll["pollster"],
        "commissioner": poll.get("commissioner"),
        "method": poll.get("method"),
        "sample": sample,
        "moe": margin_of_error(sample),
        "undecided": poll.get("undecided"),
        "age_days": int(age),
        "recency": round(recency, 2),
        "sample_adequacy": round(sample_adequacy, 2),
        "method_score": round(method, 2),
        "transparency": round(transparency, 2),
        "accuracy": round(accuracy, 2),
        "quality": round(overall, 3),
        "flags": flags,
        "source": poll.get("source"),
        "note": poll.get("note"),
    }


def aggregate_quality(polls, rel_map, ref_date, party_index=0):
    per = [poll_quality(p, (p.get("reliability") if p.get("reliability") is not None
                            else rel_map.get(p["pollster"])), ref_date) for p in polls]
    n14 = sum(1 for p in polls if (ref_date - p["date"]).days <= 14)
    n30 = sum(1 for p in polls if (ref_date - p["date"]).days <= 30)
    samples = [p["sample"] for p in polls if p.get("sample")]
    mean_sample = int(statistics.mean(samples)) if samples else None

    method_mix = {}
    for p in polls:
        m = (p.get("method") or "άγνωστη").strip()
        method_mix[m] = method_mix.get(m, 0) + 1

    undecideds = [p["undecided"] for p in polls if p.get("undecided") is not None]
    undecided_avg = round(statistics.mean(undecideds), 1) if undecideds else None

    # Συμφωνία εταιρειών: διασπορά του 1ου κόμματος στις μετρήσεις των τελευταίων 30 ημ.
    recent = [p for p in polls if (ref_date - p["date"]).days <= 30]
    vals = [p["vals"][party_index] for p in recent if len(p["vals"]) > party_index]
    dispersion = round(statistics.pstdev(vals), 2) if len(vals) > 1 else None
    agreement = max(0.0, min(1.0, 1 - (dispersion or 0) / 5.0)) if dispersion is not None else None

    mean_q = round(statistics.mean([q["quality"] for q in per]), 3) if per else 0
    vol_score = 0.4 * min(1, n30 / 6) + 0.3 * mean_q + 0.3 * (agreement if agreement is not None else 0.5)
    label = ("Υψηλή" if vol_score >= 0.7 else "Μέτρια" if vol_score >= 0.5 else "Χαμηλή")

    notes = []
    if n30 < 4:
        notes.append("Λίγες πρόσφατες μετρήσεις — αυξημένη αβεβαιότητα.")
    if dispersion is not None and dispersion > 2.5:
        notes.append("Μεγάλη διαφωνία μεταξύ εταιρειών στο 1ο κόμμα.")
    if mean_sample is None:
        notes.append("Ελλιπής δημοσιοποίηση μεγέθους δείγματος (χαμηλή διαφάνεια).")

    return {
        "per_poll": sorted(per, key=lambda q: q["date"], reverse=True),
        "n_polls": len(polls),
        "n_last_14d": n14,
        "n_last_30d": n30,
        "mean_sample": mean_sample,
        "method_mix": method_mix,
        "undecided_avg": undecided_avg,
        "first_party_dispersion": dispersion,
        "agreement_index": round(agreement, 2) if agreement is not None else None,
        "mean_quality": mean_q,
        "evidence_quality": label,
        "evidence_score": round(vol_score, 2),
        "notes": notes,
    }
