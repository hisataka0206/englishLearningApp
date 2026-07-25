# 現行アプリ仕様書（`apps/local`）

対象: `apps/local/`（Mac常駐版・**稼働中**） / 現行バージョン: v1.37.1（画面右上に表示）
最終更新: 2026-07-26

> **本書の位置づけ** — 現行アプリについての**唯一の仕様書**。
> 家族版・事業版の仕様は `family-edition-spec.md` / `saas-diff-spec.md` を参照。

## この文書の読み方

| 目的 | 読む部 |
|---|---|
| このアプリが何なのかを知る | **第I部 概要とねらい** |
| 記事モード（Notion同期）の仕組みを知る | **第II部 記事モード** |
| **家族版へ移植する／移植漏れを防ぐ** | **第III部 実装棚卸し** |

> 第III部の節番号（§1〜§12）は他文書から `§6.5` のような形で参照されている。**番号は変えないこと。**

---
---

# 第I部 概要とねらい

## 概要

日本語で言いたいことを入力すると外国語（[[英語]]・[[中国語]]）に翻訳し、その文を[[発音練習]]・保存・[[単語帳]]登録・[[失敗履歴]]記録できる、スマホ対応の[[ブラウザアプリ]]。加えて[[Notion]]の中国語学習記事を取り込んで練習する[[記事モード]]と、[[Azure AI Speech]]による[[発音評価]]を持つ。

翻訳は[[ローカルLLM]]（[[Ollama]]）、読み上げはブラウザ内蔵の[[音声合成]]（Web Speech API）を用い、データは[[Google Drive]]に[[GAS]]（Google Apps Script）経由で保存する。

## 対象者と背景

主たる対象は、作成者の子ども（[[小学生]]）。英語・中国語を学び始めた段階の学習者を想定している。市販の学習アプリは大人向けの語彙・例文が多く、子どもが「自分が本当に言いたいこと」を外国語にして練習する体験が得にくい。そこで、日本語で思ったことを入力するだけで、その子自身の言葉を外国語化し、繰り返し声に出して練習できる環境を目的として自作した。

翻訳の口調は小学生が実際に話すようなやさしい表現に寄せており、例文もプレースホルダから子ども向けの内容にしている。

## 目標（このアプリで解決したいこと）

第一に、[[言いたいことを外国語で言える]]ようにすること。教科書の例文ではなく、学習者自身の発話を起点にすることで学習の動機と定着を高める。

第二に、[[発音の反復練習]]をしやすくすること。文を節（意味のまとまり）ごとに分解し、節単位で再生・一時停止・任意の節から再生できるようにして、聞き取れない部分だけを繰り返せるようにしている。

第三に、[[学習の記録と振り返り]]。保存した文と単語を日付ごとに履歴として残し、実施日・失敗回数を自動で蓄積する。

中国語については、[[拼音]]（ピンイン）は読めるようになったが[[漢字と発音の結びつき]]が弱い、という具体的な課題がある。これを視覚的に補助するために、字の上に拼音を重ねる[[ルビ表示]]と、Notion記事を取り込む[[記事モード]]（第II部）を追加した。

## 基本動作原理

利用者はまず対象言語（英語／中国語）をボタンで選ぶ。日本語を入力して翻訳を実行すると、Mac上で常駐する小さなサーバー（Python標準ライブラリのみ）が[[ローカルLLM]]に問い合わせ、自然な訳文を返す。訳文が出た時点で即座に音声合成による[[発音]]が始まり、同時に[[重要キーワード]]を抽出して単語候補として提示する。中国語モードでは[[pypinyin]]により全文と各単語の拼音を併記する。

訳文は画面上でタップして直接編集できる。発音の区切りは「✂️ 区切り編集」ボタンで格子UIに切り替え、**文字（中国語）または語（英語）のすき間をタップして**指定する。編集内容は下部の[[練習ウィンドウ]]の節チップに即時反映される。

> **区切り編集を開くと以後は自動の節分割を行わず、指定した区切りだけを使う**（`explicitBreaks` フラグ）。区切りを手打ちの `/` で入れた場合も同様。自動分割と併用されるのは、どちらも行っていないときだけ。

保存すると、文・日本語・区切り位置・拼音・登録日・失敗履歴・実施履歴を1レコードとして[[固有ID]]付きで保持し、[[GAS]]経由でGoogle Driveの指定フォルダにJSONとして書き込む（人間が読みやすいMarkdownビューも同時生成）。英語と中国語はそれぞれ別ファイル（`sentences.json` / `sentences_zh.json` など）に保存される。

履歴から過去の文を呼び出す（再学習）と、区切り位置も復元してメイン画面に読み込み、発音練習・上書き保存・単語登録ができる。実施日は発音のたびに自動記録される。

## 画面構成

ヘッダーのナビゲーションは「[[自分の文]]」「[[記事]]」「[[記録]]」の**3系統**（＋再読込ボタン）。「自分の文」は**自分が言いたいことを外国語化して練習する**機能、「記事」は**外部データ（Notion記事）を取り込んで練習する**機能で、この2つがアプリの柱である。

「自分の文」の中は「作成」「履歴」の2サブタブに分かれる。作成側は「日本語入力 → 訳文の表示・編集 → 発音練習」に特化し、練習中に履歴が視界に入らないようにしている。履歴側は日付別（文と単語をまとめて表示）・文のみ・単語のみのタブと検索を備え、表形式で見つけやすくしている。

画面下部の[[フレーズプレイヤー]]は、節チップ・再生/一時停止・速度調整（プリセットと保存）・区切りモード（ふつう／細かめ／文単位、既定は細かめ）・録音による発音評価を持ち、長文でも領域の高さを制限して他の操作を妨げない。

「記録」には発音評価の履歴と[[苦手な音]]の集計（過去30日）を置き、拼音を字の上に重ねて表示する。

## データと保存

保存の実体は Google Drive 上の JSON ファイル（[[GAS]]の Web アプリ経由でアクセス）。ローカルの `data/` を作業コピーとし、変更のたびに直列化してアップロードする（同名ファイルの二重生成を防止）。起動時にローカルが空なら Drive から取り込むため、機種変更や再起動にも耐える。

> **push と pull で対象ファイルが異なる。** push は10ファイル（英中の `sentences`/`words` の json+md 各4本、`articles_zh.json`、`assessments.json`）だが、起動時の pull は5ファイル（`sentences*.json` / `words*.json` / `articles_zh.json`）のみで、**`assessments.json` は pull されない**。ローカルの `data/` を失うと発音評価の履歴だけ復元されない（§11.3 参照）。

失敗履歴は[[Notion]]の中国語学習運用（該当箇所に「Fail」コメントを付ける方式）に着想を得ており、文ごとにラベル＋日時で蓄積する（既定ラベルは「Fail」の1種）。

## 拡張性

UIの言語別文言は `LABELS` 辞書に、翻訳・キーワード抽出のプロンプトはサーバーの `TRANSLATE_PROMPTS` / `KEYWORDS_PROMPTS` に一元化されている。新しい言語（例: [[フランス語]]）を追加する場合は、これらに同じキーでブロックを1つ足し、言語ボタンを追加するだけで、UI表記・発音・区切り・保存が揃う設計とした。

## 動作環境・制約

翻訳は自宅MacのローカルLLMで動くため、**Macが起動している必要がある**（この制約を外すのが家族版の目的）。外出先のスマホからは[[Tailscale]]等で自宅Macのサーバーに接続する運用を想定し、利用者はTailscaleの存在を意識せずホーム画面のアイコンから使えるようにしている（サーバーはログイン時自動起動）。GitHub Actions等の外部環境からローカルLLMへ直接アクセスすることはできない。

録音（発音評価）はブラウザの `navigator.mediaDevices` を使うため **HTTPS（または `localhost`）が必須**。他端末から使うには `enable_https.sh` で証明書を用意する。

翻訳・キーワードの品質はモデルに依存する。既定は軽量な `qwen2.5:1.5b`（速度優先）で、品質を上げたい場合は画面のプルダウンで大きめのモデルに切り替えられる。

## 主なコンポーネント

| ファイル | 役割 |
|---|---|
| `server.py` | 常駐ミニサーバー（翻訳中継・保存・拼音生成・記事API・発音評価） |
| `index.html` | スマホ対応UI（発音練習・履歴・記事・記録） |
| `azure_speech.py` | Azure AI Speech の発音評価クライアント |
| `error_kind.py` | 発音誤りの R/V/T/N/F 分類 |
| `notion_client.py` | Notion REST の薄いラッパ（記事解析・失敗履歴の書き戻し） |
| `tools_import_fails.py` | Notionのインライン失敗コメントを `articles_zh.json` へ取り込むインポーター（冪等）。通常APIは音節アンカーを返さないため、MCPの get-comments 出力を渡す設計 |
| `google_drive.py` / `drive_auth.py` | GAS/OAuth の Drive クライアント |
| `gas/Code.gs` | Drive書き込み用のGASバックエンド |
| `config.json` / `config.example.json` | [[外部設定ファイル]]（保存先・モデル・失敗ラベル・Notion・Azure）。`config.json` はgit管理外、`.example` が雛形 |
| `setup.sh` / `enable_https.sh` | 常時起動セットアップ / HTTPS有効化 |

---
---

# 第II部 記事モード（Notion同期）

> **状態: 実装済み・稼働中。** 本部は実装された仕様を記述する。

## 目的

Notionで運用中の[[中国語勉強用記事]]（週1本・約600字・全文[[拼音]]付き・句ごとに中文/拼音/日本語の3行セット＋重要語彙表）を、アプリの[[発音練習]]UIで句・音節単位に練習できるようにする。さらにアプリで付けた[[失敗履歴]]（[[Fail]]）をNotionの記事へ書き戻し、既存の集計運用につなげる。

学習上の狙いは、**拼音は読めるが[[漢字と発音の結びつき]]が弱い**という課題の解消（節プレイヤー＋ルビ表示で視覚的に補助）。

## 全体構成（既存温存・UI流用）

現行の画面はそのまま維持し、ヘッダーナビに「[[記事]]」を1系統追加する。記事ページのUIは既存部品を流用する。

- 記事一覧（履歴サブタブの表形式を流用）。**最終学習日・学習回数・[[Nomiss率]]・未反映Fail数**を表示し、学習済みは背景をグレー化する
- 記事を開くと句が並び、各句は既存の[[フレーズプレイヤー]]（節分割・再生/一時停止・速度・タップ再生）で練習
- 拼音表示・[[音声合成]]（zh-CN）・Fail記録は既存機能をそのまま利用
- 重要語彙は既存の単語帳表示を流用
- 記事ページ先頭に**原文へのリンク**を表示する

## データモデル

Driveに `articles_zh.json` を追加（既存の `sentences_zh.json` 等とは別区画）。

```
Article {
  id, notion_page_id, date,
  title, zh_title, jp_title,     // 表示用タイトル（中文/日本語）
  source_url,                    // 原文のURL（記事ページ先頭に表示）
  total_chars,                   // Nomiss率の分母
  notion_fail_table_id,          // 書き戻し先テーブルのブロックID
  imported_at,

  sentences: [ { idx, zh, pinyin, ja,
                 pairs,          // [[文字, 拼音], …] 1文字表示・ルビ用
                 breaks } … ],   // 節区切り位置（この文字indexの後で区切る）

  // ★ fails は sentence 配下ではなく Article 直下の1本の配列
  fails: [ { idx,               // 句番号
             ci,                // 句内の文字index
             char, syllable,    // 該当の漢字・拼音
             label,             // F / R / V / T / N
             time,
             pushed,            // Notionへ書き戻し済みか（未反映数のバッジに使う）
             sessioned } … ],   // 勉強完了の集計に算入済みか

  sessions: [ { date, misses, total, nomiss } … ],   // 「勉強完了」ごとの記録

  vocab: [ { zh, pinyin, ja, pairs } … ]
}
```

> `updated_at` は**書き込まれていない**（存在しないフィールド）。

拼音はNotion側の[[全小文字]]表記をそのまま採用（アプリの自動生成では上書きしない）。

Notion側の構造は**変更しない**（記事子ページ＝出典情報＋「中文要约＋拼音」＋重要語彙表）。

## Notion接続

`server.py` が[[Notion REST API]]を直接呼ぶ。[[インテグレーショントークン]]は `config.json` の `notion` セクションに外部化（git管理外）。

```
"notion": {
  "token": "PUT_YOUR_NOTION_INTEGRATION_TOKEN",
  "articles_parent_page_id": "36dcd557226180e4afe0cf5739016724",
  "api_version": "2022-06-28"
}
```

Notion側で対象の親ページ（および子記事）にインテグレーションを接続しておく必要がある。

## Notion → アプリ（取り込み）

**初回のみ**親ページを指定する。以降は「記事を更新」操作で、親ページ配下の子ページのうち**まだ取り込んでいない新規記事を自動検出して取り込む**（`notion_page_id` の差分で判定）。手動で特定記事を再取り込みする補助操作も残している。

解析は**3つの記事フォーマット**に対応する（Notion側の書き方が時期によって異なるため）。

1. `第N句` ラベル付きブロック → `中文：` / `拼音：` 行を句ごとに抽出
2. `中文：` を境界にした連続ブロック
3. `1.` `2.` … の番号付きリスト形式

日本語訳は **`日本語：` で始まる行**、または直後の日本語トグル（details）から取得する（`日本語：` 行が優先）。重要語彙表を `vocab` として取得する。

取り込みは**3件ずつのループ**で行う（未取り込みが尽きるまで `limit: 3` を繰り返す）。取り込み後はオフラインでも練習でき、句単位で発音・Fail記録が可能。

既存のインラインFailの読み込みは `tools_import_fails.py` が担う（Notion通常APIは音節アンカーを返さないため、MCPの get-comments 出力を渡す）。

## アプリ → Notion（失敗履歴の書き戻し）

**方式：記事ページ末尾に「失敗履歴」テーブルを作成/更新する。** インラインコメントの新規作成はAPIで不可能なため。

- 記事の末尾（重要語彙表の下）に見出し2「失敗履歴（アプリ記録）」とテーブルを1つ設ける（探索は本文に「失敗履歴」を含む見出しの部分一致）
- 列：**`日付` / `句` / `漢字` / `拼音` / `ラベル`**（`notion_client.py` の `FAIL_HEADER`。**漢字が拼音より先**）
- 既存のインラインFail運用とは別系統として明示（見出しで区別）

**同期タイミングは手動ボタンのみ。** Failはアプリ内（Drive）に随時記録し、「Notionへ反映」ボタンでまとめて書き戻す（Fail都度の自動送信はしない）。未反映のFail件数はバッジで表示する。

## 失敗の粒度

句単位に加えて、**1文字単位**でFailを付けられる。**長押し450ms**（PC は右クリック）で F/R/V/T/N の失敗種別を選択する。位置は `fails[].idx`（句番号）と `ci`（文字index）で保持し、該当の `char` / `syllable` とともに失敗履歴テーブルへ反映する。

> ラベル定義 F/R/V/T/N は `config.json` ではなく **`server.py` の定数 `ARTICLE_FAIL_LABELS`**（code + name）にあり、`/api/health` の `article_fail_labels` で配信される。「自分の文」側の `fail_labels`（`config.json` 由来・既定は `["Fail"]`）とは別物。

## 学習の記録（勉強完了）

記事ページの「✅ 勉強完了」ボタンで**セッションを確定**する。未集計（`sessioned` が偽）のFailを数えて `nomiss = round(100 × (total_chars − misses) / total_chars, 1)`（**百分率・小数1桁**。`total_chars` が0のときは1として計算）を算出し、`sessions[]` に `{date, misses, total, nomiss}` を1件追加する。記事一覧にはここで確定した**最終学習日・学習回数・Nomiss率**が表示され、学習済みの行は背景がグレーになる。

節の区切りは記事側でも「✂️ 区切り編集」で編集でき、`sentences[].breaks` としてサーバーに永続化される（`/api/articles/breaks`）。

## 制約・非対応

- Notion既存Failと同じ「音節へのインラインコメント」の**新規作成はAPI不可**。よってアプリ発のFailは末尾テーブルに集約する
- 翻訳系のローカルLLMとは独立。記事取り込み・書き戻しはNotion接続時のみ動作（Mac起動＋トークン設定が前提）
- **記事モードは家族版には移植しない**（`family-edition-spec.md` の対象外。現行アプリでのみ使う）
- pinyin-fail-report スキルを末尾テーブル対応に調整する作業は未着手

---
---

# 第III部 実装棚卸し（[[移植チェックリスト]]）

対象: `apps/local/index.html`, `apps/local/server.py`
用途: **クラウド版への移植漏れを防ぐための唯一のチェックリスト**

## 使い方

各項目の「判定」列を **移植 / 廃止 / 変更** のいずれかで埋める。
**すべての行が埋まるまで実装完了とみなさない。** 家族版の受け入れ基準はこの表である。

> 例外が2つ。① **§6 のAPI表だけは「判定」ではなく「移行後」列**（移行先の実現手段：Supabase SDK / Edge Function / 廃止 / 対象外）を使う。② **記事モードは家族版に移植しない**ため、§1 は「自分の文」側のみを棚卸しし、記事モードのUIは対象外とする。

> 以下の節番号（§1〜§12）は他文書から参照されている。**番号を変えないこと。**

---
## 1. 画面・UI要素

> **本節は「自分の文」側とプレイヤーのみを対象とする。** 記事モードのUI（記事一覧・記事本文・長押しFailメニュー・「✅ 勉強完了」・「⬆️ Notion」・記事側の区切り編集）は**家族版に移植しないため棚卸し対象外**。仕様は第II部、APIは §6 を参照。

### 1.1 ヘッダ

| # | 機能 | 実装詳細 | 判定 |
|---|---|---|---|
| 1 | バージョン表示 | `/api/health` の `version` を `#ver` に表示 | **廃止** |
| 2 | ステータス表示 | Ollama ✅/❌ ＋ 保存先（Drive/ローカル）を2行 | **廃止**（クラウド化で意味を失う。代わりにログイン中ユーザー名を表示） |
| 3 | ナビ3種＋サブタブ2種 | ナビ `showView('main'\|'articles'\|'record')`＝✍️自分の文／📰記事／📊記録。「自分の文」内は `setSub('compose'\|'history')`＝作成／履歴。**URLは変化しない** | 移植（記事は対象外） |
| 4 | 再読込ボタン | `location.reload()` | 移植 |

### 1.2 メイン画面（作文）

| # | 機能 | 実装詳細 | 判定 |
|---|---|---|---|
| 5 | 日本語入力 textarea | `#ja`、**文字数制限なし** | **変更**（300文字上限を追加） |
| 6 | 翻訳実行ボタン | ラベルが言語で変化（英語にする/中国語にする） | 移植 |
| 7 | 言語切替タブ en/zh | `setLang()` → localStorage保存＋履歴再読込＋結果クリア＋プレイヤー閉 | 移植 |
| 8 | **モデル選択プルダウン** | `/api/health` の `models[]` から動的生成 | **廃止**（サーバー側でモデル固定） |

### 1.3 翻訳結果カード

| # | 機能 | 実装詳細 | 判定 |
|---|---|---|---|
| 9 | 訳文の contenteditable 編集 | `#english`。入力のたびに `current.marked` を再計算 | 移植 |
| 10 | ピンイン表示行 | `#pinyin`。編集中は **400msデバウンス**で再取得 | **変更**（クライアント側ライブラリで即時計算。デバウンス不要） |
| 11 | 発音ボタン | `playerLoad()` | 移植 |
| 12 | **「✂️ 区切り編集」** | `toggleMainBreakEdit()` → `#breakGrid` に格子UIを描画。文字（zh）／語（en）の**すき間をタップ**して区切る。開いた時点で `explicitBreaks = true`（§3.1） | 移植 |
| 12b | ~~「／区切り挿入」ボタン~~ | `insertSlash()` / `savedRange` は**定義されているが呼び出し元が無い死にコード**。UIにボタンは存在しない | **廃止**（移植しない） |
| 13 | 保存ボタン | 新規保存 / `current.pageId` があれば上書き | 移植 |
| 14 | キーワード一覧 | チェックボックス＋語/ピンイン/意味＋個別🔊 | 移植 |
| 15 | 単語一括登録 | チェック済みを順次POST。**未保存なら先に文を保存** | 移植 |

### 1.4 履歴画面

| # | 機能 | 実装詳細 | 判定 |
|---|---|---|---|
| 16 | タブ3種＋更新 | 日付別 / {文}のみ / 単語のみ。2つ目のラベルは `LABELS.sentTab` で言語により変化（en=英文のみ / zh=中国語のみ）。「更新」ボタンで `loadHistory()` | 移植 |
| 17 | **検索フィルタ** | クライアント側substring（文=英文+日本語 / 単語=語+意味+例文） | 移植 |
| 18 | 文テーブル | 日付・訳文(+ピンイン)+日本語・実施(回数/最終日)・fail(件数バッジ+ラベル別ボタン)・操作 | 移植 |
| 19 | 単語テーブル | 日付・語(+ピンイン)+例文・意味・操作(🔊/🗑) | 移植 |
| 20 | 日付別グルーピング | `created` の日付でdesc、「文N件」「単語N語」の小見出し | 移植 |
| 21 | **fail記録ボタン** | `config.json` の `fail_labels[]` から動的生成 | **変更**（クライアント側の定数へ。§6「`fail_labels` の移行先」で決定済み） |
| 22 | 削除（文・単語） | confirm → API → 再読込 | 移植 |
| 23 | **再学習（🔊 study）** | 下記 §2 に詳述。**最も複雑な導線** | **変更**（キーワード再抽出の扱い。§2.2） |

### 1.5 発音プレイヤー（画面下部固定）

| # | 機能 | 実装詳細 | 判定 |
|---|---|---|---|
| 24 | 固定下部バー | 初期 `display:none`。表示時に body の `paddingBottom` を自動調整 | 移植 |
| 25 | 節チップ | クリックで単発再生。`active`/`done`/通常 の3状態。`scrollIntoView({block:"nearest"})` で追従 | 移植 |
| 26 | zhチップ下のピンイン | `/api/pinyin` にバッチ送信して差し込み | **変更**（拼音はクライアント側で計算。ただし `words[]`＝jieba分かち書きの取得は §7 #43.5 の代替が入るまで残る。§3.3） |
| 27 | 速度スライダ | 0.4〜1.5 / step 0.05 / 既定0.9。**localStorage `speechRate` に永続** | **変更**（`profiles.default_rate` へ。§4） |
| 28 | 速度プリセット3種 | ゆっくり0.6 / ふつう0.9 / 速い1.2。**押下で試聴サンプルを再生** | 移植 |
| 29 | 再生/一時停止/再開/もう一度 | ボタン文言が状態で3通りに変化 | 移植 |
| 30 | 最初から | `idx=0` にして再生 | 移植 |
| 31 | **区切りモード選択** | normal/fine/sentence。**localStorage `splitMode` に永続。既定 `fine`** | **変更**（`profiles.default_split_mode` を追加。§4） |
| 32 | 閉じる | 停止＋非表示＋padding解除 | 移植 |
| 32b | 録音・発音評価 | `#btnRec`🎙録音 / `#btnPlayRec`▶自分 / `#btnPlayModel`▶お手本 / `#assessBox`。機能は **§6.5**、APIは **§6「発音評価・記録のAPI」** | 移植 |

---

## 2. 複雑な導線の詳細

### 2.1 再学習（study）の一連の流れ

履歴の🔊をタップしたときの動作。**12の副作用が連鎖する**ので、移植時に落としやすい。

```
study(id)
 1. sentCache[id] から文を取得（無ければ何もしない）
 2. メイン画面へ切替（showView("main")）
 2b. ★ 作成サブタブへ戻す（setSub("compose")）— これが無いと履歴表のまま画面が変わらない
 3. #ja に japanese を復元
 4. current = {japanese, english, marked, keywords:[], pageId:id}
    ★ pageId をセットすることで、以後の保存が「上書き」になる
 4b. ★ resetMainBreak() — 区切り編集モードを解除し explicitBreaks を再判定（§3.1）
     ※ marked に「/」があれば true のまま残る（false にはならない）
 5. 結果カードを表示、#english に marked（区切り「/」込み）を復元
 6. 保存ボタンを disabled にし、「再学習中」メッセージを表示
 7. 画面を smooth scroll で最上部へ
 8. playerLoad(marked) → 分割して自動再生開始
 9. POST /api/practice → 実施を自動記録 → 履歴を再読込
10. POST /api/keywords → キーワードを再抽出して表示
```

### 2.2 ★ 移行時に判断が必要：study のたびにキーワードを再抽出している

現行は **`study()` のたびに `/api/keywords` を無条件で再実行**している。ローカルLLMなので無料だったが、**クラウド化すると再学習1回ごとにLLM課金が発生する**。

| 案 | 内容 | 評価 |
|---|---|---|
| **A（推奨）** | 保存済みの単語（`words` テーブルの `source_id` で紐づくもの）を表示し、**再抽出しない** | 原価ゼロ。既に登録済みの語が出るので学習上も自然 |
| B | 抽出結果を `sentences` にキャッシュし、無ければ抽出 | 初回のみ課金。実装がやや増える |
| C | 現行どおり毎回抽出 | **採用しない**。再学習は最も頻度の高い操作 |

**→ A を採用する。** `usage_logs` の `kind='keywords'` の発生は「新規翻訳時のみ」となる。

---

## 3. フレーズ分割ロジック（移植難度が最も高い）

**この規則が本アプリの中核。1行でも落とすと発音の区切りが変わる。**

### 3.1 手動区切りと `explicitBreaks`

```js
text.split(/[/|｜／]+/)
```

**`explicitBreaks` フラグで挙動が2分岐する。ここを落とすと区切りが変わる。**

| `explicitBreaks` | 挙動 |
|---|---|
| `true` | **手動区切りのみを使う。自動分割を一切足さない** |
| `false` | 手動区切りは自動区切りへの「追加」。各セグメントにさらに自動分割をかける |

`true` になる契機は、① 訳文に `/` を手打ちした（`/[/|｜／]/` を検出）、② **「✂️ 区切り編集」を開いた**。

`false` 側は**再判定型と直接代入型の2種**がある。

| 型 | 呼ばれる場面 | 挙動 |
|---|---|---|
| **再判定** | 訳文の編集 `englishEdited()` / 言語切替 `setLang()` / 新規翻訳 `doTranslate()` / 再学習 `study()`（後3者は `resetMainBreak()` 経由） | **`false` を代入するのではなく `current.marked` に `/` があるかで再判定する**。→ `/` 入りの文を再学習すると **`true` のまま残る**。逆に編集で `/` を全部消すと `false` に戻る |
| **直接代入** | 記事を開く `openArticle()` / 記事の句を再生 `playArtSentence()` | `explicitBreaks = false` |

### 3.2 英語 `autoSplit(text, mode)`

**語数による閾値判定は存在しない。** 接続詞/前置詞を分けたリストも存在せず、`ENG_BREAK` という単一の正規表現で処理する。

| モード | 規則 |
|---|---|
| `sentence` | `/[^.!?]+[.!?]*/g` で文単位に分割 |
| `normal` | `/[^,;:.!?]+[,;:.!?]*/g` の**句読点分割のみ**（接続詞分割はしない） |
| `fine` | 句読点分割の各節に `ENG_BREAK` を**無条件適用** |

```js
const ENG_BREAK = /\s+(?=(?:and|but|or|nor|so|yet|because|although|though|while|when|whenever|whereas|if|unless|until|since|that|which|who|whose|whom|where|after|before|to|in|on|at|with|for|from|of|about|into|onto|over|under|through|during|between|among|against|without|within)\b)/i;
```

**★ 後処理2つ（移植時に落とすと区切りが変わる）**

```js
// ① 1語だけの断片は前のグループに結合（"I / love" のような分断を防ぐ）
if (merged.length && p.split(/\s+/).length <= 1) merged[merged.length - 1] += " " + p;
else merged.push(p);
// ② 先頭が1語だけの孤立なら次に結合
if (merged.length > 1 && merged[0].split(/\s+/).length <= 1)
  merged.splice(0, 2, merged[0] + " " + merged[1]);
```

### 3.3 中国語 `zhSplit(text, mode)`

**モードによって分割の粒度が異なる。`fine` は jieba による単語分割を使う。**

| モード | 規則 |
|---|---|
| `sentence` | `/[^。！？]+[。！？]*/g` |
| `normal` | `/[^，。！？、；：]+[，。！？、；：]*/g`（句読点＝節レベル） |
| `fine` | **jieba の単語分割**（词レベル）。句読点トークンは直前の語に結合する |

`fine` が使う単語列は `/api/pinyin` のレスポンス `words[]`（サーバー側 jieba）を `zhWordsMap`（clean中文 → 単語配列）にキャッシュしたもの。`playerLoad()` と `toggleMainBreakEdit()` が事前に取得する。**未取得のときは `normal` と同じ句読点分割にフォールバックする。**

> **移植上の含意:** クライアント完結にするには pypinyin 相当だけでなく**分かち書きの代替も必要**（§7 #43.5 参照）。

---

## 4. 状態管理・永続化

### 4.1 グローバル変数

| 変数 | 役割 |
|---|---|
| `current` | `{japanese, english, marked, keywords[], pageId}`。`pageId` が保存の新規/上書きを決める |
| `failLabels` | `/api/health` から取得。failボタンの生成に使う |
| `sentCache` | `{id → 文オブジェクト}`。study の復元に必須 |
| `lang` | `'en'` / `'zh'` |
| `player` | `{text, phrases[], idx, playing, gen}` |
| `savedRange` | 区切り挿入用に保持したカーソル位置。読み手の `insertSlash()` が死んでいるため**値は使われない**が、**`selectionchange` リスナーは常時動いて書き込み続けている**（§1.3 #12b・§11.4。落とすときはリスナーごと） |
| `view` | `'main'` / `'articles'` / `'record'` |
| `sub` | `'compose'` / `'history'`（「自分の文」内のサブタブ） |
| `explicitBreaks` | 手動区切りのみを使うか（§3.1）。**移植必須** |
| `zhWordsMap` | clean中文 → jieba単語配列のキャッシュ（§3.3）。**移植必須** |
| `allS`, `allW`, `histTab` | 履歴の全件データとタブ状態 |
| `pinyinTimer` | ピンイン再取得のデバウンス用 |

### 4.2 ★ `player.gen` — 非同期再生のキャンセル機構

**再実装時に確実に落とすロジック。必ず移植すること。**

Web Speech API の `utterance.onend` は非同期に連鎖するため、**停止しても既に予約された onend が発火して次の節を喋り始めてしまう**。これを防ぐために世代カウンタを使っている。

```js
// 再生開始時に世代を進め、そのローカルコピーを保持
const gen = ++player.gen;
const speakNext = () => {
  if (gen !== player.gen || !player.playing) return;  // ★世代が変わったら中断
  ...
  u.onend = () => { if (gen === player.gen && player.playing) { player.idx++; speakNext(); } };
};
```

`player.gen++` を実行する箇所：`playerPlay` / `playerPlayOne` / `playerPause` / `playerStop` / `playerSync`

### 4.3 localStorage の3キー

| キー | 既定値 | 移行後の扱い |
|---|---|---|
| `targetLang` | `'en'` | `profiles.default_lang` を正とし、localStorageはキャッシュとして残す |
| `speechRate` | `0.9` | `profiles.default_rate` を正とする |
| `splitMode` | `'fine'` | **`profiles.default_split_mode` を新設**（現行スキーマに無い） |

**方針：DBを正、localStorageは初回描画を速くするためのキャッシュ。** ログイン直後にDB値でlocalStorageを上書きする。

### 4.4 SPA構造

- URLは常に `/`。ビュー切替は `display` 制御のみ。**History API 未使用**
- 履歴データは**文200件・単語500件を毎回全取得**し、クライアント側で検索・グルーピング

---

## 5. 発音（Web Speech API）

**クライアント完結のため原価ゼロ。ロジックをそのまま移植する。**

| 項目 | 実装 |
|---|---|
| `lang` | en: `en-US` / zh: `zh-CN` |
| `rate` | 速度スライダの値 |
| **voice選択** | `getVoices()` を `lang.startsWith(voicePref)` でフィルタ → 名前が正規表現に一致するものを優先 → 無ければ先頭<br>en: `/Samantha/` ／ zh: `/Ting\|Tingting\|Meijia\|Sinji/` |
| 連続再生 | `onend` チェーン。`gen` 不一致で中断（§4.2） |
| **一時停止** | `speechSynthesis.cancel()` するが `idx` は保持 → **節の先頭から再開**（途中再開ではない） |
| 単発再生 | 次へ進まない。以後「▶再開」でその節から通し再生 |
| `speak()` | 単語・試聴サンプル用。プレイヤーを止めてから発話 |

**確認事項**：家族の実機（iPhone/iPad）に上記のvoiceが存在するか。無い場合は先頭のvoiceにフォールバックする。

---

## 6. 現行API仕様

共通エンベロープ： `{ok: true, data: {...}}` / `{ok: false, error: "..."}`

| メソッド / パス | 入力 | 出力 | 移行後 |
|---|---|---|---|
| `GET /api/health` | — | version, ollama_ok, ollama_error, models[], default_model, storage_*, drive_ready/error, notion_ready, azure_ready, **fail_labels[]**, **article_fail_labels[]**<br>※副作用: config再読込・warm_up | **廃止** |
| `GET /api/sentences?lang=` | lang | 直近200件（新しい順）<br>id/english/japanese/marked/pinyin/created(日付10桁)/fail_count/practice_count/last_practiced | Supabase SDK |
| `GET /api/words?lang=` | lang | 直近500件<br>id/word/meaning/example(空なら出典文)/pinyin/created | Supabase SDK |
| `POST /api/translate` | japanese, model?, lang | `{english, pinyin?}` | **Edge Function** |
| `POST /api/keywords` | english, japanese, model?, lang | `{keywords: [{word, meaning, pinyin?}]}` 最大3件 | **Edge Function** |
| `POST /api/pinyin` | texts[] | `{pinyins[], pairs[], words[]}`<br>`pairs`=[文字,拼音]の列 / **`words`=jieba分かち書き**（§3.3が依存） | **変更**（クライアント処理にするなら分かち書きの代替が要る） |
| `POST /api/sentences` | japanese, english, marked, memo?, lang, **id?** | `{id}` / `{id, updated:true}` | Supabase SDK |
| `POST /api/words` | word, meaning, example, source_id, lang | `{id}` | Supabase SDK |
| `POST /api/words/delete` | id | `{deleted: 削除したid}`（真偽値ではない） | Supabase SDK |
| `POST /api/fail` | id, label | `{fail_count}` | Supabase SDK |
| `POST /api/practice` | id | `{practice_count, last_practiced}` | Supabase SDK |
| `POST /api/delete` | id | `{deleted: 削除したid}`（真偽値ではない） | Supabase SDK |

### 発音評価・記録のAPI（機能一覧は §6.5）

| メソッド / パス | 入力 | 出力 | 移行後 |
|---|---|---|---|
| `POST /api/assess` | **生の音声バイトをbody**、`lang`/`text`/`source` はクエリ文字列、形式は `X-Audio-Type` ヘッダ<br>※他のAPIと異なり JSON body ではない。`source` はクライアント未送信 | `{ok, recognized, scores, words[], heard_text}`<br>※`heard_text` は**zhのみ**（参照なし認識の結果）。`recognized` は参照あり認識のDisplay文字列で**クライアント未使用**。2つは別物なので取り違えないこと | **Edge Function**（Azureプロキシ） |
| `GET /api/assessments` | `lang`, `mode=weak\|history` | 苦手語集計（直近30日）／評価履歴 | Supabase SDK |
| `POST /api/assessments/clear` | lang | `{deleted}` | Supabase SDK |

### 記事モードのAPI（第II部）

> **POSTの記事IDのキーは `id` ではなく `article_id`。** クエリで受ける `GET /api/article?id=` だけが `id`。

| メソッド / パス | 入力 | 出力 | 移行後 |
|---|---|---|---|
| `GET /api/articles` | — | 記事一覧（最終学習日・学習回数・Nomiss率・未反映Fail数） | **対象外** |
| `GET /api/article` | `id`（クエリ） | 記事1件（sentences/vocab/fails/sessions） | **対象外** |
| `POST /api/articles/refresh` | limit（**サーバー既定4**／クライアントは3を送る） | 未取り込みのNotion記事を取り込む | **対象外** |
| `POST /api/articles/fail` / `/unfail` | article_id, idx, ci, **char, syllable**, label | Fail の付与・解除 | **対象外** |
| `POST /api/articles/breaks` | article_id, idx, breaks[] | 節区切りの永続化 | **対象外** |
| `POST /api/articles/session` | article_id | 勉強完了。`{date, misses, total, nomiss}` | **対象外** |
| `POST /api/articles/push` | article_id | 失敗履歴テーブルをNotionへ書き戻し | **対象外** |

### `fail_labels` の移行先

現行は `config.json` の `fail_labels: ["Fail"]` をサーバーが配信し、UIがボタンを動的生成している。

**移行後：クライアント側の定数にする**（現在1種類しかなく、増やす予定も未定のため）。将来増やすときに `profiles` か専用テーブルへ移す。

---

## 6.5 発音評価・記録（★2026-07-26 追記。当初の棚卸しから漏れていた）

> **項番は §7 の続き #45〜53。** 追記のため、節の位置（§6 と §7 の間）と項番の順序が前後している。

本棚卸しは発音評価機能（v1.27〜v1.37）の実装前に作成されたため、以下が欠落していた。
**いずれも本アプリの中核機能であり、家族版に含める。**

| # | 機能 | 内容 | 判定 |
|---|---|---|---|
| 45 | 録音ボタン | MediaRecorderで録音。55秒で自動停止、経過秒を表示 | 移植 |
| 46 | **WAV変換** | webm/opus → 16kHz mono WAV。**必須**（webmだとAzureの時間軸が壊れる） | **移植（重要）** |
| 47 | 音量正規化 | ピーク -3dBFS に揃える（最大8倍） | 移植 |
| 48 | マイク設定 | ノイズ抑制・エコーキャンセル・AGCを**すべてOFF**（子音が削られるため） | 移植 |
| 49 | 発音評価API | Azure Speech（Granularity=Phoneme、Prosody有効） | **変更**（Mac常駐→Edge Function） |
| 50 | ミス種類の分類 | 正解の拼音と「実際に聞こえた文」を突き合わせ **R/V/T/N/F** を判定 | **変更**（Python→クライアントJS） |
| 51 | 結果表示 | 単語ごとの色分け（緑/黄/赤/グレー）＋長押しで詳細 | 移植 |
| 52 | 録音の再生 | 「▶自分」「▶お手本」で聴き比べ | 移植 |
| 53 | 記録タブ（📊） | 苦手一覧（**直近30日**のミス率・種類・拼音ルビ）／履歴／言語別削除 | 移植 |

> **注意**：Azureは音節スコアに声調と母音を統合して返すため、スコアだけでは声調誤りを切り分けられない。
> R/V/T/N の判定は「参照なし認識」の結果との比較で行う（中国語のみ）。
> 音声認識が文脈で自動補正する場合は検出できず、種類は空になる（点数は正しく低く出る）。

---

## 7. サーバー内部ロジック

| # | 機能 | 内容 | 判定 |
|---|---|---|---|
| 33 | 言語別ファイル分割 | `sentences.json` / `sentences_zh.json` / `words.json` / `words_zh.json` | **廃止**（`lang` 列に統合） |
| 34 | **Markdown自動生成** | 書き込みのたびに4本の `.md` を再生成（実施日一覧・fail一覧・メモを含む） | **変更**（オンデマンドのエクスポート機能へ） |
| 35 | Drive push/pull | push=**10ファイル**を非同期アップロード（直列化）。起動時のpullは**5ファイル**（`sentences*.json`/`words*.json`/`articles_zh.json`）で、**`assessments.json` はpull対象外**（§11.3） | **廃止** |
| 36 | `migrate_ids()` | 起動時にID欠落レコードへUUID付与 | **廃止**（移行スクリプトで吸収） |
| 37 | `warm_up()` | 起動時・health時にOllamaへダミー投げ | **廃止** |
| 38 | 排他制御 | グローバル`LOCK` ＋ `.tmp`→`os.replace` の原子的書き込み | **廃止**（Postgresが担う） |
| 39 | `_clean()` | `<think>` ブロックと前後の引用符を除去 | **変更**（クラウドLLMでは不要だが、引用符除去は残す） |
| 40 | **翻訳の3段リトライ** | `num_predict=512` → `think=false` → 無指定 | **廃止**（Ollama固有。クラウドAPIでは単純リトライに） |
| 41 | キーワードのJSON修復 | `json_mode` 失敗時に `/\{.*\}/s` で抽出 | 移植（構造化出力を使っても保険として） |
| 42 | **word/meaning 入替補正** | §7.1 参照 | **移植（重要）** |
| 43 | ピンイン | `pypinyin.lazy_pinyin(style=TONE)`。未導入なら自動 pip install | **変更**（JSライブラリへ） |
| 43.5 | **jieba 分かち書き** | `segment_zh()`。未導入なら自動 pip install。`/api/pinyin` の `words[]` として返し、**中国語の `fine` 分割が依存**（§3.3） | **変更**（クライアント側に代替が必要。落とすと `fine` が句読点分割に退化する） |
| 44 | Ollama設定 | temperature 0.3 / stream false / keep_alive 24h | **変更**（temperature 0.3 は維持） |

### 7.1 word/meaning 入替補正（移植必須）

LLMが `word` と `meaning` を取り違えることがあるため、日本語判定で検出して入れ替える。

```python
bad = _has_kana if lang == "zh" else _has_japanese
#   en: word に日本語（ひらがな・カタカナ・漢字）が入っていたら誤り
#   zh: word に「かな」が入っていたら誤り（★漢字は正常なので除外）
if bad(w) and not bad(m): w, m = m, w   # 逆なら入れ替え
if bad(w) or not w: continue            # それでも不正なら除外
```

正規表現：
- `_has_japanese`: `[぀-ヿ㐀-鿿]`（かな＋漢字）
- `_has_kana`: `[぀-ゟ゠-ヿ]`（かなのみ）

---

## 8. プロンプト全文（移植対象）

### 8.1 翻訳

**en**
```
Translate the Japanese text into natural, conversational English.
The learner is an elementary-school child, so use simple, friendly words
that a kid would actually say. Keep it short and natural.
Output ONLY the English translation. No explanations, no quotes.

Japanese text:
```

**zh**
```
Translate the Japanese text into natural, conversational Chinese
(Simplified characters). The learner is an elementary-school child, so use
simple, friendly words that a kid would actually say. Keep it short and natural.
Output ONLY the Chinese translation. No explanations, no quotes, no pinyin.

Japanese text:
```

### 8.2 キーワード抽出

**en**（zhは "English"→"Chinese" に置換したもの）
```
From the English sentence below, pick up to 3 keywords/phrases
worth memorizing for a Japanese learner.
Rules:
- "word" MUST be English, copied exactly from the English sentence.
- "meaning" MUST be Japanese, copied from the original Japanese text below
  (the expression that corresponds to the word). Do NOT invent a new translation.
Respond ONLY with JSON: {"keywords": [{"word": "...", "meaning": "..."}]}
```

呼び出し時に以下を付加（**プロンプト本文の直後に空行が1行入る**。本文が `\n` で終わり、さらに `\n{label} sentence:` を連結するため）：
```

{English|Chinese} sentence:
{english}

Original Japanese text:
{japanese}
```

> **「小学生の子どもが実際に言う簡単な言葉で」というペルソナ指定が本アプリの性格を決めている。** クラウドLLMへ移す際も必ず維持すること。

---

## 9. UIラベル定義（LABELS）

言語追加は `LABELS` に1ブロック足すだけの設計。**この構造を維持する。**

| キー | en | zh |
|---|---|---|
| `name` | 英語 | 中国語 |
| `toBtn` | 英語にする | 中国語にする |
| `transHead` | 英訳 ✏️ | 中国語訳 ✏️ |
| `sentTab` | 英文のみ | 中国語のみ |
| `sentCol` | 英文 / 日本語 | 中国語 / 日本語 |
| `unit` | 英文 | 文 |
| `delConfirm` | この英文を削除しますか？ | この文を削除しますか？ |
| `restudy` | 保存済みの英文を再学習中（…上書きされます） | 保存済みの文を再学習中（…） |
| ~~`slashHint`~~ | ~~区切りたい位置を英文内でタップしてから押してください~~ | ~~区切りたい位置を文中で…~~<br>**死にコード。§11.4 — 移植しない** |
| `sample` | This is the speaking speed. | 这是朗读的速度。 |
| `ttsLang` | en-US | zh-CN |
| `voicePref` | en | zh |
| `voiceRe` | `/Samantha/` | `/Ting\|Tingting\|Meijia\|Sinji/` |

---

## 10. データモデル（現行JSON）

**sentence**
```
id       : hex文字列（uuid4().hex、ハイフンなし32桁）
japanese : string
english  : string          → 移行後は target に改名
marked   : string          → 区切り「/」込みの原文
memo     : string
created  : "%Y-%m-%d %H:%M:%S"（★ナイーブなローカル時刻。タイムゾーン情報なし）
fails    : [{label, time}]
practices: [時刻文字列]
pinyin   : string（zhのみ）
```

**word**
```
id        : hex文字列
word      : string
meaning   : string
example   : string
source_id : sentenceのid
created   : 同上
pinyin    : string（zhのみ）
```

---

## 11. ★ 既知の不具合（移行前に認識が必要）

### 11.1 `record_fail()` が中国語文に対応していない

```python
def record_fail(sentence_id, label="Fail"):
    items = _load("sentences.json")   # ★ SENT_FILES を使っていない
```

他の関数は `SENT_FILES`（en+zh両方）をループしているが、`record_fail` だけ英語ファイル固定。
**中国語文へのfail記録は必ず `sentence not found` になっていた。**

移行後のスキーマは `lang` 非依存なので自然に直るが、**既存データのzh側 `fails` は空である**ことを移行検証の期待値とすること。

### 11.2 study のたびにキーワード再抽出（§2.2 で対処済み）

### 11.3 `assessments.json` が Drive から復元されない

`assessments.json` は push 対象（10ファイル）に入っているが、起動時の pull 対象（5ファイル）に入っていない。
**ローカルの `data/` を失うと、発音評価の履歴と苦手語の集計だけ復元されない。**

移行後はPostgresが単一の保管場所になるため自然に解消する。**移行前にローカル `data/` を消さないこと。**

### 11.4 死にコード：`insertSlash()` / `savedRange` / `LABELS.slashHint`

「／区切り挿入」ボタンは「✂️ 区切り編集」に置き換えられたが、**関数・状態・UIラベルが残っている**（`insertSlash()` に呼び出し元なし）。移植しない。

ただし `savedRange` に書き込む **`selectionchange` リスナーは常時動いている**（読み手が居ないだけ）。削除するときはリスナーも一緒に落とすこと。

---

## 12. 廃止・対象外とするもの一覧

| 対象 | 理由 |
|---|---|
| Ollama 連携全般 | クラウドLLMへ移行 |
| Google Drive / GAS 連携（`google_drive.py`, `drive_auth.py`, `gas/Code.gs`） | Postgresへ移行 |
| Tailscale 前提の運用 | 公開HTTPSへ |
| `config.json` / `config.example.json` | 環境変数へ |
| **記事モード一式**（`notion_client.py`, `tools_import_fails.py`, `/api/articles/*`, 記事UI） | **家族版では対象外**（第II部）。現行アプリでのみ使い続ける |
| `setup.sh`（launchd登録） | 不要 |
| `enable_https.sh` / 自己署名証明書 | ホスティング側のHTTPSに置換 |
| `/api/health`, `warm_up()`, `migrate_ids()`, `list_models()` | 不要 |
| ローカル `data/` ディレクトリと排他制御 | Postgresが担う |

> **ただし `server.py` 系のファイルは削除しないこと。** `../00-business/exit-plan.md` §4.2（ローカル構成への回帰）の保険として、動く状態のブランチを1本残す。

---

### 関連ドキュメント

- `family-edition-spec.md` — 家族版の仕様書（本書の移植先）
- `../20-plans/status-summary.md` — 検討の現況整理
- `../30-research/saas-migration-study.md` — 事業版の設計書
