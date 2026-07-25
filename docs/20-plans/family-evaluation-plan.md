# 家族版 評価計画書

作成日: 2026-07-26 / 対象期間: **家族版リリース後の2ヶ月（Phase 1.9）**

> この2ヶ月で集めたデータをもとに、`../00-business/go-nogo-plan.md` の判断を行う。
> **期間中は新機能を実装しない。** 作りながら評価すると、何が効いたのか分からなくなる。

---

## 1. 何のための期間か

| 目的 | 具体的に知りたいこと |
|---|---|
| **商品価値の検証** | 娘は使い続けるか。使って上達するか |
| **原価の実測** | 記事1本1.74円・1人月50円という試算は正しいか |
| **運用負荷の把握** | 月に何時間かかるか（撤退ライン③の前提） |
| **技術的な安定性** | Free枠で足りるか。障害は起きないか |

---

## 2. 測るもの

### 2.1 自動で貯まるもの（DBから取得）

| 指標 | 取得元 | 見方 |
|---|---|---|
| 学習日数・頻度 | `practices` / `assessments` の `occurred_at` | 週あたり何日使ったか |
| 作文数 | `sentences` | 月150文の無料枠は妥当か |
| **消費トークン** | `usage_logs.input_tokens / output_tokens` | **原価の裏取り（最重要）** |
| **発音評価の利用量** | `usage_logs` の `audio_seconds` / `calls` | Azureは音声の秒数で課金。**F0無料枠は月5時間＝18,000秒**。使用率が何%か（超過したら翌月まで使えない） |
| 発音スコアの推移 | `assessments.scores.pron` | 上達しているか＝商品価値の証拠 |
| 苦手語の推移 | `assessments.words` | 弱点が減っているか |

### 2.2 手で記録するもの

| 指標 | 方法 | 頻度 |
|---|---|---|
| 娘の感想 | 対話。「使いにくいところ」「あったらいいもの」 | 2週に1回 |
| **使った機能／使わなかった機能** | 観察とヒアリング。区切り編集・速度プリセット・履歴検索・記録タブなど | 2週に1回 |
| 運用時間 | 障害対応・調整にかけた時間をメモ | 都度 |
| 障害・不具合 | 内容と対応をメモ | 都度 |

---

## 3. 集計の手順（月1回）

```sql
-- 原価の実測 ①LLM（Gemini はトークン課金）
select kind, model, count(*) as rows,
       sum(input_tokens) as in_tok, sum(output_tokens) as out_tok,
       round(avg(input_tokens)) as avg_in, round(avg(output_tokens)) as avg_out
from usage_logs
where created_at >= now() - interval '30 days'
  and kind in ('translate', 'keywords')
group by kind, model;

-- 原価の実測 ②発音評価（Azure は【音声の長さ】で課金。トークン列では測れない）
--   ★ F0 無料枠は月5時間 = 18,000秒。中国語は1回で2回呼ぶため2倍で計上済み。
select date_trunc('month', created_at) as month,
       count(*)                as assessments,
       sum(calls)              as azure_calls,
       round(sum(audio_seconds))            as total_seconds,
       round(sum(audio_seconds) / 3600.0, 2) as hours,
       round(100 * sum(audio_seconds) / 18000.0, 1) as pct_of_free_quota,
       round(avg(audio_seconds), 1)         as avg_seconds
from usage_logs
where kind = 'assess'
group by 1 order by 1 desc;

-- 1人あたり月いくらか（条件Cの判定用）
select user_id,
       round(sum(audio_seconds))             as assess_seconds,
       sum(input_tokens + output_tokens)     as llm_tokens
from usage_logs
where created_at >= now() - interval '30 days'
group by user_id;

-- 利用頻度（ユーザー別・日別）
select user_id, date(occurred_at) as d, count(*) as n
from practices
where occurred_at >= now() - interval '60 days'
group by 1, 2 order by 2 desc;

-- 週あたりの学習日数（条件A「週2日以上が2ヶ月継続」の判定用）
select user_id, date_trunc('week', occurred_at) as wk,
       count(distinct date(occurred_at)) as days
from practices
where occurred_at >= now() - interval '60 days'
group by 1, 2 order by 2;

-- 発音スコアの推移
select date(created_at) as d, lang,
       round(avg((scores->>'pron')::numeric)) as avg_pron, count(*) as n
from assessments
where created_at >= now() - interval '60 days'
group by 1, 2 order by 1;
```

---

## 4. 中間チェック（1ヶ月時点）

**この時点では判断しない。軌道修正のためだけに見る。**

| 確認事項 | 対応 |
|---|---|
| 娘が使っていない | **理由を聞く。** UXの問題なら直す（実装凍結の例外） |
| 原価が想定の3倍以上 | プロンプト・モデルを見直す |
| Free枠を圧迫している | 使用量の内訳を確認 |
| **Azure F0 の月5時間に迫っている**（使用率70%超） | 娘の利用が増えている良い兆候。S0への切替を検討する（`AZURE_SPEECH_TIER=s0`） |
| **429（同時実行）が頻発** | F0は同時1件。使う時間帯をずらすか S0 へ |
| 障害が頻発している | 原因を潰す |

---

## 5. 並行して進めてよいこと（調査のみ）

実装は凍結するが、**Phase 1.5 の前提となる調査**は進めてよい。

1. 中国語ソースの方針決定（アーカイブ / 台湾政府系 / 英語のみ）
2. arXiv のカテゴリ特定と実供給量の計測
3. 各サイトの robots.txt・利用規約の確認
4. **「教材にする価値がある記事」の判断基準の言語化** ← GO条件E。最重要
5. **記事生成の手動試作**（GO条件F）。**アプリには実装しない**手元スクリプトに限る。
   これは §7 の「新機能の追加」には当たらない（アプリの挙動を変えないため）

> 4 は机上で考えるより、**実際に自分が記事を選ぶときに「なぜ選んだか」をその場でメモする**のが早い。
> 20〜30件貯まれば、共通する判断軸が見えてくる。

---

## 6. 期間終了時の成果物

**1ページの評価レポート。** 以下を数字と事実で埋める。

```
1. 利用実績     … 娘/自分の週あたり学習日数、作文数、発音チェック回数
2. 上達         … 発音スコアの推移、苦手語の減少
3. 原価         … 記事1本あたり・1人月あたりの実測値（円）
4. 運用負荷     … 月あたりの時間、障害件数
5. 定性         … 娘の感想（そのまま引用する）
6. 目利きの言語化 … 判断軸が書けたか／書けなかったか
7. 使われた機能 … 2ヶ月で一度も使われなかった機能（事業版から落とす候補）
8. 結論         … GO / NO-GO / 延長
```

これをもって `../00-business/go-nogo-plan.md` §2 の表を埋め、判断する。

---

## 7. この期間で避けること

| やらないこと | 理由 |
|---|---|
| 新機能の追加 | 何が効いたか分からなくなる。UX上の不具合修正は例外 |
| 他人への公開 | 法務対応が未了。評価軸も家族に絞る |
| 判断の先送り | 期日を決めて必ず結論を出す（曖昧なまま実装に入らない） |

---

### 関連文書

- `../00-business/go-nogo-plan.md` — この評価をもとに何を判断するか
- `execution-plan.md` — 全体の工程
- `../10-specs/family-edition-spec.md` — 評価対象の仕様
