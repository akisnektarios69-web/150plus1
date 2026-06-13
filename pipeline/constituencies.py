"""Κατανομή εδρών ανά εκλογική περιφέρεια (59 περιφέρειες + 15 Επικρατείας).

Μέθοδος (standard πρακτική ψηφολογικής ανάλυσης):
  1. Βάση: πραγματικά αποτελέσματα Ιουνίου 2023 ανά περιφέρεια (έδρες κάθε
     περιφέρειας + ποσοστά κομμάτων), που διαβάζονται ΑΥΤΟΜΑΤΑ από τον πίνακα
     της Wikipedia — κανένα χειροκίνητο/επινοημένο δεδομένο.
  2. Αναλογικό swing: μερίδιο κόμματος p στην περιφέρεια c σήμερα
        s'_{c,p} ∝ εθνικό_τώρα_p × (s2023_{c,p} / εθνικό_2023_p)
     (κόμματα χωρίς ιστορικό 2023 παίρνουν τεκμηριωμένο proxy γεωγραφίας).
  3. Διπλο-αναλογική προσαρμογή (IPF) + largest remainder ώστε:
     άθροισμα ανά περιφέρεια = έδρες περιφέρειας, άθροισμα ανά κόμμα =
     εθνικές έδρες του μοντέλου (με το μπόνους). 15 έδρες Επικρατείας
     κατανέμονται εθνικά-αναλογικά και αφαιρούνται πριν το βήμα 3.

Proxies νέων κομμάτων (δηλώνονται και στο JSON):
  ELAS→γεωγραφία ΣΥΡΙΖΑ 2023 · SAM→γεωγραφία ΝΔ · ELPIDA→ομοιόμορφη ·
  FL→στήλη της αν υπάρχει, αλλιώς γεωγραφία ΕΛ.

Fail-safe: οποιοδήποτε σφάλμα ⇒ επιστρέφεται None και το μοντέλο συνεχίζει
με την εθνική κατανομή όπως πριν.
"""
import re

from config import PKEYS, THRESHOLD

WIKI_2023 = ("https://en.wikipedia.org/wiki/"
             "June_2023_Greek_legislative_election")

# 2023 στήλες-πηγές ανά σημερινό κόμμα (None = proxy)
SOURCE_2023 = {
    "ND":     ["nd", "new democracy"],
    "ELAS":   ["syriza"],                      # proxy: γεωγραφία ΣΥΡΙΖΑ
    "PASOK":  ["pasok"],
    "ELPIDA": None,                            # ομοιόμορφη κατανομή
    "EL":     ["greek solution", "elliniki", "ellinikí"],
    "KKE":    ["kke", "communist"],
    "PE":     ["plefsi", "course of freedom", "freedom"],
    "FL":     ["voice of reason", "foni"],     # αν δεν βρεθεί → proxy ΕΛ
    "SAM":    ["nd", "new democracy"],         # proxy: γεωγραφία ΝΔ
}
PROXY_FALLBACK = {"FL": "EL"}
STATE_SEATS = 15

_CONST_HINTS = ("athens", "attica", "piraeus", "thessaloniki", "achaea",
                "heraklion", "larissa", "evros", "boeotia", "corinthia",
                "ioannina", "serres", "kavala", "rhodope", "cyclades",
                "messenia", "magnesia", "lesbos", "chania", "drama")


def _txt(c):
    return (" ".join(str(x) for x in c) if isinstance(c, tuple) else str(c)).lower()


def _num(cell):
    m = re.search(r"(\d{1,2}(?:[\.,]\d{1,2})?)", str(cell))
    return float(m.group(1).replace(",", ".")) if m else 0.0


def _int(cell):
    m = re.search(r"(\d{1,3})", str(cell))
    return int(m.group(1)) if m else 0


CONST_URL = ("https://en.wikipedia.org/wiki/"
             "List_of_parliamentary_constituencies_of_Greece")


def _norm_name(x):
    x = str(x).lower().strip()
    x = re.sub(r"constituency|electoral district|[\u2018\u2019'\"()\[\]]+", " ", x)
    return re.sub(r"\s+", " ", x).strip()


def _get(url):
    import io as _io
    import requests
    import pandas as pd
    r = requests.get(url, timeout=25, headers={"User-Agent": "150plus1-model/1.0"})
    r.raise_for_status()
    return pd.read_html(_io.StringIO(r.text))


def _seat_map():
    """Έδρες ανά περιφέρεια από τη σελίδα Constituencies of Greece."""
    best = {}
    for t in _get(CONST_URL):
        seats_col = None
        for ci, c in enumerate(t.columns):
            if ci > 0 and "seat" in _txt(c):
                seats_col = ci
                break
        if seats_col is None or len(t) < 40:
            continue
        m = {}
        for _, row in t.iterrows():
            n = _norm_name(row.iloc[0])
            sv = _int(row.iloc[seats_col])
            if n and 0 < sv <= 20:
                m[n] = sv
        if len(m) > len(best):
            best = m
    return best


def fetch_2023():
    """[(όνομα, έδρες, {κόμμα2023: %}), ...] — ενώνει 2 σελίδες Wikipedia."""
    tables = _get(WIKI_2023)
    best, score = None, 0
    for t in tables:
        first = t.iloc[:, 0].astype(str).str.lower()
        hits = sum(first.str.contains(h, regex=False).any() for h in _CONST_HINTS)
        if hits > score and len(t) >= 40:
            best, score = t, hits
    if best is None or score < 8:
        raise ValueError(f"δεν βρέθηκε πίνακας περιφερειών (max hits={score}, tables={len(tables)})")
    cols = {}
    seats_col = None
    for ci, c in enumerate(best.columns):
        f = _txt(c)
        if ci > 0 and ("seat" in f or "έδρες" in f) and seats_col is None:
            seats_col = ci
        for key, pats in SOURCE_2023.items():
            if pats and key not in cols and any(p in f for p in pats):
                cols[key] = ci
    if "ND" in cols and "SAM" not in cols:
        cols["SAM"] = cols["ND"]
    needed = {"ND", "ELAS", "PASOK", "KKE"}
    if not needed.issubset(cols):
        raise ValueError(f"λείπουν στήλες κομμάτων 2023 (βρέθηκαν: {sorted(cols)})")
    smap = {} if seats_col is not None else _seat_map()
    if seats_col is None and len(smap) < 45:
        raise ValueError(f"χωρίς στήλη εδρών και η σελίδα περιφερειών έδωσε μόνο {len(smap)} εγγραφές")
    rows = []
    unmatched = []
    for _, row in best.iterrows():
        name = str(row.iloc[0]).strip()
        nl = name.lower()
        if not name or nl.startswith(("total", "nan", "greece", "source")):
            continue
        if seats_col is not None:
            seats = _int(row.iloc[seats_col])
        else:
            seats = smap.get(_norm_name(name), 0)
            if not seats:
                unmatched.append(name)
        if seats <= 0 or seats > 20:
            continue
        shares = {k: _num(row.iloc[ci]) for k, ci in cols.items()}
        if shares.get("ND", 0) < 5:
            continue
        rows.append((name, seats, shares))
    tot = sum(s for _, s, _ in rows)
    if len(rows) < 45 or not 270 <= tot <= 300:
        raise ValueError(f"επικύρωση: {len(rows)} περιφέρειες/{tot} έδρες"
                         + (f" · αταίριαστες: {unmatched[:5]}" if unmatched else ""))
    return rows


def _swing_matrix(base2023, national_now):
    """Μερίδια ανά περιφέρεια σήμερα με αναλογικό swing + proxies."""
    nat23 = {}
    tot = sum(s for _, s, _ in base2023)
    for k in PKEYS:
        vals = [sh.get(k, 0.0) * s for _, s, sh in base2023]
        nat23[k] = sum(vals) / tot if tot else 0.0
    W = []
    for name, seats, sh in base2023:
        row = {}
        for i, k in enumerate(PKEYS):
            now = national_now[i]
            if now <= 0:
                row[k] = 0.0
                continue
            base = sh.get(k, 0.0)
            if (not base) and k in PROXY_FALLBACK:
                base = sh.get(PROXY_FALLBACK[k], 0.0)
                ref = nat23.get(PROXY_FALLBACK[k], 0.0)
            else:
                ref = nat23.get(k, 0.0)
            row[k] = now * (base / ref) if (base and ref) else now  # ομοιόμορφο
        W.append((name, seats, row))
    return W


def allocate_constituencies(base2023, national_now, national_seats):
    """Διπλο-αναλογική κατανομή: γραμμές=περιφέρειες, στήλες=κόμματα."""
    # 12 Επικρατείας: εθνικά-αναλογικά στα κόμματα με έδρες
    tot_nat = sum(national_seats)
    state = [0] * len(PKEYS)
    if tot_nat >= 300:
        quo = [(national_seats[i] * STATE_SEATS / 300, i) for i in range(len(PKEYS))]
        give = [int(q) for q, _ in quo]
        rem = STATE_SEATS - sum(give)
        for _, i in sorted(quo, key=lambda x: -(x[0] - int(x[0])))[:rem]:
            give[i] += 1
        state = give
    target = [max(0, national_seats[i] - state[i]) for i in range(len(PKEYS))]
    W = _swing_matrix(base2023, national_now)
    R = [seats for _, seats, _ in W]
    if sum(target) != sum(R):                      # ασφάλεια συνέπειας
        diff = sum(R) - sum(target)
        order = sorted(range(len(PKEYS)), key=lambda i: -target[i])
        j = 0
        while diff != 0 and order:
            i = order[j % len(order)]
            step = 1 if diff > 0 else -1
            if target[i] + step >= 0:
                target[i] += step
                diff -= step
            j += 1
    n = len(PKEYS)
    M = [[W[c][2][PKEYS[i]] for i in range(n)] for c in range(len(W))]
    # μηδενισμός κομμάτων κάτω του στόχου 0
    for i in range(n):
        if target[i] == 0:
            for c in range(len(W)):
                M[c][i] = 0.0
    # IPF
    a = [1.0] * len(W)
    b = [1.0] * n
    for _ in range(60):
        for c in range(len(W)):
            s = sum(M[c][i] * b[i] for i in range(n))
            a[c] = R[c] / s if s > 0 else 0.0
        for i in range(n):
            s = sum(M[c][i] * a[c] for c in range(len(W)))
            b[i] = target[i] / s if s > 0 else 0.0
    X = [[M[c][i] * a[c] * b[i] for i in range(n)] for c in range(len(W))]
    # largest remainder ανά περιφέρεια
    S = []
    for c in range(len(W)):
        fl = [int(X[c][i]) for i in range(n)]
        rem = R[c] - sum(fl)
        order = sorted(range(n), key=lambda i: -(X[c][i] - int(X[c][i])))
        for i in order[:max(0, rem)]:
            fl[i] += 1
        S.append(fl)
    # διόρθωση στηλών (στόχοι κομμάτων) με ελάχιστες μετακινήσεις
    def coltot(i):
        return sum(S[c][i] for c in range(len(W)))
    for _ in range(600):
        over = [i for i in range(n) if coltot(i) > target[i]]
        under = [i for i in range(n) if coltot(i) < target[i]]
        if not over or not under:
            break
        moved = False
        for io_ in over:
            for iu in under:
                cands = [(X[c][iu] - X[c][io_], c) for c in range(len(W))
                         if S[c][io_] > 0]
                for _, c in sorted(cands, key=lambda x: -x[0]):
                    S[c][io_] -= 1
                    S[c][iu] += 1
                    moved = True
                    break
                if moved:
                    break
            if moved:
                break
        if not moved:
            break
    out = []
    for c, (name, seats, _) in enumerate(W):
        out.append({
            "name": name, "seats": seats,
            "alloc": {PKEYS[i]: S[c][i] for i in range(n) if S[c][i] > 0},
        })
    return {
        "constituencies": out,
        "state_seats": {PKEYS[i]: state[i] for i in range(n) if state[i] > 0},
        "method": ("Βάση: Ιούνιος 2023 ανά περιφέρεια (Wikipedia) · "
                   "αναλογικό swing · διπλο-αναλογική προσαρμογή (IPF). "
                   "Proxies: ΕΛ.Α.Σ.→γεωγρ. ΣΥΡΙΖΑ, ΣΑΜ→γεωγρ. ΝΔ, "
                   "Ελπίδα→ομοιόμορφη."),
    }
