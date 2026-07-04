# English Learning App

[[英語学習]]用のスマホ対応ブラウザアプリ。日本語を入力すると[[ローカルLLM]]（[[Ollama]]）が英訳し、ブラウザ内蔵の音声合成で[[発音]]します。英文と[[重要キーワード]]は[[Notion]]に保存でき、[[中国語学習記事]]と同じ方式で[[失敗履歴]]（ページへのコメント）を残せます。

## 構成

- `server.py` — Mac上で動くミニサーバー（Python標準ライブラリのみ）。UI配信・Ollama翻訳・Notion API中継。
- `index.html` — スマホ対応UI（発音は Web Speech API）。
- `config.json` — [[外部設定ファイル]]。NotionのID・トークン、Ollamaのモデル等はここで変更。

## Notion保存先（作成済み）

- 親ページ: 英語学習用 `393cd557226180d592cef58441a21af6`
- English Sentences DB: `4209bc8eb6cd491c873c309b85edefda`（English / Japanese / Memo / FailCount）
- English Words DB: `e42c489747ad48b69541ed8e6185d479`（Word / Meaning / Example / Source→Sentencesへのリレーション）

失敗履歴は[[運用ルール]]に倣い、英文ページへのコメント（Fail / F / T / R / V。`config.json` の `fail_labels` で変更可）で記録し、FailCountも自動加算します。

## セットアップ

1. Notionの [My integrations](https://www.notion.so/my-integrations) で[[インテグレーション]]を作成し、トークンを `config.json` の `notion.token` に設定。
2. Notionの「英語学習用」ページの「…」→ 接続先 から、作成したインテグレーションを追加（配下のDBにも権限が及びます）。
3. Ollamaが起動していることを確認し（`ollama serve`）、使うモデルを `config.json` の `ollama.model` に設定（UIのプルダウンでも切替可）。
4. サーバー起動: `python3 server.py`
5. Macでは `http://localhost:8765`、スマホ（同一Wi-Fi）では `http://<MacのIPアドレス>:8765` を開く。MacのIPは `ipconfig getifaddr en0` で確認。

## 外出先から使う場合

[[Tailscale]] をMacとスマホに導入すると、同一Wi-Fi外からも `http://<Macのマシン名>:8765` でアクセスできます（GitHub Actions/Pagesから自宅PCへの直接アクセスは不可のため、トンネルが必要）。

## APIエンドポイント

- `GET /api/health` — Ollama/Notion設定の状態、モデル一覧
- `POST /api/translate` — `{japanese, model?}` → `{english, keywords[]}`
- `GET/POST /api/sentences` — 英文の一覧取得 / 保存
- `POST /api/words` — 単語登録（`source_page_id` で英文と紐付け）
- `POST /api/fail` — `{page_id, label}` 失敗コメント追加＋FailCount加算
