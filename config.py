"""Central configuration for the 150+1 model.

Party order here MUST match the order used in the frontend (PARTIES array in
150plus1.html), so seat vectors line up everywhere.
"""

SEATS = 300
THRESHOLD = 3.0        # % of valid votes required to enter parliament
MAJORITY = 151         # seats needed for a single-party / coalition majority
N_SIMS = 2000          # Monte Carlo iterations
HALF_LIFE_DAYS = 21    # exponential time-decay half-life for poll weighting

# key, display name, short label, hex colour, search terms for news sentiment
PARTIES = [
    {"key": "ND",     "name": "Νέα Δημοκρατία",     "short": "ΝΔ",      "color": "#1f4f9c",
     "terms": ["Νέα Δημοκρατία", "ΝΔ"]},
    {"key": "ELAS",   "name": "ΕΛ.Α.Σ.",            "short": "ΕΛ.Α.Σ.", "color": "#e6a532",
     "terms": ["ΕΛΑΣ", "ΕΛ.Α.Σ."]},
    {"key": "PASOK",  "name": "ΠΑΣΟΚ – ΚΙΝΑΛ",       "short": "ΠΑΣΟΚ",   "color": "#179b54",
     "terms": ["ΠΑΣΟΚ", "ΚΙΝΑΛ"]},
    {"key": "ELPIDA", "name": "Ελπίδα",              "short": "ΕΛΠΙΔΑ",  "color": "#c8a96b",
     "terms": ["Ελπίδα"]},
    {"key": "EL",     "name": "Ελληνική Λύση",       "short": "ΕΛ",      "color": "#7aa6d6",
     "terms": ["Ελληνική Λύση"]},
    {"key": "KKE",    "name": "ΚΚΕ",                 "short": "ΚΚΕ",     "color": "#c8202a",
     "terms": ["ΚΚΕ", "Κομμουνιστικό Κόμμα"]},
    {"key": "PE",     "name": "Πλεύση Ελευθερίας",   "short": "ΠΕ",      "color": "#7d4a98",
     "terms": ["Πλεύση Ελευθερίας"]},
    {"key": "FL",     "name": "Φωνή Λογικής",        "short": "ΦΛ",      "color": "#2b333f",
     "terms": ["Φωνή Λογικής"]},
    # Νέο κόμμα Αντώνη Σαμαρά — ανενεργό (0%) μέχρι να ανακοινωθεί/μετρηθεί.
    {"key": "SAM",    "name": "Κόμμα Σαμαρά (αναμενόμενο)", "short": "ΣΑΜ", "color": "#0d5b8c",
     "terms": ["Σαμαράς", "Σαμαρά"]},
]

PKEYS = [p["key"] for p in PARTIES]

# Economic fallback values (used when live APIs are unreachable)
ECON_FALLBACK = {"growth": 2.1, "inflation": 5.0, "unemp": 9.5, "conf": -52.2}

# Greek-language news RSS feeds for the sentiment layer (edit freely)
NEWS_FEEDS = [
    "https://www.naftemporiki.gr/feed/",
    "https://www.kathimerini.gr/feed/",
    "https://www.tovima.gr/feed/",
    "https://www.efsyn.gr/rss.xml",
]
