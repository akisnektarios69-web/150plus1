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


# --- Register real automated sources here -------------------------------
SOURCES = [
    # CsvUrlSource("https://example.org/greek_polls.csv", "aggregator"),
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
