# kabuhandan_hojo 要件仕様書 v1.4

## 1. 目的

日本株の監視と判断補助を行うローカルアプリを提供する。ユーザーが地合い、材料、需給、テクニカル、保有状況、狙い中銘柄を横断して確認でき、OpenAI APIを使う場合も自動売買や断定的な投資助言ではなく、判断材料、反証条件、リスク、代替案、執行条件を整理することを目的とする。

v1.4では、v1.3の機能を累積継承し、canonical個別銘柄AI経路をstatelessなOpenAI requestとして明示し、AI回答生成とローカルSQL保存の成否を分離する。さらに、既定bindをloopbackへ限定し、DB初期化をFastAPI lifespanへ一本化する。active promptは2026.08.18へ更新し、根拠ラベルを正式表記へ固定する。

## 2. 基本方針

- 自動売買は行わない。
- 断定的な投資助言を行わない。
- AI分析は判断補助であり、最終的な投資判断と執行はユーザーが行う。
- 正式ソースを優先し、規約違反やrobots無視のスクレイピングを行わない。
- OpenAI APIキーはサーバー側だけで扱い、browser、公開API response、通常ログへ露出しない。
- OpenAI APIの失敗、空回答、未完了responseを成功として扱わない。
- model選択と回答品質presetは別の設定軸として扱う。
- canonical個別銘柄経路とlegacy portfolio経路の異なる挙動を暗黙に混在させない。
- 取得できていない情報を現在の事実として推測で補完しない。

## 3. データソース方針

- 基幹sourceはJ-Quants、EDINET API、YouTube Data API、allowlist化した公式IRに限定する。
- 価格データはJ-Quants、法定開示はEDINET APIを第一候補とする。
- allowlist公式IRとYouTube Data APIは、上記基幹source内の補助情報として扱う。
- 会社IR、決算短信、決算説明資料、適時開示、取引所、公式統計、企業発表を一次情報として優先する。
- ニュース、SNS、YouTube、個人投資家情報は補助情報として扱う。
- Web検索を使う経路では、取得元、日付、一次情報性、前提差を明示できる形で返す。
- データ欠損時は`未取得`、`未提供`、`【U】`等で明示し、取得済み情報と区別する。

canonical個別銘柄経路では、v1.4時点で新たなWeb検索、J-Quants同期、外部市場データ取得を実行しない。利用可能なcontextは、登録済み`security_master`の以下の項目に限定する。

- 銘柄コード
- 銘柄名
- 市場
- 17業種および33業種（登録されている場合）
- 上場日（登録されている場合）

現在価格、価格取得時刻、決算、コンセンサス、チャート、テクニカル、出来高、信用、空売り、指数、セクター相対強弱、為替、金利、マクロ、直近材料、今後のイベント、保有状況、許容損失、希望時間軸は、この経路では未提供情報として扱う。

## 4. 保有・監視・候補銘柄要件

- watchlistの登録、一覧、再利用ができる。
- portfolio holdingの登録、一覧、評価価格更新ができる。
- legacy portfolio経路の狙い中銘柄は、実DBが未整備でもmock candidatesでAI分析UIを検証できる。
- legacy portfolio経路では、実DBの保有銘柄、実DBの監視銘柄、ローカル保存データ、mock dataの順で利用する。
- canonical個別銘柄経路では、登録済みかつactiveな銘柄を1件選択する。
- canonical個別銘柄経路では、未登録またはinactiveな銘柄を別銘柄やmockへfallbackしない。

## 5. AI経路の責務分離

v1.4では、次の2経路を独立して扱う。

| 項目 | canonical個別銘柄経路 | legacy portfolio / multi-mode経路 |
|---|---|---|
| 主endpoint | `POST /api/ai/analyses`、`GET /api/ai/analyses/{request_id}` | `POST /api/ai/stock-review`および既存互換endpoint |
| 主UI | `GET /ui/analysis`、`GET /ui/analysis/results/{request_id}` | dashboardのPortfolio AI分析パネル |
| 対象 | 登録済み個別銘柄1件 | 保有、監視、候補、選択銘柄、portfolio全体 |
| preset / mode | `STANDARD`のみ | `scanner` / `analyst` / `judge` / `critical` / `prompt_only` |
| prompt管理 | `IndividualSecurityPromptCompiler`とversioned Markdown asset | 既存Prompt Registry / Prompt Builder |
| OpenAI出力 | `response.output_text`のプレーンテキスト | mode別Structured Outputsまたは既存parse経路 |
| Web検索 | OFF、tool未使用 | modeと設定に応じて既存機能を使用 |
| mock / cache / fallback | 使用しない | v1.1までの既存仕様を維持 |

canonical個別銘柄経路の追加を理由として、legacy endpoint、legacy UI、既存Prompt Registry、既存mock、既存cache、既存history、既存parse処理を削除または挙動変更しない。

## 6. canonical個別銘柄AI最小縦スライス

### 6.1 機能フロー

次の単一路を成立させる。

```text
登録済み個別銘柄1件
+
自由質問
+
STANDARD
↓
FastAPI
↓
OpenAI Responses API
↓
response.output_text
↓
browserへプレーンテキスト表示
```

route、service、OpenAI client、response validation、UI表示を分離し、OpenAI APIへは1分析につき1回だけrequestする。

### 6.2 request要件

`POST /api/ai/analyses`は次を受け取る。

- `security_code`: 入力時4〜10文字の登録銘柄コード。前後空白は除去し、空白だけの値は拒否する。
- `question`: 入力時1〜4,000文字の自由質問。前後空白を除去し、空白だけの質問は拒否する。
- `preset`: v1.4では`STANDARD`のみ。未指定時も`STANDARD`とする。

未知fieldは受け付けず、未対応presetはvalidation errorとする。

### 6.3 response要件

成功時は次を返す。

- `request_id`
- `status = success`
- 非空の`answer_text`
- `error = null`
- 銘柄コード、銘柄名、市場からなる`security` snapshot
- `openai_response_id`
- `persistence_status = saved | failed`
- 保存成功時だけ非nullとなる`saved_at`
- 保存失敗時だけユーザー向け説明を持つ`persistence_warning`

AI回答生成に成功した場合、ローカルSQL保存に失敗してもHTTP 200、`status = success`、非空`answer_text`を返す。生成失敗と保存失敗を同じstatusで表現しない。

失敗時は次を返す。

- `request_id`
- `status = error`
- `answer_text = null`
- 公開可能なcodeと簡潔なmessageからなる`error`
- 取得できている場合だけ`openai_response_id`
- `persistence_status = null`、`saved_at = null`、`persistence_warning = null`

prompt本文、ユーザー質問、APIキー、内部stack trace、OpenAI SDK例外本文は公開responseへ含めない。

### 6.4 service要件

- `security_master`から指定銘柄を解決する。
- 未登録またはinactiveな銘柄ではOpenAI APIを呼ばない。
- 銘柄contextと質問を`IndividualSecurityPromptCompiler`へ渡す。
- compilerが返す`instructions`、`input`、trace metadataを独立OpenAI clientへ渡す。
- OpenAIの検証済み`output_text`だけを`answer_text`としてrouteへ返す。

### 6.5 成功回答の永続保存要件

- `POST /api/ai/analyses`は、OpenAI response ID、`completed` status、非空`output_text`を検証した後、その成功結果をローカルSQLの`AiAnalysisRecord`として自動保存する。
- 保存keyは公開responseの`request_id`と同じUUIDとする。
- 保存対象は、質問、回答本文、銘柄snapshot、preset、model、reasoning / verbosity設定、OpenAI response ID、prompt version / profile / module / asset ID / hashからなるprompt trace、および生成日時とする。
- APIキー、Authorization header、prompt全文、provider raw response、provider raw error、内部stack traceは保存しない。
- 保存に失敗した場合はtransactionをrollbackするが、生成済み回答を捨てず、HTTP 200、`status=success`、`persistence_status=failed`、`saved_at=null`、安全な`persistence_warning`を返す。
- 保存失敗を理由にOpenAI APIを再呼び出さず、1回のユーザー送信に対するOpenAI callは最大1回とする。
- 保存成功時は`persistence_status=saved`、`saved_at`を設定し、`persistence_warning=null`とする。
- 保存失敗時はrecordが存在しないため、同じrequest IDの詳細GETはnot foundのままとする。
- OpenAI側のResponses Application State保存を`store=false`で無効化する。これはOpenAI API全体のZero Data Retentionを保証せず、組織のdata control設定やabuse monitoring logの扱いとは別である。
- OpenAI API側の保存をアプリ履歴の代替とせず、保存に成功したローカルSQL recordだけを再表示の正本とする。

### 6.6 保存回答の1件取得要件

- `GET /api/ai/analyses/{request_id}`はUUIDで保存済み成功回答を1件取得する。
- 存在しないrequest IDはsuccessや空回答へfallbackせず、not foundとして扱う。
- 回答一覧、検索、削除、export、保持期限管理は提供しない。
- canonical AIのPOST / GET responseには、FastAPIがhandler前に返すvalidation errorを含めて`Cache-Control: no-store`を付与する。

## 7. OpenAI APIと回答preset要件

canonical個別銘柄経路では、次を固定する。

```text
API: OpenAI Responses API
model: gpt-5.6-terra
preset: STANDARD
reasoning.effort: medium
reasoning.mode: 未送信
text.verbosity: medium
timeout: 60秒
```

- modelは回答preset定義へ含めず、runtime設定として分離する。
- `STANDARD`以外へ暗黙変換しない。
- 指定modelを利用できない場合、別model、mock、cacheへfallbackしない。
- `temperature`を主要UI制御項目にしない。
- Web search tool、その他tool、Structured Outputs、JSON Schema、streaming、backgroundをrequestへ追加しない。
- `store=false`を必ず明示し、`previous_response_id`を送信しない。
- `store=false`はResponses Application State保存を無効化する設定であり、Zero Data Retention全体の保証として表示・説明しない。
- SDK側の自動retryは使用しない。

## 8. IndividualSecurityPromptCompiler要件

### 8.1 asset管理

canonical個別銘柄経路のpromptは、PythonコードやUI内の巨大文字列として保持せず、`app/prompts/individual_security/`配下のversioned Markdown assetとmanifestで管理する。

v1.4で使用するactive prompt versionは`2026.08.18`、compilerは`individual-security-v2`とする。source titleは「株判断プロジェクト｜定型プロンプト集 v2026.08.18（根拠ラベル表記正規化版）」、source SHA-256は`B1C0AF5B2C33D76E4F836A428380237383FB7EAEA8B6FEAFFD9CC82632416D30`とし、非送信の`assets/v2026_08_18/SOURCE.md`で検証する。v2026.08.17原資料のtitle/hashは`revision.base_source`として保持する。v2026.08.18はruntime canonicalizationと旧括弧ラベルのfail-closed検証を加えたreleaseであり、v2026.08.17 assetは履歴として変更しない。次のassetだけを組み込む。

1. 「1. 株判断共通OS」
2. 「2. 共通入力テンプレート」の個別銘柄MVPに必要な部分
3. Web検索・外部tool・追加市場データを利用できないことを明示するアプリ実行制約
4. 「3.1 総合的な個別銘柄分析」

用途module 3.2〜3.14、アプリ向け構造化出力schema、人間向けの重複出力templateは、この経路へ読み込まない。

原資料v2026.08.17の命名規則をactive prompt 2026.08.18へ継承し、銘柄の表示・言及は原則として「銘柄名（銘柄コード）」とする。外国銘柄を将来扱う場合は「会社名（ticker）」とする。共通入力では銘柄名と銘柄コードを別項目として扱うが、現行MVPのrequest fieldは互換性のため`security_code`を維持し、銘柄名は解決済み`security_master`から渡す。根拠ラベルは`【V】確認済み`、`【E】推定`、`【U】未確認`だけを正式表記とし、active compiled promptに旧括弧表記が含まれる場合はOpenAI APIを呼ばずfail closedとする。

### 8.2 manifestと整合性

manifestでは最低限次を追跡する。

- prompt version
- prompt profile ID
- compiler version
- source titleとsource SHA-256
- compile order
- asset ID、path、source section、asset SHA-256
- 使用module IDとmodule名

compilerはmanifest、compile order、module 3.1、asset path、UTF-8、非空内容、asset SHA-256を検証する。manifest不正、asset欠落、hash不一致ではOpenAI API呼び出しを行わず、旧minimal promptや別moduleへfallbackしない。

assetをPython packageへ含め、source tree実行とpackage実行で同じprompt bundleを読めるようにする。

### 8.3 合成順序

静的`instructions`は次の順で合成する。

1. 共通OS
2. 共通入力ルール
3. Web・外部市場データなしの実行制約
4. 用途module 3.1「総合的な個別銘柄分析」

実行時`input`は次の順で合成する。

1. `security_master`由来の銘柄context
2. 未提供contextの明示
3. ユーザー自由質問

質問は静的`instructions`へ混入させず、JSON文字列化した実行時dataとして区切る。

### 8.4 provenance

各compile結果で次を生成する。

- prompt version
- prompt profile ID
- compiler version
- module ID、module名
- 使用asset ID一覧
- source SHA-256
- compiled prompt SHA-256

これらの非機密識別子とhashをOpenAI Responses requestの`metadata`へ付与し、`openai_response_id`と関連付けられるようにする。prompt本文とユーザー質問はmetadataへ含めない。公開FastAPI responseとbrowserへprompt provenanceを追加しない。通常ログへはprompt本文、質問、秘密情報を出さず、安全な識別子とhashだけを記録できる。

## 9. 情報不足と分析品質要件

- 個別材料、fundamentals、株価momentum、technical、需給、信用状況、sector、市場全体、地合い、金利、為替、macro、決算、直近・今後のevent、市場の織り込み、強気・基準・弱気scenario、risk、反証条件、no-tradeを必要に応じて検討する。
- 全項目を埋めるために未提供の事実や数値を創作しない。
- 重要主張は、確認済み`【V】`、推定`【E】`、未確認`【U】`を区別する。
- `security_master`に存在する銘柄属性と、価格・市場・決算等の時事dataを混同しない。
- 根拠不足時は無理に買い・売りを断定せず、`insufficient_data`または`no_trade`を選択肢に含める。
- 「良い会社か」と「現在価格で買う価値があるか」、「良い材料か」と「株価が上がる材料か」を分離する。
- 短期、中期、中長期、長期を区別し、主因、補正項、反証条件、撤退条件、再評価条件を示す。
- 現在価格や最新dataがない場合、具体的な価格水準や現在の市場状態を確認済み事実として断定しない。

## 10. response検証とerror要件

OpenAI clientは次を検証する。

- OpenAI response IDが存在する。
- `response.status`が`completed`である。
- trim後の`response.output_text`が非空である。

最低限、次のOpenAI error codeを区別する。

- `AUTHENTICATION_ERROR`
- `MODEL_UNAVAILABLE`
- `INVALID_API_PARAMETERS`
- `RATE_LIMITED`
- `TIMEOUT`
- `NETWORK_ERROR`
- `EMPTY_RESPONSE`
- `UNKNOWN_OPENAI_ERROR`

アプリ固有errorとして、少なくとも次を区別する。

- `SECURITY_NOT_FOUND`
- `DATABASE_UNAVAILABLE`
- `PERSISTENCE_ERROR`（schema互換のため残すが、OpenAI成功後の通常の保存失敗には使用しない）

OpenAI失敗、timeout、未完了response、空回答をsuccessに変換しない。raw response表示、JSON修復、parse失敗時の再AI呼び出しも行わない。ユーザー向けmessageと開発用診断情報を分離し、APIキーや秘密情報をどちらにも含めない。

## 11. canonical最小AI画面要件

`GET /ui/analysis`はlegacy dashboardの巨大AI UIから独立した最小画面とし、次を備える。

- 銘柄コードまたは銘柄名による登録銘柄検索
- 個別銘柄1件の選択状態
- 自由質問textarea
- `STANDARD`で送信するbutton
- 送信中のloading表示
- 送信中の銘柄検索・銘柄選択・質問編集のロック
- 簡潔なerror表示
- 回答本文表示
- request IDとOpenAI response IDの診断表示
- 保存結果のwarning表示
- `persistence_status=saved`の場合だけ表示する`別ウィンドウで大きく表示`の導線

保存失敗でも生成済み回答本文を表示し、保存済み表示、`saved_at`、大型表示導線は表示しない。回答本文は`textContent`と`white-space: pre-wrap`によるプレーンテキスト表示とする。成功導線は保存済みrequest IDに対応する`GET /ui/analysis/results/{request_id}`を`target="_blank"`かつ`rel="noopener"`で開く。大型回答画面も`GET /api/ai/analyses/{request_id}`から保存済み回答を取得し、同じプレーンテキスト規則で表示する。Markdown renderer、HTML挿入、構造化cardを導入しない。browserからOpenAI APIを直接呼ばず、APIキーやprompt本文をbrowserへ送らない。

## 12. testと評価要件

canonical個別銘柄経路では、少なくとも次をunit testで固定する。

- PromptCompilerが共通OSを読み込む。
- PromptCompilerが用途module 3.1を読み込む。
- 銘柄contextと自由質問が実行時inputへ入る。
- 用途module 3.2〜3.14とJSON Schema指示が混入しない。
- prompt version、asset ID、module ID、hashを取得できる。
- trace metadataへprompt本文と質問が入らない。
- Web検索と外部toolを利用できない制約が入る。
- prompt assetの合成順序を維持する。
- OpenAI clientの正常系、空回答、未完了status、timeout、SDK例外分類が動作する。
- FastAPI endpointの正常系、OpenAI error、未知銘柄、未対応presetが動作する。
- 最小UIが銘柄選択、質問、`STANDARD`、loading、error、プレーンテキスト回答表示を持つ。
- OpenAI成功・保存成功では`persistence_status=saved`と`saved_at`を返す。
- OpenAI成功・保存失敗ではrollback後もHTTP 200、`status=success`、非空`answer_text`、`persistence_status=failed`、安全なwarningを返し、OpenAIを再呼び出さない。
- `GET /api/ai/analyses/{request_id}`が保存回答を1件返し、未知IDをnot foundにする。
- 成功時の別ウィンドウ導線が`target="_blank"`と`rel="noopener"`を持ち、大型回答画面が保存回答をプレーンテキスト表示する。
- canonical POST / GET responseに、validation errorを含めて`Cache-Control: no-store`が付く。

人間によるbefore / after比較用に、次の観点を網羅する5〜10件のversioned fixtureを保持する。

- 買い判断
- 決算後判断
- 市場要因と個別要因の分離
- momentum
- 需給
- event
- risk
- 反証条件
- 情報不足
- no-trade

評価dimensionは最低限、観点の広さ、反証条件、情報不足の扱い、冗長性とする。v1.4では投資判断の正しさを自動採点しない。

## 13. legacy portfolio / multi-mode AI要件

この章の要件はlegacy portfolio経路だけに適用し、canonical個別銘柄経路へ暗黙適用しない。

### 13.1 対象とPrompt Registry

legacy OpenAI API経路は次を扱う。

- 保有銘柄の一括分析
- 狙い中銘柄の一括分析
- 個別または少数銘柄の詳細分析
- portfolio全体の買い売り判断
- 重要局面分析
- ChatGPT手動投入用prompt生成

既存Prompt Registry / Prompt Builderは次の責務を分離する。

- `basePolicy`
- `analysisSections`
- `modeProfiles`
- `outputSchemas`
- `promptBuilder`
- `costControl`
- `webSearchPolicy`

ユーザー指定のlegacy株式分析prompt全文は`app/prompts/stock_analysis/user_stock_analysis_prompt_full.py`の`USER_STOCK_ANALYSIS_PROMPT_FULL`に保持する。`prompt_only`は全文を使い、API実行modeはmode profileに応じて必要章を選択・圧縮する。入力にない項目は`未入力`と明示する。

### 13.2 legacy mode

| mode | 目的 | Web検索 | 出力方針 |
|---|---|---|---|
| `scanner` | 保有・監視・候補銘柄を軽量分類する | OFF可 | 銘柄ごとに短く分類し、詳細分析や全体判断が必要か返す |
| `analyst` | 個別銘柄を詳細分析する | 原則ON | 市況、テーマ、fundamentals、需給、technical、執行案、反証条件を返す |
| `judge` | 複数銘柄とportfolioを横比較する | 原則ON | 買い候補、売り候補、減らす候補、資金配分、集中riskを返す |
| `critical` | 決算跨ぎ、大型position、急騰急落等を分析する | 強く推奨 | 強気・中立・弱気、期待値、position size、event跨ぎ、辛口checkを返す |
| `prompt_only` | ChatGPTへ手動copyするpromptを生成する | API検索なし | 全文promptとアプリ側入力JSONを返す |

### 13.3 legacy Web検索

- `analyst`、`judge`、`critical`は`include_web_search`未指定時にONを既定とする。
- `scanner`はWeb検索OFFでも実行できる。
- Web検索OFF時はwarningsに「最新Web確認なし」を入れ、重要主張は`【U】`または`【E】`として扱う。
- `prompt_only`はOpenAI API検索を行わず、生成prompt内で手動投入先にWeb確認を依頼する。
- `max_web_search_calls`と`OPENAI_MAX_WEB_SEARCH_CALLS`の小さい方を実効上限にする。

### 13.4 legacy Structured Outputs / JSON

- mode別JSON Schemaを使う。
- parse失敗時もlegacy UIを壊さず、`raw_model_output`とwarningを保持する。
- 長い非JSON応答は、Web検索なしのJSON整形retryで救済する。
- JSON整形retryにも失敗した場合、OpenAIから分析本文らしき応答が返っていれば、legacy経路では生応答を表示・保存できる。
- validation warningはresponseの`warnings`へ出す。
- 銘柄別card、portfolio総合判断、執行案、反証条件、辛口checkをUI表示しやすいJSONで返す。

このfallbackはcanonical個別銘柄経路では禁止する。

### 13.5 legacy UI

dashboardのPortfolio AI分析パネルでは次を選べる。

- 軽量scan
- 個別詳細分析
- 全体売買判断
- 重要局面分析
- ChatGPT投入用prompt生成

対象は保有銘柄、狙い中銘柄、監視銘柄、選択銘柄、テスト用仮銘柄から選べる。prompt入力欄が空でもPrompt Builder templateを適用し、高cost modeやWeb検索ONでは実行前に確認できる。warnings、sources、銘柄別card、portfolio総合判断、執行案、反証条件、辛口check、履歴・前回結果を表示する。

### 13.6 legacy mock / cache / history

- mock holdingsとmock candidatesを用意し、legacy UIを実DBが空でも検証できる。
- `mock_response=true`はOpenAI APIを呼ばず固定応答を返す。
- `target=mock`、`use_mock_holdings=true`、legacy DB未登録によるmock fallbackではOpenAI APIを呼ばない。
- legacy AI分析結果はローカルJSON履歴と同一入力cacheに保存できる。

これらをcanonical個別銘柄経路へ接続しない。

## 14. 非機能・security要件

- ローカルで起動できる。
- mock modeとlive modeを切り替えられる。
- live modeの通常UIではmock補完を行わない。
- canonical個別銘柄経路はlive modeと利用可能な銘柄DBを必要とする。
- `.env`はgit管理せず、`.env.example`だけを設定例として管理する。
- API responseやerror表示にAPIキー、内部stack trace、秘密情報を含めない。
- prompt全文と自由質問を通常ログへ出さない。
- canonical成功回答はローカルSQLへ保存を試みるが、APIキー、prompt全文、provider raw responseは保存しない。
- `create_app()`はDB初期化を行わず、通常起動時の`init_db()`はFastAPI lifespanから1回だけ呼ぶ。TestClientはcontext managerでlifespanを起動し、DBを直接使うunit testはfixtureで明示的に初期化する。
- SQLite / PostgreSQLのどちらでも同じ初期化責務とし、mock / live modeの既存境界を維持する。
- prompt assetはUTF-8でversion管理し、package buildにも含める。
- UIはOpenAI APIへ直接接続しない。
- 通信失敗とUI表示失敗を混同しない。

## 15. v1.4受け入れ条件

canonical個別銘柄経路は、次をすべて満たしたとき受け入れ可能とする。

1. activeな登録銘柄1件、非空質問、`STANDARD`を送ると、OpenAI Responses APIを1回だけ呼ぶ。
2. 実OpenAI APIでresponse ID、`completed` status、非空`output_text`を取得できる。
3. FastAPI経由で`request_id`、`status=success`、非空`answer_text`、銘柄snapshot、OpenAI response IDを取得できる。
4. browserで銘柄検索・選択、質問入力、送信、loading、answer表示が成立する。
5. modelは`gpt-5.6-terra`、presetは`STANDARD`、`reasoning.effort`と`text.verbosity`は`medium`のままである。
6. model選択とpreset定義が分離され、別modelへのfallbackがない。
7. 共通OS、共通入力の必要部分、no-tools実行制約、用途module 3.1がmanifest記載順で実requestへ入る。
8. 銘柄contextと自由質問が分離して合成される。
9. 用途module 3.2〜3.14、Web tool、Structured Outputs、JSON Schemaがrequestへ混入しない。
10. 未提供の価格、決算、technical、需給、市場、macro、eventを現在の事実として補完しないようpromptで制約する。
11. prompt version、asset、module、hashを追跡でき、prompt本文と質問はmetadata、公開response、browserへ出ない。
12. manifest不正、asset欠落、hash不一致で別promptへfallbackしない。
13. OpenAI error、timeout、未完了response、空回答をsuccessにしない。
14. `AUTHENTICATION_ERROR`、`MODEL_UNAVAILABLE`、`INVALID_API_PARAMETERS`、`RATE_LIMITED`、`TIMEOUT`、`NETWORK_ERROR`、`EMPTY_RESPONSE`、`UNKNOWN_OPENAI_ERROR`を区別する。
15. canonical経路でmock、cache、raw-response fallback、Web検索、JSON修復、再AI呼び出し、streaming、backgroundを使わない。
16. legacy portfolio endpoint、Prompt Registry、mode、mock、cache、historyの既存挙動を変更しない。
17. compiler、OpenAI client、FastAPI endpoint、最小UIのunit testが成功する。
18. 評価fixtureが指定された10観点を網羅し、人間がbefore / afterを比較できる。
19. 成功したcanonical回答が同じ`request_id`の`AiAnalysisRecord`としてローカルSQLへ保存される。
20. OpenAI成功後の保存失敗ではrollbackし、OpenAIを再呼び出さず、HTTP 200、`status=success`、非空`answer_text`、`persistence_status=failed`、`saved_at=null`、安全なwarningを返す。
21. `GET /api/ai/analyses/{request_id}`で保存済み回答を1件取得でき、存在しないIDをsuccess扱いしない。
22. `/ui/analysis`は保存成功時だけ大型表示導線と保存済み表示を出し、保存失敗時は回答本文とwarningだけを表示する。
23. 保存recordと公開responseへAPIキー、prompt全文、provider raw responseを含めない。
24. active prompt versionが`2026.08.18`、compilerが`individual-security-v2`で、共通OS、必要な共通入力rule、no-tools制約、module 3.1だけが実requestへ入り、根拠ラベルが`【V】`、`【E】`、`【U】`である。v18 source provenanceと`revision.base_source`のv17 provenanceを追跡できる。
25. OpenAI request kwargsに`store=false`が含まれ、`previous_response_id`とbackground modeがない。
26. APIの既定bindは`127.0.0.1`であり、`--host 0.0.0.0`を指定したときだけLAN到達可能になる。
27. 通常のFastAPI lifespan起動1回につき`init_db()`が1回だけ呼ばれ、`create_app()`自体はDB初期化を行わない。

## 16. v1.4の非対象

次はv1.4のcanonical個別銘柄経路へ実装しない。

- `LIGHT`、`HIGH`、`PRO`、`MAX` preset
- model選択UIとmodel切替
- 複数銘柄分析
- 市場全体分析
- 保有・監視銘柄と市場を組み合わせる総合分析
- 用途module 3.2〜3.14の投入
- Web検索
- J-Quants、EDINET、YouTube Data API、allowlist公式IR等の追加context統合
- Structured OutputsとJSON Schema
- JSON修復、parse retry、再AI呼び出し
- mock、cache、prompt cache
- background response、polling、streaming
- Markdown rendererと構造化card UI
- 回答内容または投資判断の自動採点
- 保存回答の一覧・検索・削除・export・共有
- 保存recordの保持期限設定と自動purge
- canonical画面/APIの認証・認可
- legacy portfolio AIの削除、廃止、統合、大規模refactor

## 17. 既知制約

- canonical endpointにはアプリ独自の認証、利用者分離、server-side rate limit、daily quota、TLS終端がない。runnerの既定bind hostは`127.0.0.1`で、ローカルPCからだけ接続できる。LAN確認時は利用者が明示的に`python scripts/run_api.py --host 0.0.0.0`を指定できるが、信頼できる閉じたLANだけで利用し、Internetへ直接公開しない。Android対応や外部公開の前に認証、HTTPS、rate limitを実装する。
- prompt manifestやasset構成異常はfail closedになるが、現行routeは`PromptConfigurationError`をtyped `AiAnalysisError`へ変換せず、HTTP 500になり得る。
- generated OpenAPIはcanonical endpointの200 / 422以外の実行時error responseをまだ宣言していない。
- canonical個別銘柄経路の入力dataは主に`security_master`の識別情報であり、現在価格や最新市場dataを持たない。そのため、具体的な売買判断より`insufficient_data`、`no_trade`、確認項目、条件付きscenarioが中心になり得る。
- 共通OSは広い観点と標準出力を要求するため、単純な質問でも回答が冗長になる可能性がある。
- canonical経路は成功回答をローカルSQLへ保存するが、一覧、検索、削除、export、共有、保持期限、自動purgeを持たない。保存recordへのアクセス制御も未実装である。
- OpenAI側のmodel利用権限、billing、quota、rate limit、network状態により実API確認が失敗し得る。失敗時は別modelやmockで成功扱いにしない。
- 評価fixtureは人間比較用であり、回答の投資判断としての正しさを保証または自動採点しない。
- FastAPIを介さないsmoke scriptはOpenAI APIそのものの疎通確認用であり、PromptCompiler、銘柄DB、canonical endpoint、browser UIの確認を代替しない。
- canonical経路とlegacy経路ではWeb、Structured Outputs、mock、cache、fallbackの方針が異なる。この差異はv1.4時点の意図的な責務分離である。
- 現行schemaは`security_code`の4〜10文字制約をtrim前に評価するため、空白でpaddingした短いcodeがtrim後4文字未満になってもvalidationを通る場合がある。UIはtrim済みの検索結果codeを送るが、server-side正規化後の長さ再検証は未実装である。

## 18. 文書内変更履歴

| version | 日付 | 概要 |
|---|---|---|
| v1.0 | 2026-04-22 | 日本株判断補助アプリの目的、基本機能、data source、live modeのno-mock方針を定義 |
| v1.1 | 2026-06-15 | legacy portfolio向けPrompt Registry / Prompt Builder、multi-mode AI、Web検索、Structured Outputs、mock、cache、history要件を追加 |
| v1.2 | 2026-08-17 | canonical個別銘柄AI最小縦スライス、固定`STANDARD`設定、versioned PromptCompiler、plain `output_text`、typed error、legacy経路との責務分離を追加 |
| v1.3 | 2026-08-17 | canonical成功回答のローカルSQL自動保存、UUIDによる1件取得、大型別ウィンドウ画面、prompt source v2026.08.17と銘柄名・コード併記規則を追加 |
| v1.4 | 2026-08-17 | OpenAI `store=false`、生成/保存結果の分離、保存失敗時の回答維持、loopback既定、lifespan-only DB初期化、active prompt 2026.08.18の正式根拠ラベルを追加 |
