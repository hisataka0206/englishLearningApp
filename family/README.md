# 家族版（[[Supabase]] + [[PWA]]）

`docs/family-edition-spec.md` の実装。**記事フィードと課金は含まない**。

```
family/
├── supabase/
│   ├── migrations/20260726000001_init.sql   … 7テーブル・RLS・トリガー
│   └── functions/
│       ├── _shared/common.ts                … JWT検証・クォータ・Gemini・usage_logs
│       ├── translate/index.ts               … 翻訳（小学生ペルソナのプロンプト移植）
│       └── keywords/index.ts                … 語彙抽出（word/meaning入替補正つき）
├── web/                                     … クライアント（素のJS・Vercelに配置）
│   ├── index.html / app.js / data-api.js / config.js / manifest.json
├── scripts/migrate_to_supabase.py           … 既存JSONの移行（冪等）
└── .github/workflows/keepalive.yml          … Freeプランの一時停止対策
```

---

## セットアップ手順

### 1. Supabase プロジェクト作成

1. [supabase.com](https://supabase.com) で新規プロジェクト（**リージョン Tokyo / Free**）
2. **Authentication → Providers → Email → "Enable email signup" を OFF**（第三者の登録を防ぐ）
3. SQL Editor に `supabase/migrations/20260726000001_init.sql` を貼って実行
4. Authentication → Users → **Add user** で家族分を手動作成（`email_confirm` をON）
   - 娘のアカウントは親のエイリアス（`you+daughter@example.com`）でよい

### 2. Edge Function のデプロイ

```bash
npm i -g supabase
supabase login
supabase link --project-ref <PROJECT_REF>

# APIキーはここにのみ置く（クライアントには絶対に出さない）
supabase secrets set GEMINI_API_KEY=xxxxx
supabase secrets set GEMINI_MODEL=gemini-2.5-flash-lite
supabase secrets set MAX_INPUT_CHARS=300

supabase functions deploy translate
supabase functions deploy keywords
```

Gemini APIキーは [Google AI Studio](https://aistudio.google.com/apikey) で取得。

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
python3 migrate_to_supabase.py --data ../../data --dry-run    # まず確認

export SUPABASE_URL=https://xxxx.supabase.co
export SUPABASE_SERVICE_ROLE_KEY=eyJ...      # service_role キー（絶対に公開しない）
export USER_ID=<自分のユーザーUUID>
python3 migrate_to_supabase.py --data ../../data
```

### 5. デプロイ（Vercel Hobby）

`web/` をルートとして配置する。SPAのルーティングのため、`vercel.json` に以下を置く。

```json
{ "rewrites": [{ "source": "/(.*)", "destination": "/index.html" }] }
```

アイコン（`icon-192.png` / `icon-512.png`）を `web/` に置くとPWAとしてホーム画面に追加できる。

### 6. keepalive

GitHub リポジトリの Secrets に `SUPABASE_URL` と `SUPABASE_ANON_KEY` を登録する。

---

## 現行版との違い

| 項目 | 現行（Mac常駐） | 家族版 |
|---|---|---|
| 保存先 | ローカルJSON + Google Drive | Supabase Postgres（RLSで個人別） |
| 翻訳 | ローカルLLM（Ollama） | Gemini（Edge Function経由） |
| ピンイン | サーバーで pypinyin | **クライアントで pinyin-pro**（原価ゼロ・即時） |
| 発音 | Web Speech API | 同じ（変更なし） |
| 認証 | なし | メール＋パスワード（サインアップ無効） |
| Mac | 起動が必須 | **不要** |

記事モード・発音評価（Azure）は家族版の対象外。現行アプリでそのまま使える。

---

## 受け入れ確認（spec §13）

- [ ] 家族3人がログインでき、互いのデータが見えない（RLS）
- [ ] 設定画面に家族の最終利用日だけが見える
- [ ] 既存データが全件移行されている
- [ ] iPhoneのホーム画面から起動し、発音・保存・履歴・再学習が動く
- [ ] `usage_logs` にトークン数が記録されている
- [ ] クライアントのバンドルにAPIキーが含まれていない
