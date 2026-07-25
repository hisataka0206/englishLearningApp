# 事業版[[差分仕様書]]

作成日: 2026-07-26 / ベースライン: `family-edition-spec.md`
対象: 家族版から**有料SaaS版へ拡張する差分のみ**

> **本書は差分のみを記述する。** 家族版と同一の部分は書かない。
> 「家族版 + 本書 = 事業版の完全な仕様」となるように構成している。
> 記述の形式は **追加 / 変更 / 削除** の3種類。

---

## 1. 全体像

### 1.1 アーキテクチャの差分

```mermaid
flowchart TB
    subgraph CLIENT["ブラウザ / PWA"]
        UI1["作文・履歴・プレイヤー"]:::base
        UI2["記事フィード<br/>興味設定・リクエスト"]:::add
        UI3["プラン・お支払い<br/>法務ページ"]:::add
    end

    subgraph EDGE["Supabase Edge Functions"]
        EF1["translate / keywords"]:::chg
        EF2["lessons 系 7本"]:::add
        EF3["billing 系 3本"]:::add
        EF4["cron: 取り込み・定期生成"]:::add
    end

    subgraph DB["Supabase Postgres"]
        T1["コア7テーブル<br/>profiles/sentences/words<br/>fails/practices<br/>subscriptions/usage_logs"]:::chg
        T2["記事フィード7テーブル<br/>sources/raw_articles/lessons<br/>lesson_vocab/lesson_reads<br/>interests/lesson_requests"]:::add
    end

    EXT1["Gemini / OpenAI API"]:::base
    EXT2["情報源<br/>Global Voices / arXiv / 政府系"]:::add
    EXT3["Stripe"]:::add

    UI1 --> EF1
    UI1 --> T1
    UI2 --> EF2
    UI3 --> EF3
    EF1 --> EXT1
    EF2 --> EXT1
    EF2 --> T2
    EF4 --> EXT2
    EF4 --> T2
    EF3 --> EXT3
    EXT3 -.Webhook.-> EF3
    EF3 --> T1

    classDef base fill:#eceff1,stroke:#607d8b,color:#263238
    classDef add fill:#e8f5e9,stroke:#2e7d32,color:#1b5e20
    classDef chg fill:#fff8e1,stroke:#f9a825,color:#e65100
```

**凡例**： ⬜ 家族版のまま　🟩 **追加**　🟨 **変更**

### 1.2 差分の総量

| 領域 | 家族版 | 追加 | 変更 | 削除 |
|---|---|---|---|---|
| テーブル | 7 | **+7** | 2 | 0 |
| RLSポリシー | 9 | +14 | 1 | **1** |
| Edge Function | 2 | **+12** | 2 | 0 |
| 画面 | 5 | **+11** | 2 | 1 |
| 外部依存 | 1 | **+2** | 0 | 0 |

---

## 2. データベースの差分

### 2.1 ER図（コア＋追加分）

```mermaid
erDiagram
    auth_users ||--|| profiles : "1:1"
    auth_users ||--|| subscriptions : "1:1"
    auth_users ||--o{ sentences : ""
    auth_users ||--o{ words : ""
    sentences ||--o{ fails : ""
    sentences ||--o{ practices : ""
    sentences ||--o{ words : "source_id"
    auth_users ||--o{ usage_logs : ""

    auth_users ||--o{ interests : "ADD"
    auth_users ||--o{ lesson_requests : "ADD"
    auth_users ||--o{ lesson_reads : "ADD"
    sources ||--o{ raw_articles : "ADD"
    lessons ||--o{ lesson_vocab : "ADD"
    lessons ||--o{ lesson_reads : "ADD"
    lessons ||--o{ lesson_requests : "ADD"
    lessons ||--o{ words : "ADD vocab-to-words"
```

> **`lessons` は `user_id` を持たない。** 全ユーザーの共有プールであることがこの設計の要。

### 2.2 追加テーブル（7本）

定義の全文は `../30-research/saas-migration-study.md` §5.1b を参照。役割の要約：

| テーブル | 役割 | `user_id` |
|---|---|---|
| `sources` | 事前選定した情報源。**ライセンス・帰属テンプレ・利用可能範囲を保持** | なし（管理者データ） |
| `raw_articles` | 取り込んだ生記事。**ユーザーには直接見せない**（事実抽出のネタ元） | なし |
| `lessons` | **生成された学習教材。共有プールの本体** | なし（★重要） |
| `lesson_vocab` | 教材の重要語彙 | なし |
| `lesson_reads` | 誰がどの教材を読んだか | **あり** |
| `interests` | ユーザーの興味キーワード | **あり** |
| `lesson_requests` | リクエスト履歴。**プラン上限のカウント対象** | **あり** |

### 2.3 変更テーブル（2本）

#### `subscriptions` — 課金連携のためのカラム追加と値域変更

```sql
-- 【変更】plan の値域
--   家族版: 'family' 固定
--   事業版: 'free' | 'standard' | 'pro'
-- 【追加】Stripe連携カラム
alter table subscriptions
  add column stripe_customer_id     text unique,
  add column stripe_subscription_id text unique,
  add column current_period_end     timestamptz;

-- 【変更】status の値域
--   家族版: 'active' 固定
--   事業版: 'active' | 'trialing' | 'past_due' | 'canceled' | 'inactive'
```

> **既存の家族3人は `plan='family'` のまま残す**（無料で全機能が使える内部ユーザーとして扱う）。値域に `'family'` を含めたまま拡張する。

#### `usage_logs` — 記事生成系の記録に対応

```sql
-- 【変更】kind の値域に3種を追加
--   家族版: 'translate' | 'keywords'
--   事業版: + 'screening' | 'lesson_write' | 'lesson_vocab'
-- 【追加】記事生成時の対象を記録
alter table usage_logs add column lesson_id uuid;
-- 【変更】user_id を nullable に（定期生成分は user_id なし）
alter table usage_logs alter column user_id drop not null;
```

### 2.4 ★ 削除するRLSポリシー（見落とし注意）

家族版で**家族間の最終利用日を共有するために入れた全開放ポリシーを、事業版では必ず削除する。**

```sql
-- 【削除】家族版の profiles 全開放
drop policy "family read" on profiles;
```

**これを消し忘れると、全ユーザーのプロフィール（表示名・最終利用日）が他人から見える。** 事業版では重大なプライバシー問題になる。

あわせてアカウント設定画面の「家族の最終利用日」欄も削除する（§4.3）。

### 2.5 追加するRLSポリシー

```sql
-- 管理者専用（サービスロールのみ）
alter table sources      enable row level security;
alter table raw_articles enable row level security;
-- ポリシーを作らない = anon/authenticated からは一切アクセス不可

-- 教材は Edge Function 経由でのみ配信するため、直接SELECTは禁止
alter table lessons      enable row level security;
alter table lesson_vocab enable row level security;
-- ポリシーを作らない

-- 本人のみ
alter table lesson_reads     enable row level security;
alter table interests        enable row level security;
alter table lesson_requests  enable row level security;

create policy "own rows" on lesson_reads for all
  using (auth.uid() = user_id) with check (auth.uid() = user_id);
create policy "own rows" on interests for all
  using (auth.uid() = user_id) with check (auth.uid() = user_id);
create policy "own read" on lesson_requests for select
  using (auth.uid() = user_id);
```

> **`lessons` にポリシーを作らない**のが肝。Supabase SDK から直接引けないため、Free/有料の出し分けを Edge Function で強制できる。

---

## 3. API の差分

### 3.1 追加エンドポイント（12本）

| メソッド / パス | 用途 | 認証 |
|---|---|---|
| `GET /lessons` | 記事フィード一覧。プラン判定＋Freeは月3本でゲート | 必要 |
| `GET /lessons/:id` | 記事詳細。本文・対訳・語彙・**出典リンク・帰属表示** | 必要 |
| `POST /lessons/request` | キーワード指定の生成。キャッシュ判定→枠消費→生成 | 必要 |
| `GET /lessons/quota` | 当月のリクエスト残数・作文残文数 | 必要 |
| `POST /lessons/:id/read` | 既読記録 | 必要 |
| `POST /lessons/:id/vocab-to-words` | 抽出語彙を自分の単語帳へ登録 | 必要 |
| `POST /lessons/:id/proofread` | 記事の語彙を使った自作文のAI添削（Pro） | 必要 |
| `POST /billing/checkout` | Stripe Checkout セッション作成 | 必要 |
| `POST /billing/portal` | Stripe カスタマーポータルURL発行 | 必要 |
| `POST /stripe-webhook` | **署名検証必須。冪等性処理必須** | 署名 |
| 内部 `cron_ingest_sources()` | 情報源からの記事取り込み（pg_cron 日次） | — |
| 内部 `cron_generate_daily()` | 人気カテゴリの定期生成（pg_cron 日次） | — |

`interests` のCRUDは Supabase SDK 直叩き（RLSで本人のみ）。

### 3.2 変更エンドポイント（2本）

#### `/translate` `/keywords` — クォータ判定を有効化

家族版では**判定コードパスを通すだけで素通し**していた箇所を、実際に効かせる。

```mermaid
flowchart LR
    A["リクエスト"] --> B["JWT検証"]
    B --> C["subscriptions.plan 取得"]
    C --> D{"プラン判定"}
    D -->|family| E["無制限で通過"]:::base
    D -->|free| F["月150文"]:::add
    D -->|standard| G["月1,500文"]:::add
    D -->|pro| H["月3,000文"]:::add
    E --> I["LLM呼び出し"]
    F --> J{"超過?"}
    G --> J
    H --> J
    J -->|Yes| K["402 Payment Required"]:::add
    J -->|No| I

    classDef base fill:#eceff1,stroke:#607d8b
    classDef add fill:#e8f5e9,stroke:#2e7d32
```

**コードの変更点は「上限値を返す関数」だけ。** 判定を呼ぶ場所は家族版で既に実装済み。

### 3.3 記事リクエストのフロー（新規）

**共有プールの肝。キャッシュヒット時は枠を消費しない。**

```mermaid
flowchart TD
    A["ユーザーがキーワード入力"] --> B["プラン別の月次上限を確認"]
    B --> C{"上限到達?"}
    C -->|Yes| D["402 を返す"]
    C -->|No| E["lessons を検索<br/>lang + keyword + expires_at > now()"]
    E --> F{"ヒット?"}
    F -->|Yes| G["既存教材を返す<br/>★枠を消費しない（原価ゼロ）"]
    F -->|No| H["raw_articles を全文検索<br/>上位3本を選定"]
    H --> I["① スクリーニング<br/>Gemini 2.5 Flash-Lite"]
    I --> J["② 書き下ろし<br/>gpt-5.4-mini（Proは gpt-5.4）"]
    J --> K["③ 語彙抽出＋対訳＋ピンイン<br/>Gemini 2.5 Flash-Lite"]
    K --> L["lessons / lesson_vocab に INSERT<br/>★共有プールに追加"]
    L --> M["帰属表示を自動生成して埋め込む"]
    M --> N["枠を1消費"]
    N --> O["usage_logs に3件記録"]

    style G fill:#e8f5e9,stroke:#2e7d32
    style L fill:#e3f2fd,stroke:#1976d2
```

---

## 4. 画面の差分

### 4.1 画面遷移図（追加分をハイライト）

```mermaid
flowchart TD
    LOGIN["/login<br/>ログイン"]:::chg
    SIGNUP["/signup<br/>サインアップ"]:::add
    RESET["/reset<br/>パスワードリセット"]:::add
    MAIN["/<br/>メイン（作文）"]:::base
    HIST["/history<br/>履歴"]:::base
    SET["/settings<br/>アカウント設定"]:::chg
    FEED["/feed<br/>記事フィード一覧"]:::add
    LESSON["/feed/:id<br/>記事詳細"]:::add
    REQ["/feed/request<br/>記事リクエスト"]:::add
    INT["/settings/interests<br/>興味キーワード設定"]:::add
    BILL["/settings/billing<br/>プラン・お支払い"]:::add
    LEGAL["/terms /privacy /tokushoho<br/>法務3ページ"]:::add

    SIGNUP --> LOGIN
    LOGIN --> MAIN
    LOGIN -.-> RESET
    MAIN <--> HIST
    HIST -->|"🔊 再学習"| MAIN
    MAIN --> SET
    MAIN <--> FEED
    FEED --> LESSON
    FEED --> REQ
    REQ --> LESSON
    LESSON -->|"語彙を単語帳へ"| HIST
    LESSON -->|"音読"| MAIN
    SET --> INT
    SET --> BILL
    BILL -.Stripe.-> BILL
    LOGIN -.-> LEGAL

    classDef base fill:#eceff1,stroke:#607d8b
    classDef add fill:#e8f5e9,stroke:#2e7d32
    classDef chg fill:#fff8e1,stroke:#f9a825
```

### 4.2 追加画面（11）

| 画面 | 内容 | 必須度 |
|---|---|---|
| サインアップ | メール/パスワード + Googleログイン | 必須 |
| パスワードリセット | Supabase Auth 標準機能 | 必須 |
| **記事フィード一覧** | 新着／カテゴリ別／既読・未読。Freeは月3本でゲート | 必須 |
| **記事詳細** | 本文・日本語対訳・ピンイン・重要語彙。**出典リンクと帰属表示は法的に必須** | 必須 |
| **記事リクエスト** | キーワード入力。残数表示＋「既にあれば消費しない」旨の提示 | 必須 |
| **興味キーワード設定** | `interests` の登録・削除 | 必須 |
| **プラン・お支払い** | 現在のプラン、当月使用量、アップグレード、Stripeポータル導線 | 必須 |
| 退会 | 全データ削除の確認 | 必須 |
| 利用規約 / プライバシーポリシー / 特商法表記 | 静的3ページ | **法的に必須** |
| アーカイブ | 鮮度切れの教材を別表示 | 推奨 |
| 連載ビュー | 同一トピックの深掘り（Pro） | 推奨 |

### 4.3 変更画面（2）

#### ログイン画面

| | 家族版 | 事業版 |
|---|---|---|
| サインアップ導線 | **なし**（signup無効） | **あり** |
| パスワードリセット導線 | なし | **あり** |
| Googleログイン | なし | **あり** |
| 法務ページへのリンク | なし | **あり** |

#### アカウント設定画面

| 項目 | 家族版 | 事業版 |
|---|---|---|
| 表示名 / 既定言語 / 発音速度 / 区切りモード | ○ | ○ |
| **家族の最終利用日** | ○ | **削除**（§2.4） |
| エクスポート / ログアウト | ○ | ○ |
| プラン・使用量 | — | **追加** |
| 興味キーワード | — | **追加** |
| 退会 | — | **追加** |

---

## 5. 認証の差分

```mermaid
flowchart LR
    subgraph FAM["家族版"]
        F1["signup OFF"]:::base
        F2["管理者が<br/>ダッシュボードで作成"]:::base
        F3["メール確認なし"]:::base
        F4["リセット画面なし"]:::base
    end
    subgraph SAAS["事業版"]
        S1["signup ON"]:::add
        S2["自己サインアップ<br/>+ Googleログイン"]:::add
        S3["メール確認 必要"]:::add
        S4["リセット画面 必要"]:::add
    end
    FAM ==>|差分| SAAS

    classDef base fill:#eceff1,stroke:#607d8b
    classDef add fill:#e8f5e9,stroke:#2e7d32
```

| 項目 | 家族版 | 事業版 | 作業 |
|---|---|---|---|
| Email signup | **OFF** | **ON** | ダッシュボード設定 |
| メール確認 | 不要 | **必要** | **カスタムSMTP設定が必要**（Supabase内蔵SMTPは送信数制限あり） |
| パスワードリセット | 画面なし | **画面を実装** | 追加 |
| ソーシャルログイン | なし | **Google / Apple** | 追加 |
| 新規登録時の初期化 | トリガーで `profiles` + `subscriptions(plan='family')` | 同トリガーで **`plan='free'`** | **変更** |

> **カスタムSMTPの設定を忘れると、サインアップ直後にメールが届かず登録が完了しない。** 事業版で最初につまずくポイント。

---

## 6. インフラ・運用の差分

| 項目 | 家族版 | 事業版 | 備考 |
|---|---|---|---|
| Supabase | **Free** | **Pro（$25/月）** | `raw_articles` を作った時点で500MB上限を超える。**記事フィード着手＝Pro移行** |
| ホスティング | **Vercel Hobby（無料）** | **Vercel Pro（$20/月）** | **Hobbyは非商用限定。課金開始前に必ず移行** |
| ドメイン | `*.vercel.app` | **独自ドメイン** | 特商法表記の信頼性にも影響 |
| pg_cron | 未使用 | **有効化** | 記事取り込みと定期生成 |
| keepalive | GitHub Actions 週1回 | **不要**（Proは停止しない） | 削除してよい |
| バックアップ | なし | **日次・7日保持**（Pro標準） | |
| エラー監視 | なし | **Sentry等** | |
| レート制限 | なし | **必要** | 翻訳・記事リクエストの乱用防止 |
| スクレイピング | なし | **不要の見込み** | 推奨情報源はすべてRSS／公式API |

---

## 7. 撤退時の逆操作（差分の巻き戻し）

**本書の差分は、そのまま撤退手順の裏返しになる。**

```mermaid
flowchart LR
    A["事業版<br/>稼働中"]:::saas --> B["① pg_cron 停止"]
    B --> C["② フィード系UIを<br/>フラグで非表示"]
    C --> D["③ Stripe 全解約<br/>Product無効化"]
    D --> E["④ raw_articles / lessons<br/>を退避して削除"]
    E --> F["⑤ Supabase Pro→Free<br/>Vercel Pro→Hobby"]
    F --> G["家族版<br/>月130円"]:::fam

    classDef saas fill:#fff8e1,stroke:#f9a825
    classDef fam fill:#e8f5e9,stroke:#2e7d32
```

**テーブルを DROP する必要はない。** cron を止めれば `raw_articles` は増えず、UIを隠せば `lessons` は参照されない。Free枠の500MBに収めるためにデータを退避・削除するだけでよい。

所要時間は半日程度（`../00-business/exit-plan.md` §4.1）。

**注意**：撤退時に `profiles` の `"family read"` ポリシーを**復活させる**か判断すること（家族の最終利用日を再び見せるなら必要）。

---

## 8. 差分の索引（実装時のチェックリスト）

### 8.1 追加

- [ ] テーブル7本（`sources` `raw_articles` `lessons` `lesson_vocab` `lesson_reads` `interests` `lesson_requests`）
- [ ] RLSポリシー（本人のみ3本。`lessons` 系は**ポリシーを作らない**）
- [ ] Edge Function 12本（§3.1）
- [ ] 画面11（§4.2）
- [ ] Stripe 連携（Product / Price / Checkout / Portal / Webhook）
- [ ] 情報源の取り込みバッチと定期生成（pg_cron）
- [ ] 帰属表示の自動生成（`sources.attribution_template` から）
- [ ] レート制限
- [ ] カスタムSMTP

### 8.2 変更

- [ ] `subscriptions`：Stripeカラム追加、`plan`/`status` の値域拡張
- [ ] `usage_logs`：`kind` に3種追加、`lesson_id` 追加、`user_id` を nullable に
- [ ] `/translate` `/keywords`：クォータ判定を実際に効かせる
- [ ] 新規登録トリガー：`plan='family'` → `plan='free'`
- [ ] ログイン画面：サインアップ・リセット・Googleログインの導線を追加
- [ ] アカウント設定：プラン欄・興味キーワード・退会を追加
- [ ] Supabase Free→Pro、Vercel Hobby→Pro

### 8.3 削除

- [ ] **`profiles` の `"family read"` RLSポリシー**（§2.4。**最重要の見落としポイント**）
- [ ] アカウント設定の「家族の最終利用日」欄
- [ ] GitHub Actions の keepalive

---

## 9. 差分を壊さないための原則

1. **依存は「フィード → コア」の一方向に限定する。** `sentences` 等のコアテーブルが `lessons` を参照してはいけない（`words` に記事由来の語彙を入れるのはOK。`source_id` は `sentences` を指すため）
2. **`lessons` に `user_id` を持たせない。** 共有プールの前提が崩れ、原価構造が壊れる
3. **教材の配信は必ず Edge Function 経由。** `lessons` にRLSポリシーを作らないことで構造的に強制する
4. **家族3人は `plan='family'` のまま残す。** 有料プランの検証時に自分が課金対象になると面倒
5. **帰属表示は自動生成に限る。** 人手のチェックリストに頼るとライセンス違反が必ず起きる

---

### 関連ドキュメント

- `family-edition-spec.md` — **ベースライン（本書と対で使う）**
- `current-app-spec.md` — 現行機能の移植チェックリスト
- `../30-research/saas-migration-study.md` — 事業版の背景・意思決定・法務要件
- `../00-business/pricing-plan.md` — 料金プラン・原価計算
- `../30-research/content-sources.md` — 情報源の評価（**ライセンスの正典**）
- `../00-business/exit-plan.md` — 撤退ラインと退避先
