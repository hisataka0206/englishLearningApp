# English / Chinese Learning App

小学生の子ども向けの語学学習アプリ。**日本語で言いたいことを入力すると外国語になり、節ごとに発音を練習でき、発音の良し悪しを採点してくれる。**

---

## このリポジトリの構成

```
.
├── apps/
│   ├── local/     現行アプリ（Mac常駐サーバー・稼働中）
│   └── family/    家族版（Supabase + PWA・実装済み／環境構築が未了）
└── docs/          事業・仕様・計画・調査（→ docs/README.md が地図）
```

| 見たいもの | 行き先 |
|---|---|
| **今どう動いているか / 使い方** | `apps/local/README.md` |
| **これから何を作るのか** | `docs/10-specs/family-edition-spec.md` |
| **どの順で進めるか・現在地** | `docs/20-plans/execution-plan.md` |
| **事業としての全体像** | `docs/00-business/business-plan.md` |
| ドキュメント全体の地図 | `docs/README.md` |

---

## 2つのアプリの関係

| | `apps/local`（現行） | `apps/family`（家族版） |
|---|---|---|
| 状態 | **稼働中** | 実装済み・**未デプロイ** |
| 実行場所 | Macに常駐（launchd） | Supabase + Vercel |
| 翻訳 | ローカルLLM（Ollama） | Gemini（Edge Function） |
| 保存 | ローカルJSON + Google Drive | Postgres（RLSで個人別） |
| 利用者 | 本人のみ | 家族3人（ログインあり） |
| Macの起動 | **必須** | 不要 |
| 記事モード（Notion同期） | あり | なし（現行のみ） |
| 発音評価（Azure） | あり | あり |

家族版が動き出すまで、現行アプリはそのまま使い続ける。**記事モードは現行にしかない。**

---

## 稼働中のアプリを触るとき（注意）

現行アプリは launchd で常駐している。**ファイルを移動したら再設定が必要。**

```bash
cd apps/local
bash setup.sh          # launchdの登録をやり直す（パスが変わったとき）
launchctl kickstart -k gui/$(id -u)/com.englishlearningapp.server   # 再起動
```

設定・データ・証明書はすべて `apps/local/` の中にある（`config.json` `data/` `cert.pem` などは git 管理外）。
