# 150+1 — Αυτόματο backend

Τραβάει δημοσκοπήσεις + οικονομικά δεδομένα + συναίσθημα ειδήσεων, τα σταθμίζει,
τρέχει 2.000 προσομοιώσεις Monte Carlo με τον ελληνικό εκλογικό νόμο, και παράγει
`api/latest.json` — το ίδιο αρχείο που διαβάζει αυτόματα το frontend (`150plus1.html`).

## Δομή
```
config.py                 ρυθμίσεις + ορισμός κομμάτων (ίδια σειρά με το frontend)
pipeline/
  ingest_polls.py         εισαγωγή δημοσκοπήσεων (πηγές + seed fallback)
  aggregate.py            στάθμιση (χρόνος × √δείγμα × αξιοπιστία) + house effects
  economy.py              οικονομικοί δείκτες (Eurostat) + δείκτης υγείας
  sentiment.py            συλλογή ειδήσεων (RSS) + βαθμολόγηση συναισθήματος
  electoral_law.py        κατανομή εδρών (ενισχυμένη αναλογική)
  simulate.py             Monte Carlo: έδρες, αυτοδυναμία, συνασπισμοί
  build_model.py          ενορχήστρωση -> γράφει api/latest.json
api/
  server.py               FastAPI: σερβίρει latest.json + το frontend
  latest.json             η ΕΞΟΔΟΣ (το «συμβόλαιο»)
run_scheduler.py          αυτόματη επανεκτέλεση κάθε X ώρες
data/seed_polls.csv       εφεδρικά δεδομένα όταν δεν υπάρχει live πηγή
.github/workflows/        παράδειγμα cron αυτοματισμού (serverless)
```

## Γρήγορη εκκίνηση
```bash
pip install -r requirements.txt
python -m pipeline.build_model          # παράγει api/latest.json (offline -> seed)
mkdir -p web && cp /διαδρομή/150plus1.html web/index.html
uvicorn api.server:app --port 8000      # άνοιξε http://localhost:8000
```

## Αυτοματισμός (διάλεξε ένα)
- **GitHub Actions** (πιο απλό, serverless): `.github/workflows/update.yml` τρέχει
  κάθε 6 ώρες, ξαναχτίζει το `latest.json` και το κάνει commit. Το frontend μπορεί
  να το διαβάζει κατευθείαν από το raw URL (όρισε `window.LIVE_URL`).
- **In-process scheduler**: `python run_scheduler.py` (κρατάει το `latest.json`
  ενημερωμένο δίπλα στο API).
- **System cron**: `0 */6 * * * cd /app && python -m pipeline.build_model`.

## Πώς προστίθενται πραγματικές πηγές δημοσκοπήσεων
Άνοιξε `pipeline/ingest_polls.py`. Υλοποίησε ένα `Source.fetch()` που επιστρέφει
την κανονική μορφή, ή χρησιμοποίησε έτοιμο τον `CsvUrlSource` δείχνοντας σε ένα
δημοσιευμένο CSV (ίδιες στήλες με το `data/seed_polls.csv`). Πρόσθεσέ το στη
λίστα `SOURCES`. Αν καμία πηγή δεν απαντήσει, χρησιμοποιείται το seed.

## Συναίσθημα ειδήσεων
Default: `LexiconScorer` (χωρίς εξαρτήσεις). Για καλύτερη ακρίβεια ενεργοποίησε
`TransformerScorer` (ελληνικό μοντέλο HuggingFace) ή γράψε `LLMScorer`. Όρισε τα
RSS feeds και τους όρους αναζήτησης ανά κόμμα στο `config.py`.

## Το «συμβόλαιο» JSON (api/latest.json)
```jsonc
{
  "generated_at": "2026-06-07T06:00:00Z",
  "reference_date": "2026-06-02",
  "half_life_days": 21,
  "polls": [ { "date": "...", "pollster": "...", "sample": 1009,
              "reliability": null, "vals": { "ND": 28.3, ... } } ],
  "reliability": { "GPO": 0.88, ... },        // auto house effects
  "econ": { "growth": 2.1, "inflation": 5.0, "unemp": 9.5, "conf": -52.2 },
  "health_index": -0.27,
  "sentiment": { "ND": -0.1, ... },           // [-1,+1] per party
  "base_pct": { "ND": 28.2, ... },            // pure poll aggregate
  "effective_pct": { "ND": 28.0, ... },       // after fundamentals nudge
  "results": {
     "parties": [ { "short":"ΝΔ","mean_seats":111,"low90":75,"high90":139, ... } ],
     "self_sufficiency": 0.011,
     "coalitions": [ { "labels":["ΝΔ","ΠΑΣΟΚ","ΕΛ"], "mean_seats":174,
                       "p_majority":0.79 } ]
  }
}
```

Το frontend διαβάζει `polls` + `econ` (+ `sentiment`) και ξανατρέχει τη μηχανή
τοπικά, ώστε να παραμένει διαδραστικό· τα `results` είναι η εκδοχή του server.
