#!/usr/bin/env python3
"""Compute eval metrics: judge predictions vs ground truth.

Input: predictions.json — list of {media_id, score (0-100), tier (S/A/B/C)}
Compares against eval_dataset.json dev_key (or holdout_key).
"""
import json, sys
from math import sqrt

def spearman(xs, ys):
    n = len(xs)
    rx = {v:i for i,v in enumerate(sorted(set(xs)))}
    ry = {v:i for i,v in enumerate(sorted(set(ys)))}
    # average ranks for ties, simplified
    def ranks(vals, mapping):
        s = sorted(vals); pos = {}
        for v in set(vals):
            idx = [i for i,x in enumerate(s) if x==v]
            pos[v] = sum(idx)/len(idx)
        return [pos[v] for v in vals]
    rx, ry = ranks(xs, None), ranks(ys, None)
    mx, my = sum(rx)/n, sum(ry)/n
    num = sum((a-mx)*(b-my) for a,b in zip(rx,ry))
    den = sqrt(sum((a-mx)**2 for a in rx)*sum((b-my)**2 for b in ry))
    return num/den if den else 0.0

which = sys.argv[1] if len(sys.argv)>1 else "dev"
ds = json.load(open("/home/hatch/workspace/threads-eval/eval_dataset.json"))
key = ds[f"{which}_key"]
preds = {p["media_id"]: p for p in json.load(open("/home/hatch/workspace/threads-eval/predictions.json"))}

rows = []
for mid, p in preds.items():
    if mid not in key: continue
    truth = key[mid]
    rows.append({"mid": mid, "score": p["score"], "tier": p["tier"],
                 "label": truth["label"], "eng_rate": truth["engagement_rate"]})

# 爆文召回率: actual 爆 among predicted A/S
hit = [r for r in rows if r["label"]=="爆" and r["tier"] in ("S","A")]
all_boom = [r for r in rows if r["label"]=="爆"]
recall = len(hit)/len(all_boom) if all_boom else 0

# 誤報率: predicted A/S but actually 普
flagged = [r for r in rows if r["tier"] in ("S","A")]
fp = [r for r in flagged if r["label"]=="普"]
fpr = len(fp)/len(flagged) if flagged else 0

# 排序相關性: score vs engagement_rate
rho = spearman([r["score"] for r in rows], [r["eng_rate"] for r in rows])

print(f"=== eval on {which} (n={len(rows)}) ===")
print(f"爆文召回率 (recall): {recall:.0%}  ({len(hit)}/{len(all_boom)} 篇真爆文被評為 A/S)")
print(f"誤報率 (false alarm): {fpr:.0%}  ({len(fp)}/{len(flagged)} 篇評為 A/S 但實際沒爆)")
print(f"分數-互動率排序相關 (spearman): {rho:.2f}")
print()
print("missed 爆文 (judge said B/C but actually 爆):")
for r in rows:
    if r["label"]=="爆" and r["tier"] in ("B","C"):
        print(f"  [{r['tier']}] score={r['score']} eng_rate={r['eng_rate']:.3f} mid={r['mid']}")
print("false alarms (judge said S/A but actually 普):")
for r in rows:
    if r["label"]=="普" and r["tier"] in ("S","A"):
        print(f"  [{r['tier']}] score={r['score']} eng_rate={r['eng_rate']:.3f} mid={r['mid']}")
