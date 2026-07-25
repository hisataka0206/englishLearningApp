# 家族版（[[Supabase]] + [[PWA]]）

`../../docs/10-specs/family-edition-spec.md` の実装。**記事フィードと課金は含まない**。

```
family/
├── supabase/
│   ├── migrations/
│   │   ├── 20260726000001_init.sql          … 7テーブル・RLS・トリガー
│   │   ├── 20260726000002_assessments.sql   … 発音評価の記録（★流し忘れ注意）
│   │   └── 20260726000003_usage_units.sql   … 課金単位（audio_seconds / calls）＋ keepalive用 ping()
│   └── functions/
│       ├── _shared/common.ts                … JWT検証・クォータ・Gemini・usage_logs
│       ├── translate/index.ts               … 翻訳（小学生ペルソナのプロンプト移植）
│       ├── keywords/index.ts                … 語彙抽出（word/meaning入替補正つき）
│       └── assess/index.ts                  … 発音評価（Azure Speech のプロキシ）
├── web/                                     … クライアント（素のJS・Vercelに配置）
│   ├── index.html / app.js / data-api.js / assess.js / config.js
│   ├── manifest.json / vercel.json          … PWA / SPAルーティング
│   └── icon-192.png / icon-512.png / apple-touch-icon.png   … 差し替え可の仮アイコン
├── scripts/migrate_to_supabase.py           … 既存JSONの移行（★fails/practicesは冪等でない）

（keepalive のワークフローは **リポジトリルートの `.github/workflows/keepalive.yml`**。
　GitHub Actions はルートの `.github/` しか読まないため、ここには置けない）
```

---

## セットアップ手順

### 1. Supabase プロジェクト作成

1. [supabase.com](https://supabase.com) で新規プロジェクト（**リージョン Tokyo / Free**）
2. **Authentication → Providers → Email → "Enable email signup" を OFF**（第三者の登録を防ぐ）
3. SQL Editor でマイグレーションを**3本とも**実行する（順番どおり）
   1. `supabase/migrations/20260726000001_init.sql`
   2. `supabase/migrations/20260726000002_assessments.sql`
   3. `supabase/migrations/20260726000003_usage_units.sql`
   ★ 2本目を忘れると `assessments` が無く、**発音評価と📊記録タブが動かない**
   ★ 3本目を忘れると **発音評価の原価が測れない**（GO/NO-GO 条件Cの判定材料が取れない）＋ **keepalive が落ちる**（`public.ping()` が無いため）
4. Authentication → Users → **Add user** で家族分を手動作成（`email_confirm` をON）
   - 娘のアカウントは親のエイリアス（`you+daughter@example.com`）でよい

### 2. Edge Function のデプロイ

```bash
npm i -g supabase
supabase login
supabase link --project-ref <PROJECT_REF>

# APIキーはここにのみ置く（クライアントには絶対に出さない）
# ↓ 値は下の「キーの取得元」を参照。手で打たずコピペする
supabase secrets set GEMINI_API_KEY=<GOOGLE_API_KEY>
supabase secrets set GEMINI_MODEL=gemini-2.5-flash-lite
supabase secrets set MAX_INPUT_CHARS=300

# 発音評価
supabase secrets set AZURE_SPEECH_KEY=<azure.key>
supabase secrets set AZURE_SPEECH_REGION=japaneast
supabase secrets set AZURE_SPEECH_TIER=f0        # 無料枠。S0にしたら s0 に変える

supabase functions deploy translate
supabase functions deploy keywords
supabase functions deploy assess
```

### キーの取得元（既に手元にある）

| Secret | 取得元 | 備考 |
|---|---|---|
| `GEMINI_API_KEY` | `~/work/humanoidAsAService/Tools/translateChineseWebpage/.env` の **`GOOGLE_API_KEY`** | [[AI Studio]] 発行。インフォグラフィック生成（Nano Banana）と共用 |
| `AZURE_SPEECH_KEY` / `AZURE_SPEECH_REGION` | `~/work/englishLearningApp/apps/local/config.json` の **`azure.key` / `azure.region`** | 現行アプリが使っているものと同じ |

いずれも `.gitignore` 済み。新規発行するなら Gemini は [Google AI Studio](https://aistudio.google.com/apikey)。

> **⚠️ `GOOGLE_API_KEY` を共用する場合の注意**
> このキーは humanoidAsAService 側の画像生成（プリペイド課金）でも使っている。
> **家族版の翻訳と課金が同じキーに混ざるため、`usage_logs` の実測とAPIコンソールの請求額が一致しなくなる。**
> 原価の実測（GO/NO-GO 条件C）を正確にやるなら、**家族版専用のキーを新規発行するのが望ましい**。
>
> **⚠️ Azureキーは一度チャットに貼られている。** 再発行を推奨（Azure ポータル → キーの再生成。`config.json` と Supabase Secrets の両方を更新すること）。

> **Azure は F0（無料枠）で運用する。** 月5時間・**同時リクエスト1件**（調整不可）。
> 家族が同時に録音すると429になるため、Edge Function 側で2回まで再試行する。
> 中国語は1回の評価で2回呼ぶので消費は2倍（実質2.5時間ぶん）。

### 3. クライアント設定

`web/config.js` の2値を、Supabase の Project Settings → API から書き換える。

```js
export const CONFIG = {
  SUPABASE_URL: "https://xxxx.supabase.co",
  SUPABASE_ANON_KEY: "eyJ...",   // RLSが効いている前提で公開可
};
```

### 4. データ移行

```bash
cd scripts
python3 migrate_to_supabase.py --data ../../local/data --dry-run    # まず確認

export SUPABASE_URL=https://xxxx.supabase.co
export SUPABASE_SERVICE_ROLE_KEY=eyJ...      # service_role キー（絶対に公開しない）
export USER_ID=<自分のユーザーUUID>
python3 migrate_to_supabase.py --data ../../local/data
```

> データは `apps/local/data/` にある（`scripts/` から見て `../../local/data`）。

### 5. デプロイ（Vercel Hobby）

**`web/` をプロジェクトのルートディレクトリとして配置する。** 必要なファイルは同梱済み。

| ファイル | 役割 |
|---|---|
| `vercel.json` | SPAのルーティング（`/history` などを直接開いても404にしない） |
| `manifest.json` | PWA |
| `icon-192.png` / `icon-512.png` / `apple-touch-icon.png` | ホーム画面のアイコン。**仮のもの**なので好きな絵に差し替えてよい（同名・同サイズで置くだけ） |

> iOS はホーム画面追加時に manifest の `icons` を見ないため、`apple-touch-icon.png` が別に要る（`index.html` で参照済み）。

### 6. keepalive

1. GitHub リポジトリの Secrets に `SUPABASE_URL` と `SUPABASE_ANON_KEY` を登録する
2. **Actions タブから `keepalive` を手動実行（Run workflow）して、緑になることを確認する**

> ワークフローは**リポジトリルートの `.github/workflows/keepalive.yml`**（GitHub Actions はルートしか読まない）。
> DBに必ず到達させるため `public.ping()` を呼ぶ（migration 3本目で作成）。
> テーブルを直接読む方式だと、RLSポリシーを変えたときに黙って壊れるため。

### 7. 動作確認

下の「受け入れ確認」を実機（iPhone）で1つずつ確認する。

---

## 現行版との違い

| 項目 | 現行（Mac常駐） | 家族版 |
|---|---|---|
| 保存先 | ローカルJSON + Google Drive | Supabase Postgres（RLSで個人別） |
| 翻訳 | ローカルLLM（Ollama） | Gemini（Edge Function経由） |
| ピンイン | サーバーで pypinyin | **クライアントで pinyin-pro**（原価ゼロ・即時） |
| 分かち書き（中国語の区切り） | サーバーで jieba | **クライアントで `pinyin-pro` の `segment()`**（词レベル。同等） |
| 発音 | Web Speech API | 同じ（変更なし） |
| 認証 | なし | メール＋パスワード（サインアップ無効） |
| Mac | 起動が必須 | **不要** |
| 発音評価 | Mac常駐サーバーがAzureを呼ぶ | **Edge Function経由**（キーはサーバー側のみ） |
| ミス種類の分類 | Python（pypinyin） | **クライアントJS**（pinyin-pro） |

| 家族間の可視性 | — | **なし**（互いのデータもプロフィールも見えない） |

記事モード（Notion同期）のみ家族版の対象外。現行アプリでそのまま使える。

---

## 既知の制約

| 項目 | 内容 |
|---|---|
| **Azure F0** | 月5時間・**同時リクエスト1件**。家族が同時に録音すると待たされる（自動で2回再試行） |
| **移行スクリプトの再実行** | `sentences` / `words` は冪等だが、**`fails` / `practices` は2回流すと二重に入る**。やり直すときは先に該当ユーザーの行を消す |
| **バックアップ** | Supabase Free に自動バックアップは**無い**。定期 `pg_dump` は未実装（`../../docs/00-business/exit-plan.md` §3） |

---

## 受け入れ確認（spec §13）

- [ ] 家族3人がログインでき、**互いのデータもプロフィールも見えない**（RLS）
- [ ] 既存データが全件移行されている
- [ ] iPhoneのホーム画面から起動し、発音・保存・履歴・再学習・**発音チェック**が動く
- [ ] **📊記録タブ**で苦手な音（直近30日）が出る
- [ ] 中国語の区切り「細かめ」が**词（単語）単位**になっている（1文字ずつではない）
- [ ] 深夜（JST 0〜9時）に保存した文の日付が**その日**になっている
- [ ] `usage_logs` にトークン数が記録されている
- [ ] `usage_logs` の `kind='assess'` の行に **`audio_seconds` と `calls` が入っている**（0のままなら原価が測れない）
- [ ] クライアントのバンドルにAPIキーが含まれていない
