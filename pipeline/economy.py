"""Economic fundamentals layer.

Tries to pull live indicators from Eurostat's REST API; on any failure falls
back to config.ECON_FALLBACK so the pipeline never breaks. Computes the same
economic-health index as the frontend (defaults land near -0.28).
"""
from config import ECON_FALLBACK

# Eurostat dataset codes (Greece, latest period). These endpoints are real;
# the JSON shape varies, so each getter is defensive and returns None on doubt.
EUROSTAT = "https://ec.europa.eu/eurostat/api/dissemination/statistics/1.0/data"


def _eurostat_latest(dataset, params):
    import requests
    url = f"{EUROSTAT}/{dataset}"
    q = {"format": "JSON", "geo": "EL", **params}
    r = requests.get(url, params=q, timeout=20)
    r.raise_for_status()
    data = r.json()
    values = data.get("value", {})
    if not values:
        return None
    # take the entry with the highest time index (most recent period)
    last_key = max(values.keys(), key=lambda k: int(k))
    return float(values[last_key])


def fetch_economy():
    econ = dict(ECON_FALLBACK)
    try:
        infl = _eurostat_latest("prc_hicp_manr", {"coicop": "CP00"})        # annual inflation %
        if infl is not None:
            econ["inflation"] = round(infl, 1)
    except Exception as e:
        print(f"  · inflation: fallback ({e})")
    try:
        unemp = _eurostat_latest("une_rt_m", {"sex": "T", "age": "TOTAL", "unit": "PC_ACT", "s_adj": "SA"})
        if unemp is not None:
            econ["unemp"] = round(unemp, 1)
    except Exception as e:
        print(f"  · unemployment: fallback ({e})")
    try:
        conf = _eurostat_latest("ei_bsco_m", {"indic": "BS-CSMCI", "s_adj": "SA"})  # consumer confidence
        if conf is not None:
            econ["conf"] = round(conf, 1)
    except Exception as e:
        print(f"  · confidence: fallback ({e})")
    # GDP growth is published quarterly; keep fallback unless you wire na_q here.
    return econ


def health_index(econ):
    zg = (econ["growth"] - 1.5) / 2.0
    zi = (econ["inflation"] - 2.0) / 2.0
    zu = (econ["unemp"] - 7.0) / 3.0
    zc = (econ["conf"] + 10) / 30.0
    return round(0.3 * (0.30 * zg - 0.25 * zi - 0.25 * zu + 0.30 * zc), 3)
