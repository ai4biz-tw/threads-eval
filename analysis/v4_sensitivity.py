#!/usr/bin/env python3
"""v4 草案的離線敏感度檢查（不呼叫任何 LLM／Jev，只讀 repo 內既有檔案）。

用法：python3 analysis/v4_sensitivity.py
讀：eval_dataset.json、predictions_v3.json、pred_holdout.json、all_posts.json
（選用）predictions_v4_dev.json / predictions_v4_holdout.json 若存在，加跑「路徑制」重組檢查。

注意：holdout 已經在 v3 結案時看過一次、盲區也已公開，這裡的 holdout 數字只當參考，
不能拿來選 v4 參數；v4 要用 2026-09-24 之後的新貼文另建 holdout-2 驗證。
"""
import json, re, statistics as st
from pathlib import Path
from math import sqrt

ROOT = Path(__file__).resolve().parent.parent
ds = json.load(open(ROOT / "eval_dataset.json", encoding="utf-8"))
v3 = {p["media_id"]: p for p in json.load(open(ROOT / "predictions_v3.json", encoding="utf-8"))}
v3.update({p["media_id"]: p for p in json.load(open(ROOT / "pred_holdout.json", encoding="utf-8"))})
raw = {p["media_id"]: p for p in json.load(open(ROOT / "all_posts.json", encoding="utf-8"))}


def spearman(xs, ys):
    def ranks(v):
        s = sorted(v); pos = {}
        for x in set(v):
            idx = [i for i, y in enumerate(s) if y == x]
            pos[x] = sum(idx) / len(idx)
        return [pos[x] for x in v]
    rx, ry = ranks(xs), ranks(ys); n = len(xs)
    mx, my = sum(rx) / n, sum(ry) / n
    num = sum((a - mx) * (b - my) for a, b in zip(rx, ry))
    den = sqrt(sum((a - mx) ** 2 for a in rx) * sum((b - my) ** 2 for b in ry))
    return num / den if den else 0.0


def rows(split):
    out = []
    for b in ds[f"{split}_blind"]:
        k = ds[f"{split}_key"][b["media_id"]]
        out.append({"mid": b["media_id"], "cap": b["caption"] or "", "split": split,
                    "media_type": raw.get(b["media_id"], {}).get("media_type", "?"),
                    "score": v3[b["media_id"]]["score"], "note": v3[b["media_id"]].get("note", ""),
                    **k})
    return out


def metrics(rs, score_key="score", cut=70, label_key="label"):
    boom = [r for r in rs if r[label_key] == "爆"]
    flag = [r for r in rs if r[score_key] >= cut]
    hit = [r for r in boom if r[score_key] >= cut]
    fp = [r for r in flag if r[label_key] != "爆"]
    rho = spearman([r[score_key] for r in rs], [r["engagement_rate"] for r in rs])
    return (f"召回 {len(hit)}/{len(boom)}｜誤報 {len(fp)}/{len(flag)}｜spearman {rho:.2f}")


dev, hold = rows("dev"), rows("holdout")
allr = dev + hold

print("== A. v3 門檻敏感度（A/S 門檻＝判定為爆文的分數線）==")
for cut in (70, 65, 60, 55):
    print(f"  cut={cut}: dev {metrics(dev, cut=cut)}   holdout(僅參考) {metrics(hold, cut=cut)}")

print("\n== B. 標籤定義敏感度（v3 分數不變，只換「爆文」定義；dev+holdout 共 64 篇）==")
ers = sorted((r["engagement_rate"] for r in allr), reverse=True)
views = sorted(r["views"] for r in allr)
med_v = st.median(views)
print(f"  views 中位數 = {med_v}")
print(f"  v3 分數 vs views spearman（與標籤無關）= {spearman([r['score'] for r in allr], [r['views'] for r in allr]):.2f}")
for name, fn in [
    ("原定義：ER 前 20%", lambda r: r["label"] == "爆"),
    ("ER 前 20% 且 views ≥ 中位數", lambda r: r["label"] == "爆" and r["views"] >= med_v),
    ("ER 前 20% 且 views ≥ 1000", lambda r: r["label"] == "爆" and r["views"] >= 1000),
    ("views 前 20%", lambda r: r["views"] >= sorted(views, reverse=True)[int(len(views) * 0.2) - 1]),
]:
    for r in allr: r["_lab"] = "爆" if fn(r) else "普"
    n = sum(r["_lab"] == "爆" for r in allr)
    boom = [r for r in allr if r["_lab"] == "爆"]
    print(f"  {name}: 爆 {n} 篇｜v3≥70 抓到 {sum(r['score'] >= 70 for r in boom)}/{n}")
small = [r for r in allr if r["label"] == "爆" and r["views"] < 1000]
print("  views < 1000 的『爆文』：", [(r["mid"], r["views"], r["likes"] + r["replies"] + r["reposts"] + r["quotes"]) for r in small])

print("\n== C. 媒體類型基準率（judge 盲評時看不到 IMAGE/VIDEO，全被壓成 POST）==")
by = {}
for r in allr:
    by.setdefault(r["media_type"], []).append(r)
for mt, rs in sorted(by.items()):
    print(f"  {mt}: {sum(r['label']=='爆' for r in rs)}/{len(rs)} 爆")

print("\n== D. 「獨家切入」判準稽核：v3 note 提到「獨家」的貼文 ==")
ang = [r for r in allr if "獨家" in r["note"] and "無獨家" not in r["note"] and "非作者" not in r["note"]]
for r in sorted(ang, key=lambda r: -r["engagement_rate"]):
    print(f"  {r['label']} er={r['engagement_rate']:.4f} views={r['views']} v3={r['score']} {r['mid']} {r['cap'][:28]!r}")
print(f"  → v3 判「有獨家切入」{len(ang)} 篇，其中爆文 {sum(r['label']=='爆' for r in ang)} 篇")

print("\n== E. 實用收藏 proxy（純關鍵字，非 LLM；只用來看方向）==")
# 注意：這個 proxy 是看過 holdout 盲區之後才寫的，天生偏向抓到證照文，只能看方向、不能當成績。
SAVE = re.compile(r"收藏|懶人包|步驟|證照|證書|必考|清單|一次搞懂|教你|攻略|怎麼答|整理好")
LIST_LINE = re.compile(r"^\s*(\d+[\.、)]|\d\ufe0f?\u20e3|✅|•|-)\s*", re.M)
def save_proxy(cap):
    body = re.sub(r"#[^\s#]+", "", cap)  # 去掉 hashtag（#收藏 這種不算）
    return bool(SAVE.search(body)) or len(LIST_LINE.findall(body)) >= 3
for r in allr:
    r["save"] = save_proxy(r["cap"])
sv = [r for r in allr if r["save"]]
for r in sorted(sv, key=lambda r: -r["engagement_rate"]):
    rl = r["reposts"] / r["likes"] if r["likes"] else 0
    print(f"  {r['split']:7} {r['label']} er={r['engagement_rate']:.4f} views={r['views']} reposts={r['reposts']} "
          f"repost/like={rl:.2f} v3={r['score']} {r['mid']} {r['cap'][:24]!r}")
non = [r for r in allr if not r["save"] and r["cap"].strip()]
print(f"  命中 {len(sv)} 篇：ER 中位數 {st.median(r['engagement_rate'] for r in sv):.4f}；"
      f"其餘非空內文 {len(non)} 篇：ER 中位數 {st.median(r['engagement_rate'] for r in non):.4f}")
def rl(r): return r["reposts"] / r["likes"] if r["likes"] >= 10 else None
a = [x for x in (rl(r) for r in sv) if x is not None]; b = [x for x in (rl(r) for r in non) if x is not None]
print(f"  reposts/likes 中位數（likes≥10）：命中 {st.median(a):.3f}（n={len(a)}）vs 其餘 {st.median(b):.3f}（n={len(b)}）")

print("\n== F. 模擬：v3 分數 ×0.85 + 收藏 proxy 15 分（粗估 v4 加維度的方向，非真實 v4）==")
for r in allr:
    r["sim"] = round(r["score"] * 0.85 + (15 if r["save"] else 0))
for cut in (70, 65, 60):
    print(f"  cut={cut}: dev {metrics(dev, 'sim', cut)}   holdout(僅參考) {metrics(hold, 'sim', cut)}")

print("\n== G. caption 長度 vs ER（dev）==")
print(f"  spearman = {spearman([len(r['cap']) for r in dev], [r['engagement_rate'] for r in dev]):.2f}")

# ---- 選用：本機若有 Jev v4 題組預測（未 commit），做「加總制 vs 路徑制」重組 ----
p4d, p4h = ROOT / "predictions_v4_dev.json", ROOT / "predictions_v4_holdout.json"
if p4d.exists() and p4h.exists():
    print("\n== H.（選用）Jev v4 各維度重組：加總制 vs 路徑制（不重新呼叫 Jev）==")
    MAX = {"identity": 20, "angle": 15, "save_value": 10}
    for split, path, rs in (("dev", p4d, dev), ("holdout", p4h, hold)):
        p4 = {p["media_id"]: p for p in json.load(open(path, encoding="utf-8"))}
        for r in rs:
            d = p4[r["mid"]]["dims"]
            r["v4add"] = p4[r["mid"]]["score"]
            route = max(d["identity"] / 20, d["angle"] / 15, d["save_value"] / 10)  # 0–1
            shared = d["hook"] + d["substance"] + d["audience"] + d["reply"] + d["format"]  # 滿分 55
            r["v4route"] = round(route * 45 + shared)
        print(f"  {split}: 加總制 {metrics(rs, 'v4add')}｜路徑制 {metrics(rs, 'v4route')}")
