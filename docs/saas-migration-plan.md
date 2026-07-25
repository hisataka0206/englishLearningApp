# English Learning App — [[SaaS化]]移行設計書

作成日: 2026-07-25 / 対象リポジトリ: `englishLearningApp`

---

## 0. エグゼクティブサマリ

現状は**完全な個人用ローカルアプリ**であり、有料展開するには**バックエンドの作り直し**が必要。ただし `index.html`（UI）と学習ロジックは資産としてほぼ全量流用できる。

**推奨構成**

| レイヤ | 推奨 | 理由 |
|---|---|---|
| 提供形態 | [[PWA]]（クラウドSaaS） | ストア審査・手数料15〜30%を回避。既存UIをそのまま活かせる |
| LLM | [[Gemini]] 2.5 Flash-Lite（既定）＋ [[gpt-5.4-mini]]（上位プラン） | 1文あたり約0.02円。原価がほぼ無視できる |
| 認証・DB | [[Supabase]]（Auth + Postgres + [[RLS]]） | 認証・DB・行レベルセキュリティが一体。個人開発の最短ルート |
| 課金 | [[Stripe]] Billing（実効手数料 4.3%） | ストア課金の1/4以下 |
| 音声 | [[Web Speech API]]（現状維持） | **クラウドTTSを使わないことが最大の原価優位**。ここは変えない |

**収益モデル**：作文・翻訳・発音は**無料**。有料機能は「**興味キーワードから学習教材が自動生成される[[記事フィード]]**」。
**損益分岐点：有料会員 13人**（詳細は `pricing-plan.md`）。

> ⚠️ **重要**：情報源として [[Weibo]] を使う設計は成立しない。規約が「API取得データの他用途利用」「第三者サーバーでの保存」を明示禁止しており、共有プール設計と真っ向から矛盾する。詳細と代替策は `pricing-plan.md` §10.1。

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

- ◎ 手数料が圧倒的に安い。月額680円なら手取り651円（ストア経由なら578円）
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
  user_id uuid not null references auth.users on delete cascade,
  kind text not null,             -- 'translate' | 'keywords'
  model text not null,
  input_tokens int not null default 0,
  output_tokens int not null default 0,
  created_at timestamptz not null default now()
);
create index on usage_logs (user_id, created_at desc);
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
  fetch_method text not null default 'rss',  -- 'rss' | 'http' | 'firecrawl'
  enabled boolean not null default true,
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
  level text not null default 'mid',  -- 'easy' | 'mid' | 'hard'
  title text not null,
  body text not null,              -- AI書き下ろしの本文（オリジナル）
  body_ja text,                    -- 日本語対訳
  pinyin text,
  source_urls text[] not null,     -- 出典リンク（必ず表示する）
  model text not null,
  requested_by uuid references auth.users on delete set null,
  created_at timestamptz not null default now(),
  expires_at timestamptz           -- 鮮度切れ判定（3〜7日）
);
create index on lessons (lang, keyword, created_at desc);
create index on lessons (lang, category, created_at desc);

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

| 現行 | 移行後 | 備考 |
|---|---|---|
| `GET /api/health` | 廃止 | Ollama状態確認は不要に |
| `POST /api/translate` | Edge Function `POST /translate` | JWT必須、使用量チェック追加 |
| `POST /api/keywords` | Edge Function `POST /keywords` | 同上 |
| `POST /api/pinyin` | Edge Function `POST /pinyin` | pypinyin相当をサーバー側で |
| `GET/POST /api/sentences` | Supabase SDK 直叩き | RLSで保護 |
| `POST /api/words` `/words/delete` | Supabase SDK 直叩き | 同上 |
| `POST /api/fail` `/practice` `/delete` | Supabase SDK 直叩き | 同上 |
| — | `POST /billing/checkout` | Stripe Checkout セッション作成 |
| — | `POST /billing/portal` | Stripe カスタマーポータル（解約導線） |
| — | `POST /stripe-webhook` | 署名検証必須 |
| — | `POST /account/export` | データエクスポート（法的にも実務的にも必要） |
| — | `POST /account/delete` | 退会・全データ削除 |

---

## 7. 新規に必要な画面

| 画面 | 内容 | 必須度 |
|---|---|---|
| ログイン / サインアップ | メール+パスワード、Googleログイン | 必須 |
| パスワードリセット | Supabase Auth 標準機能 | 必須 |
| アカウント設定 | 表示名、既定言語、発音速度、パスワード変更 | 必須 |
| プラン・お支払い | 現在のプラン、当月使用量、アップグレード、Stripeポータルへの導線 | 必須 |
| 退会 | 全データ削除の確認 | 必須 |
| データエクスポート | JSON / Markdown ダウンロード（現行の `sentences.md` 生成を流用） | 推奨 |
| 弱点レポート | Fail履歴の集計・可視化 | 差別化の核 |
| 利用規約 / プライバシーポリシー / 特商法表記 | 静的ページ | **法的に必須** |

---

## 8. 実装ロードマップ

### Phase 0：意思決定と準備（1週間）

- [ ] サービス名・ドメイン取得
- [ ] Supabaseプロジェクト作成（リージョン: Tokyo）
- [ ] LLMプロバイダのAPIキー取得（Gemini / OpenAI）
- [ ] Stripeアカウント開設（本人確認に数日かかる）
- [ ] 屋号・[[特定商取引法]]表記の住所方針を決定（後述 §10）

### Phase 1：マルチユーザー化（2〜3週間）★ 最大の山

- [ ] DBスキーマ + RLS適用
- [ ] Supabase Auth 組み込み（ログイン／サインアップ／リセット画面）
- [ ] `index.html` のデータアクセスを `fetch('/api/...')` から Supabase SDK に置換
- [ ] 翻訳Edge Function 実装（Ollama → Gemini API）
- [ ] 既存プロンプトのクラウドLLM向け再調整と品質確認
- [ ] 自分のデータを移行して**自分がドッグフーディング**
- [ ] アカウント設定・エクスポート・退会画面

### Phase 1.5：記事フィード機能（2〜3週間）★ 商品価値の本体

**既に完成している部分と、これから作る部分を区別すること。**

| 工程 | 状態 |
|---|---|
| ① 情報源から候補記事を集める | **未着手**（現在はWeiboを人力で巡回） |
| ② 候補から教材にする価値のあるものを選ぶ | **未着手**（現在はあなたの目利き） |
| ③ 記事化 | **稼働中**（要約型 → 書き下ろし型への改修が必要） |
| ④ 重要語彙の抽出 | **稼働中**（ほぼそのまま流用可） |

**新規開発の本体は①②。③④は移植と改修。**

**① 情報源の自動収集**

- [ ] 事前選定サイトのリスト作成（10〜20本）。**RSSの有無・robots.txt・利用規約を1本ずつ確認**
- [ ] Weibo抜きで中国語ソースを確保（新聞社・技術メディア・企業プレスリリース・政府系）
- [ ] 記事取り込みバッチ（pg_cron で日次。RSS優先、必要な場合のみ Firecrawl）
- [ ] `raw_articles` の全文検索インデックス構築（外部検索APIは使わない）

**② 目利きの自動化 ★ ここが最大の未知数**

- [ ] 「教材にする価値がある記事」の判断基準を**言語化する**
- [ ] スクリーニングプロンプトを作成
- [ ] **一致率テスト**：候補50件に自分で印をつけ、プロンプトの選定結果と突き合わせる。**7割を切るなら基準の言語化が不足**
- [ ] 2〜3日分繰り返して基準を具体化

**③④ 既存パイプラインの移植**

- [ ] Notion運用の生成プロンプトをEdge Functionへ移植
- [ ] **要約型 → 書き下ろし型への改修**（有料配信では要約は翻案リスク。`pricing-plan.md` §10.2）
- [ ] 難易度・長さの指定パラメータを追加（改修の副産物。Proの機能になる）
- [ ] **実際の消費トークンを計測し、原価試算を実測値に差し替える**

**共通基盤**

- [ ] 共有プールのキャッシュ判定（キーワード×言語×鮮度）
- [ ] 人気カテゴリの定期生成（1日2本）
- [ ] 記事の音読トレーニングUI（既存プレイヤーを流用）

### Phase 2：課金（1〜2週間）

- [ ] Stripe Product / Price 定義（月額・年額）
- [ ] Checkout セッション作成 + Webhook（署名検証・冪等性処理）
- [ ] プラン別の機能ゲート（Edge Function側で判定。**クライアント側だけの制限は無意味**）
- [ ] 使用量カウントと無料枠超過時のUX
- [ ] 無料トライアル設計

### Phase 3：法務・公開準備（1週間）

- [ ] 利用規約
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
- [ ] LP（ランディングページ）と集客

### Phase 5：差別化（公開後）

- [ ] Fail履歴を使った弱点レポート・出題優先度づけ
- [ ] 復習スケジューリング（間隔反復）
- [ ] 中国語コースの正式商品化（既に実装済みの資産）

**現実的な総工数目安：週10時間の稼働で 3.5〜4.5ヶ月**（記事生成パイプラインが既存資産として使えるため）。

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

---

## 11. リスクと対策

| リスク | 影響 | 対策 |
|---|---|---|
| **集客できない** | 最大のリスク。技術より難しい | Phase 1完了時点でLPを公開し、事前登録で需要を測る。作り込む前に検証 |
| LLM費用の暴走 | 一部ユーザーの乱用で赤字 | 入力長制限、レート制限、プラン別上限、Stripeとは別に費用アラート設定 |
| LLMの翻訳品質がOllamaより悪い | 体験劣化 | Phase 1でプロンプト再調整と自分でのA/B比較を必ず実施 |
| iOS SafariのWeb Speech API仕様変更 | 発音機能が壊れる | 主要機能なので複数OSバージョンで定期確認。最悪クラウドTTSへの退避策を用意（原価は上がる） |
| Supabase無料枠の一時停止 | サービス断 | 公開時点で必ずProへ |
| 個人情報漏洩 | 事業継続不能 | RLSの徹底、service_roleキーの管理、ログに本文を残さない |
| 特商法の住所表示 | 自宅住所の公開に抵抗 | 「請求があれば遅滞なく開示」方式、またはバーチャルオフィス（条件あり） |

---

## 12. 次のアクション（推奨順）

1. **`pricing-plan.md` のプラン設計を確認・確定する**
2. **LPを先に作り、事前登録を集めて需要を検証する**（実装より先にこれをやる価値が高い）
3. Supabaseプロジェクトを作り、§5のスキーマを流し込む
4. Gemini APIで既存プロンプトを叩き、Ollamaとの品質差を確認する
5. Phase 1に着手

---

### 関連ドキュメント

- `docs/pricing-plan.md` — 料金プラン設計・原価計算・損益分岐点
