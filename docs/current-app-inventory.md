# 現行アプリ機能棚卸し — [[移植チェックリスト]]

作成日: 2026-07-26 / 対象: `index.html`（v1.16.0相当）, `server.py`
用途: **クラウド版への移植漏れを防ぐための唯一のチェックリスト**

## 使い方

各項目の「判定」列を **移植 / 廃止 / 変更** のいずれかで埋める。
**すべての行が埋まるまで実装完了とみなさない。** 家族版の受け入れ基準はこの表である。

---

## 1. 画面・UI要素

### 1.1 ヘッダ

| # | 機能 | 実装詳細 | 判定 |
|---|---|---|---|
| 1 | バージョン表示 | `/api/health` の `version` を `#ver` に表示 | **廃止** |
| 2 | ステータス表示 | Ollama ✅/❌ ＋ 保存先（Drive/ローカル）を2行 | **廃止**（クラウド化で意味を失う。代わりにログイン中ユーザー名を表示） |
| 3 | 履歴/戻るトグル | `toggleView()`。URLは変化しない | 移植 |
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
| 12 | **「／区切り挿入」ボタン** | `selectionchange` で保持した `savedRange` の位置に ` / ` を挿入 | 移植 |
| 13 | 保存ボタン | 新規保存 / `current.pageId` があれば上書き | 移植 |
| 14 | キーワード一覧 | チェックボックス＋語/ピンイン/意味＋個別🔊 | 移植 |
| 15 | 単語一括登録 | チェック済みを順次POST。**未保存なら先に文を保存** | 移植 |

### 1.4 履歴画面

| # | 機能 | 実装詳細 | 判定 |
|---|---|---|---|
| 16 | タブ3種 | 日付別 / 英文のみ / 単語のみ | 移植 |
| 17 | **検索フィルタ** | クライアント側substring（文=英文+日本語 / 単語=語+意味+例文） | 移植 |
| 18 | 文テーブル | 日付・訳文(+ピンイン)+日本語・実施(回数/最終日)・fail(件数バッジ+ラベル別ボタン)・操作 | 移植 |
| 19 | 単語テーブル | 日付・語(+ピンイン)+例文・意味・操作(🔊/🗑) | 移植 |
| 20 | 日付別グルーピング | `created` の日付でdesc、「文N件」「単語N語」の小見出し | 移植 |
| 21 | **fail記録ボタン** | `config.json` の `fail_labels[]` から動的生成 | **変更**（設定の置き場をDBかクライアント定数へ。§6参照） |
| 22 | 削除（文・単語） | confirm → API → 再読込 | 移植 |
| 23 | **再学習（🔊 study）** | 下記 §2 に詳述。**最も複雑な導線** | **変更**（キーワード再抽出の扱い。§2.2） |

### 1.5 発音プレイヤー（画面下部固定）

| # | 機能 | 実装詳細 | 判定 |
|---|---|---|---|
| 24 | 固定下部バー | 初期 `display:none`。表示時に body の `paddingBottom` を自動調整 | 移植 |
| 25 | 節チップ | クリックで単発再生。`active`/`done`/通常 の3状態。`scrollIntoView({block:"nearest"})` で追従 | 移植 |
| 26 | zhチップ下のピンイン | `/api/pinyin` にバッチ送信して差し込み | **変更**（クライアント側で計算） |
| 27 | 速度スライダ | 0.4〜1.5 / step 0.05 / 既定0.9。**localStorage `speechRate` に永続** | **変更**（`profiles.default_rate` へ。§4） |
| 28 | 速度プリセット3種 | ゆっくり0.6 / ふつう0.9 / 速い1.2。**押下で試聴サンプルを再生** | 移植 |
| 29 | 再生/一時停止/再開/もう一度 | ボタン文言が状態で3通りに変化 | 移植 |
| 30 | 最初から | `idx=0` にして再生 | 移植 |
| 31 | **区切りモード選択** | normal/fine/sentence。**localStorage `splitMode` に永続。既定 `fine`** | **変更**（`profiles.default_split_mode` を追加。§4） |
| 32 | 閉じる | 停止＋非表示＋padding解除 | 移植 |

---

## 2. 複雑な導線の詳細

### 2.1 再学習（study）の一連の流れ

履歴の🔊をタップしたときの動作。**7つの副作用が連鎖する**ので、移植時に落としやすい。

```
study(id)
 1. sentCache[id] から文を取得（無ければ何もしない）
 2. メイン画面へ切替（showView("main")）
 3. #ja に japanese を復元
 4. current = {japanese, english, marked, keywords:[], pageId:id}
    ★ pageId をセットすることで、以後の保存が「上書き」になる
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

### 3.1 手動区切り（最優先）

```js
text.split(/[/|｜／]+/)
```

**自動分割の「置き換え」ではなく「追加」。** 手動で区切った各セグメントに対し、さらに自動分割をかける。

### 3.2 英語 `autoSplit(text, mode)`

| モード | 語数上限 | 規則 |
|---|---|---|
| `sentence` | — | `/[^.!?]+[.!?]*/g` で文単位に分割 |
| `normal` | **8** | ① `/[^,;:.!?]+[,;:.!?]*/g` で分割 → ② 語数が8超なら**接続詞の前**で分割 |
| `fine` | **4** | ①② に加え → ③ なお4語超なら**前置詞の前**でも分割 |

**接続詞リスト（CONJ）** — 正規表現は `\s+(?=(?:…)\b)` の先読み、`i` フラグ付き

```
and, but, or, so, because, when, while, that, which, who, whose,
where, after, before, if, although, though, until, unless, since, as
```

**前置詞リスト（PREP）** — fine モードのみ使用

```
to, in, on, at, with, for, from, about, into, over, under,
around, through, during, near, behind, between
```

### 3.3 中国語 `zhSplit(text, mode)`

| モード | 区切り文字 |
|---|---|
| `sentence` | `。！？` |
| `normal` / `fine` | `，。！？、；：` （**モード差なし**） |

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
| `savedRange` | 区切り挿入用に保持したカーソル位置 |
| `view` | `'main'` / `'history'` |
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
| `GET /api/health` | — | version, ollama_ok, models[], storage_*, **fail_labels[]**<br>※副作用: config再読込・warm_up | **廃止** |
| `GET /api/sentences?lang=` | lang | 直近200件（新しい順）<br>id/english/japanese/marked/pinyin/created(日付10桁)/fail_count/practice_count/last_practiced | Supabase SDK |
| `GET /api/words?lang=` | lang | 直近500件<br>id/word/meaning/example(空なら出典文)/pinyin/created | Supabase SDK |
| `POST /api/translate` | japanese, model?, lang | `{english, pinyin?}` | **Edge Function** |
| `POST /api/keywords` | english, japanese, model?, lang | `{keywords: [{word, meaning, pinyin?}]}` 最大3件 | **Edge Function** |
| `POST /api/pinyin` | texts[] | `{pinyins[]}` | **廃止**（クライアント処理） |
| `POST /api/sentences` | japanese, english, marked, memo?, lang, **id?** | `{id}` / `{id, updated:true}` | Supabase SDK |
| `POST /api/words` | word, meaning, example, source_id, lang | `{id}` | Supabase SDK |
| `POST /api/words/delete` | id | `{deleted}` | Supabase SDK |
| `POST /api/fail` | id, label | `{fail_count}` | Supabase SDK |
| `POST /api/practice` | id | `{practice_count, last_practiced}` | Supabase SDK |
| `POST /api/delete` | id | `{deleted}` | Supabase SDK |

### `fail_labels` の移行先

現行は `config.json` の `fail_labels: ["Fail"]` をサーバーが配信し、UIがボタンを動的生成している。

**移行後：クライアント側の定数にする**（現在1種類しかなく、増やす予定も未定のため）。将来増やすときに `profiles` か専用テーブルへ移す。

---

## 7. サーバー内部ロジック

| # | 機能 | 内容 | 判定 |
|---|---|---|---|
| 33 | 言語別ファイル分割 | `sentences.json` / `sentences_zh.json` / `words.json` / `words_zh.json` | **廃止**（`lang` 列に統合） |
| 34 | **Markdown自動生成** | 書き込みのたびに4本の `.md` を再生成（実施日一覧・fail一覧・メモを含む） | **変更**（オンデマンドのエクスポート機能へ） |
| 35 | Drive push/pull | 8ファイルを非同期アップロード（直列化）、起動時にpull | **廃止** |
| 36 | `migrate_ids()` | 起動時にID欠落レコードへUUID付与 | **廃止**（移行スクリプトで吸収） |
| 37 | `warm_up()` | 起動時・health時にOllamaへダミー投げ | **廃止** |
| 38 | 排他制御 | グローバル`LOCK` ＋ `.tmp`→`os.replace` の原子的書き込み | **廃止**（Postgresが担う） |
| 39 | `_clean()` | `<think>` ブロックと前後の引用符を除去 | **変更**（クラウドLLMでは不要だが、引用符除去は残す） |
| 40 | **翻訳の3段リトライ** | `num_predict=512` → `think=false` → 無指定 | **廃止**（Ollama固有。クラウドAPIでは単純リトライに） |
| 41 | キーワードのJSON修復 | `json_mode` 失敗時に `/\{.*\}/s` で抽出 | 移植（構造化出力を使っても保険として） |
| 42 | **word/meaning 入替補正** | §7.1 参照 | **移植（重要）** |
| 43 | ピンイン | `pypinyin.lazy_pinyin(style=TONE)`。未導入なら自動 pip install | **変更**（JSライブラリへ） |
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

呼び出し時に以下を付加：
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
| `transHead` | 英訳（タップで編集可…） | 中国語訳（タップで編集可…） |
| `sentTab` | 英文のみ | 中国語のみ |
| `sentCol` | 英文 / 日本語 | 中国語 / 日本語 |
| `unit` | 英文 | 文 |
| `delConfirm` | この英文を削除しますか？ | この文を削除しますか？ |
| `restudy` | 保存済みの英文を再学習中（…上書きされます） | 保存済みの文を再学習中（…） |
| `slashHint` | 区切りたい位置を英文内でタップしてから押してください | 区切りたい位置を文中で… |
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

---

## 12. 廃止するもの一覧

| 対象 | 理由 |
|---|---|
| Ollama 連携全般 | クラウドLLMへ移行 |
| Google Drive / GAS 連携（`google_drive.py`, `drive_auth.py`, `gas/Code.gs`） | Postgresへ移行 |
| Tailscale 前提の運用 | 公開HTTPSへ |
| `config.json` / `config.example.json` | 環境変数へ |
| `setup.sh`（launchd登録） | 不要 |
| `/api/health`, `warm_up()`, `migrate_ids()`, `list_models()` | 不要 |
| ローカル `data/` ディレクトリと排他制御 | Postgresが担う |

> **ただし `server.py` 系のファイルは削除しないこと。** `exit-plan.md` §4.2（ローカル構成への回帰）の保険として、動く状態のブランチを1本残す。

---

### 関連ドキュメント

- `docs/family-edition-spec.md` — 家族版の仕様書（本書の移植先）
- `docs/status-summary.md` — 検討の現況整理
- `docs/saas-migration-plan.md` — 事業版の設計書
