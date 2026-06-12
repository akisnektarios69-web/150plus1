"""Poll ingestion — turns external sources into the canonical poll schema.

Canonical poll dict:
    {
      "date": datetime,
      "pollster": str,
      "sample": int,
      "reliability": float | None,
      "vals": [pct for each party in config.PKEYS order],
    }

Add real automated sources by implementing `fetch()` on a Source subclass and
appending it to SOURCES. A CsvUrlSource is provided (point it at any published
CSV that follows the template). If no source returns data (e.g. offline), the
local seed file is used so the pipeline always produces output.
"""
import csv
import io
import os
from datetime import datetime

from config import PKEYS

SEED_PATH = os.path.join(os.path.dirname(__file__), "..", "data", "seed_polls.csv")


def _parse_rows(reader):
    polls = []
    for row in reader:
        try:
            d = datetime.fromisoformat(row["date"].strip())
        except Exception:
            continue
        vals = []
        for k in PKEYS:
            v = row.get(k) or row.get(k.upper()) or row.get(k.lower()) or 0
            try:
                vals.append(float(v))
            except ValueError:
                vals.append(0.0)
        rel = row.get("reliability")
        samp_raw = (row.get("sample") or "").strip()
        def _num(x):
            try:
                return float(x)
            except (TypeError, ValueError):
                return None
        polls.append({
            "date": d,
            "pollster": (row.get("pollster") or "—").strip(),
            "sample": int(float(samp_raw)) if samp_raw else None,   # None = αδιαφανές
            "reliability": float(rel) if rel not in (None, "", "—") else None,
            "vals": vals,
            # quality metadata (optional)
            "commissioner": (row.get("commissioner") or "").strip() or None,
            "method": (row.get("method") or "").strip() or None,
            "moe": _num(row.get("moe")),
            "undecided": _num(row.get("undecided")),
            "source": (row.get("source") or "").strip() or None,
            "note": (row.get("note") or "").strip() or None,
        })
    return polls


class Source:
    name = "base"
    def fetch(self):
        raise NotImplementedError


class CsvUrlSource(Source):
    """Fetch a CSV (same columns as the template) from any public URL."""
    def __init__(self, url, name=None):
        self.url = url
        self.name = name or url

    def fetch(self):
        import requests
        r = requests.get(self.url, timeout=20)
        r.raise_for_status()
        return _parse_rows(csv.DictReader(io.StringIO(r.text)))


class WikipediaSource(Source):
    """Αυτόματη ανάγνωση του πίνακα δημοσκοπήσεων της Wikipedia.

    Η σελίδα 'Opinion polling for the next Greek parliamentary election'
    συγκεντρώνει κάθε δημοσιευμένη μέτρηση (iefimerida, ΣΚΑΪ, Έθνος κ.λπ.),
    ελεγμένη από ανθρώπους και ήδη αναγμένη σε κοινή βάση (rule of three).
    Fail-safe: σε ΟΠΟΙΟΔΗΠΟΤΕ σφάλμα επιστρέφει [] και το pipeline συνεχίζει
    με τις επόμενες πηγές / το seed.
    """
    name = "wikipedia"
    URL = ("https://en.wikipedia.org/wiki/"
           "Opinion_polling_for_the_next_Greek_parliamentary_election")
    # ευέλικτη αντιστοίχιση στηλών -> κόμματα (πιάνει EN/GR/παραλλαγές)
    COLMAP = {
        "ND":     ["nd", "new democracy", "νδ", "νεα δημοκρατια"],
        "ELAS":   ["elas", "ελασ", "ελ.α.σ", "tsipras", "left alliance"],
        "PASOK":  ["pasok", "πασοκ", "kinal"],
        "ELPIDA": ["elpida", "ελπιδα", "hope", "karystianou"],
        "EL":     ["greek solution", "ελληνικη λυση", "el ", "ελ "],
        "KKE":    ["kke", "κκε", "communist"],
        "PE":     ["plefsi", "course of freedom", "πλευση", "pe "],
        "FL":     ["foni", "voice of reason", "φωνη λογικης", "fl ", "φλ "],
        "SAM":    ["samaras", "σαμαρα"],
    }
    MONTHS = {m: i + 1 for i, m in enumerate(
        ["jan", "feb", "mar", "apr", "may", "jun",
         "jul", "aug", "sep", "oct", "nov", "dec"])}

    def _match(self, header):
        h = " " + str(header).lower().strip() + " "
        for key, pats in self.COLMAP.items():
            for p in pats:
                if p in h:
                    return key
        return None

    def _num(self, cell):
        import re
        m = re.search(r"(\d{1,2}(?:\.\d)?)", str(cell))
        return float(m.group(1)) if m else 0.0

    def _date(self, cell, default_year):
        import re
        s = str(cell)
        year = default_year
        ym = re.search(r"(20\d\d)", s)
        if ym:
            year = int(ym.group(1))
        # τελευταία αναφορά ημέρας+μήνα (λήξη fieldwork)
        hits = re.findall(r"(\d{1,2})\s*([A-Za-z]{3})", s)
        if not hits:
            return None
        day, mon = hits[-1]
        mon_n = self.MONTHS.get(mon.lower()[:3])
        if not mon_n:
            return None
        return datetime(year, mon_n, int(day))

    def fetch(self):
        import io as _io
        import requests
        import pandas as pd
        r = requests.get(self.URL, timeout=25,
                         headers={"User-Agent": "150plus1-model/1.0"})
        r.raise_for_status()
        tables = pd.read_html(_io.StringIO(r.text))
        best, best_cols = None, {}
        for t in tables:
            cols = {}
            for ci, c in enumerate(t.columns):
                flat = " ".join(str(x) for x in c) if isinstance(c, tuple) else str(c)
                k = self._match(flat)
                if k and k not in cols.values():
                    cols[ci] = k
            if len(cols) >= 4 and (best is None or len(cols) > len(best_cols)):
                best, best_cols = t, cols
        if best is None:
            return []
        # εντόπισε στήλες ημερομηνίας / εταιρείας / δείγματος
        meta = {}
        for ci, c in enumerate(best.columns):
            flat = (" ".join(str(x) for x in c) if isinstance(c, tuple) else str(c)).lower()
            if "date" in flat or "fieldwork" in flat:
                meta.setdefault("date", ci)
            if "firm" in flat or "poll" in flat:
                meta.setdefault("firm", ci)
            if "sample" in flat:
                meta.setdefault("sample", ci)
        if "date" not in meta or "firm" not in meta:
            return []
        year_now = datetime.now().year
        polls = []
        for _, row in best.iterrows():
            try:
                firm = str(row.iloc[meta["firm"]]).split("/")[0].strip()
                if not firm or "election" in firm.lower() or firm.lower() == "nan":
                    continue
                d = self._date(row.iloc[meta["date"]], year_now)
                if d is None:
                    continue
                samp = None
                if "sample" in meta:
                    import re
                    sm = re.search(r"([\d,\.]{3,})", str(row.iloc[meta["sample"]]))
                    if sm:
                        samp = int(float(sm.group(1).replace(",", "")))
                vals = [0.0] * len(PKEYS)
                for ci, key in best_cols.items():
                    vals[PKEYS.index(key)] = self._num(row.iloc[ci])
                if sum(vals) < 40:          # σκουπίδι/κενή γραμμή
                    continue
                polls.append({
                    "date": d, "pollster": firm,
                    "sample": samp, "reliability": None, "vals": vals,
                    "commissioner": None, "method": None, "moe": None,
                    "undecided": None,      # Wikipedia: ήδη αναγμένα
                    "source": "wikipedia", "note": "auto (Wikipedia, αναγμένα)",
                })
            except Exception:
                continue
        return polls if len(polls) >= 3 else []


# --- Register real automated sources here -------------------------------
SOURCES = [
    WikipediaSource(),
    # CsvUrlSource("PUT_GOOGLE_SHEET_CSV_URL_HERE", "google-sheet"),
]
# ------------------------------------------------------------------------


def load_seed():
    with open(SEED_PATH, encoding="utf-8") as f:
        return _parse_rows(csv.DictReader(f))


def _dedupe(polls):
    seen = {}
    for p in polls:
        key = (p["pollster"], p["date"].date())
        seen[key] = p  # last one wins
    return sorted(seen.values(), key=lambda p: p["date"])


def ingest():
    collected = []
    for src in SOURCES:
        try:
            rows = src.fetch()
            print(f"  · {src.name}: {len(rows)} polls")
            collected.extend(rows)
        except Exception as e:
            print(f"  · {src.name}: FAILED ({e})")
    if not collected:
        print("  · no live sources — using local seed file")
        collected = load_seed()
    return _dedupe(collected)
