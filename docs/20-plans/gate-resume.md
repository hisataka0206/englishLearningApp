# ゲート再開メモ（カレンダーから飛んでくる先）

家族版リリース: **2026-07-26** ／ 評価期間: **2ヶ月**

| 日付 | やること |
|---|---|
| 2026-08-26（水） | **中間チェック**（判断はしない。軌道修正だけ） |
| 2026-09-26（土） | **GO / NO-GO 判断** |

---

## 貼り付け用プロンプト

カレンダーの予定にも同じものを入れてある。Cowork にそのまま貼れば再開できる。

### 中間チェック（1ヶ月）

```
englishLearningApp の家族版、中間チェックの日です。
docs/20-plans/gate-resume.md と docs/20-plans/family-evaluation-plan.md を読んで、
Supabase から集計SQLを流す手順を出してください。
判断はまだしません。軌道修正が必要かだけ見ます。
```

### GO / NO-GO 判断（2ヶ月）

```
englishLearningApp の家族版、GO/NO-GO 判断の日です。
docs/20-plans/gate-resume.md、docs/20-plans/family-evaluation-plan.md、
docs/00-business/go-nogo-plan.md を読んで、
評価レポート（1ページ）の雛形と、埋めるべき数字を出すSQLをください。
そのうえで GO / NO-GO / 延長 のどれかを、数字と事実で判断します。
```

---

## 見るファイル

| 目的 | パス |
|---|---|
| **何を測るか・集計SQL** | `family-evaluation-plan.md` |
| **判断基準（A〜D / E〜G / X〜W）** | `../00-business/go-nogo-plan.md` |
| GO のとき次に作るもの | `../10-specs/saas-diff-spec.md`（特に §10「初期リリースに含めないもの」） |
| 原価・料金の前提 | `../00-business/pricing-plan.md` |
| 撤退ライン（事業開始**後**の話） | `../00-business/exit-plan.md` |
| 家族版の仕様・運用 | `../../apps/family/README.md` |

Supabase ダッシュボード → SQL Editor で流す。プロジェクト: `hnjpsvqoldcfuyyjztwa`

---

## 集計SQL（そのまま貼れる）

### 1. 娘と自分がどれだけ使ったか（条件A・B）

```sql
-- 週あたりの学習日数（条件A「週2日以上が2ヶ月継続」）
select user_id, date_trunc('week', occurred_at) as wk,
       count(distinct date(occurred_at)) as days
from practices
where occurred_at >= now() - interval '60 days'
group by 1, 2 order by 2;
```

### 2. 原価の実測（条件C）

```sql
-- LLM（Gemini はトークン課金）
select kind, model, count(*) as rows,
       sum(input_tokens) as in_tok, sum(output_tokens) as out_tok
from usage_logs
where created_at >= now() - interval '30 days'
  and kind in ('translate','keywords')
group by kind, model;

-- 発音評価（Azure は音声の秒数で課金。F0無料枠は月5時間＝18,000秒）
select date_trunc('month', created_at) as month,
       count(*) as assessments, sum(calls) as azure_calls,
       round(sum(audio_seconds)) as total_seconds,
       round(100 * sum(audio_seconds) / 18000.0, 1) as pct_of_free_quota
from usage_logs where kind = 'assess'
group by 1 order by 1 desc;
```

### 3. 上達しているか（商品価値の裏づけ）

```sql
select date(created_at) as d, lang,
       round(avg((scores->>'pron')::numeric)) as avg_pron, count(*) as n
from assessments
where created_at >= now() - interval '60 days'
group by 1,2 order by 1;
```

---

## 判断の骨子（詳細は go-nogo-plan.md）

**必須条件A〜Dを1つでも欠いたら NO-GO。** そのうえで E〜G のどれかがあれば GO。

| | 条件 | しきい値 |
|---|---|---|
| **A** | **娘が使い続けている** | **週2日以上が2ヶ月**（最重要） |
| B | 自分も使っている | 週1日以上 |
| C | 原価が想定内 | 作文 0.02円/文以下、1人あたり月50円以下 |
| D | 復旧不能な事故が0件 | — |
| E | **目利きの言語化ができた** | 「教材にする価値がある記事」の基準が他人に指示できる形に |
| F | 記事フィードの試作が動いた | 手元スクリプトでよい |
| G | 外部の需要の兆候 | 補助的。能動的な計測手段はない |

**NO-GO は失敗ではない。** 家族版はそのまま月10円程度で使い続けられる。

---

## 評価期間中にやらないこと

- **新機能の追加**（UX上の不具合修正は例外）
- 他人への公開
- 判断の先送り

## 並行して進めてよいこと（調査のみ）

1. 中国語ソースの方針決定
2. arXiv のカテゴリ特定と実供給量の計測
3. robots.txt・利用規約の確認
4. **「教材にする価値がある記事」の判断基準の言語化** ← 条件E。最重要
5. 記事生成の手動試作（アプリには実装しない手元スクリプト）

---

## 未対応で残っているもの

| 項目 | 影響 |
|---|---|
| ~~定期バックアップ~~ | **対応済み**（週次JSONダンプ・90日保持）。完全な `pg_dump` は事業版に進むときに |
| R/V/T/N 分類のアライメント | 欠落を「置換」として分類しており、集計にノイズ |
| 移行スクリプトの `fails`/`practices` | 冪等でない（再実行すると倍になる） |
| `sentences.memo` 列 | 実装で未使用。廃止するか決める |

詳細は `../40-tests/spec-review-family-saas.md` §3。
