# [[情報源]]の評価と選定方針

作成日: 2026-07-25 / 対象: 有料の語学学習サービスにおける記事教材の元ネタ

---

## 0. 結論

**Wikipedia は補助的な用途には最適だが、主たる情報源には向かない。**
理由は2つ ——「[[ShareAlike]] が有料配信と衝突する」「ニュース性がない」。

主軸として推奨するのは以下の3つ。

| 優先 | 情報源 | ライセンス | ShareAlike | 適性 |
|---|---|---|---|---|
| ★1 | **[[Global Voices]]** | CC BY 3.0 | **なし** | **中・英・日の対訳が既に存在する。語学教材として最適** |
| ★2 | **[[arXiv]] アブストラクト** | **CC0** | なし | ヒューマノイド／ロボティクス領域と相性が抜群 |
| ★3 | **政府系プレスリリース** | CC BY 4.0 / OGL3 / PDL1.0 / PD | なし | EU は多言語で同一内容が出る。対訳教材化しやすい |
| 補助 | Wikipedia | CC BY-SA 4.0 | **あり** | 語彙・固有名詞の背景説明に限定して使う |

---

## 1. Wikipedia の評価

### 1.1 結論：主軸には使わない。補助に留める

「無料で自由に使える」というイメージがあるが、**有料サービスの元ネタとしては最も注意が必要なライセンス**。

### 1.2 問題① ShareAlike が有料配信と衝突する

Wikipedia のテキストは **CC BY-SA 4.0**（GFDLとのデュアルだが、外部インポート分はCC BY-SAのみのため実務上はCC BY-SA前提で設計すべき）。

CC BY-SA 4.0 Section 3(b) の要求：

> if You Share **Adapted Material** You produce, ... The Adapter's License You apply must be a Creative Commons license with the same License Elements ... **You may not offer or impose any additional or different terms or conditions on** ... Adapted Material that restrict exercise of the rights granted

**何が起きるか**

| 論点 | 可否 |
|---|---|
| 課金壁・ログイン壁の内側に置くこと | **○ 問題ない** |
| 教材を CC BY-SA 4.0 で提供する義務 | **発生する** |
| 利用規約に「無断転載・再配布を禁止」と書くこと | **✗ 書けない**（CC BY-SA由来部分について） |
| DRM等の技術的保護手段をかけること | **✗ 不可** |

Creative Commons 公式FAQ が明示的に答えている：

> you may post material under any CC license on a site restricted to members of a certain school, **or to paying customers**, but you may not place effective technological measures (including DRM) on the files that prevents them from sharing the material elsewhere.

> **Can I use effective technological measures (such as DRM) when I share CC-licensed material? No.**

つまり**「有料で配ること自体は合法だが、有料会員がその教材を第三者にばら撒くのを止められない」**。有料サービスの標準的な転載禁止条項が、Wikipedia由来部分については書けなくなる。

### 1.3 問題② 翻訳は確実に ShareAlike を発動させる

CC公式FAQ は adaptation（翻案）の例として**翻訳を明示的に挙げている**。

> a modification rises to the level of an adaptation ... **such as a translation of a novel from one language to another**

中国語版Wikipediaの記事を日本語に訳して教材にする、という最も直感的な使い方が**ほぼ確実にアウト**。語学学習サービスにとってこれは致命的。

### 1.4 回避策はあるが、条件付き

**「事実だけ抽出して、自前の表現で書き起こす」**なら著作権が及ばないため、ライセンス条件が発動しない。これは既に採用方針としている[[AI書き下ろし型]]と完全に整合する。

根拠となる公式記述：

- Wikimedia 利用規約 第7条(a)：「**facts you contribute to the projects may be reused freely without attribution**」
- Wikipedia:Copyrights：「copyright law governs **the creative expression of ideas, not the ideas or information themselves**. Therefore, it is legal to read an encyclopedia article ..., **reformulate the concepts in your own words** ..., so long as **you do not follow the source too closely**」

**ただし「follow the source too closely」の線引きは最終的に各国著作権法次第**であり、Wikimedia も CC も「法律次第」としか言っていない。有料サービスの主軸をこのグレーゾーンに置くのは賢明でない。

### 1.5 問題③ そもそもニュース性がない

これがライセンスとは別の、より根本的な問題。

本サービスの中核価値は**「あなたの興味のキーワードで、毎日の学習教材が自動で作られる」**。Wikipedia は更新されるが、学習者にとって「今日の新着」にはならない。「宇树科技」の記事は昨日も今日も概ね同じ内容で、**プロダクトの心臓部と噛み合わない**。

加えて文体が百科事典調で、中国語学習で欲しい「今使われている言い回し」が学べない。

### 1.6 API 面の制約（2026年に強化された）

| 項目 | 内容 |
|---|---|
| **レート制限（2026年新設）** | 未認証bot（準拠UA付き）で **200 req/min**、UAなしは **10 req/min**、同時接続 **3以下** |
| User-Agent | 必須。`python-requests/x` 等のデフォルト値はブロック対象。連絡先を含む記述的UAが要求される |
| **サブライセンス／ホワイトラベル禁止** | 「may not sublicense... It is not permissible to implement an API client that **white labels in a manner that obscures the identity of the ultimate service provider**」→ **有料サービスから直接APIを叩いて中継する設計はリスクあり。自前で取り込んで配信する形にすべき** |
| 大規模商用 | Wikimedia Enterprise（**無料枠あり**：Snapshot API 月30リクエスト、On-demand API 月50,000リクエスト、クレカ不要）またはダンプ配布へ誘導 |

なお **zh.wikipedia.org はサーバー側からのAPI取得は正常**（WMF側の制限なし）。ただし**中国本土からは2019年5月以降ブロックされている**ため、中国在住ユーザーが出典リンクを踏めない点に留意。

### 1.7 Wikipedia の正しい使いどころ

主軸から外したうえで、**補助的には非常に有用**。

| 用途 | 評価 |
|---|---|
| 記事に出てきた固有名詞・専門用語の背景説明 | ◎ 「宇树科技とは」を短く添える |
| **言語間リンクを使った対訳語彙の自動生成** | ◎ 同一概念の中国語名・英語名・日本語名を機械的に取得できる。**語彙帳の質が一段上がる** |
| 難易度の低い入門教材のベース | ○ ニュースが少ない領域の穴埋め |
| 主たる記事教材の元ネタ | **✗**（§1.2〜1.5） |

特に**言語間リンクによる対訳語彙生成は、他の情報源では代替しにくい固有の価値**がある。ここだけは積極的に使うべき。

---

## 2. 推奨する主軸情報源

### 2.1 ★1 Global Voices — 語学教材として最有力

| 項目 | 内容 |
|---|---|
| ライセンス | **CC BY 3.0**（表示のみ。**ShareAlike なし**） |
| 商用利用 | ○ 「for any purpose, **even commercially**」 |
| 改変 | ○ 「remix, transform, and build upon」 |
| **多言語対訳** | **簡体字中文・繁體中文・日本語版あり**。翻訳プロジェクト "Lingua" により**同一記事の多言語版が構造的に存在** |
| 帰属方法 | 記事**冒頭**に原記事へのリンクと著者名。例：「This story by ○○ originally appeared on Global Voices on ○○.」 |
| 注意 | **画像・音声・動画は別ライセンスの可能性がある。テキストのみに限定すること** |

**なぜ最有力か**：ShareAlikeがないので改変物を自分の条件で提供でき、しかも**同一記事の中国語版・英語版・日本語版が既に存在する**。対訳教材を作るうえでこれほど条件の揃ったソースは他にない。

出典: https://globalvoices.org/about/global-voices-attribution-policy/

### 2.2 ★2 arXiv アブストラクト — ヒューマノイド領域との相性が抜群

| 項目 | 内容 |
|---|---|
| **メタデータ（タイトル・アブストラクト・著者・分類）** | **CC0 1.0（パブリックドメイン相当）**。ShareAlikeも帰属義務もなし。**法的に最もクリーン** |
| 本文（PDF等） | **使えない前提で設計すること**。「圧倒的多数は arXiv perpetual license で、再利用を制限する」。自サーバーでの保存・配信は禁止 |
| レート制限 | **3秒に1リクエスト、同時接続1** |
| 商用利用 | 禁止されていない。ただし「affiliate になることを検討せよ」との案内あり |
| 必須表示 | 「Thank you to arXiv for use of its open access interoperability.」／arXivのブランド名・ロゴの使用は不可 |
| cs.RO の供給量 | **約39件/日**（2026年上半期実測）。ただし月次で655〜1,577件と**2.4倍の振れ幅**があり、学会締切に連動する |

**使い方**：アブストラクト（CC0）を元ネタにし、abs ページへリンクする。arXiv 自身も「Direct users to arXiv.org to retrieve e-print content. We encourage you to link to the abstract page.」と推奨している。

**注意**：英語のみ。学術文体なので難易度が高く、**書き下ろし時のレベル調整が前提**になる。逆に言えば Pro プランの「難易度レベル指定」が活きる領域。

**「毎日N件安定供給」を前提にした設計は危険**（供給量の変動が大きい）。他ソースとの併用が必須。

出典: https://info.arxiv.org/help/api/tou.html / https://info.arxiv.org/help/license/

### 2.3 ★3 政府・公的機関のプレスリリース

| 機関 | ライセンス | 商用 | 改変 | ShareAlike |
|---|---|---|---|---|
| **EU（欧州委員会）** | CC BY 4.0 | ○ | ○ | なし |
| **英国政府** | Open Government Licence v3.0 | ○ | ○ | なし |
| **日本政府** | 公共データ利用規約 PDL1.0 | ○ | ○ | なし |
| **米国連邦政府** | **著作権保護なし（PD）** | ○ | ○ | なし |

**EU が特に有用**：同一内容が多言語で発表されるため、**対訳教材化しやすい**。

**日本政府 PDL1.0 の要求**：出典記載に加え、「**編集・加工等を行ったこと及びその主体を記載**」が必要。未加工であるかのような態様での公表は禁止。

**共通の注意**：ロゴ・紋章・第三者素材・肖像の写った画像は適用外。

出典: https://commission.europa.eu/legal-notice_en / https://www.nationalarchives.gov.uk/doc/open-government-licence/version/3/ / https://www.digital.go.jp/copyright-policy

---

## 3. 使えないと判明した情報源

### 3.1 Weibo（微博）— 規約上、共有プール設計と矛盾

既に `pricing-plan.md` §10.1 に記載済み。要点のみ：

- 開発者協議 2.7.7「APIで取得したデータは接続したアプリにのみ供され、**その他いかなる用途にも使用してはならない**」
- 「**第三者のサーバサイドでのユーザーデータ保存を禁止**」→ 共有プール設計と真っ向から矛盾
- 個人開発者登録に中国の身分証情報が必要、レート制限は1日100回
- データ収集して第三者に提供する事業は**商業データAPI＋別途契約が必須**

**→ 個人の情報収集手段としては引き続き有効**。「Weiboで見つけた話題をキーワードとして投入し、上記のクリーンなソースで裏取りして書き下ろす」運用にすれば、あなたの目利きは資産として残る。

### 3.2 Wikinews — 2026年5月4日に全言語版が凍結

**WMF理事会が閉鎖を決定し、全エディションが read-only 化された**（2026年3月30日発表、5月4日実施）。

> the Board of Trustees of the Wikimedia Foundation has approved the closure of Wikinews. ... **all Wikinews editions will transition to read-only mode** ... on 4 May.

| | 記事数 | 最新記事 | 過去30日の新規 |
|---|---|---|---|
| 英語版 | 22,237 | 2026-05-03 | **0件** |
| 中国語版 | 18,686 | 2026-05-06 | **0件** |

**ライセンスは CC BY 4.0（ShareAlikeなし）で扱いやすい**ため、約4万記事の**ストックとしては今も利用可能**。ただし**日次ニュース供給源としては死んでいる**。

移行先として "Wikinews Pulse" 構想が議論されているが、**稼働時期は不明**。

出典: https://meta.wikimedia.org/wiki/Wikimedia_Foundation_Board_noticeboard/Archives/2026

### 3.3 The Conversation — 改変不可（ND）

CC BY-**ND** のため、語彙置換・リライト・難易度調整といった**語学教材の中核加工ができない**。加えて再掲載時にページビューカウンタ（トラッキングピクセル）の埋め込みが義務。**採用不可**。

### 3.4 企業のプレスリリース — 個別確認が必要

業界標準の再利用ルールは存在せず、圧倒的多数は All Rights Reserved。**体系的に依拠するのは推奨できない**が、個社ごとに規約を確認して使う分には問題ない。企業広報は拡散を望んでいるため、出典明示＋リンクなら実務上のトラブルは起きにくい（ただし法的な許諾とは別問題）。

---

## 4. 推奨する組み合わせ

単一ソースでは供給量も鮮度も足りない。**複数を役割分担させる**。

| 役割 | ソース | 想定比率 |
|---|---|---|
| 日々の主力（時事・多言語対訳） | Global Voices | 40% |
| 技術・ロボティクス（あなたの主戦場） | arXiv アブストラクト | 30% |
| 政策・産業動向 | EU / 英国 / 日本 / 米国 政府PR | 20% |
| 穴埋め・背景解説 | Wikipedia（**事実抽出のみ**）＋ Wikinews ストック | 10% |
| 語彙の対訳生成 | Wikipedia 言語間リンク | 全記事の後処理 |

**この構成なら、ライセンス面はすべて ShareAlike なし（Wikipedia部分は事実抽出に限定）** で統一でき、教材に通常の利用規約を適用できる。

### 供給量の目安

| ソース | 1日あたり |
|---|---|
| Global Voices | 不明（要実測） |
| arXiv cs.RO | 約39件（振れ幅大） |
| 政府PR（4機関合計） | 不明（要実測） |

`pricing-plan.md` の試算では「人気カテゴリ 1日2本の定期生成＋リクエスト対応」を前提としており、**上記の供給量で十分足りる**。

---

## 5. 次にやること

1. **Global Voices の中国語版・英語版・日本語版のRSS／API提供状況を確認**（最優先。最有力ソースなので）
2. **各ソースの1日あたり実供給量を1週間計測**する
3. arXiv cs.RO 以外に、ヒューマノイド関連で拾うべきカテゴリを特定（cs.AI、cs.LG、cs.CV あたり）
4. Wikipedia 言語間リンクAPIで対訳語彙を生成する処理を試作（補助機能だが効果が大きい）
5. 上記が固まった段階で、**弁護士に一度リストごと確認**する

---

## 6. 出典

**Wikipedia / Wikimedia**
- 利用規約: https://foundation.wikimedia.org/wiki/Policy:Terms_of_Use
- 再利用ガイド: https://en.wikipedia.org/wiki/Wikipedia:Reusing_Wikipedia_content
- Wikipedia:Copyrights: https://en.wikipedia.org/wiki/Wikipedia:Copyrights
- APIレート制限（2026年新設）: https://www.mediawiki.org/wiki/Wikimedia_APIs/Rate_limits
- API利用ガイドライン: https://foundation.wikimedia.org/wiki/Policy:Wikimedia_Foundation_API_Usage_Guidelines
- User-Agentポリシー: https://foundation.wikimedia.org/wiki/Policy:Wikimedia_Foundation_User-Agent_Policy
- Wikimedia Enterprise: https://enterprise.wikimedia.com/pricing/

**Creative Commons**
- CC BY-SA 4.0 リーガルコード: https://creativecommons.org/licenses/by-sa/4.0/legalcode.en
- 公式FAQ: https://creativecommons.org/faq/

**その他ソース**
- Global Voices 帰属ポリシー: https://globalvoices.org/about/global-voices-attribution-policy/
- arXiv API 利用規約: https://info.arxiv.org/help/api/tou.html
- arXiv ライセンス: https://info.arxiv.org/help/license/
- Wikinews 閉鎖決定: https://meta.wikimedia.org/wiki/Wikimedia_Foundation_Board_noticeboard/Archives/2026
- Wikinews 著作権: https://en.wikinews.org/wiki/Wikinews:Copyright
- EU 法的通知: https://commission.europa.eu/legal-notice_en
- 英国 OGL v3.0: https://www.nationalarchives.gov.uk/doc/open-government-licence/version/3/
- デジタル庁 コピーライトポリシー: https://www.digital.go.jp/copyright-policy
- 米国 17 U.S.C. §105: https://www.copyright.gov/title17/92chap1.html#105

---

### 関連ドキュメント

- `docs/status-summary.md` — 検討の現況整理
- `docs/pricing-plan.md` — 料金プラン設計・原価計算
- `docs/saas-migration-plan.md` — 移行設計書・アーキテクチャ
