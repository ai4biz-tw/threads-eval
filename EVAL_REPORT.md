# Threads 爆文 Judge Eval — 結案報告（2026-09-24）

## 做了什麼
把 threads-post-judge 從「一份 prompt」升級成「可驗證的 eval」：
用 @cychenac 69 篇歷史貼文 + 真實 insights（views/likes/replies/reposts/quotes）
做盲評測試，迭代三版 rubric。

## 方法
- 64 篇（views ≥ 200）→ 爆文 = engagement rate 前 20%（12 篇）
- dev 45 篇（調 rubric 用）/ holdout 19 篇（只跑一次最終驗證）
- 評分時只看內文，看不到任何數據（盲評）

## 三版成績（dev, n=45）
| | v1 | v2 | v3 |
|---|---|---|---|
| 爆文召回率 | 20% | 20% | **50%** |
| 誤報率 | 82% | 33% | **0%** |
| 排序相關 (spearman) | 0.49 | 0.60 | **0.66** |

## 每次迭代學到的事
- **v1→v2**：回覆槓桿 30 分太高（他的爆文不靠回覆，康輔社文 15 萬瀏覽只有 49 回覆）；
  身份情感共鳴從 15→30 分；二手數據整理降權。誤報率 82%→33%。
- **v2→v3**：v2 矯枉過正，把他全帳號互動率最高的文（Anthropic 154 頁挖台灣，8.5%）
  壓到 57 分。修正：評的不是一手/二手，是**有沒有獨家切入角度**。
  召回率 20%→50%，誤報率歸零。

## Holdout 最終驗證（n=19，從未參與調參）
- 召回率 0%（0/2）、誤報率 0%、spearman 0.07
- 2 篇漏掉的都是特殊案例：
  1. Claude 證照整理 carousel（15.9 萬瀏覽、634 轉發）：**實用收藏型**是 rubric
     沒 cover 到的爆文類型 → v4 方向：新增「實用收藏價值」維度
  2. 「有沒人也在現場的？」（配圖文，caption 只有一句）：只看文字無法評，
     這是 caption-only 盲評的方法盲點
- Holdout n=19 太小（只有 2 篇真爆文），數字本身噪音大；但它成功暴露了真缺口，
  這正是保留集的價值。**沒有拿 holdout 回頭調參**，保持驗證乾淨。

## 他的爆文公式（eval 證實）
1. 具體個人記憶 + 身份群體共鳴（台灣人/留學生/校友）→ 讚+轉發驅動
2. 獨家切入角度（台灣視角重挖、親手重算）→ 一手二手都可以爆
3. 實用收藏型 carousel（v4 待補）
4. 數據密度高 ≠ 會爆；回覆數不是必要條件

## 檔案
- `eval_dataset.json`：dev/holdout 切分 + 標籤
- `metrics.py`：`python3 metrics.py dev|holdout`
- `predictions_v1/v2/v3.json`、`pred_holdout.json`：各版預測
- `../skills/threads-post-judge/SKILL.md`：v3 凍結版 rubric（線上生效中）

---

# v4：Jev 題組版（2026-09-25，threads-eval#1）

## 為什麼做 v4
1. 回應 v3 holdout 的兩個盲區：實用收藏型 carousel、caption-only 配圖文
2. 把 judge 從 Claude prompt（`judge/SKILL.md`）改成 Jev 題組（`jev/threads_judge.py`），
   才能在 CI 裡對每一則文案自動評分（ai4biz-tw board R10）

## v4 改了什麼
- 新增「實用收藏價值」維度（清單、步驟、懶人包、證照整理、範本）
- 「獨家切入角度」改成列舉式判準，任一成立即算獨家：
  1. 從冷門或外文原始資料挖出沒人講過的在地（台灣）角度
  2. 親手重算、比對出新數字
  3. 有證據的反共識結論
  4. 作者親身經歷的第一手現場
- 新增「內容份量」維度：dev 上 caption 長度與互動率的 spearman 是 +0.52，一兩句話的短文幾乎都不爆
- 格式紀律改用程式機械判定（主文連結、hashtag 數、段落長度），不花 Jev 題
- caption 少於 60 字標 `low_confidence`（caption-only 盲評的方法限制，照實標示，不硬評）
- 各維度分數＝Σ P(等級)×分值，用 Jev 回傳的機率算期望值，不取 argmax

## 迭代（dev n=45，上限 3 輪）
| | 召回率 | 誤報率 | spearman | 改了什麼 |
|---|---|---|---|---|
| v3（Claude） | **50%** | **0%** | **0.66** | 對照組 |
| v4 第 1 輪 | 20% | 33% | 0.40 | 獨家切入拆成 4 題 noul |
| v4 第 2 輪（凍結） | 30% | 57% | 0.50 | 獨家切入改單題 choice＋內容份量＋依鑑別力重配權重 |
| v4 第 3 輪 | 10% | 67% | 0.49 | Hook 25→15、獨家 15→25，更差，退回第 2 輪 |

第 1 輪各維度鑑別力（spearman vs 互動率）：Hook +0.46、受眾 +0.38、身份共鳴 +0.20、收藏 +0.15、
回覆 +0.06、**獨家切入（4 題 noul）+0.03**。改成單題 choice 後，獨家切入升到 +0.45。
所以問題不在判準本身，而在 noul 題型：Jev 對「是否從冷門資料挖出在地角度」這類需要綜合判斷的是非題幾乎給 0.5。

## Holdout（n=19，只跑一次）
| | 召回率 | 誤報率 | spearman |
|---|---|---|---|
| v3（Claude） | 0% (0/2) | — | 0.07 |
| v4（Jev） | 0% (0/2) | — | 0.16 |

- **Claude 證照整理 carousel**：新的「收藏價值」給 8.6/10，**這個維度確實抓到了**；
  但身份共鳴 2.1、獨家切入 2.9，總分 46 仍是 C。
- 真正的發現：**爆文有兩條不相干的路**（身份共鳴，或實用收藏），加總式 rubric 會把只走一條路的文壓下去。
  → v5 方向：改成「取最強的那條路」的計分方式（max of routes），不是再加權重。這個結論來自 holdout，
  依規則**沒有回頭調參**，留給 v5 用新資料驗證。
- 「有沒人也在現場的？」仍被標 low_confidence，符合預期。

## 結論
- v4 Jev 版**沒有贏過 v3 Claude 版**，`judge/SKILL.md` 維持 v3 線上。
- v4 的用途：CI 閘門裡的**爆文參考分數**（只顯示、不擋 merge），每次呼叫都記進 Jev Ledger。
- Jon 的第 2 題「獨家切入夠不夠落地」：v4 的四條列舉判準可以直接寫回 SKILL.md（Claude 版）；
  Jev 版要用單題 choice，不能拆成是非題。
- 重跑：`python3 jev/threads_judge.py dev|holdout` → `python3 metrics.py dev|holdout predictions_v4_<split>.json`
  （Jev 回應快取在 `jev/cache_v4.jsonl`，同版題組不重複計費）
