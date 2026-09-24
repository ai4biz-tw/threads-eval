#!/usr/bin/env python3
"""Build the eval dataset from raw insights.

Label: 爆文 = engagement_rate in top 20% (engagement = likes+replies+reposts+quotes / views).
Split: 70% dev (tune the rubric), 30% holdout (final validation, do not peek).
Output: eval_dataset.json with blind items (caption only) + labels kept separate.
"""
import json, random

random.seed(42)

rows = json.load(open("/home/hatch/workspace/threads-eval/insights.json"))
# drop posts with too few views to be meaningful (< 200 views: not enough distribution to judge)
rows = [r for r in rows if (r.get("views") or 0) >= 200]
print(f"posts with >=200 views: {len(rows)}")

for r in rows:
    v = r["views"] or 1
    eng = (r.get("likes",0) + r.get("replies",0) + r.get("reposts",0) + r.get("quotes",0))
    r["engagement_rate"] = eng / v
    r["engagement"] = eng

rows.sort(key=lambda r: r["engagement_rate"], reverse=True)
cut = max(1, int(len(rows) * 0.2))
for i, r in enumerate(rows):
    r["label"] = "爆" if i < cut else "普"

print(f"labeled: {cut} 爆 / {len(rows)-cut} 普")
print("top 5 by eng_rate:")
for r in rows[:5]:
    print(f"  {r['engagement_rate']:.3f} views={r['views']} eng={r['engagement']} {r['date']} {(r['caption'] or '')[:50]}")

random.shuffle(rows)
n_hold = max(1, int(len(rows) * 0.3))
holdout, dev = rows[:n_hold], rows[n_hold:]

def blind(items):
    return [{"media_id": r["media_id"], "date": r["date"],
             "caption": r["caption"], "post_type": r.get("post_type")}
            for r in items]

def keyed(items):
    return {r["media_id"]: {"label": r["label"], "views": r["views"],
            "likes": r["likes"], "replies": r["replies"],
            "reposts": r["reposts"], "quotes": r["quotes"],
            "engagement_rate": round(r["engagement_rate"],4)} for r in items}

out = {
    "dev_blind": blind(dev), "dev_key": keyed(dev),
    "holdout_blind": blind(holdout), "holdout_key": keyed(holdout),
}
json.dump(out, open("/home/hatch/workspace/threads-eval/eval_dataset.json","w"), ensure_ascii=False)
print(f"dev={len(dev)} holdout={len(holdout)} -> eval_dataset.json")
