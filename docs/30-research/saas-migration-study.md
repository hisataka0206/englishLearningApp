# English Learning App — [[SaaS化]]移行設計書

作成日: 2026-07-25 / 最終更新: 2026-07-25（記事フィードのAPI・画面・著作権要件を追加）
対象リポジトリ: `englishLearningApp`

---

> ## ⚠️ 本書の位置づけ（2026-07-26 改訂）
>
> 本書は**背景・意思決定・法務要件を記録する文書**であり、**実装仕様書ではない**。
> 実装は以下の3本を使うこと。本書の §5（スキーマ）§6（API）§7（画面）は**参考情報**であり、
> 家族版と事業版の内容が混在しているため、**正典は下記に移譲済み**。
>
> | 用途 | 正典 |
> |---|---|
> | 現行機能の移植チェックリスト | **`../10-specs/current-app-spec.md`** |
> | 家族版の実装仕様 | **`../10-specs/family-edition-spec.md`** |
> | 事業版の差分仕様 | **`../10-specs/saas-diff-spec.md`** |
> | 情報源・ライセンス | `content-sources.md` |
> | 料金・原価 | `../00-business/pricing-plan.md` |
> | 撤退 | `../00-business/exit-plan.md` |
>
> **本書に残る固有の価値**：§2（提供形態の比較）§3（認証基盤の比較）§10（法務要件）§11（リスク）。
> これらは他文書に重複がない。

---

## 0. エグゼクティブサマリ

現状は**完全な個人用ローカルアプリ**であり、有料展開するには**バックエンドの作り直し**が必要。ただし `index.html`（UI）と学習ロジックは資産としてほぼ全量流用できる。

**推奨構成**

| レイヤ | 推奨 | 理由 |
|---|---|---|
| 提供形態 | [[PWA]]（クラウドSaaS） | ストア審査・手数料15〜30%を回避。既存UIをそのまま活かせる |
| LLM | 選別・語彙＝[[Gemini]] 2.5 Flash-Lite／書き下ろし＝[[gpt-5.4-mini]]（Proは gpt-5.4） | 作文 約0.015円/文、記事1本 1.74円（Pro 5.37円）。原価が制約にならない |
| 認証・DB | [[Supabase]]（Auth + Postgres + [[RLS]]） | 認証・DB・行レベルセキュリティが一体。個人開発の最短ルート |
| 課金 | [[Stripe]] Billing（実効手数料 4.3%） | ストア課金の1/4以下 |
| 音声 | [[Web Speech API]]（現状維持） | **クラウドTTSを使わないことが最大の原価優位**。ここは変えない |
| 情報源 | [[Global Voices]] 40% / [[arXiv]] 30% / 政府系PR 20% / Wikipedia補助 10% | **すべて [[ShareAlike]] なし**。詳細は `content-sources.md` |

**収益モデル**：作文・翻訳・発音は**無料（月150文の上限あり）**。有料機能は「**興味キーワードから学習教材が自動生成される[[記事フィード]]**」。
**損益分岐点：有料会員 10人**（8:2混在なら9人。詳細は `../00-business/pricing-plan.md`）。

> ⚠️ **重要①**：情報源として [[Weibo]] を使う設計は成立しない。規約が「API取得データの他用途利用」「第三者サーバーでの保存」を明示禁止しており、共有プール設計と真っ向から矛盾する。
> ⚠️ **重要②**：Wikipedia は **CC BY-SA（ShareAlike）** のため主軸には使えない。翻案物を CC BY-SA で提供する義務が生じ、利用規約に「無断転載禁止」が書けなくなる。補助（言語間リンクによる対訳語彙生成）に限定する。
> **情報源に関する正典は `content-sources.md`。**

---

## 1. 現状アーキテクチャの棚卸し

### 1.1 構成

```
[iPhone] --Tailscale VPN--> [自宅Mac]
                              ├─ server.py (Python標準ライブラリのみ, port 8765)
                              │    ├─ UI配信 (index.html)
                              │    ├─ /api/translate → localhost:11434 (Ollama)
                              │    └─ data/*.json 読み書き
                              └─ Google Drive (GAS Webアプリ経由でJSONアップロード)
```

### 1.2 有料展開の観点での致命的な前提

| # | 現状の前提 | 有料展開での問題 |
|---|---|---|
| 1 | **[[Ollama]] がローカル実行** | 他人のMacでは動かない。クラウドLLMへの置換が必須 |
| 2 | **[[Tailscale]] 経由でしか到達できない** | 一般ユーザーにVPN設定は求められない。公開HTTPSが必要 |
| 3 | **ユーザー概念が存在しない** | 全データがグローバル共有。`sentences.json` に user_id の概念なし |
| 4 | **認証が一切ない** | URLを知れば誰でも全データを読み書きできる |
| 5 | **保存先が開発者個人のGoogle Drive** | 他人の学習データを自分のDriveに入れるのは論外（個人情報保護法上も不可） |
| 6 | **JSONファイル全体をロック→全読み→全書き** | 同時アクセスで破綻。数十人規模でも耐えられない |
| 7 | **[[config.json]] にシークレット直書き** | サーバー環境変数への移行が必要 |
| 8 | Python標準ライブラリの `BaseHTTPRequestHandler` | シングルスレッド。CSRF/レート制限/入力検証なし |

### 1.3 そのまま流用できる資産

- `index.html` のUI全体（発音プレイヤー、フレーズ分割、履歴ビュー、中国語ピンイン対応）
- 翻訳・キーワード抽出の**プロンプト設計**（`translate()` / `extract_keywords()`）
- データモデルの考え方（sentence に fails / practices を配列で持つ設計はそのまま正規化できる）
- 「失敗履歴」「実施履歴」という**学習ログのコンセプト**。これが本アプリの差別化点

---

## 2. 提供形態の選択肢：メリット・デメリット

### 2.1 比較表

| 観点 | A. [[PWA]]（クラウドSaaS） | B. [[ネイティブアプリ]] | C. [[セルフホスト]]ライセンス |
|---|---|---|---|
| 決済手数料 | **4.3%**（Stripe） | 15〜30%（ストア） | 4.3% |
| 審査 | **なし**（即日リリース可） | あり（初回1〜2週、更新の度に発生） | なし |
| 既存UI流用 | **ほぼ100%** | 大幅な作り直し | 100% |
| 開発工数 | 中 | 大（iOS/Android各々） | 小 |
| サーバー運用コスト | 発生する | 発生する | **ゼロ** |
| 顧客獲得経路 | 自力集客のみ | ストア検索の流入がある | 極めて限定的 |
| 音声合成 | Web Speech API（**無料**） | ネイティブTTS（無料・高品質） | 無料 |
| プッシュ通知 | iOS PWAでも可（iOS16.4+） | 完全対応 | 不可 |
| オフライン動作 | 限定的 | 対応可 | ローカルなので強い |
| 解約・返金対応 | 自分で対応 | ストアが処理 | 自分で対応 |
| 法務負担 | [[特定商取引法]]表記が必須 | ストアが一部代行するが表記は必要 | 同左 |

### 2.2 各案の評価

**A. PWA（クラウドSaaS）— 推奨**

- ◎ 手数料が圧倒的に安い。月額980円なら手取り938円（ストア経由15%なら833円）
- ◎ 現在の `index.html` が既にモバイル前提で作られており、「ホーム画面に追加」の運用実績もある
- ◎ バグ修正が即反映。審査待ちがない
- △ ストアからの自然流入がゼロ。SNS・ブログ等での集客が全てになる
- △ iOSのWeb Speech APIは音声品質・挙動がSafariバージョン依存
- △ 「アプリ」としての信頼感がストア配信より弱く、初回の課金ハードルは上がる

**B. ネイティブアプリ**

- ◎ ストア検索からの流入が見込める。個人開発の最大の集客課題を一部解決
- ◎ 音声・バックグラウンド再生・通知が確実に動く
- ✗ 手数料が重い。Appleは[[小規模事業者プログラム]]（年間100万USD以下）で15%、Google Playは定期購入一律15%。それでもStripeの3.5倍
- ✗ UIの全面書き直し（React Native / Flutter）で工数が数倍
- ✗ 審査リジェクトのリスクと更新サイクルの遅さ

**C. セルフホストライセンス販売**

- ◎ サーバー運用コスト・障害対応・個人情報保護責任がほぼ発生しない
- ✗ 購入者が自分でOllamaとPythonを構築する必要があり、**顧客層が実質エンジニアのみ**。有料市場としてほぼ成立しない
- ✗ ライセンスキー検証は容易に回避される

### 2.3 結論

**A（PWA）で開始**し、有料会員が100人を超えて継続率が確認できた段階で、既存Web資産をラップする形（Capacitor等）でB（ストア配信）を集客チャネルとして追加する二段構えを推奨。

---

## 3. 認証・データ基盤の選択肢：メリット・デメリット

### 3.1 比較表

| 観点 | A. [[Supabase]] | B. [[Firebase]] | C. 自前（[[FastAPI]] + Postgres） |
|---|---|---|---|
| 認証 | メール/パスワード、Google、Apple、Magic Link 標準搭載 | 同等（実績豊富） | 全部自前実装 |
| DB | Postgres（リレーショナル） | Firestore（NoSQL） | Postgres |
| 権限分離 | **[[RLS]]（行レベルセキュリティ）でDB側で強制** | セキュリティルールで記述 | アプリ層で毎回チェック |
| 既存データとの相性 | 正規化が必要だが移行は容易 | **現在のJSON構造とほぼそのまま対応** | 正規化が必要 |
| 無料枠 | 500MB DB / 50,000 MAU | Auth 50,000 MAU 無料、Firestore 1GiB + 読取5万/日 | なし（サーバー代が直接発生） |
| 有料開始 | Pro $25/月 | 従量課金（Blaze） | Render等で $13/月〜 |
| 学習コスト | 中 | 中 | **高** |
| ベンダーロックイン | 低（素のPostgres。いつでも移設可） | **高**（Firestore固有のクエリモデル） | なし |
| 集計・分析クエリ | SQLで自由（弱点分析に強い） | 苦手（複雑な集計は別途実装） | SQLで自由 |
| 運用負荷 | 低 | 低 | **高**（バックアップ、パッチ、監視すべて自分） |

### 3.2 各案の評価

**A. Supabase — 推奨**

- ◎ **RLSがDB側で効くのが決定的**。`user_id = auth.uid()` のポリシーを1回書けば、アプリ側のバグでデータが混ざる事故を構造的に防げる。他人の学習データ漏洩は個人情報保護法上の報告義務事案になり得るため、ここは仕組みで担保すべき
- ◎ 「失敗ラベル別・日付別の弱点集計」といった本アプリの中核機能はSQLの方が圧倒的に書きやすい
- ◎ 素のPostgresなので、将来的に自前サーバーへ移設する場合も `pg_dump` で済む
- △ 無料プランは**1週間無操作でプロジェクトが一時停止**する。本番では Pro $25/月 が事実上必須
- △ 日本リージョン（Tokyo）は選べるが、Supabase自体は米国企業。外国にある第三者への提供として[[プライバシーポリシー]]への記載が必要

**B. Firebase**

- ◎ 現在の `sentences.json`（sentence配下に fails/practices を配列で持つ）の構造をほぼ無変換で移せる
- ◎ Auth の実績と日本語情報量が最多
- △ Firestore は「Fail履歴を月別・ラベル別に集計」といったクエリが苦手で、集計用のフィールドを二重管理するか BigQuery 連携が必要になる
- ✗ ロックインが強い。移行コストが後で効いてくる
- ✗ 読み取り課金モデルのため、履歴一覧を毎回全件読む現在の実装をそのまま持ち込むとコストが跳ねる

**C. 自前（FastAPI + Postgres）**

- ◎ 制約がなく、どんな要件にも対応できる
- ✗ パスワードハッシュ、セッション管理、メール確認、パスワードリセット、レート制限、ソーシャルログイン、OAuthのコールバック処理を全部自作・保守する必要がある
- ✗ **セキュリティ事故の責任を全部引き受ける**。個人開発でここに時間を使うのは投資対効果が悪い
- △ 選ぶとしたら、Supabaseの Auth だけ使い、APIサーバーはFastAPIで書くハイブリッドが現実的

### 3.3 結論

**A（Supabase）**。ただし「Supabaseに全部載せる」のではなく、以下の役割分担を推奨：

- **Supabase Auth** → ログイン・セッション（JWT発行）
- **Supabase Postgres + RLS** → 学習データ（クライアントから直接読み書き）
- **自前APIサーバー（軽量）** → LLM APIキーを守るための翻訳プロキシ。ここだけは絶対にクライアントに露出させられない。Supabase Edge Functions でも可

---

## 4. 目標アーキテクチャ

```
[ブラウザ / PWA]
   │  ①ログイン (Supabase Auth SDK)
   │  ②学習データCRUD (Supabase JS SDK → RLSで自分の行のみ)
   │  ③翻訳リクエスト (JWT付き)
   ▼
[Edge Function: /translate]  ← APIキーはここにのみ存在
   ├─ JWT検証 → user_id特定
   ├─ subscriptions テーブルでプラン確認
   ├─ usage_logs で当月使用量チェック（無料枠超過なら拒否）
   ├─ Gemini / OpenAI API 呼び出し
   └─ usage_logs に記録

[Stripe] ──Webhook──▶ [Edge Function: /stripe-webhook] ──▶ subscriptions テーブル更新
```

**音声合成はブラウザ内蔵のWeb Speech APIのまま**（サーバーを経由しない＝原価ゼロ）。

---

## 5. データベース設計

> ⚠️ **正典は移譲済み。** 家族版のスキーマとRLS全文は `../10-specs/family-edition-spec.md` §5、事業版の差分は `../10-specs/saas-diff-spec.md` §2 を参照。
> 以下は設計の経緯として残す。**§5.1b の記事フィード7テーブルの定義文は事業版の正典**（差分仕様書から参照されている）。

### 5.1 スキーマ

```sql
-- ユーザープロフィール（auth.users を拡張）
create table profiles (
  id uuid primary key references auth.users on delete cascade,
  display_name text,
  default_lang text not null default 'en',   -- 'en' | 'zh'
  default_rate numeric not null default 0.9, -- 発音速度
  created_at timestamptz not null default now()
);

-- 英文／中文
create table sentences (
  id uuid primary key default gen_random_uuid(),
  user_id uuid not null references auth.users on delete cascade,
  lang text not null default 'en',
  japanese text not null,
  target text not null,          -- 旧 english
  marked text,                   -- 「/」区切り位置付き
  pinyin text,
  memo text,
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now()
);
create index on sentences (user_id, lang, created_at desc);

-- 単語帳
create table words (
  id uuid primary key default gen_random_uuid(),
  user_id uuid not null references auth.users on delete cascade,
  lang text not null default 'en',
  word text not null,
  meaning text,
  example text,
  pinyin text,
  source_id uuid references sentences on delete set null,
  created_at timestamptz not null default now()
);
create index on words (user_id, lang, created_at desc);

-- 失敗履歴（配列→行に正規化。ここが分析機能の土台）
create table fails (
  id bigserial primary key,
  user_id uuid not null references auth.users on delete cascade,
  sentence_id uuid not null references sentences on delete cascade,
  label text not null default 'Fail',
  occurred_at timestamptz not null default now()
);
create index on fails (user_id, occurred_at desc);
create index on fails (sentence_id);

-- 実施履歴
create table practices (
  id bigserial primary key,
  user_id uuid not null references auth.users on delete cascade,
  sentence_id uuid not null references sentences on delete cascade,
  occurred_at timestamptz not null default now()
);
create index on practices (user_id, occurred_at desc);

-- サブスクリプション状態（Stripe Webhookが唯一の書き手）
create table subscriptions (
  user_id uuid primary key references auth.users on delete cascade,
  stripe_customer_id text unique,
  stripe_subscription_id text unique,
  plan text not null default 'free',      -- 'free' | 'standard' | 'pro'
  status text not null default 'inactive',-- active | trialing | past_due | canceled
  current_period_end timestamptz,
  updated_at timestamptz not null default now()
);

-- 使用量ログ（無料枠制御と原価把握）
create table usage_logs (
  id bigserial primary key,
  user_id uuid references auth.users on delete cascade,  -- 定期生成分は null
  kind text not null,             -- 'translate' | 'keywords'
                                  -- | 'screening' | 'lesson_write' | 'lesson_vocab'
  lesson_id uuid,                 -- 記事生成系のとき、対象のlesson
  model text not null,
  input_tokens int not null default 0,
  output_tokens int not null default 0,
  created_at timestamptz not null default now()
);
create index on usage_logs (user_id, created_at desc);
create index on usage_logs (kind, created_at desc);
```

### 5.1b 記事フィード機能のスキーマ（有料機能の中核）

**設計思想：生成物は全ユーザーの共有資産**。`lessons` は user_id を持たず、誰のリクエストで生成されたものでも同じ興味を持つ全員が読める。これが原価効率の源泉。

```sql
-- 事前選定した情報源（自分が管理。RSS優先）
create table sources (
  id uuid primary key default gen_random_uuid(),
  name text not null,
  url text not null,
  rss_url text,
  lang text not null,              -- 'en' | 'zh'
  category text[],                 -- 主に扱うカテゴリ
  fetch_method text not null default 'rss',  -- 'rss' | 'api' | 'http' | 'firecrawl'
  enabled boolean not null default true,
  -- ★ライセンス順守のための必須カラム
  license text not null,           -- 'CC-BY-3.0' | 'CC0-1.0' | 'CC-BY-4.0' | 'OGL-3.0' | 'PDL-1.0' | 'PD'
  attribution_template text,       -- 帰属表示の定型文（ソースごとに要求が異なる）
  usable_scope text not null,      -- 'full' | 'abstract_only'（arXivは本文不可）
  requires_adaptation_notice boolean not null default false,  -- 日本政府PDL1.0等
  robots_checked_at timestamptz,   -- robots.txt / 規約の確認記録
  created_at timestamptz not null default now()
);

-- 取り込んだ生記事（ネタ元。ユーザーには直接見せない）
create table raw_articles (
  id uuid primary key default gen_random_uuid(),
  source_id uuid not null references sources on delete cascade,
  url text not null unique,
  title text not null,
  body text,                       -- 事実抽出用。配信はしない
  lang text not null,
  published_at timestamptz,
  fetched_at timestamptz not null default now(),
  search_vector tsvector           -- 全文検索用（外部検索API不要）
);
create index on raw_articles using gin (search_vector);
create index on raw_articles (lang, published_at desc);

-- 生成された学習教材（★共有プール。user_id を持たない）
create table lessons (
  id uuid primary key default gen_random_uuid(),
  lang text not null,
  keyword text not null,           -- リクエストされたキーワード
  category text,
  level text not null default 'mid',    -- 'easy' | 'mid' | 'hard'（Pro機能）
  length text not null default 'normal',-- 'short' | 'normal' | 'long'（Pro機能）
  title text not null,
  body text not null,              -- AI書き下ろしの本文（オリジナル）
  body_ja text,                    -- 日本語対訳
  pinyin text,
  -- ★出典・帰属表示（法的に必須）
  source_urls text[] not null,     -- 出典リンク（必ず表示する）
  source_authors text[],           -- Global Voices は著者名の表示が必要
  license_notes text,              -- 記事に表示するライセンス告知
  is_adapted boolean not null default true,  -- PDL1.0等の「加工した旨」表示用
  -- 連載（Pro機能：背景→現状→論点）
  series_id uuid,
  series_order int,
  model text not null,
  requested_by uuid references auth.users on delete set null,
  created_at timestamptz not null default now(),
  expires_at timestamptz           -- 鮮度切れ判定（3〜7日）
);
create index on lessons (lang, keyword, created_at desc);
create index on lessons (lang, category, created_at desc);
create index on lessons (series_id, series_order);

-- 教材の重要語彙
create table lesson_vocab (
  id bigserial primary key,
  lesson_id uuid not null references lessons on delete cascade,
  word text not null,
  reading text,                    -- ピンイン等
  meaning_ja text not null,
  example text,
  position int
);

-- 誰がどの教材を読んだか（進捗表示・重複回避）
create table lesson_reads (
  user_id uuid not null references auth.users on delete cascade,
  lesson_id uuid not null references lessons on delete cascade,
  read_at timestamptz not null default now(),
  primary key (user_id, lesson_id)
);

-- ユーザーの興味カテゴリ／キーワード登録
create table interests (
  id bigserial primary key,
  user_id uuid not null references auth.users on delete cascade,
  lang text not null,
  keyword text not null,
  created_at timestamptz not null default now(),
  unique (user_id, lang, keyword)
);

-- リクエスト履歴（プラン上限のカウント対象。★キャッシュヒットは消費しない）
create table lesson_requests (
  id bigserial primary key,
  user_id uuid not null references auth.users on delete cascade,
  keyword text not null,
  lang text not null,
  lesson_id uuid references lessons on delete set null,
  cache_hit boolean not null default false,
  created_at timestamptz not null default now()
);
create index on lesson_requests (user_id, created_at desc);
```

**RLSの方針**

| テーブル | 読み取り | 書き込み |
|---|---|---|
| `sources` `raw_articles` | サービスロールのみ | サービスロールのみ |
| `lessons` `lesson_vocab` | **有料プランのユーザーは全件**／Freeは月3本まで（Edge Function経由で配信） | サービスロールのみ |
| `lesson_reads` `interests` | 本人のみ | 本人のみ |
| `lesson_requests` | 本人のみ（SELECT） | サービスロールのみ |

`lessons` を Supabase SDK から直接引かせると Free/有料の出し分けができないため、**教材の配信は必ず Edge Function を経由させる**。

### 5.1c リクエスト処理フロー

```
ユーザーがキーワードを入力
  → プラン確認（Free: 月3本 / Standard: 月20本 / Pro: 月100本）
  → lessons を (lang, keyword, expires_at > now()) で検索
      ├─ ヒット → 既存教材を返す。★リクエスト枠を消費しない（原価ゼロ）
      └─ ミス   → raw_articles を全文検索 → 上位3本を選定
                 → ①スクリーニング ②書き下ろし ③語彙抽出
                 → lessons / lesson_vocab に INSERT（共有プールに追加）
                 → リクエスト枠を1消費
```

**キャッシュヒットで枠を消費しない**のが体験上の要。「他の人が既に作っていた」ことがユーザーの得になるため、プールの充実がそのまま満足度になる。

**Free ユーザーには新規生成をさせない**（月3本の閲覧はキャッシュヒット分のみ）。ここを開けると無料ユーザーの原価が跳ねる。

### 5.1d 作文側のクォータ判定

記事フィードと同様に、**作文の翻訳にもプラン別の上限判定が必要**。

```
翻訳リクエスト
  → JWT検証 → subscriptions.plan 取得
  → usage_logs から当月の kind='translate' 件数を集計
  → Free: 月150文 / Standard: 月1,500文 / Pro: 月3,000文 を超えたら 402 を返す
```

**Free の月150文は必須**。無制限にすると有料1,000人規模で月293,000円の持ち出しになる（`../00-business/pricing-plan.md` §5）。

### 5.2 RLSポリシー（全テーブル共通の型）

```sql
alter table sentences enable row level security;

create policy "own rows" on sentences
  for all
  using (auth.uid() = user_id)
  with check (auth.uid() = user_id);
```

`subscriptions` と `usage_logs` は **SELECTのみ本人に許可、INSERT/UPDATEはサービスロール（Edge Function）限定**にする。ここをクライアントに開けると、ユーザーが自分のプランを書き換えられてしまう。

### 5.3 現行JSONからの移行

自分の既存データは、`data/sentences.json` `words.json` を読んで `user_id` を自分のUUIDで埋めて INSERT する使い捨てスクリプトで移せる（`fails` / `practices` の配列は行に展開）。

---

## 6. API設計（現行との対応）

> ⚠️ **正典は移譲済み。** 家族版のEdge Function契約（入出力JSON・エラーコード）は `../10-specs/family-edition-spec.md` §6、事業版の追加12本は `../10-specs/saas-diff-spec.md` §3 を参照。
> 以下は現行APIとの対応関係を示す参考表。

| 現行 | 移行後 | 備考 |
|---|---|---|
| `GET /api/health` | 廃止 | Ollama状態確認は不要に |
| `POST /api/translate` | Edge Function `POST /translate` | JWT必須、使用量チェック追加 |
| `POST /api/keywords` | Edge Function `POST /keywords` | 同上 |
| `POST /api/pinyin` | Edge Function `POST /pinyin` | pypinyin相当をサーバー側で |
| `GET/POST /api/sentences` | Supabase SDK 直叩き | RLSで保護 |
| `POST /api/words` `/words/delete` | Supabase SDK 直叩き | 同上 |
| `POST /api/fail` `/practice` `/delete` | Supabase SDK 直叩き | 同上 |
| — | `GET /lessons` | **記事フィード一覧**。プラン判定＋Freeは月3本でゲート |
| — | `GET /lessons/:id` | **記事詳細**。本文・対訳・語彙・**出典リンク・帰属表示**を返す |
| — | `POST /lessons/request` | **キーワード指定の生成**。キャッシュ判定 → 枠消費判定 → 生成 |
| — | `GET /lessons/quota` | 当月のリクエスト残数・作文残文数 |
| — | `POST /lessons/:id/read` | 既読記録（`lesson_reads`） |
| — | `POST /lessons/:id/vocab-to-words` | 抽出語彙を自分の単語帳へ登録 |
| — | `POST /lessons/:id/proofread` | 記事の語彙を使った自作文のAI添削（Pro） |
| — | `GET/POST/DELETE /interests` | 興味キーワード管理。Supabase SDK直叩き（RLSで本人のみ） |
| — | 内部：`cron_generate_daily()` | 人気カテゴリの定期生成（pg_cron から日次実行） |
| — | 内部：`cron_ingest_sources()` | 情報源からの記事取り込み（pg_cron から日次実行） |
| — | `POST /billing/checkout` | Stripe Checkout セッション作成 |
| — | `POST /billing/portal` | Stripe カスタマーポータル（解約導線） |
| — | `POST /stripe-webhook` | 署名検証必須 |
| — | `POST /account/export` | データエクスポート（法的にも実務的にも必要） |
| — | `POST /account/delete` | 退会・全データ削除 |

---

## 7. 新規に必要な画面

> ⚠️ **正典は移譲済み。** 家族版の画面とURL設計は `../10-specs/family-edition-spec.md` §4、事業版の追加11画面・変更2画面は `../10-specs/saas-diff-spec.md` §4 を参照。
> 本節の「必須度」列は**事業版としての必須度**であり、家族版には適用されない。

### 7.1 記事フィード（商品価値の本体）

| 画面 | 内容 | 必須度 |
|---|---|---|
| **記事フィード一覧** | 新着／カテゴリ別／既読・未読。Freeは月3本でゲート | 必須 |
| **記事詳細** | 本文・日本語対訳・ピンイン・重要語彙。**出典リンクと帰属表示は法的に必須** | 必須 |
| **記事の音読トレーニング** | フレーズ分割・速度調整・失敗記録（既存プレイヤーを流用） | 必須 |
| **興味キーワード設定** | `interests` の登録・削除。カテゴリ選択 | 必須 |
| **記事リクエスト** | キーワード入力。**残数表示＋「既にあれば消費しない」旨の提示** | 必須 |
| アーカイブ | 鮮度切れの記事をプールに残したまま別表示 | 推奨 |
| 連載ビュー | 同一トピックの深掘り（背景→現状→論点）を順に読む（Pro） | 推奨 |

### 7.2 アカウント・課金・法務

| 画面 | 内容 | 必須度 |
|---|---|---|
| ログイン / サインアップ | メール+パスワード、Googleログイン | 必須 |
| パスワードリセット | Supabase Auth 標準機能 | 必須 |
| アカウント設定 | 表示名、既定言語、発音速度、パスワード変更 | 必須 |
| プラン・お支払い | 現在のプラン、**当月の作文文数・記事リクエスト残数**、アップグレード、Stripeポータルへの導線 | 必須 |
| 退会 | 全データ削除の確認 | 必須 |
| データエクスポート | JSON / Markdown ダウンロード（現行の `sentences.md` 生成を流用） | 推奨 |
| 弱点レポート | Fail履歴の集計・可視化 | 差別化の核 |
| 利用規約 / プライバシーポリシー / 特商法表記 | 静的ページ | **法的に必須** |

---

## 8. 実装ロードマップ

### 8.0 基本方針：家族版を先に出す

**[[Plan A]]（無料版・家族利用）を「撤退先」ではなく「出発点」にする。**

```
【従来の想定】 SaaSを作る → ダメなら家族版へ撤退
【採用する順序】 家族版を作る → 動いたら収益化を足す
```

この順序が優れている理由は、**Phase 1（マルチユーザー化）が、そのまま家族版として完成品になる**こと。作業の重複がない。

| | 家族版 | 収益版 | 差分 |
|---|---|---|---|
| Supabase Auth | ○ | ○ | **同一** |
| Postgres + RLS | ○ | ○ | **同一** |
| コアのスキーマ | ○ | ○ | **同一** |
| index.html → SDK移行 | ○ | ○ | **同一** |
| 翻訳 Edge Function | ○ | ○ | **同一** |
| PWA | ○ | ○ | **同一** |
| Supabase プラン | Free | Pro | **トグル1つ** |
| 記事フィード | ✗ | ○ | 追加 |
| Stripe | ✗ | ○ | 追加 |
| 法務ページ | **不要** | 必須 | 追加 |

**リスク構造が反転する。** 従来は「作り切ってから撤退判断」だったが、この順序なら**撤退という工程自体が存在しない**。家族版は常に動いており、収益化を「足すか足さないか」を選ぶだけになる。

### 8.0.1 ★ 家族版の時点で必ず作り込むもの（後付けが困難）

**ここが本節の核心。** 「家族しか使わないから」と省略すると、収益化時に作り直しになる項目。

| # | 項目 | 家族版で省略した場合の代償 |
|---|---|---|
| 1 | **[[RLS]] を全テーブルで有効化** | 後から有効化すると全クエリの再監査が必要。**2人でも最初から入れる** |
| 2 | **全行に `user_id`** | 後付けは既存データのマイグレーションが必要 |
| 3 | **APIキーを Edge Function にのみ置く** | 「家族用だから」とクライアントに置くと**必ず忘れて公開時に漏れる** |
| 4 | **`usage_logs` への記録** | 収益化時の原価計算とクォータ制御の土台。**家族版の期間が実測データの取得期間になる** |
| 5 | **`subscriptions` テーブルと `plan` カラム** | 全員 `plan='family'` でよい。プラン概念が無いと、後から全エンドポイントに条件分岐を通すことになる |
| 6 | **クォータ判定のコードパス** | 上限を実質無制限に設定しておく。**判定を書く場所だけ用意**しておけば、後は数値を変えるだけ |
| 7 | **スキーマをマイグレーションファイルで管理** | ダッシュボードでポチポチ作ると再現できない |
| 8 | **エクスポート機能** | 既存の `sentences.md` 生成を流用。データポータビリティは最初から |

**逆に、家族版で作らなくてよいもの**：Stripe、記事フィード（`sources` / `raw_articles` / `lessons` 系）、課金画面、利用規約・特商法表記、ソーシャルログイン。

### 8.0.2 家族版で得られるもの

| 得られるもの | 意義 |
|---|---|
| **実測の消費トークン** | 原価1.74円/0.015円は推定値。**実データで置き換えられる** |
| **実際の利用文数** | 「月150文」の上限設定が妥当か検証できる |
| **娘というリアルユーザー** | 技術者でない学習者のUXフィードバック。**最も得がたい情報** |
| 継続利用の実績 | 自分が毎日使うかの答え合わせ（撤退ライン④） |
| 動くものが常に手元にある | 半端なSaaSより精神衛生が良い |

### 8.0.3 この順序のリスク

| リスク | 対策 |
|---|---|
| **家族版で満足して収益化に進まない** | **最大のリスク。** 家族版リリースから**2ヶ月**を評価期間と決め、その時点で収益化に進むか判断する |
| Supabase Free の1週間無操作で一時停止 | 娘が毎日使うなら発生しない。念のため **GitHub Actions で週1回APIを叩く**（無料） |
| Vercel Hobby は非商用限定 | 家族利用の間は問題なし。**課金開始時に必ず Pro へ**（規約違反を放置しない） |
| Free枠 500MB を超える | コアデータ（テキストのみ）は数MB程度。**`raw_articles` を作った時点で超えるので、記事フィード着手＝Pro移行**とセットで考える |

---

## 8.1 フェーズ構成

### Phase -1：前提の確定（1週間）

> **方針変更**：需要検証（LP事前登録）と目利きの一致率テストは**実施しない**。投資コストが低いため、作って出して、ダメなら畳む。代わりに**撤退ラインを事前に決める**（`../00-business/exit-plan.md`）。

- [x] **Global Voices の実地確認**（完了。**中国語版が停止していることが判明** → `content-sources.md` §2.1）
- [ ] **中国語ソースの方針決定** — アーカイブ教材で割り切る／台湾政府系を調査／英語のみで出す（`content-sources.md` §3.5）
- [ ] arXiv で拾うカテゴリを特定（cs.RO に加え cs.AI / cs.LG / cs.CV）
- [ ] 各サイトの robots.txt・利用規約を確認（Global Voices は **Crawl-delay: 10秒**）
- [ ] 既存パイプラインの**消費トークンを実測**し、原価1.74円の裏取り
- [ ] **撤退コストを下げる設計判断を確定**（`../00-business/exit-plan.md` §3）

**供給量についての結論**

新規記事の供給は当初想定（40〜60本/日）に遠く届かない（Global Voices 英語 1.8本/日、中国語ほぼ0本/日）。
**「毎日の新着」から「アーカイブ＋新着」へ方針転換した**（`content-sources.md` §4）。Global Voices だけで英語10万本・中国語1.2万本のストックがあり、**供給量は制約ではなくなった**。

### Phase 0：意思決定と準備（1週間）

- [ ] サービス名・ドメイン取得
- [ ] Supabaseプロジェクト作成（リージョン: Tokyo）
- [ ] LLMプロバイダのAPIキー取得（Gemini / OpenAI）
- [ ] Stripeアカウント開設（本人確認に数日かかる）
- [ ] 屋号・[[特定商取引法]]表記の住所方針を決定（後述 §10）

### Phase 1：マルチユーザー化（2〜3週間）★ = 家族版のリリース

**このフェーズの完了＝家族版の完成。ここで一度出して使い始める。** 費用は0円（Supabase Free + Vercel Hobby）。

§8.0.1 の8項目を**必ずこのフェーズで作り込むこと**。

- [ ] DBスキーマ + RLS適用
- [ ] Supabase Auth 組み込み（ログイン／サインアップ／リセット画面）
- [ ] `index.html` のデータアクセスを `fetch('/api/...')` から Supabase SDK に置換
- [ ] 翻訳Edge Function 実装（Ollama → Gemini API）
- [ ] 既存プロンプトのクラウドLLM向け再調整と品質確認
- [ ] 自分のデータを移行して**自分がドッグフーディング**
- [ ] アカウント設定・エクスポート・退会画面
- [ ] **`subscriptions` テーブル作成**（全員 `plan='family'`）と**クォータ判定のコードパス**（上限は実質無制限に設定）
- [ ] **`usage_logs` への記録**（この期間の実測データが原価試算の裏取りになる）
- [ ] GitHub Actions で週1回APIを叩く（Supabase Free の一時停止対策）
- [ ] **娘のアカウントを作り、実際に使ってもらう**

### Phase 1.9：評価期間（2ヶ月）

家族版を運用しながら、収益化に進むかを判断する。**期限を切ること**（切らないと永久に家族版のまま終わる）。

- [ ] 実測トークン数から**原価を確定**（推定1.74円/記事、0.015円/文の答え合わせ）
- [ ] 実際の月間利用文数を確認し、**Freeの月150文が妥当か検証**
- [ ] 娘のUXフィードバックを反映
- [ ] **2ヶ月後、収益化に進むか判断する**。進まないならこのまま家族版として運用（撤退不要）

### Phase 1.5：記事フィード機能（2〜3週間）★ 商品価値の本体

> ⚠️ **コアと疎結合に保つこと**（`../00-business/exit-plan.md` §3.2）
> 撤退時は「pg_cron を止める」「フィード系画面をフラグで隠す」の2操作で済む状態を維持する。
> **依存はフィード→コアの一方向に限定**し、`sentences` 等のコアテーブルがフィード側を参照しないようにする。

**既に完成している部分と、これから作る部分を区別すること。**

| 工程 | 状態 |
|---|---|
| ① 情報源から候補記事を集める | **未着手**（現在はWeiboを人力で巡回） |
| ② 候補から教材にする価値のあるものを選ぶ | **未着手**（現在はあなたの目利き） |
| ③ 記事化 | **稼働中**（要約型 → 書き下ろし型への改修が必要） |
| ④ 重要語彙の抽出 | **稼働中**（ほぼそのまま流用可） |

**新規開発の本体は①②。③④は移植と改修。**

**① 情報源の自動収集**

確定した情報源構成（詳細は `content-sources.md` §4）:

| 役割 | ソース | ライセンス | 比率 |
|---|---|---|---|
| 日々の主力・多言語対訳 | Global Voices | CC BY 3.0 | 40% |
| 技術・ロボティクス | arXiv アブストラクト | **CC0** | 30% |
| 政策・産業動向 | EU / 英国 / 日本 / 米国 政府PR | CC BY 4.0 等 | 20% |
| 穴埋め・背景 | Wikipedia（事実抽出のみ）＋ Wikinews ストック | — | 10% |

- [ ] 上記に加え、事前選定サイトを10〜20本まで拡張。**RSSの有無・robots.txt・利用規約を1本ずつ確認**
- [ ] `sources` テーブルに **license / attribution_template / usable_scope** を登録
- [ ] 記事取り込みバッチ（pg_cron で日次。RSS・公式API優先）
- [ ] `raw_articles` の全文検索インデックス構築（外部検索APIは使わない）
- [ ] **arXiv は3秒に1リクエスト・同時接続1**、Wikipedia は **UA必須・同時接続3以下** のレート制限を実装に反映

**② 目利きの自動化 ★ ここが最大の未知数**

- [ ] 「教材にする価値がある記事」の判断基準を**言語化する**
- [ ] スクリーニングプロンプトを作成
- [ ] **一致率テスト**：候補50件に自分で印をつけ、プロンプトの選定結果と突き合わせる。**7割を切るなら基準の言語化が不足**
- [ ] 2〜3日分繰り返して基準を具体化

**③④ 既存パイプラインの移植**

- [ ] Notion運用の生成プロンプトをEdge Functionへ移植
- [ ] **要約型 → 書き下ろし型への改修**（有料配信では要約は翻案リスク。`../00-business/pricing-plan.md` §10.2）
- [ ] 難易度・長さの指定パラメータを追加（改修の副産物。Proの機能になる）
- [ ] **帰属表示の自動生成**（`sources.attribution_template` から記事冒頭・末尾に埋め込む）
- [ ] **実際の消費トークンを `usage_logs` に記録し、原価試算を実測値に差し替える**

**共通基盤**

- [ ] 共有プールのキャッシュ判定（キーワード×言語×鮮度）
- [ ] 人気カテゴリの定期生成（**10カテゴリ × 各1日2本 = 1日20本**）
- [ ] 記事フィード一覧・記事詳細・リクエスト・興味設定の各画面（§7.1）
- [ ] 記事の音読トレーニングUI（既存プレイヤーを流用）
- [ ] 作文・記事リクエストのクォータ判定（§5.1c / §5.1d）

### Phase 2：課金（1〜2週間）

> ⚠️ **撤退コストを下げる設計判断を守ること**（`../00-business/exit-plan.md` §3）
> - **年払いは出さない。最初の6ヶ月は月額のみ。** 年払いがあると撤退時に残期間の返金債務を抱える
> - Stripe Customer Portal を有効にし、**全サブスクを一括キャンセルできる状態**にしておく
> - 利用規約に**サービス終了条項（30日前告知・最終月は課金しない）を最初から**入れる

- [ ] Stripe Product / Price 定義（**月額のみ**。年額は継続判断後に追加）
- [ ] Checkout セッション作成 + Webhook（署名検証・冪等性処理）
- [ ] プラン別の機能ゲート（Edge Function側で判定。**クライアント側だけの制限は無意味**）
- [ ] 使用量カウントと無料枠超過時のUX
- [ ] 無料トライアル設計

### Phase 3：法務・公開準備（1週間）

- [ ] 利用規約
- [ ] **出典・帰属表示の実装確認**（Global Voices は記事冒頭に原記事リンクと著者名、arXiv は定型謝辞、PDL1.0 は加工主体の記載。§10.5）
- [ ] **CC BY-SA 由来のテキストが混入していないことの確認**（Wikipedia は事実抽出のみのはず）
- [ ] プライバシーポリシー（外国にある第三者への提供＝Supabase / LLMプロバイダを明記）
- [ ] 特定商取引法に基づく表記
- [ ] 申込み最終確認画面の表示要件対応（§10）
- [ ] 問い合わせ窓口（メール）
- [ ] PWA manifest / アイコン / OGP

### Phase 4：品質・運用（継続）

- [ ] レート制限（翻訳APIの乱用防止）
- [ ] エラー監視（Sentry無料枠等）
- [ ] バックアップ確認（Supabase Pro の日次バックアップ）
- [ ] 障害時の告知手段（X等）
- [ ] 集客用LPの本格制作（Phase -1 の需要検証LPを商用版に作り込む）と集客

### Phase 5：差別化（公開後）

- [ ] Fail履歴を使った弱点レポート・出題優先度づけ
- [ ] 復習スケジューリング（間隔反復）
- [ ] 中国語コースの正式商品化（既に実装済みの資産）

**工数の内訳**

| フェーズ | 期間 | 費用 | マイルストーン |
|---|---|---|---|
| Phase -1 前提の確定 | 1週 | 0円 | |
| Phase 0 準備 | 1週 | 0円 | |
| Phase 1 マルチユーザー化 | 2〜3週 | **0円** | **★ 家族版リリース** |
| **家族版まで小計** | **4〜5週（約1〜1.2ヶ月）** | **0円** | |
| Phase 1.9 評価期間 | 2ヶ月 | 0円 | **★ 収益化のGO/NO-GO判断** |
| Phase 1.5 記事フィード | 2〜3週 | Pro移行 | |
| Phase 2 課金 | 1〜2週 | | |
| Phase 3 法務・公開準備 | 1週 | | **★ 有料公開** |
| **有料公開まで小計** | **8〜11週の実装＋評価2ヶ月** | | |
| Phase 4 品質・運用／Phase 5 差別化 | 公開後も継続 | | |

**家族版までは1ヶ月・0円。** ここまでは何があっても損をしない。

**有料公開までの実装は通算8〜11週（約2〜2.5ヶ月）**、間に評価期間2ヶ月が挟まる。手戻りを含めると着手から有料公開まで**約5〜6ヶ月**を見ておく。

> 評価期間を挟むぶん有料公開は遅くなるが、**その間の費用は0円で、実測データと娘のフィードバックが得られる**。急いで有料化しても集客はすぐには立ち上がらないので、実質的な損失はない。

---

## 9. セキュリティ上の必須対応

| 項目 | 内容 |
|---|---|
| APIキー | **絶対にクライアントに置かない**。Edge Function の環境変数のみ |
| RLS | 全テーブルで有効化。無効のまま公開＝全データ流出 |
| service_role キー | サーバー側限定。漏洩するとRLSを完全に無視できる |
| Stripe Webhook | 署名検証必須。検証なしだと誰でも「有料会員になった」と偽装できる |
| レート制限 | 翻訳エンドポイントにIP・ユーザー単位の制限。LLM費用の暴走を防ぐ |
| 入力長制限 | 日本語入力に文字数上限（例: 300文字）。プロンプト経由のコスト攻撃対策 |
| HTTPS | 必須。PWAの動作要件でもある |
| パスワード | Supabase Auth に委譲（自前でハッシュ実装しない） |
| ログ | 学習内容は個人情報になり得る。ログに本文を残さない設計 |

---

## 10. 法務要件（※法的助言ではなく事実整理。実行前に専門家確認を推奨）

### 10.1 特定商取引法に基づく表記

有料のオンラインサービス提供は**通信販売**に該当し、個人事業主でも表記義務がある。

**表示必須項目**：販売価格、支払時期・方法、役務の提供時期、申込みの撤回・解除に関する事項、**動作環境（推奨ブラウザ・OS）**、**2回以上継続して契約する必要がある場合はその販売条件**、メール広告を送る場合はメールアドレス。

**氏名・住所・電話番号について**：原則として個人事業者は**戸籍上の氏名**（屋号のみは不可）、**現に活動している住所**、**確実に連絡が取れる電話番号**の表示が必要。ただし法11条ただし書により、**「消費者からの請求があれば遅滞なく書面または電子メールで提供する」旨を広告に表示し、実際にその体制を整えている場合は、氏名・住所・電話番号の表示を省略可能**。私書箱は不可。バーチャルオフィスは一定条件下で可。

**サブスク特有の要件**：
- 自動更新（無期限契約）の場合、総額表示ができないため**半年分・1年分などの目安金額**を示し、目安である旨を明示。かつ**「解約通知がない限り継続する」ことを認識しやすく表示**
- **申込み最終確認画面**（法12条の6）に、分量・価格・支払時期方法・提供時期・申込期間の定め・解除に関する事項を**一覧性をもって**表示。違反すると**申込みの意思表示を取り消される**
- 解約申出の期限、違約金がある場合は具体的な額まで表示
- 通信販売にクーリング・オフはない

**海外ユーザー**：特商法26条により、海外にいる人への提供は適用除外。

出典: [消費者庁 特定商取引法ガイド 通信販売](https://www.no-trouble.caa.go.jp/what/mailorder/) / [広告Q&A](https://www.no-trouble.caa.go.jp/qa/advertising.html)

### 10.2 個人情報保護法

会員のメールアドレスと学習データをDBで管理する時点で**個人情報取扱事業者**に該当（件数の下限なし）。

**プライバシーポリシーに実質的に必要な記載**（法32条1項）：
1. 事業者の氏名または名称・住所
2. 全ての保有個人データの利用目的
3. 開示・訂正・利用停止請求に応じる手続（手数料を定める場合はその額）
4. 安全管理のために講じた措置、苦情の申出先

**特に注意すべき点**：Supabase・Gemini/OpenAI はいずれも**外国にある第三者**にあたる。法28条の対応（提供先の所在国、当該国の個人情報保護制度、提供先の措置に関する情報提供）が必要。

**入力内容の学習利用**：ユーザーが入力した日本語文をLLMプロバイダに送る以上、「入力内容がAI事業者に送信されること」「モデル学習に使われないプランを利用していること」を明記すべき。API利用は通常学習に使われないが、規約で確認が必要。

なお、令和8年改正個人情報保護法（課徴金制度、AI関連の新ルール等）が2026年4月に国会提出済み。施行は公布から2年以内（2028年中見込み）で、動向の追跡が必要。

出典: [個人情報保護委員会 ガイドライン（通則編）](https://www.ppc.go.jp/personalinfo/legal/guidelines_tsusoku/) / [個人情報保護法32条](https://laws.e-gov.go.jp/law/415AC0000000057)

### 10.3 資金決済法（前払式支払手段）

**通常の月額サブスク（定額でサービス使い放題）は該当しない**。金融庁事務ガイドラインは「使用に応じて減少するものではないもの」は前払式支払手段に該当しないと明記している。

**ただし該当しうる設計**：「AI添削10回分チケット」のような**回数券・ポイントを先に販売して消費させる設計**は該当し得る。その場合、
- 発行日から**6ヶ月以内**にのみ使用可能な設計なら適用除外（法4条2号）
- 基準日（3/31・9/30）の未使用残高が**1,000万円**を超えたら届出＋残高の1/2以上を供託
- 第三者型（他社でも使える）は**法人限定**のため個人事業主は発行不可

→ **回数券型・ポイント型は避け、期間課金一本にするのが安全**。

出典: [資金決済法](https://laws.e-gov.go.jp/law/421AC0000000059) / [金融庁 事務ガイドライン](https://www.fsa.go.jp/common/law/guide/kaisya/05.pdf)

### 10.4 消費税・インボイス

- 個人事業者は**前々年**の課税売上高1,000万円以下なら免税事業者。BtoC中心のサービスでは購入者が仕入税額控除を必要としないため、**インボイス登録しない選択の実務上の不利益は小さい**（法人研修用途の需要が見込まれる場合は要検討）
- 登録して課税事業者になった場合、**2割特例**が令和8年9月30日の属する課税期間まで適用可（個人事業者は令和5年分〜令和8年分の4回）。加えて国税庁ページに**令和9年・令和10年分は3割特例**の記載あり（詳細要件は本調査時点で未公表）
- **海外ユーザーへの提供は不課税**。オンライン英語学習は「電気通信利用役務の提供」に該当し、内外判定は**役務提供を受ける者の住所**で行う。国外の消費者・事業者への提供は国外取引となり消費税不課税（客観的かつ合理的な基準での住所判定が必要）

出典: [国税庁 2割特例](https://www.nta.go.jp/publication/pamph/shohi/kaisei/202304/01.htm) / [国税庁 No.6118](https://www.nta.go.jp/taxes/shiraberu/taxanswer/shohi/6118.htm)

### 10.5 著作権・ライセンス順守

**この項目は `content-sources.md` が正典。** 実装上の必須要件のみここに再掲する。

**基本方針：[[AI書き下ろし型]]**。元記事の要約ではなく、複数ソースから事実だけ抽出して学習用テキストをオリジナルで構成する。現行のNotion運用は要約型のため、**商用転用にあたり改修が必要**。

| ソース | 実装しなければならないこと |
|---|---|
| **Global Voices**（CC BY 3.0） | 記事**冒頭**に原記事へのリンクと**著者名**。例「This story by ○○ originally appeared on Global Voices on ○○.」／**画像・音声・動画は別ライセンスの可能性があるためテキストのみ使用** |
| **arXiv**（メタデータ CC0） | **アブストラクトのみ使用。本文（PDF等）を自サーバーに保存・配信しない**／定型謝辞「Thank you to arXiv for use of its open access interoperability.」を表示／arXivのロゴ・ブランド名を使わない／abs ページへリンク |
| **政府系**（CC BY 4.0 / OGL3 / **PDL1.0**） | 出典記載。**日本政府 PDL1.0 は「編集・加工等を行ったこと及びその主体」の記載が必須**／ロゴ・紋章は使用不可 |
| **Wikipedia**（CC BY-SA 4.0） | **事実抽出のみ。翻訳・翻案は禁止**（ShareAlikeが発動し、教材をCC BY-SAで提供する義務が生じる）／API利用時はUA必須・同時接続3以下／**サブライセンス／ホワイトラベル禁止条項があるため、APIを直接中継せず自前で取り込む** |

**実装で担保する仕組み**

- `sources.attribution_template` と `sources.usable_scope` を必ず埋め、**帰属表示を記事生成時に自動で埋め込む**（人手に頼らない）
- 書き下ろしプロンプトに「**原文の言い回し・語順・段落構成をなぞらない**」を明示的に禁止条項として入れる
- 事前選定サイトのリストが確定した段階で**弁護士に一度まとめて確認**する

---

## 11. リスクと対策

| リスク | 影響 | 対策 |
|---|---|---|
| **目利きの自動化ができない** | **商品価値の中核が成立しない。最大の未知数** | Phase -1 で候補50件の一致率テスト。**7割を切るなら実装前に基準を再言語化** |
| **集客できない** | 最大のリスク。技術より難しい | **実装着手前（Phase -1）**にLPを公開し、事前登録50件を実装のGO判断基準にする |
| **著作権（要約型のまま配信）** | 翻案権侵害。事業継続不能 | 書き下ろし型への改修を Phase 1.5 の完了条件にする。サイトリスト確定後に弁護士確認 |
| **ライセンス条件違反（帰属表示漏れ）** | CC BY 3.0 / PDL1.0 等の違反 | 帰属表示を `sources.attribution_template` から**自動生成**し、人手に頼らない（§10.5） |
| **CC BY-SA の混入** | 教材に転載禁止を主張できなくなる | Wikipedia は事実抽出のみ。Phase 3 で混入チェックを実施 |
| **情報源の供給量不足・RSS停止** | 「毎日新着」が破綻 | Phase -1 で1週間の実供給量計測を先行。単一ソース依存を避ける（arXivは月次2.4倍の振れ幅） |
| **リクエスト機能の乱用** | 記事生成の原価暴走 | サーバー側で月次上限判定。同一キーワードの連投はキャッシュヒット扱いで原価を発生させない |
| 生成品質のばらつき | 解約に直結 | 公開前に自分で50本読んで合格率を測る。8割を切るならプロンプトが未完成 |
| ソースサイトの構造変更 | パーサーが壊れる | RSS・公式APIを優先し、HTML依存を減らす |
| LLM費用の暴走 | 一部ユーザーの乱用で赤字 | 入力長制限、レート制限、プラン別上限、Stripeとは別に費用アラート設定 |
| LLMの翻訳品質がOllamaより悪い | 体験劣化 | Phase 1でプロンプト再調整と自分でのA/B比較を必ず実施 |
| iOS SafariのWeb Speech API仕様変更 | 発音機能が壊れる | 主要機能なので複数OSバージョンで定期確認。最悪クラウドTTSへの退避策を用意（原価は上がる） |
| Supabase無料枠の一時停止 | サービス断 | 公開時点で必ずProへ |
| 個人情報漏洩 | 事業継続不能 | RLSの徹底、service_roleキーの管理、ログに本文を残さない |
| 特商法の住所表示 | 自宅住所の公開に抵抗 | 「請求があれば遅滞なく開示」方式、またはバーチャルオフィス（条件あり） |

---

## 12. 次のアクション（推奨順）

**当面は家族版（Phase 1）に集中する。記事フィードと課金の検討は評価期間の後でよい。**

1. **Supabaseプロジェクト作成**（リージョン: Tokyo、**Freeプラン**）
2. コアのスキーマをマイグレーションファイルで投入（`profiles` `sentences` `words` `fails` `practices` `subscriptions` `usage_logs`）+ **RLS有効化**
3. Gemini APIキーを取得し、**Edge Function の翻訳プロキシ**を作る（キーはクライアントに置かない）
4. `index.html` のデータアクセスを Supabase SDK に置換
5. 自分のデータを移行し、**娘のアカウントを作って使い始める**
6. 2ヶ月使い、実測データを見てから収益化を判断する

**着手前に確定しておくこと**：`../00-business/exit-plan.md` §3 の設計判断（特に**コアと記事フィードの疎結合**。家族版の時点でコアだけを作るので自然に守られる）。

---

### 関連ドキュメント

- `../10-specs/current-app-spec.md` — 現行機能の移植チェックリスト
- `../10-specs/family-edition-spec.md` — **家族版の実装仕様（正典）**
- `../10-specs/saas-diff-spec.md` — **事業版の差分仕様（正典）**
- `../20-plans/status-summary.md` — 検討の現況整理
- `../00-business/exit-plan.md` — 撤退ラインと最低コスト退避先（**§3の設計判断は実装前に確定させること**）
- `content-sources.md` — 情報源の評価と選定方針（**情報源・ライセンスに関する正典**）
- `../00-business/pricing-plan.md` — 料金プラン設計・原価計算・損益分岐点
