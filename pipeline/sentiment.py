"""News-sentiment layer.

Pipeline: collect recent Greek news (RSS) -> score each article's polarity ->
attribute polarity to the parties mentioned -> aggregate into a per-party
sentiment index in roughly [-1, +1].

Scorers are pluggable:
  * LexiconScorer   — zero-dependency Greek polarity lexicon (default, always runs).
  * TransformerScorer — hook for a fine-tuned Greek sentiment model (e.g. a
    HuggingFace model); requires `transformers`/`torch`.
  * LLMScorer        — hook for scoring via an LLM API.

The sentiment index is intentionally used only as a *small directional nudge*
in the model, never as a hard predictor.
"""
import re
from collections import defaultdict
from datetime import datetime, timezone

from config import PARTIES, PKEYS, NEWS_FEEDS

# --- tiny Greek polarity lexicon (extend for production) ----------------
POS = {
    "άνοδος", "ενίσχυση", "προβάδισμα", "νίκη", "κέρδη", "ανάκαμψη", "θετικό",
    "στήριξη", "συμφωνία", "επιτυχία", "αύξηση", "ισχυρό", "πρωτιά", "ανοδική",
    "κερδίζει", "ενισχύεται", "προηγείται", "δυναμική", "αισιοδοξία", "επένδυση",
    "βελτίωση", "ρεκόρ", "ανάπτυξη", "σταθερότητα", "εμπιστοσύνη", "υπεροχή",
}
NEG = {
    "πτώση", "υποχώρηση", "κρίση", "σκάνδαλο", "ήττα", "απώλειες", "αρνητικό",
    "πίεση", "διαφωνία", "αποτυχία", "μείωση", "φθορά", "καταδίκη", "διαμαρτυρία",
    "παραίτηση", "κατηγορίες", "έρευνα", "καταγγελία", "οργή", "αντιδράσεις",
    "χάνει", "υποχωρεί", "καθίζηση", "δυσαρέσκεια", "ακρίβεια", "απεργία",
    "ρήξη", "αποχώρηση", "εσωκομματική", "αμφισβήτηση", "ένταση",
}
# ------------------------------------------------------------------------


def collect_news(feeds=NEWS_FEEDS, max_age_days=30):
    """Return list of {title, summary, published} from RSS feeds."""
    import feedparser
    cutoff = datetime.now(timezone.utc).timestamp() - max_age_days * 86400
    articles = []
    for url in feeds:
        try:
            feed = feedparser.parse(url)
            for e in feed.entries:
                ts = None
                if getattr(e, "published_parsed", None):
                    ts = datetime(*e.published_parsed[:6], tzinfo=timezone.utc).timestamp()
                if ts and ts < cutoff:
                    continue
                articles.append({
                    "title": getattr(e, "title", ""),
                    "summary": re.sub("<[^>]+>", " ", getattr(e, "summary", "")),
                })
        except Exception as ex:
            print(f"  · feed {url}: FAILED ({ex})")
    return articles


class LexiconScorer:
    def polarity(self, text):
        t = text.lower()
        pos = sum(t.count(w) for w in POS)
        neg = sum(t.count(w) for w in NEG)
        if pos + neg == 0:
            return 0.0
        return (pos - neg) / (pos + neg)


class TransformerScorer:  # pragma: no cover - optional heavy dependency
    """Hook for a fine-tuned Greek sentiment model."""
    def __init__(self, model="nlpaueb/bert-base-greek-uncased-v1"):
        from transformers import pipeline
        self.clf = pipeline("sentiment-analysis", model=model)

    def polarity(self, text):
        out = self.clf(text[:512])[0]
        sign = 1 if out["label"].upper().startswith(("POS", "LABEL_2")) else -1
        return sign * float(out["score"])


def compute_sentiment(articles, scorer=None):
    scorer = scorer or LexiconScorer()
    acc = defaultdict(lambda: [0.0, 0])  # key -> [sum_polarity, count]
    for a in articles:
        text = f"{a['title']} {a['summary']}"
        pol = scorer.polarity(text)
        for p in PARTIES:
            if any(term.lower() in text.lower() for term in p["terms"]):
                acc[p["key"]][0] += pol
                acc[p["key"]][1] += 1
    sentiment = {}
    for k in PKEYS:
        s, c = acc[k]
        sentiment[k] = round(s / c, 3) if c else 0.0
    return sentiment


def run_sentiment(scorer=None):
    try:
        articles = collect_news()
    except Exception as e:
        print(f"  · sentiment: no articles ({e})")
        return {k: 0.0 for k in PKEYS}
    if not articles:
        return {k: 0.0 for k in PKEYS}
    print(f"  · scored {len(articles)} articles")
    return compute_sentiment(articles, scorer)
