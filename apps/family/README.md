# 家族版（[[Supabase]] + [[PWA]]）

`../../docs/10-specs/family-edition-spec.md` の実装。**記事フィードと課金は含まない**。

```
family/
├── deploy.sh                                … デプロイ補助（check / db / functions / all）
├── supabase/
│   ├── config.toml                          … CLI設定（★無いと link も db push も動かない）
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

> **★ すべての `supabase` コマンドは `apps/family/` で実行する。**
> CLI は「カレントディレクトリの `supabase/` フォルダ」を見るため、場所を間違えると
> 「supabase directory not found」で止まる。
>
> ```bash
> cd ~/work/englishLearningApp/apps/family
> bash deploy.sh check     # 前提が揃っているか確認（何も変更しない）
> ```

### 必要な値と、その在り処（先にここを開いて全部コピーしておくと速い）

| 必要な値 | ダッシュボードのどこ | 使う場所 |
|---|---|---|
| **Project ID**（＝ Reference ID） | **Settings → General → Project ID**「Reference used in APIs and URLs」<br>例: `hnjpsvqoldcfuy…` | `supabase link --project-ref <ここ>` |
| **Project URL** | Settings → API → Project URL<br>`https://<Project ID>.supabase.co`<br>**★ パスを含めない**（`/rest/v1/` が付いた「RESTful endpoint」と間違えやすい） | `web/config.js` の `SUPABASE_URL`<br>GitHub Secrets の `SUPABASE_URL`<br>移行スクリプトの `SUPABASE_URL` |
| **Publishable key**<br>（＝旧 anon key） | Settings → **API Keys** → Publishable key<br>`sb_publishable_…` または `eyJ…` | `web/config.js` の `SUPABASE_ANON_KEY`<br>GitHub Secrets の `SUPABASE_ANON_KEY` |
| **Secret key**<br>（＝旧 service_role key） | Settings → **API Keys** → Secret keys<br>**目のアイコン（Reveal）で表示**（伏せているだけで何度でも見られる）<br>見つからなければ **Legacy API Keys** タブの `service_role`（`eyJ…`）でも可 | 移行スクリプトの `SUPABASE_SERVICE_ROLE_KEY`<br>GitHub Secrets の `SUPABASE_SECRET_KEY`<br>**絶対に公開しない** |
| **ユーザーUUID** | Authentication → Users → 自分の行の UID | 移行スクリプトの `USER_ID` |
| **DBパスワード** | プロジェクト作成時に自分で決めたもの<br>忘れたら Settings → Database → Reset database password | `supabase link` で聞かれる |

> **キーの名前が新しくなっている。** Supabase は `anon` / `service_role` を
> **`publishable` / `secret`** に置き換えつつある（旧キーも当面は動く）。
> ダッシュボードに「anon」が見つからないときは **API Keys タブ**を見る。
>
> **同じ値が3つの名前で出てくるので注意。**
>
> | 実体 | 移行スクリプト | GitHub Secrets | `web/config.js` |
> |---|---|---|---|
> | Publishable（旧 anon） | — | `SUPABASE_ANON_KEY` | `SUPABASE_ANON_KEY` |
> | **Secret（旧 service_role）** | `SUPABASE_SERVICE_ROLE_KEY` | **`SUPABASE_SECRET_KEY`** | 使わない |
>
> **Secret キーが分からなくなったら**：①ターミナルの履歴（`history | grep SERVICE_ROLE`）
> ②ダッシュボードで Reveal ③Legacy API Keys タブの `service_role`
> ④作り直してもよい（既存キーは無効化されない）

---

### 0. CLI の準備（初回だけ）

```bash
npm i -g supabase
supabase --version
supabase login           # ブラウザが開く。アクセストークンを発行して貼る
```

> Docker は**ローカル実行**（`supabase functions serve`）に必要。
> **デプロイだけなら通常は不要**。求められたら Docker Desktop を入れる。

### 1. Supabase プロジェクト作成とリンク

1. [supabase.com](https://supabase.com) で新規プロジェクト（**リージョン Tokyo / Free**）
2. **認証の設定**（★ここを間違えるとログインできなくなる）

   | 設定 | 値 | 場所 |
   |---|---|---|
   | **Email プロバイダ** | **ON**（有効のまま） | Authentication → Sign In / Providers → **Email** |
   | **Allow new users to sign up**<br>（新規登録の許可） | **OFF** | 同ページの **User Signups** セクション |

   > **「Email プロバイダ」自体を OFF にしてはいけない。**
   > OFF にすると新規登録だけでなく**ログインも塞がれ**、
   > `Email logins are disabled` が出て誰も入れなくなる。
   >
   > 止めたいのは**第三者の新規登録だけ**なので、切るのは「Allow new users to sign up」の方。
   >
   > **順番に確認するのが安全**：まず Email プロバイダ ON のままログインできることを確かめ、
   > そのあと signup を OFF にして、**もう一度ログインできることを確認**する。
3. プロジェクトを CLI に紐付ける

```bash
cd ~/work/englishLearningApp/apps/family
supabase projects list                    # REFERENCE ID 列を控える
supabase link --project-ref <REFERENCE_ID>
```

> DBパスワードを聞かれる。プロジェクト作成時に決めたもの。忘れたら
> Dashboard → Settings → Database → Reset database password で再設定できる。

4. Authentication → Users → **Add user** で家族分を手動作成（`email_confirm` をON）
   - 娘のアカウントは親のエイリアス（`you+daughter@example.com`）でよい

### 2. マイグレーションの適用

```bash
bash deploy.sh db          # = supabase db push（3本を順番に適用）
```

> **Dashboard の SQL Editor に貼っても同じ**だが、`db push` なら順番も適用済み管理も
> CLI がやる。手で貼る場合は `supabase/migrations/` の3本を**番号順に**実行すること。

| # | ファイル | 忘れると |
|---|---|---|
| 1 | `20260726000001_init.sql` | 何も動かない |
| 2 | `20260726000002_assessments.sql` | **発音評価と📊記録タブが全滅** |
| 3 | `20260726000003_usage_units.sql` | **原価が測れない**（GO/NO-GO 条件C）＋ **keepalive が落ちる**（`public.ping()` が無い） |

適用できたかの確認 — SQL Editor で `select public.ping();` が時刻を返せばOK。

### 3. Edge Function のデプロイ

**Dashboard の「Create new edge function」画面は使わない。** 関数3本と共有モジュールは
リポジトリにあり、手で貼ると git と乖離する。CLI から出す。

まず**シークレットを登録**する（関数から参照される。クライアントには絶対に出ない）。

```bash
cd ~/work/englishLearningApp/apps/family

supabase secrets set GEMINI_API_KEY=<GOOGLE_API_KEY>
supabase secrets set GEMINI_MODEL=gemini-2.5-flash-lite
supabase secrets set MAX_INPUT_CHARS=300

supabase secrets set AZURE_SPEECH_KEY=<azure.key>
supabase secrets set AZURE_SPEECH_REGION=japaneast
supabase secrets set AZURE_SPEECH_TIER=f0        # 無料枠。S0にしたら s0

supabase secrets list                            # 6つ入ったか確認
```

つぎに**デプロイ**する。

```bash
bash deploy.sh functions
```

やっていることは3行だけ。

```bash
supabase functions deploy translate
supabase functions deploy keywords
supabase functions deploy assess
```

| 補足 | |
|---|---|
| `_shared/common.ts` | 先頭が `_` のフォルダは**関数として扱われない**。各関数が `../_shared/common.ts` を相対importしており、**デプロイ時に自動で同梱**される。個別にデプロイする必要はない |
| JWT検証 | `config.toml` で3本とも `verify_jwt = true`。ログイン必須なのでこのまま |
| 反映確認 | Dashboard → Edge Functions に3本並び、各関数の Logs でエラーが出ていないこと |

> **デプロイしてもすぐには動かない。** シークレット未設定だと 502（LLM未設定）が返る。
> 先に `supabase secrets list` で確認すること。

#### キーの取得元（既に手元にある）

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

### 4. クライアント設定

`web/config.js` の2値を書き換える（上の表の **Project URL** と **Publishable key**）。

> **★ よくある取り違え**：API設定ページには似たURLが複数並んでいる。
> **`https://<ref>.supabase.co` を使う**（パス無し）。
> `https://<ref>.supabase.co/rest/v1/`（RESTful endpoint）を貼ると、
> **ログイン時に `Invalid path specified in request URL` が出て何もできない**。
> （`data-api.js` の `baseUrl()` で自動的に落とすようにしたが、正しい値を入れるのが本筋）

```js
export const CONFIG = {
  SUPABASE_URL: "https://xxxx.supabase.co",
  SUPABASE_ANON_KEY: "sb_publishable_...",   // Publishable key。RLSが効いている前提で公開可
};
```

### 5. データ移行

```bash
cd scripts
python3 migrate_to_supabase.py --data ../../local/data --dry-run    # まず確認

export SUPABASE_URL=https://xxxx.supabase.co
export SUPABASE_SERVICE_ROLE_KEY=sb_secret_...   # Secret key（旧 service_role）。絶対に公開しない
export USER_ID=<自分のユーザーUUID>
python3 migrate_to_supabase.py --data ../../local/data
```

> データは `apps/local/data/` にある（`scripts/` から見て `../../local/data`）。

**つまずきやすい点**

| 症状 | 原因 | 対処 |
|---|---|---|
| `HTTP 404 PGRST125 Invalid path specified in request URL` | **`SUPABASE_URL` の末尾に `/` が付いている**（`//rest/v1/...` になる）。ダッシュボードからコピーすると付くことがある | 末尾の `/` を外す。スクリプト側でも自動で落とすようにした |
| `HTTP 401` | Publishable（旧anon）キーを使っている | **Secret（旧service_role）キー**を使う |
| `HTTP 404`（PGRST125以外） | テーブルが無い | マイグレーション3本を適用したか確認 |
| **ログイン画面で** `Invalid path specified in request URL` | `web/config.js` の `SUPABASE_URL` に `/rest/v1/` が付いている | Project URL（パス無し）に直して push（Vercelが自動で再デプロイ） |
| **ログイン画面で** `Email logins are disabled` | **Email プロバイダごと OFF になっている**（新規登録だけを止めたつもりで全部止まっている） | Authentication → Sign In / Providers → **Email を ON**。止めるのは「Allow new users to sign up」の方（手順1-2） |
| **ログイン画面で** `メールアドレスかパスワードが違います` | 文字どおり。または**ユーザーをまだ作っていない** | Authentication → Users → Add user（`email_confirm` をON） |
| `violates foreign key constraint` | `USER_ID` が実在しない | Authentication → Users の UID をコピーする |
| 実施回数が倍になった | **`fails` / `practices` は冪等でない** | 先に消してから再実行する<br>`delete from practices where user_id='<UID>';`<br>`delete from fails where user_id='<UID>';` |

> スクリプトは投入前に `fails` / `practices` の既存行を数え、**0でなければ止まる**。
> 承知のうえで続けるときだけ `--force` を付ける。

### 6. デプロイ（Vercel Hobby）

アプリの**画面をインターネットに公開する**作業。ここまでで作ったのは裏側（DB・認証・Edge Function）だけで、
`web/` はまだ手元にしかない。公開して初めて **娘のiPhoneから使える**ようになる。
録音（発音チェック）は **HTTPS でないと動かない**ので、その意味でも必須。

#### 6.1 先に push する

Vercel は **GitHub 上のコード**を見る。手元のコミットが残っていると古い版が公開される。

```bash
cd ~/work/englishLearningApp
git status          # 未コミットが無いこと
git push
```

#### 6.2 GitHub と連携する（★URLを貼る欄は使わない）

トップの「Let's build something new」に **`.git` のURLを貼る欄があるが、これは公開リポジトリ専用**。
本リポジトリは **private**（事業計画・収益予測を含むため公開しない）なので、貼ると

```
Could not access the repository. Please ensure you have access to it.
```

で弾かれる。**正しい手順はこちら。**

1. Vercel で **Add New → Project**
2. **Import Git Repository** の欄で GitHub アカウントを接続
3. **「Adjust GitHub App Permissions」** を開き、**`englishLearningApp` にアクセスを許可**する
   （All repositories でも、Only select repositories でこのリポジトリだけでもよい）
4. 一覧に出てきた `englishLearningApp` の **Import** を押す

> **★「New Project / Cloning from GitHub」という画面に入ったら、それは別物。**
> `Git Scope` と **`Private Repository Name`** の入力欄がある画面は
> 「**テンプレートを複製して新しいリポジトリを作る**」フロー。
> そのまま Create すると **別リポジトリが新規作成され、既存の `englishLearningApp` と切り離される**
> （以後 `git push` しても反映されない）。
> 画面下部の **「Import a different Git Repository →」** から入り直すこと。

> Vercel Hobby は**private リポジトリでもデプロイできる**。公開する必要はない。

#### 6.3 設定

| 項目 | 値 |
|---|---|
| **Root Directory** | **`apps/family/web`** ★ここが最重要。既定のままだとリポジトリ全体を公開しようとして失敗する |
| Framework Preset | **Other**（ビルド不要の素のHTML/JS） |
| Build Command | 空のまま |
| Output Directory | 空のまま |

**必要なファイルは同梱済み。**

| ファイル | 役割 |
|---|---|
| `vercel.json` | SPAのルーティング（`/history` などを直接開いても404にしない） |
| `manifest.json` | PWA |
| `icon-192.png` / `icon-512.png` / `apple-touch-icon.png` | ホーム画面のアイコン。**仮のもの**なので好きな絵に差し替えてよい（同名・同サイズで置くだけ） |

> iOS はホーム画面追加時に manifest の `icons` を見ないため、`apple-touch-icon.png` が別に要る（`index.html` で参照済み）。

> **★ 手順4（`web/config.js` の書き換え）を先に済ませること。**
> Supabase の URL とキーが入っていないと、デプロイしても真っ白な画面になる。

発行された `https://xxxx.vercel.app` を iPhone で開き、**共有 → ホーム画面に追加**。

### 7. keepalive

1. GitHub リポジトリの Secrets に `SUPABASE_URL` と `SUPABASE_ANON_KEY` を登録する
2. **Actions タブから `keepalive` を手動実行（Run workflow）して、緑になることを確認する**

| 失敗したら | 意味 | 対処 |
|---|---|---|
| `HTTP 401 Invalid API key` | Secrets の `SUPABASE_ANON_KEY` が違う／余分な空白・改行が入っている | Publishable key を貼り直す |
| `HTTP 404` | `public.ping()` が無い | マイグレーション**3本目**を適用（`bash deploy.sh db`） |
| `HTTP 000` | URLに到達できない | `SUPABASE_URL` を確認（`https://<ref>.supabase.co`） |

> **APIキーは `apikey` ヘッダにのみ載せる。** 新形式の Publishable key（`sb_publishable_…`）は
> **JWTではない**ため、`Authorization: Bearer` に載せると JWT として解釈され `Invalid API key` になる。
> （旧 anon key はJWTだったので両方に載せても通っていた）

> ワークフローは**リポジトリルートの `.github/workflows/keepalive.yml`**（GitHub Actions はルートしか読まない）。
> DBに必ず到達させるため `public.ping()` を呼ぶ（migration 3本目で作成）。
> テーブルを直接読む方式だと、RLSポリシーを変えたときに黙って壊れるため。

### 8. バックアップ（週次・自動）

Supabase Free に**自動バックアップは無い**。評価期間の2ヶ月ぶんは
「アプリのデータ」であると同時に**GO/NO-GO の判断材料**なので、薄く保険をかける。

1. GitHub → Settings → Secrets → **`SUPABASE_SECRET_KEY`** を追加
   - 値は **Secret key**（`sb_secret_…`。Settings → API Keys → Secret keys の **Reveal**）
   - 移行スクリプトの `SUPABASE_SERVICE_ROLE_KEY` と**同じ値**（`history | grep SERVICE_ROLE` でも出る）
   - `SUPABASE_URL` は keepalive で登録済みのものを共用する
2. Actions → **backup** → Run workflow で1回試す
3. 実行結果の **Artifacts** から `backup-YYYYMMDD-HHMM` をダウンロードできる

| | |
|---|---|
| 頻度 | 毎週日曜 12:10 JST（＋手動実行） |
| 対象 | 8テーブルをJSONで（`profiles` `sentences` `words` `fails` `practices` `assessments` `usage_logs` `subscriptions`） |
| 保持 | **90日**（評価期間2ヶ月をカバー） |
| 対象外 | `auth.users`（アカウント）。ダッシュボードで作り直せるので実害なし |

> **主キーがテーブルで揃っていない点に注意。** `subscriptions` だけ `user_id` が主キーで
> `id` 列が無いため、`order=id` を決め打ちすると 400 になる。
> ワークフローはテーブルごとに並び順のキーを持たせてある。

> **`pg_dump` は使っていない。** 守る対象が小さいテーブル数本なので、
> PostgREST から JSON で吸い出すだけにしてある。事業版に進むなら
> そのときに完全なダンプへ切り替える（`../../docs/00-business/exit-plan.md` §3）。

> **戻し方**：JSONをそのまま `POST /rest/v1/<table>`（Secret キー、`Prefer: resolution=ignore-duplicates`）に投げる。
> `scripts/migrate_to_supabase.py` の `post()` がそのまま使える。

### 9. 動作確認

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
| **バックアップ** | Supabase Free に自動バックアップは**無い**。週次のJSONダンプで代替している（手順8）。完全な `pg_dump` は事業版に進むときに |

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
