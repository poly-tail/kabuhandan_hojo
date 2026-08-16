# kabuhandan_hojo 要件仕様書 v1.1

## 1. 目的

日本株の監視と判断補助を行うローカルアプリを提供する。ユーザーが地合い、材料、需給、テクニカル、保有状況、狙い中銘柄を横断して確認でき、OpenAI API を使う場合も自動売買や断定的な投資助言ではなく、判断材料、反証条件、リスク、代替案、執行条件を整理することを目的とする。

## 2. 基本方針

- 自動売買は行わない
- 断定的な投資助言を行わない
- 正式ソースを優先する
- 規約違反のスクレイピングを行わない
- OpenAI API キーはサーバー側だけで扱い、フロントエンドへ露出しない
- AI分析は「判断補助」であり、ユーザーが最終判断する前提の材料整理に限定する

## 3. データソース方針

- 価格データは J-Quants を第一候補とする
- 開示データは EDINET API と TDnet API を canonical source とする
- allowlist IR と YouTube Data API は補助ソースとする
- 会社IR、決算短信、決算説明資料、適時開示、取引所、公式統計、企業発表を一次情報として優先する
- ニュース、SNS、YouTube、個人投資家情報は補助情報として扱う
- Web検索を使う場合も、取得元、日付、一次情報性、前提差を明示できる形で返す

## 4. 保有・監視・候補銘柄要件

- watchlist の登録、一覧、再利用ができる
- portfolio holding の登録、一覧、評価価格更新ができる
- 狙い中銘柄は、実DBが未整備でも mock candidates でAI分析検証できる
- 実DBの保有銘柄、実DBの監視銘柄、ローカル保存データ、mock data の順で利用する
- 選択銘柄指定では、入力された銘柄コードを対象に個別または少数銘柄分析できる

## 5. AI分析要件

OpenAI APIで次の問い合わせを行う際は、Prompt Registry / Prompt Builder を通じて、ユーザー指定の株式分析プロンプトを毎回適用する。

- 保有銘柄の一括分析
- 狙い中銘柄の一括分析
- 個別銘柄の詳細分析
- ポートフォリオ全体の買い売り判断
- 重要局面分析
- ChatGPT手動投入用プロンプト生成

ただし、長文プロンプト全文を全モードにそのまま送らない。API実行時は以下の責務を分離する。

- `basePolicy`
- `analysisSections`
- `modeProfiles`
- `outputSchemas`
- `promptBuilder`
- `costControl`
- `webSearchPolicy`

## 6. Prompt Registry 要件

- ユーザー指定の株式分析プロンプト全文は `app/prompts/stock_analysis/user_stock_analysis_prompt_full.py` に保存する
- 変数名は `USER_STOCK_ANALYSIS_PROMPT_FULL` とする
- `prompt_only` mode ではこの全文を使う
- API実行時は mode profile に応じて必要章だけを抽出・圧縮して使う
- Base Policy は全API分析で必ず入れる
- 入力にない項目は「未入力」と明示する

## 7. AI分析モード要件

| mode | 目的 | Web検索 | 出力方針 |
|---|---|---|---|
| `scanner` | 保有・監視・候補銘柄を軽量分類する | OFF可 | 銘柄ごとに短く分類し、詳細分析や全体判断が必要か返す |
| `analyst` | 個別銘柄を詳細分析する | 原則ON | 市況、テーマ、ファンダ、需給、テクニカル、執行案、反証条件を返す |
| `judge` | 複数銘柄とポートフォリオを横比較する | 原則ON | 買い候補、売り候補、減らす候補、資金配分、集中リスクを返す |
| `critical` | 決算跨ぎ、大型ポジション、急騰急落など高損失リスク局面を分析する | 強く推奨 | 強気/中立/弱気、期待値、ポジションサイズ、イベント跨ぎ、辛口チェックを返す |
| `prompt_only` | ChatGPTへ手動コピペするプロンプトを生成する | API検索なし | 全文プロンプトとアプリ側入力JSONを返す |

## 8. Web検索要件

- `analyst` / `judge` / `critical` は `include_web_search` 未指定時にONを既定とする
- `scanner` はWeb検索OFFでも実行できる
- Web検索OFF時は warnings に「最新Web確認なし」を入れ、重要主張は【U】または【E】として扱う
- `prompt_only` はOpenAI API検索を行わず、生成プロンプト内でChatGPTにWeb確認を依頼する
- `max_web_search_calls` と `OPENAI_MAX_WEB_SEARCH_CALLS` の小さい方を実効上限にする

## 9. Structured Outputs / JSON 要件

- OpenAI API呼び出しでは mode 別 JSON Schema を使う
- parse失敗時もUIを壊さず、`raw_model_output` と warning を保持する
- 長い非JSON応答は、Web検索なしのJSON整形リトライで救済する
- JSON整形リトライにも失敗した場合でも、OpenAIから分析本文らしき応答が返っている場合は、生応答をアプリ上に表示・保存する
- validation warning は response の `warnings` に出す
- 銘柄別カード、ポートフォリオ総合判断、具体的な執行案、反証条件、辛口チェックをUI表示しやすいJSONで返す

## 10. UI要件

- dashboard の Portfolio AI分析パネルで次を選べる
  - 軽量スキャン
  - 個別詳細分析
  - 全体売買判断
  - 重要局面分析
  - ChatGPT投入用プロンプト生成
- 対象は次を選べる
  - 保有銘柄
  - 狙い中銘柄
  - 監視銘柄
  - 選択銘柄
  - テスト用仮銘柄
- プロンプト入力欄が空でも、Prompt Builder のテンプレートを自動適用して実行する
- `全体売買判断` ボタンだけで保有銘柄全体に judge mode を実行できる
- 高コストモードやWeb検索ONでは実行前に確認できる
- warnings、sources、銘柄別カード、ポートフォリオ総合判断、具体的な執行案、反証条件、辛口チェック、履歴/前回結果を表示する

## 11. mock data 要件

- mock holdings を用意し、実DBが空でも動作確認できる
- mock candidates を用意し、狙い中銘柄分析をDB未整備でも検証できる
- `mock_response=true` はOpenAI APIを呼ばず、UI表示確認用の固定応答を返す
- `target=mock`、`use_mock_holdings=true`、またはDB未登録によるmock fallbackでは、OpenAI APIを呼ばず固定応答を返す

## 12. 非機能要件

- ローカルで起動できる
- mock mode と live mode を切り替えられる
- live mode では通常UIのmock補完を行わない
- データ欠損時は `未取得` または空表示で扱う
- `.env` はgit管理せず、`.env.example` のみ更新する
- APIレスポンスやエラー表示にAPIキー、内部スタックトレース、秘密情報を含めない
- AI分析結果はローカルJSON履歴と同一入力キャッシュに保存できる
