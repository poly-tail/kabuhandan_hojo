# Changelog

## 2026-08-18 security search to portfolio input

- dashboardの検索案内を銘柄名・数字/英字コード対応へ改め、各結果へ`保有入力へ`と`詳細を見る`を追加した。
- `保有入力へ`は公開codeをPortfolio panelへprefillし、数量欄へfocusするだけで自動保存しない。quantityを必須、average costとnoteを任意とする既存保存contractを維持した。
- 英字5文字末尾`0`のJ-Quants raw identifierは、検索結果の表示とportfolio入力だけ公開4文字へ変換し、detail actionにはraw identifierを維持した。
- `PortfolioService`へ完全一致優先かつ一意な`<4文字>0` alias解決を追加し、公開`285A`を既存キオクシアmaster`285A0`へ紐付けてplaceholder重複を防ぐようにした。既存5文字入力は維持した。
- master primary key migrationとJ-Quants connector全体のcode canonical化は行っていない。
- 既存TDnet connectorの設定案内と揃えるため、`.env.example`へ空の`TDNET_API_KEY`と既定`TDNET_BASE_URL`を追加した。
- 要件 v1.6、API v1.9、画面 v2.1と`SC-2026-08-18-01`を追加し、旧版を変更せず現行baselineを更新した。

## 2026-08-17 legacy stock-review usage / quota / cost estimate

- legacy stock-reviewの`OPENAI_DAILY_REQUEST_LIMIT`既定値を50から300へ変更した。quotaは銘柄数ではなく正常完了したtop-level一括reviewの`review_runs`を使い、5銘柄一括scanも1回として扱う。
- provider Responses APIの`api_calls`をreview quotaから分離し、primary response、JSON整形repair、後段parseに失敗したresponseのusageを記録するようにした。mock、cache hit、prompt-only、limit拒否はreview/API countを増やさない。
- `app/services/ai_usage.py`とgit管理外`data/ai_review_usage_v2.json`を追加し、JST日別bucketから当日・当月のreview/API/token/実Web検索/概算額/未算定callを集計するようにした。atomic replace時の一時的なWindows `PermissionError`は短く再試行し、旧`ai_review_usage.json`はtest汚染の可能性があるため移行しない。
- pricing catalog `openai-standard-2026-08-17`へgpt-5.4 / gpt-5.5 / gpt-5.6-terraのstandard token rate、long-context multiplier、実Web検索USD 0.01/call、公式sourceを記録した。reasoning tokenはoutput内訳として二重加算せず、unknown modelやusage不整合は`unpriced_api_calls`へ記録する。
- `GET /api/ai/stock-review/usage`を追加し、scope、Asia/Tokyo、daily limit/remaining、today/month、pricing provenance、旧履歴不完全flagを`Cache-Control: no-store`で返すようにした。ledger/APIへprompt、質問、回答、APIキーを含めない。
- dashboardのlegacy Portfolio AI panelへ、本日/今月の成功review、OpenAI呼出数、残数、token由来概算、未算定/旧履歴注記を追加した。事前heuristicは「今回の事前概算」と区別し、`database`等のholdings sourceを利用者向け日本語labelへ変換した。
- unit testのusage/history/cacheを一時pathへ隔離し、repository local dataのcounter汚染を防止した。
- 要件 v1.5、API v1.8、画面 v2.0と`SC-2026-08-17-04`を現行baselineへ追加した。canonical `/api/ai/analyses`のmodel、STANDARD preset、保存、prompt、error契約は変更していない。

## 2026-08-17 canonical AI safety / persistence outcome / prompt v2026.08.18

- canonical `OpenAIResponsesClient`のResponses requestへ`store=false`を固定し、`previous_response_id`やbackgroundを追加せず単発stateless requestにした。これはResponses Application State保存の無効化であり、Zero Data Retention全体を保証しないことをREADMEと仕様へ記録した。
- OpenAI回答生成とローカルSQL保存の成否を分離し、成功responseへ`persistence_status`、`saved_at`、`persistence_warning`を追加した。commit失敗はrollbackするが、HTTP 200と生成済み本文を返し、OpenAIを再呼び出ししない。
- `/ui/analysis`は保存失敗でも回答本文とwarningを表示し、保存済み表示と大画面reader linkは保存成功時だけ表示するようにした。保存詳細GETは保存済みrecordだけを返す既存契約を維持した。
- runner、Settings、`.env.example`の既定bindを`127.0.0.1`へ変更し、Docker Composeのhost公開portもloopbackへ限定した。`--host 0.0.0.0`は信頼できる閉じたLANでの明示利用だけに残した。
- DB初期化をFastAPI lifespanの1回へ一元化し、`create_app()`からDB副作用を除いた。
- immutableなv2026.08.17 assetを残してactive bundle v2026.08.18を追加し、静的assetの旧括弧をfail closed、runtime値の旧括弧を正式な`【V】` / `【E】` / `【U】`へ正規化するcompiler v2へ更新した。
- 要件 v1.4、API v1.7、画面 v1.9と`SC-2026-08-17-03`を追加し、client、API、UI、startup、promptの回帰testを更新した。legacy portfolio AI経路は変更していない。

## 2026-08-17 canonical AI response persistence / large reader

- canonical `POST /api/ai/analyses` のcompletedかつ非空の成功回答だけを、新しいSQLAlchemy `ai_analysis_record`へ自動保存するようにした。既存のUUID `request_id`を保存IDとして再利用する。
- 質問、回答、銘柄snapshot、model / preset / reasoning / verbosity、OpenAI response ID、prompt version / asset / hashを保存し、APIキー、prompt全文、provider raw response / errorは保存しない。
- DB commit失敗はrollbackし、HTTP 500 `PERSISTENCE_ERROR`として扱う。未保存回答を成功にせず、legacy JSON履歴、mock、cacheへfallbackしない。
- `GET /api/ai/analyses/{request_id}` を追加し、保存済み回答1件をbrowser-safe schemaで返すようにした。未知UUIDは `ANALYSIS_NOT_FOUND`、invalid UUIDは422とし、responseは`Cache-Control: no-store`とした。
- `/ui/analysis` に保存済み表示と `別ウィンドウで大きく表示` リンクを追加し、`/ui/analysis/results/{request_id}` の最大幅1380px readerで質問・回答をプレーンテキスト再表示できるようにした。
- AI送信中は銘柄検索・選択と質問編集を無効化し、待機中に選択銘柄が変わって旧回答が別銘柄の下へ表示される競合を防止した。
- `/api/ai/analyses` 配下へmiddlewareで`Cache-Control: no-store`を付け、route handler前に生成されるFastAPI validation errorもcache対象外にした。
- 保存transaction、POST→GET、失敗時の非保存、reader shell、秘密非露出をunit testへ追加した。認証、回答一覧、削除、保持期限、暗号化、利用者分離は今回の対象外とした。

## 2026-08-17 individual-security prompt v2026.08.17

- 添付 `株判断プロジェクト｜定型プロンプト集 v2026.08.17` を新しいimmutable asset bundleとして追加し、manifestのsource / asset hashとprompt versionを更新した。v2026.08.16 assetは再現用に保持する。
- 共通OSの「銘柄名（銘柄コード）」併記規則と、共通入力の銘柄名・銘柄コード分離を反映した。3.1本文とno-tools制約は維持した。
- 共通OS、必要な共通入力、実行制約、module 3.1だけを引き続き使用し、3.2〜3.14、JSON Schema、Structured Outputs、Web検索を追加していない。
- 評価fixtureをv2026.08.17へ更新し、命名規則、asset version、他module / JSON Schema非混入を回帰テストで固定した。

## 2026-08-17 specification baseline v1.3 / v1.6 / v1.8

- 要件 v1.3、API v1.6、画面 v1.8を追加し、canonical成功回答の原子的なローカル保存、UUID詳細GET、大画面reader、prompt v2026.08.17を現行契約へ昇格した。
- `SC-2026-08-17-02` として変更理由、保存内容、秘密境界、legacy互換性、非対象、trusted-local制約を `docs/spec_change_history.md` へ記録した。
- 回答一覧APIは無認証状態で露出を広げるため追加せず、UUIDを知る利用者が1件を取得する最小契約に限定した。

## 2026-08-17 public repository bootstrap safety

- 公開リポジトリの初回作成に備え、`.gitignore`で`.env`系ファイル（空の`.env.example`を除く）、秘密鍵・証明書、ローカルDB、ログ、pytest一時領域、Python cache / `egg-info`を追跡対象外にした。
- APIキーやパスワードの実値を`.env`または実行環境のsecret storeだけで扱い、文書、ログ、テストfixture、browser responseへ記録しない運用をREADMEへ明記した。
- 初回commitとpushの前に、Git indexへstageされたファイルだけを対象として高確度secret、個人絶対path、credential入りURLを検査する手順を採用した。secret値は検査結果へ出力しない。

## 2026-08-17 specification baseline v1.2 / v1.5 / v1.7

- `docs/requirements/requirements_v1.2.md`、`docs/specs/api_spec_v1.5.md`、`docs/screen_specs/screen_spec_v1.7.md` を追加し、個別銘柄AI最小縦スライスと定型prompt最小統合をversioned仕様の正本へ昇格した。
- canonical `POST /api/ai/analyses` / `GET /ui/analysis` とlegacy `POST /api/ai/stock-review` の適用範囲を分離し、新経路ではmock、cache、fallback、Web検索、Structured Outputs、JSON修復を使わないことを明記した。
- `docs/spec_change_history.md` を追加し、要件・API・画面の版対応、変更理由、互換性、非対象、既知制約を横断して追跡できるようにした。
- 既知制約として、新endpointの認証・アプリ側rate limit・TLS・永続audit未実装、OpenAPI error response宣言不足、prompt構成異常のuntyped HTTP 500、`security_code`のtrim後length再検証不足を記録した。
- `current.md` 3件、screen map / invariants / change request / UI principles、context、project guide、README、source overview、folder structure、docs templateを現行baselineへ同期した。コードと旧版文書は変更していない。

## 2026-08-17 individual-security prompt assets / compiler

- 添付 `株判断プロジェクト｜定型プロンプト集 v2026.08.16` から「1. 株判断共通OS」全文と「3.1 総合的な個別銘柄分析」だけをversioned Markdown assetとして追加した。3.2〜3.14、JSON Schema、人間向け重複templateは統合していない。
- `app/prompts/individual_security/` にmanifestと`IndividualSecurityPromptCompiler`を追加し、共通OS、共通入力ルール、Web・外部市場データなし制約、3.1 module、`security_master` context、自由質問を分離して合成するようにした。
- prompt version、使用asset、module、source/compiled SHA-256をOpenAI response metadataへ記録し、prompt全文・質問はmetadata、公開FastAPI response、browserへ出さない構成にした。
- `OpenAIResponsesClient` は静的規則を`instructions`、実行時contextを`input`として送るよう拡張した。model、STANDARD preset、reasoning effort、text verbosity、timeout、`response.output_text`検証は変更していない。
- 代表質問10件のfixtureとCompiler unit testを追加し、他13 moduleの固有文、Structured Outputs指示、Web toolが混入しないことを固定した。
- 旧portfolio AI経路は変更せず、新縦スライスにもmock、cache、fallback、Web検索、JSON修復、再AI呼び出しを追加していない。

## 2026-08-17 minimal AI vertical slice

- `POST /api/ai/analyses` と `GET /ui/analysis` を追加し、登録済み個別銘柄1件、自由質問、`STANDARD`、OpenAI Responses API、プレーンテキスト回答表示を単一路で接続した。
- 固定モデル `gpt-5.6-terra` と回答品質presetを分離し、`STANDARD` は `reasoning.effort=medium`、`text.verbosity=medium` とした。
- 独立OpenAI clientにtimeout、completed status、response ID、空回答の検証と、認証・モデル・パラメータ・rate limit・timeout・network・空回答・unknownのエラー分類を追加した。
- この経路にはmock、cache、fallback、Web検索、Structured Outputs、background、streamingを追加せず、OpenAI失敗をsuccessへ変換しない。
- FastAPIを介さない `scripts/smoke_openai_response.py` と、client / endpoint / UI shellのunit testを追加した。

## 2026-06-25 long-term non-monitoring carry risk

- Prompt Registry に `【5.5. 中長期持ち越し・非監視期間リスク】` を追加し、毎日相場を見られない前提で数日〜数週間以上保有できるかを評価する章を modeProfiles に組み込んだ。
- Structured Outputs / JSON Schema と `PortfolioAiStockAnalysis` に `long_term_carry_check`、`non_monitoring_hold_risk`、`needs_long_term_carry_check` を追加した。`scanner` は簡易判定、`analyst` / `judge` / `critical` は詳細判定を返す。
- dashboard のAI分析カードに「中長期持ち越し・非監視期間リスク」表示を追加し、警告 chip、日本語ラベル、必要アラート、確認イベント、期間別保有可否、最終判断を表示するようにした。
- 追加判定は翌営業日のギャップ要因を見る `event_carry_check` とは別物として扱い、既存の持ち越しイベント判定と混同しない。

## 2026-06-15 stock AI Prompt Registry / Builder

- `app/prompts/stock_analysis/` を追加し、ユーザー指定の株式分析プロンプト全文、Base Policy、analysisSections、modeProfiles、mode別outputSchemas、costControl、webSearchPolicyを分離した。
- `prompt_only` は Prompt Registry の全文を使い、OpenAI APIを呼ばずChatGPT手動投入用プロンプトを生成する。API実行時はmodeProfilesに応じた章だけをPrompt Builderで差し込む。
- `POST /api/ai/stock-review` は `target=candidates`、`candidates`、`user_hypothesis`、`position_intent`、`web_search_policy`、`input_summary`、`market_summary`、`action_plan`、`critical_warnings`、`candidates_snapshot` を扱えるようにした。
- `analyst` / `judge` / `critical` はWeb検索ONを標準にし、`scanner` のWeb検索OFF時は「最新Web確認なし」のwarningを返す。`prompt_only` はAPI検索を行わない。
- dashboard のAI分析パネルに狙い中銘柄、ユーザー仮説、建玉意図、sources、具体的な執行案、反証条件、辛口チェック表示を追加した。
- `.env.example` に `OPENAI_DEFAULT_VERBOSITY` と `OPENAI_CRITICAL_CONFIRMATION_REQUIRED` を追加し、`OPENAI_ENABLE_WEB_SEARCH=true`、`OPENAI_MAX_WEB_SEARCH_CALLS=5` を既定例にした。
- `tests/unit/test_stock_analysis_prompt_builder.py` を追加し、mode別章選択、prompt_only全文生成、Web検索warning、validation warningを固定した。
- `docs/requirements/requirements_v1.1.md`、`docs/specs/api_spec_v1.4.md`、`docs/screen_specs/screen_spec_v1.6.md` を追加し、要件定義、API仕様、画面仕様に今回のAI分析仕様変更を反映した。
- JSON parseとJSON整形リトライの両方に失敗しても、OpenAIから分析本文らしき応答が返っている場合は `raw_model_output` を成功レスポンスとしてUI表示するfallbackを追加した。
- `target=mock`、`use_mock_holdings=true`、mock fallbackではOpenAI APIを呼ばず、常にローカルmock応答を返すようにした。UI上もmock対象の推定コストを0にし、Web検索をOFFにする。

## 2026-06-15 multi-mode stock AI review

- `POST /api/ai/stock-review` を追加し、`scanner` / `analyst` / `judge` / `critical` / `prompt_only` のAI分析モードを扱えるようにした。
- 既存の `POST /portfolio/ai-review` と `POST /api/portfolio/ai-review` は互換入口として残し、同じ multi-mode service に接続した。
- `OPENAI_MODEL_SCANNER` / `OPENAI_MODEL_ANALYST` / `OPENAI_MODEL_JUDGE` / `OPENAI_MODEL_CRITICAL` と対応する `OPENAI_REASONING_*`、Web検索・銘柄数・日次上限の環境変数を追加した。
- `app/services/portfolio_ai_review.py` に target 解決、market snapshot抽象化、mode別prompt、Structured Outputs用JSON Schema、JSON parse fallback、推定コスト、同一入力キャッシュ、ローカル履歴保存、日次実行カウントを追加した。
- dashboard のAI分析パネルを5モード/対象選択/推定コスト/結果保存/前回結果/ChatGPT投入用プロンプト生成に更新した。ChatGPT Web画面のDOM操作、自動投稿、回答スクレイピングは実装していない。
- mock holdings を7件のテスト用銘柄へ更新し、実DB保有銘柄がある場合は引き続き実DBを優先する。
- `tests/unit/test_portfolio_ai_review.py` に `prompt_only`、新API、用途別model/reasoning、Web検索回数上限のテストを追加した。

## 2026-05-25 user-facing PDF docs

- `docs/user/` に、利用者向けの「株判断補助アプリ ユーザー向け仕様書」と「株判断補助アプリ 取扱説明書」のHTML原稿を追加。
- PDF版として `docs/user/user_spec_2026-05-25.pdf` と `docs/user/user_manual_2026-05-25.pdf` を生成できる構成にした。
- AI分析の「最新ニュースも検索（OpenAI API使用）」と「APIなしのサンプル表示（課金なし）」の違い、OpenAI Platformのbilling / quota確認、サンプル表示時は実分析ではないことをユーザー向けに明記。

## 2026-05-23 portfolio AI review MVP

- `POST /portfolio/ai-review` と互換用 `POST /api/portfolio/ai-review` を追加し、保有銘柄を一括でOpenAI Responses APIへ渡すMVPを実装
- `OPENAI_API_KEY` / `OPENAI_MODEL` をサーバー側設定に追加し、APIキー未設定、OpenAI SDK未導入、JSON parse失敗をUI向けJSON状態で返すようにした
- `OPENAI_REASONING_EFFORT=high` を追加し、AIレビューのResponses API呼び出しへ `reasoning.effort` を明示指定するようにした
- OpenAI API の `web_search` と Structured Outputs が同時利用できない制約に合わせ、Web検索ありでは構造化出力指定を外してJSON文字列parseへフォールバックするようにした
- OpenAI API の 429 insufficient_quota / 401 / 404 / 400 を画面向けの具体的なエラーメッセージに分けた
- AI分析のチェックボックス表記を `最新ニュースも検索（OpenAI API使用）` と `APIなしのサンプル表示（課金なし）` に変更し、READMEに課金有無とmock動作を追記
- DB保有銘柄を優先し、テスト用mock holdings、mock market snapshot、OpenAI APIを呼ばない `mock_response` を追加
- dashboard Portfolio パネルに `保有銘柄を一括AI分析` と `テスト用仮保有銘柄で分析`、分析カード表示、Web検索なし簡易分析の状態表示を追加
- dashboard Watchlist パネルにチェック選択、全選択/選択解除、`選択ウォッチリストをAI分析` を追加し、選択銘柄を既存AIレビューAPIで分析できるようにした
- `.env.example`、依存関係、README、source overview / folder structure / call graph、unit test を更新

## 2026-04-26 detail reference link fix

- detail 画面の `reference_links` に Yahoo!ファイナンスの手動確認リンクを復旧し、公式IRと最新開示ソースも同時に残るよう優先順を調整した
- J-Quants は基幹データソースとして使う一方、detail の主要参照先リンクには出さない扱いをテストで固定した

## 2026-04-23 J-Quants V2 master sync addendum

- J-Quants 銘柄マスタ同期を V2 `/equities/master` 優先に修正し、V2 の `CoName` / `MktNm` / `S17Nm` / `S33Nm` 形式を `security_master` に取り込めるようにした
- dashboard の `銘柄DB更新` は `require_jquants=true` で全上場銘柄取得を必須にし、`JQUANTS_API_KEY` 未設定時に 36 件のローカルCSVだけで成功表示しないようにした

## 2026-04-24 env loading addendum

- `app/core/config.py` と `src/kabuhandan_hojo/core/config.py` の `.env` 読み込み位置を repo ルート固定にした
- `scripts/run_api.py` は起動時に repo ルートへ移動するようにし、`scripts/` ディレクトリから起動しても `.env` と `data/` を見失わないようにした
- J-Quants の価格・需給 connector で 429 などの HTTP エラーを `ConnectorError` として返すようにし、UI で `500 Internal Server Error` ではなく具体的な失敗理由を表示できるようにした
- dashboard 読み込み時の市場proxy auto-sync をやめ、`市場価格更新` ボタンからだけ `1306` / `1321` を取得するようにした。lookback は 60 日へ縮め、429 の説明文も UI に追加した

## 2026-04-23 manual refresh addendum

- dashboard の global 手動更新パネルをやめ、Market / Portfolio / Watchlist / Alerts / Materials / Screening / Search の各セクション内に手動更新ボタンを分散した
- detail / chart 画面は選択銘柄のまとめ更新パネルをやめ、Factor Split / Materials / Technical / Flow / Score / Chart の各カード内に該当データの更新ボタンを配置した
- 手動更新で API エラーになった場合、押したボタンのセクション内に失敗理由を表示するようにした。0 件取得は価格・信用需給など必須データだけエラー扱いにし、EDINET / TDnet / YouTube の対象なしは正常終了に分けた
- `POST /documents/sync/youtube/monitored` を追加し、`YOUTUBE_MONITORED_CHANNELS` 設定済みチャンネルを銘柄単位で同期できるようにした

## 2026-04-23 local master addendum

- `data/security_master_jp.csv` と `app/services/security_master_catalog.py` を追加し、銘柄コードと日本語銘柄名をローカルで検索できるようにした
- `POST /securities/master/sync` をローカルCSV同期 + 任意の J-Quants listed master 同期に変更した
- dashboard に `銘柄DB更新` と `市場価格更新` の手動ボタンを追加した
- `3563` はローカルマスタで `ＦＯＯＤ　＆　ＬＩＦＥ　ＣＯＭＰＡＮＩＥＳ` として検索され、未知コード placeholder にはしないようにした

## 2026-04-23 YouTube / IR addendum

- YouTube Data API connector と `POST /documents/sync/youtube` を追加し、channel observation を raw document / event / video_item に同期できるようにした
- `POST /documents/import/ir` を追加し、allowlist domain の公式 IR URL を event 化できるようにした

## 2026-04-23 addendum

- J-Quants listed master 同期 job (`POST /securities/master/sync`) を追加し、銘柄検索を DB-only 前提へ寄せた
- portfolio panel を `portfolio_holding` ベースへ切り替え、`/portfolio` API と dashboard 手入力フォームを追加した
- J-Quants margin data からの `flow_snapshot` 同期 (`POST /securities/{ticker_code}/flow/sync`) と detail 自動補完を追加した
- TDnet official API connector と `POST /documents/sync/tdnet` を追加し、detail では当日分の自動同期も試行するようにした
- sector pulse / factor split の sector 比較を watchlist 内比較から market-wide breadth 集計へ更新した

## 2026-04-23

- J-Quants の日足 connector で 4 桁/5 桁コード差分を吸収する retry を追加
- `TOPIX(1306)` / `Nikkei225(1321)` の market proxy と live price sync が raw API 側の code 表記差分で空振りしにくいよう調整
- `tests/unit/test_jquants_connector.py` を追加し、4 桁コードから 5 桁コードへの再試行を固定
- 任意の 4 桁コードを銘柄検索で placeholder 表示しないよう修正
- 未知の `ticker_code` を detail 画面で開いたとき、別の watchlist 銘柄へフォールバックしないよう修正

## 2026-04-22

- docs 全体の文字化けを解消し、`README`、`information_sources`、spec、screen spec、analysis メモを現行実装に合わせて日本語で再記述
- `current.md` の表現を読みやすい日本語へ改め、同期スクリプト側も追従できる前提へ整理

## 2026-04-21

- live mode の UI で mock 補完を廃止
- `price_chart` が空の場合、J-Quants 日足同期を 1 回試す挙動を追加
- それでも取れない項目は `未取得` または空表示に変更
- `market_overview`、`market_headwind`、`factor_split.market` を J-Quants の `TOPIX(1306)` / `Nikkei225(1321)` proxy ベースへ更新
- chart detail を 20日 / 40日 / 全期間切替、MA overlay、RSI / MACD 補助表示付きへ強化
- top 画面の `保有銘柄更新` の dead-end button を撤去
- search panel の下に、watchlist 未登録の高スコア候補を表示
- dashboard から個別銘柄ページを新しいタブで開く挙動へ変更

## 2026-04-20

- `/ui/dashboard`、`/ui/security/{ticker_code}`、`/ui/security/{ticker_code}/chart` の 3 画面構成を追加
- `GET /ui/dashboard/data` を view model API として追加
- 個別銘柄 detail に仮説メモ、factor split、材料履歴、参考リンクを追加
- 情報源ドキュメントを更新し、TDnet、株探、みんかぶ、日経、Reuters、Bloomberg、SBI証券、楽天証券、X、StockTwits を手動参照スタックとして整理
- TDnet / EDINET の役割分担メモと backlog 文書を追加
