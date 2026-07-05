# English Learning App

[[英語学習]]用のスマホ対応ブラウザアプリ。日本語を入力すると[[ローカルLLM]]（[[Ollama]]）が英訳し、ブラウザ内蔵の音声合成で[[発音]]します。英文と[[重要キーワード]]は[[Google Drive]]に自動保存され、[[失敗履歴]]（ラベル＋日時）も英文ごとに記録できます。

## 構成

- `server.py` — Mac上で常駐するミニサーバー（Python標準ライブラリのみ）。UI配信・Ollama翻訳・Drive保存。
- `index.html` — スマホ対応UI（発音は Web Speech API）。
- `config.json` — [[外部設定ファイル]]。保存先・Ollamaモデル・失敗ラベル等はここで変更。
- `setup.sh` — 常時起動セットアップ（launchdのLaunchAgent登録）。

## データ保存（Google Drive）

Mac版[[Google Drive]]アプリの同期フォルダを自動検出し、`My Drive/EnglishLearningApp/` に保存します（API・認証は不要）。Driveアプリ未検出時はアプリ内 `data/` に保存されます。保存先を固定したい場合は `config.json` の `storage.data_dir` にパスを指定してください。

- `sentences.json` — 英文データ本体（日本語・英文・メモ・失敗履歴）
- `words.json` — 単語帳（出典英文のidと紐付け）
- `sentences.md` / `words.md` — スマホのDriveアプリでも読みやすい自動生成ビュー

失敗履歴は英文ごとに「ラベル（Fail / F / T / R / V。`config.json` の `fail_labels` で変更可）＋日時」で蓄積され、`sentences.md` にも一覧表示されます。

## 初回セットアップ（1回だけ。以後ユーザーは何も意識しない運用）

### Mac側

1. [[Ollama]] 起動確認とモデル設定（`config.json` の `ollama.model`。UIでも切替可）。
2. サーバー常時起動: `bash setup.sh`（ログイン時自動起動＋異常終了時の自動再起動）。
3. [[Tailscale]] をインストールしてログインし、メニューバー設定で「Start on login」をON。
4. スリープ防止: システム設定 → ディスプレイ →「ディスプレイがオフのときに自動でスリープさせない」をON（または `sudo pmset -a sleep 0`）。

### iPhone側

1. Tailscaleアプリを入れて同じアカウントでログイン。
2. アプリの設定で「[[VPN On Demand]]」をON → 以後は自動接続され、開閉操作は不要。
3. Safariで `http://<Macのマシン名>:8765` を開き、共有メニューから「ホーム画面に追加」。

以後は**ホーム画面のアイコンをタップするだけ**。Tailscaleの存在を意識する必要はありません。自宅Wi-Fi内なら `http://<MacのIP>:8765` でも接続できます。

## 翻訳スピードについて

- [[keep_alive]] でモデルをメモリに常駐（24h）させ、毎回のロード時間をゼロにしています。サーバー起動時・画面表示時に自動ウォームアップ。
- 翻訳（英文のみ即返却）と[[キーワード抽出]]（裏で後追い）を分離し、体感待ち時間を大幅短縮。英文が出た瞬間に発音が始まります。
- モデルはUIのプルダウンで切替可能。速度優先なら `qwen2.5:1.5b` / `llama3.2:3b`、品質優先なら `qwen2.5:7b`。導入は `ollama pull qwen2.5:1.5b`。既定は `config.json` の `ollama.model`。

## 制約

- ローカルLLMは自宅Macで動くため、**Macが起動していないと翻訳できません**（GitHub ActionsなどからローカルPCへの直接アクセスは不可）。
- 保存データはMac側で書き込み、Driveアプリが自動でクラウド同期します。

## APIエンドポイント

- `GET /api/health` — Ollama状態・モデル一覧・保存先
- `POST /api/translate` — `{japanese, model?}` → `{english, keywords[]}`
- `GET/POST /api/sentences` — 英文の一覧取得 / 保存
- `POST /api/words` — 単語登録（`source_id` で英文と紐付け）
- `POST /api/fail` — `{id, label}` 失敗履歴を追記
