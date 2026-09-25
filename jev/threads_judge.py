"""Threads 爆文評分器 v4 —— Jev 題組版（threads-post-judge 的可機器化版本，CI 閘門也用它）。

v4 相對 v3（judge/SKILL.md）：
  1. 新增「實用收藏價值」15 分（holdout 盲區：Claude 證照整理 carousel 15.9 萬瀏覽／634 轉發）
  2. 「獨家切入角度」改成列舉式判準（冷門資料挖在地角度／親手重算／有證據的反共識／第一手現場，任一成立）
     ——第 1 輪拆成 4 條 noul，dev 上鑑別力 +0.03（等於沒有），第 2 輪改成單題 choice
  3. 新增「內容份量」：dev 上 caption 長度與互動率 spearman +0.52，一兩句話的短文幾乎不爆
  4. 格式紀律改由程式機械判定（連結、hashtag 數、段落長度），不花 Jev 題
  5. caption 太短的配圖文標 low_confidence（caption-only 盲評的方法限制，照實標，不硬評）
權重（凍結＝第 2 輪）：Hook 25／身份共鳴 20／獨家切入 15／內容份量 10／收藏價值 10／受眾匹配 10／
  回覆槓桿 5／格式 5 ＝ 100。第 3 輪試過 Hook 15＋獨家 25，dev 召回 30%→10%，退回第 2 輪。
dev 成績（n=45）：召回 30%、誤報 57%、spearman 0.50——仍輸 v3 Claude 版（50%／0%／0.66），見 EVAL_REPORT。
各維度分數＝Σ P(等級)×分值（期望值），不用 argmax，保留 Jev 的不確定性。

用法：
  python3 jev/threads_judge.py dev|holdout     # 盲評 eval_dataset.json → predictions_v4_<split>.json
  python3 jev/threads_judge.py text <file>     # 評單篇文字（CI 閘門用）
回應快取在 jev/cache_v4.jsonl（同版題組、同一篇不重複計費；題組一改 VERSION 就要跳號）。
"""
import hashlib, json, re, sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent
sys.path.insert(0, str(HERE))
from client import evaluate  # noqa: E402

VERSION = "threads-judge-v4"
CACHE = HERE / "cache_v4.jsonl"
SHORT_CAPTION = 60  # 字元；低於此值的配圖文 caption-only 盲評不可信

Q = {
 "identity": {"type": "choice",
   "question": "這篇文的身份情感共鳴有多強？看的是作者本人的經歷，以及它有沒有打中某個具體身份群體的共同記憶。",
   "criteria": {"強": "作者第一手的具體個人記憶或經歷，並打中特定身份群體（台灣人、留學生、校友、父母、被裁員的人、打工人…）的集體經驗",
                "中": "有身份感或個人色彩，但偏旁觀評論，或群體不夠具體",
                "弱": "幾乎是資訊整理或評論，沒有「人」的味道"}},
 "hook": {"type": "choice",
   "question": "只看開頭前 40 個字（未展開時看得到的部分），讓人想點開看全文的力道有多強？",
   "criteria": {"強": "具體數字反差、反直覺結論、懸念，或一句話就把人拉進某個場景",
                "中": "主題清楚但不鉤人",
                "弱": "「今天想分享」「關於 X 的一些想法」這類平淡或抽象的開場"}},
 "save_value": {"type": "choice",
   "question": "讀者看完會不會想收藏這篇、或轉給別人留著備用？",
   "criteria": {"高": "可以照做或查閱的整理：清單、步驟、懶人包、證照／考試／工具整理、範本、完整攻略",
                "中": "有一兩個可以用的點，但不成體系",
                "低": "看完就過去，沒有留存的理由"}},
 "angle": {"type": "choice",
   "question": "這篇文有沒有別人寫不出來的獨家切入角度？（一手或二手資料都可以，看的是角度，不是來源）",
   "criteria": {"獨家": "至少一項成立：從冷門或外文原始資料挖出沒人講過的在地（台灣）角度，例如讀完 154 頁英文報告挑出寫到台灣的三段；親手重算或比對出新數字；有證據的反共識結論；作者親身經歷的第一手現場",
                "普通": "資訊正確紮實，但切入角度是一般人也想得到、媒體也會寫的",
                "搬運": "新聞或資料的摘要轉述，沒有自己的角度"}},
 "substance": {"type": "choice",
   "question": "以一則社群貼文來看，這篇內容的份量夠不夠？",
   "criteria": {"完整": "有完整的故事、論點或資訊，讀完有收穫",
                "普通": "有重點但偏短或偏淺",
                "單薄": "一兩句話的感想、梗或近況，沒有展開"}},
 "reply": {"type": "choice",
   "question": "這篇文自然引發讀者留言回覆的可能性？",
   "criteria": {"高": "有沒有標準答案的提問、邀請選邊站、或召喚讀者分享自己經驗",
                "中": "話題有討論空間，但沒有主動邀請",
                "低": "單向陳述，讀者沒有接話的切入點"}},
 "bait": {"type": "noul",
   "question": "這篇文是否含有互動誘餌（engagement bait）？",
   "instructions": "要求「留言+1」「同意請轉發」「按讚抽獎」「留言關鍵字領資料」這類以互動換好處或直接索取互動的句子為真；自然提問為假。"},
 "audience": {"type": "choice",
   "question": "這篇文鎖定的讀者群有多具體？",
   "criteria": {"具體": "明確打中一個具體群體（例如台灣的留美學生、某校校友、想考 AI 證照的上班族）",
                "普通": "有大致對象但範圍寬",
                "模糊": "寫給所有人，看不出對象"}},
}
LEVELS = {"identity": {"強": 20, "中": 11, "弱": 2},
          "hook": {"強": 25, "中": 12, "弱": 2},
          "angle": {"獨家": 15, "普通": 6, "搬運": 0},
          "substance": {"完整": 10, "普通": 5, "單薄": 0},
          "save_value": {"高": 10, "中": 5, "低": 0},
          "audience": {"具體": 10, "普通": 5, "模糊": 1},
          "reply": {"高": 5, "中": 2.5, "低": 0.5}}
QHASH = hashlib.sha1(json.dumps(Q, ensure_ascii=False, sort_keys=True).encode()).hexdigest()[:10]


def _ev(ans, levels):
    return sum(ans["probabilities"].get(k, 0) * v for k, v in levels.items())


def format_score(text):
    """格式紀律 5 分，機械判定：主文不放連結、tag 最多 1 個、不要一大坨文字。"""
    s, why = 5.0, []
    if re.search(r"https?://", text):
        s -= 2; why.append("主文有外部連結（演算法降權，改放第一則留言）")
    tags = re.findall(r"(?:^|\s)#[^\s#]+", text)
    if len(tags) > 1:
        s -= 1.5; why.append(f"hashtag {len(tags)} 個（Threads 一篇只用 1 個 topic tag）")
    paras = [p for p in re.split(r"\n\s*\n|\n", text) if p.strip()]
    if paras and max(len(p) for p in paras) > 160:
        s -= 1.5; why.append("有超過 160 字的段落，斷行不夠")
    return max(s, 0), why


def _cache_get(key):
    if CACHE.exists():
        for line in CACHE.read_text(encoding="utf-8").splitlines():
            r = json.loads(line)
            if r["key"] == key:
                return r["answers"]
    return None


def ask(text, *, repo, note=""):
    key = hashlib.sha1(f"{QHASH}|{text}".encode()).hexdigest()
    ans = _cache_get(key)
    if ans is None:
        ans = evaluate(text, Q, tag=VERSION, repo=repo, note=note)["answers"]
        with CACHE.open("a", encoding="utf-8") as f:
            f.write(json.dumps({"key": key, "note": note, "answers": ans}, ensure_ascii=False) + "\n")
    return ans


def score(text, post_type=None, *, repo="ai4biz-tw/threads-eval", note=""):
    a = ask(text, repo=repo, note=note)
    dims = {k: _ev(a[k], lv) for k, lv in LEVELS.items()}
    bait = a["bait"]["noul"]
    if bait > 0.5:  # 演算法明示降權：回覆槓桿歸零
        dims["reply"] = 0
    fmt, fmt_why = format_score(text)
    dims["format"] = fmt
    total = round(sum(dims.values()))
    tier = "S" if total >= 85 else "A" if total >= 70 else "B" if total >= 50 else "C"
    low_conf = len((text or "").strip()) < SHORT_CAPTION
    return {"score": total, "tier": tier, "dims": {k: round(v, 1) for k, v in dims.items()},
            "angle": a["angle"]["choice"], "bait": round(bait, 2),
            "format_issues": fmt_why, "low_confidence": low_conf, "rubric": VERSION}


def run_split(which):
    ds = json.load(open(ROOT / "eval_dataset.json", encoding="utf-8"))
    out = []
    for it in ds[f"{which}_blind"]:
        r = score(it["caption"] or "", it.get("post_type"), repo="ai4biz-tw/threads-eval#1",
                  note=f"{which}:{it['media_id']}")
        out.append({"media_id": it["media_id"], **r})
        print(f"{it['media_id']}\t{r['tier']} {r['score']:>3}\t{'LOWCONF ' if r['low_confidence'] else ''}{r['dims']}")
    dst = ROOT / f"predictions_v4_{which}.json"
    json.dump(out, open(dst, "w", encoding="utf-8"), ensure_ascii=False, indent=1)
    print(f"→ {dst.name}")


if __name__ == "__main__":
    if sys.argv[1] in ("dev", "holdout"):
        run_split(sys.argv[1])
    elif sys.argv[1] == "text":
        print(json.dumps(score(open(sys.argv[2], encoding="utf-8").read()), ensure_ascii=False, indent=1))
