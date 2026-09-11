# UI Principles

## 目的

監視銘柄の優先度、仮説、地合い、材料を短時間で読み取れることを優先する。

## 原則

- 情報の優先順位を明確にする
- live mode では不明なものを不明なまま見せる
- source policy を UI 上でも崩さない
- top から detail、detail から chart の流れを短く保つ

## 現在の表示方針

- 地合いは market proxy ベース
- detail は仮説と factor split を先に見せる
- chart は client-side 補助表示で読みやすさを優先する
- watchlist 未登録の候補も top で見えるようにする
- AI失敗や空回答を回答として表示しない
- AI回答本文とrequest ID等の診断情報を分離する
- APIキー、prompt全文、質問全文などserver-sideの内部情報を通常画面へ露出しない
- 通常の分析画面は入力と直近回答に集中し、保存済み回答の精読は別ウィンドウの幅広いreaderへ分離する
- 別ウィンドウはユーザーが押す通常リンクで開き、`noopener noreferrer`を付ける。回答本文をURLへ渡さない
- canonical個別銘柄AIの保存済み回答はMarkdownやHTMLとして解釈せず、プレーンテキストで表示する
- legacy stock-reviewの保存済み回答は検証済みfieldをsemanticな構造化UIへ対応付けるが、model由来Markdown / HTMLを直接実行しない。raw fallbackはescape済みplain textのまま扱う
- legacy保存履歴一覧はmetadataだけを保存順の新しいものから分析方法別に示し、回答本文を一覧summaryへ流用しない。detailとMarkdown exportは利用者の明示操作で開く
- legacy履歴のdetail、`.md`、別タブ印刷 / PDF表示はローカル保存済みrecordだけを読み、OpenAI、quota、usage、cacheを増やさない
- raw fallbackの画面previewを先頭20,000文字へ省略した場合は全文Markdownを案内し、印刷用cloneではraw detailsを開いて表示範囲を欠落させない
- 過去recordに存在しないnamed watchlist名は現行stateから推測表示せず、保存済みIDまたは一般的な対象labelを使う
- 保存失敗は生成失敗と混同せず、回答本文を維持したままwarningを表示し、保存済み導線だけを出さない
- legacy AIの利用量は「成功review」「OpenAI呼出」「未算定」を分け、銘柄数や正式請求額と誤認しない文言で表示する
- 送信前heuristicは「今回の事前概算」、provider token由来の日/月集計は「概算」として分離し、OpenAI Platformを請求の正本と案内する

## Dashboard legacy AIの階層と有効性

- `/ui/dashboard`の「保有・ウォッチリストAIレビュー」を`.stock-ai-workbench`内の`.stock-ai-control-pane`と`.stock-ai-result-pane`へ配置する。各classは1件、主要IDは一意で全操作はmain内に置く。
- 1440px前後は左380〜420px・右残り幅、960px以下は1カラムとする。390pxではdocument横overflowを生じさせず、長い日本語・URL・pre・フォームは折返しと`min-width: 0`で収める。
- 薄いニュートラルグレー背景、白panel、濃紺文字、薄い枠、弱いshadow、青い主操作とする。緑・赤・橙は成功・損益・警告等の意味に限定する。新CSSは`.page-top`のテーマ以外、可能な限り`.page-top .stock-ai-workbench`以下にscopeする。
- 4分析方法、分析対象、建玉意図、ユーザー仮説、Web ON/OFF、実行操作を常時表示する。4実行buttonと`stock-ai-mode` selectの重複、既存button文言・ID・data属性を維持する。
- `#stock-ai-details`へlegacy利用量、Web最大回数、mock、保存、cache、ChatGPT投入用prompt生成・copy・prompt欄をまとめる。空promptは大きな空白を占有せず、生成後はdetailsを開いて確認・copyへ案内する。
- 右paneは現在状態、送信時条件snapshot、回答生成日時、系列別の元データ基準日時、reader導線、結果を示す。入力なしの系列と、入力あり・基準日時未取得の系列を区別する。基準日時は範囲・source・件数を常時示し、各record・versionは詳細へ展開できる。readerの印刷時はsource詳細を開いて保持する。
- keyboardから4分析方法、主要条件、詳細設定、実行、readerへ到達でき、focusを視認できる。empty/loading/success/failure/長文/prompt生成済みの各状態を1440・960・390pxで確認する。
- safe renderer、escapeHtml、安全なURL、reader CSP、`noopener noreferrer`、raw failureの非成功表示を維持する。外部font、icon library、CSS/JS framework、効く保証のない期間・思考深度・verbosity controlは追加しない。

- 結果を決める条件はmode、target、ticker、仮説、建玉意図、Web ON/OFF・最大回数、mock設定、管理space・対象list・選択銘柄である。結果保存とcache利用は運用設定であり、toggleだけでは有効回答を消さない。
- 条件変更はinput/changeの重複を冪等に扱い、現在回答、現在回答reader、生成prompt、copy可否を同時に失効させる。保存済み履歴は削除しない。
- 保有追加・数量・取得単価変更・全削除を含む削除、対象list構成の変更は保存成功時に失効させる。保存失敗だけでは無関係の有効回答を消さない。
- 保存成功後のDashboard再取得が失敗しても旧回答を復活させない。データ未同期を表示し、再同期成功まで古いstateでの再分析を禁止する。変更前に開始したDashboard取得も新しいrevisionへ適用しない。
- 表示generationと実行中requestのbusy状態を分ける。条件変更後も旧通信が終わるまでは重複実行を禁止し、完了後に再実行を許す。旧成功・旧失敗・旧finallyが新しい表示を上書きしない。自動再実行、provider処理や課金まで停止したという表示は行わない。
- 送信時の対象、list名、主要条件をclient memoryのsnapshotへ固定して結果・readerへ表示する。現在のcontrol値から旧回答の意味を再推測しない。

- Web検索の許可・実行・主張の裏付けを別々に示す。実行0回や不明を検索済みとしない。
- 回答生成時点と、価格・テクニカル・需給・ニュース等の元データ基準日時を分ける。不明な日時を現在時刻で埋めない。cache再表示の元usageと今回の追加実行0を区別する。
