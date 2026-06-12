# -*- coding: utf-8 -*-
"""fix_v21: τα 0% νέων κομμάτων σε παλιές μετρήσεις = «δεν μετρήθηκε».
Τρέξε: python fix_v21.py  (μέσα στο C:\150plus1\backend)"""
import io, re, sys

OLD_PY = """    wsum = 0.0
    agg = [0.0] * len(PKEYS)
    for p in polls:
        if p["date"] > ref_date:
            continue
        wr = p["reliability"] if p.get("reliability") is not None else rel_map.get(p["pollster"], 1.0)
        w = (_time_weight(p["date"], ref_date, half_life)
             * math.sqrt((p["sample"] or 900) / 1000) * wr
             * _method_score(p.get("method")))
        if w <= 0:
            continue
        wsum += w
        for i, v in enumerate(p["vals"]):
            agg[i] += v * w
    if wsum <= 0:
        return None
    return [v / wsum for v in agg]"""

NEW_PY = """    n = len(PKEYS)
    wsum = [0.0] * n          # ανά κόμμα: το 0 σε παλιά μέτρηση = «δεν μετρήθηκε»
    agg = [0.0] * n
    any_w = 0.0
    for p in polls:
        if p["date"] > ref_date:
            continue
        wr = p["reliability"] if p.get("reliability") is not None else rel_map.get(p["pollster"], 1.0)
        w = (_time_weight(p["date"], ref_date, half_life)
             * math.sqrt((p["sample"] or 900) / 1000) * wr
             * _method_score(p.get("method")))
        if w <= 0:
            continue
        any_w += w
        for i, v in enumerate(p["vals"]):
            if v > 0:
                agg[i] += v * w
                wsum[i] += w
    if any_w <= 0:
        return None
    return [(agg[i] / wsum[i] if wsum[i] > 0 else 0.0) for i in range(n)]"""

OLD_JS = """function aggregateAt(polls, refDate, relMap){
  let wsum=0; const agg=new Array(PKEYS.length).fill(0);
  polls.forEach(p=>{ if(p.date>refDate) return;
    const wr = p.reliability!=null? p.reliability : (relMap[p.pollster]||1);
    const w = timeWeight(p,refDate) * Math.sqrt(p.sample/1000) * wr;
    if(w<=0) return; wsum+=w; p.vals.forEach((v,i)=>agg[i]+=v*w);
  });
  if(wsum<=0) return null;
  return {pct:agg.map(v=>v/wsum), wsum};
}"""

NEW_JS = """function aggregateAt(polls, refDate, relMap){
  const n=PKEYS.length, wsum=new Array(n).fill(0), agg=new Array(n).fill(0); let anyW=0;
  polls.forEach(p=>{ if(p.date>refDate) return;
    const wr = p.reliability!=null? p.reliability : (relMap[p.pollster]||1);
    const w = timeWeight(p,refDate) * Math.sqrt((p.sample||900)/1000) * wr;
    if(w<=0) return; anyW+=w;
    p.vals.forEach((v,i)=>{ if(v>0){agg[i]+=v*w; wsum[i]+=w;} });
  });
  if(anyW<=0) return null;
  return {pct:agg.map((v,i)=>wsum[i]>0? v/wsum[i]:0), wsum:anyW};
}"""

def apply(path, old, new):
    s = io.open(path, encoding="utf-8").read()
    if new in s:
        print(f"  {path}: ηδη διορθωμενο")
        return
    if old not in s:
        print(f"  {path}: ΔΕΝ βρεθηκε το σημειο — στειλε μηνυμα στον Claude"); sys.exit(1)
    io.open(path, "w", encoding="utf-8").write(s.replace(old, new))
    print(f"  {path}: OK")

apply("pipeline/aggregate.py", OLD_PY, NEW_PY)
for f in ("web/index.html", "index.html"):
    try: apply(f, OLD_JS, NEW_JS)
    except FileNotFoundError: print(f"  {f}: δεν υπαρχει (οκ)")
print("Ολοκληρωθηκε. Τρεξε: python -m pipeline.build_model")
