# threads-eval

Threads 爆文評分器（`threads-post-judge`）的評測資料集、評分腳本與結案報告。

## 背景

把 threads-post-judge 從「一份 prompt」升級成「可驗證的 eval」：
用 @cychenac 69 篇歷史貼文 + 真實 insights（views/likes/replies/reposts/quotes）做盲評測試，迭代三版 rubric。

## 方法

- 64 篇（views ≥ 200）→ 爆文 = engagement rate（(likes+replies+reposts+quotes)/views）前 20%（12 篇爆文 / 52 篇普文）
- dev 45 篇（調 rubric 用）/ holdout 19 篇（只跑一次最終驗證，seed 42）
- 評分時只看內文 + 貼文類型，看不到任何數據（盲評）

## 三版成績（dev, n=45）

|  | v1 | v2 | v3 |
|---|---|---|---|
| 爆文召回率 | 20% | 20% | **50%** |
| 誤報率 | 82% | 33% | **0%** |
| 排序相關 (spearman) | 0.49 | 0.60 | **0.66** |

迭代學到的事：

- **v1→v2**：「回覆槓桿」權重太高（他的爆文不靠回覆，康輔社文 15 萬瀏覽只有 49 回覆）；
  身份情感共鳴加權；二手數據整理降權。誤報率 82%→33%。
- **v2→v3**：v2 矯枉過正，把他全帳號互動率最高的文（Anthropic 154 頁報告挖台灣角度，8.5%）
  壓到 57 分。修正：**評的不是一手/二手，是有沒有獨家切入角度**。召回率 20%→50%，誤報率歸零。

## Holdout 最終驗證（n=19，從未參與調參）

- 召回率 0%（0/2）、誤報率 0%、spearman 0.07
- 2 篇漏掉的都是特殊案例：
  1. Claude 證照整理 carousel（15.9 萬瀏覽、634 轉發）：**實用收藏型**是 rubric 沒 cover 到的爆文類型
     → **v4 方向：新增「實用收藏價值」維度**
  2. 「有沒人也在現場的？」（配圖文，caption 只有一句）：caption-only 盲評的方法盲點
- Holdout n=19 太小（只有 2 篇真爆文），數字本身噪音大；但它成功暴露了真缺口，
  這正是保留集的價值。**沒有拿 holdout 回頭調參**，保持驗證乾淨。

## 他的爆文公式（eval 證實）

1. 具體個人記憶 + 身份群體共鳴（台灣人/留學生/校友）→ 讚+轉發驅動
2. 獨家切入角度（台灣視角重挖、親手重算）→ 一手二手都可以爆
3. 實用收藏型 carousel（v4 待補）
4. 數據密度高 ≠ 會爆；回覆數不是必要條件

## 檔案

- `EVAL_REPORT.md`：完整結案報告
- `eval_dataset.json`：dev/holdout 切分 + 爆文標籤
- `all_posts.json` / `insights.json`：原始貼文與 insights（69 篇）
- `build_dataset.py`：dataset 建構腳本
- `metrics.py`：評分指標（`python3 metrics.py dev|holdout`）
- `predictions_v1.json` / `predictions_v2.json` / `predictions_v3.json`：各版在 dev 上的預測
- `pred_holdout.json`：v3 在 holdout 上的預測
- `judge/SKILL.md`：v3 凍結版 rubric（線上生效中）

註：中間產物（batch_*.json、pred 分片檔）已省略，可由腳本重跑。
