"""Prompt registry and builder for stock analysis requests."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
import json
from typing import Any, Literal
from zoneinfo import ZoneInfo

from app.prompts.stock_analysis.user_stock_analysis_prompt_full import USER_STOCK_ANALYSIS_PROMPT_FULL


TOKYO_TIMEZONE = ZoneInfo("Asia/Tokyo")

AiReviewMode = Literal["scanner", "analyst", "judge", "critical", "prompt_only"]
WebSearchPolicy = Literal["optional", "required", "strongly_recommended", "manual_only"]


BASE_POLICY_PROMPT = """Base Policy:
- このアプリ内または過去会話のメモリに依存しない。
- 今回入力された情報、アプリ側で渡された保有情報、マーケットデータ、必要に応じてWeb確認した最新情報だけを根拠にする。
- 形式的な免責文を長々と出さず、判断材料、反証条件、リスク、代替案、執行条件を具体化する。
- 断定できないことは断定しない。
- 時事性のある情報はWebまたはアプリ側の最新取得データで確認する。
- 可能な限り一次情報を優先し、会社IR、決算短信、決算説明資料、適時開示、取引所、公式統計、企業発表を重視する。
- ニュース、SNS、YouTube、個人投資家情報は補助情報として扱う。
- ソース間に矛盾がある場合は、日付、一次情報性、前提差を明示する。
- Web確認できない情報、チャート画像だけでは分からない情報、推定情報は不確実性を明示する。
- 情報不足でも質問で止めず、現在分かる範囲で仮説を置いて分析し、不足情報を最後に列挙する。
- 短期売買判断と中長期保有判断を混同しない。
- 短期玉、中期玉、長期玉、コア玉、追加玉を分ける。
- 銘柄単体の魅力度だけでなく、ポートフォリオ全体の資金効率、集中リスク、入れ替え候補を考慮する。
- 重要主張の末尾に検証ラベルを付ける: 【V】Webまたは確認可能情報、【V｜一次情報】会社IR/取引所/公式資料、【V｜複数ソース】複数独立情報源、【E】推定・分析判断、【U】未確認。
"""


ANALYSIS_SECTIONS: dict[str, str] = {
    "0": "【0. 入力情報の整理】対象銘柄、証券コード、市場、現在値、保有株数、取得単価、含み損益、短期玉/中期玉/長期玉、追加余力、狙い中銘柄、ユーザー仮説、判断してほしいことを整理する。入力にない項目は「未入力」と明示する。",
    "1": "【1. 結論】超短期、短期、中期、長期の時間軸ごとに、買い/追加買い/保有/一部利確/全部売り/様子見/監視継続/空売り候補を明確にする。今すぐ動くか、条件到達まで待つか、引けまで待つか、短期玉と中長期玉を分けるか、反証条件を出す。",
    "2_summary": "【2. 全体市況 要約】日経平均、TOPIX、米国株、SOX/NASDAQ、金利、為替、VIX、重要イベントを追い風/中立/逆風で短く判定する。",
    "2": "【2. 全体市況】日経平均、TOPIX、グロース市場、NASDAQ、S&P500、SOX、米10年金利、ドル円、VIX、日経先物/CME/米国先物、海外投資家動向、SQ/日銀/FOMC/CPI/雇用統計/NVIDIA決算などの重要イベント、地政学/政策/関税/規制/為替急変を確認し、個別テクニカルを信じてよい地合いかを判定する。",
    "3_summary": "【3. テーマ・セクター 要約】テーマ資金、同業比較、個別材料/地合い/テーマ連動、過熱、持続性を短く確認する。",
    "3": "【3. テーマ・セクター】AI、半導体、データセンター、防衛、外食、ゲーム、サイバーセキュリティ、内需、輸出、円安/円高メリット、金利上昇/低下メリット、インバウンド、ロボット、電力、インフラなど関連テーマを確認し、資金流入、同業比較、個別材料か地合い連動か、過熱、業績に落ちる構造的テーマかを評価する。",
    "4": "【4. 個別材料・ファンダメンタル】直近決算、通期見通し、上方/下方修正、売上、営業利益、経常利益、純利益、EPS、利益率、セグメント、受注、月次、KPI、進捗率、コンセンサス、アナリスト評価、PER/PBR/PSR/EV/EBITDA/PEG、配当、自社株買い、株主還元、イベント、材料織り込みを確認する。",
    "5": "【5. 中長期投資仮説】3か月、6か月、1年、2〜3年の期待値、構造的成長、一時テーマか業績に落ちるテーマか、売上/利益/EPS/CF/ROE/ROIC/財務/競争優位/市場成長/経営陣/IR/再評価カタリストを評価し、短期テクニカルと中長期ファンダが食い違う場合は分けて判断する。",
    "5.5_short": "【5.5. 中長期持ち越し・非監視期間リスク 簡易版】毎日相場を見られない前提で、対象銘柄が短期売買向きか、数日〜数週間見られなくても持てるか、毎日監視できないなら危険かを短く判定する。scanner modeでは non_monitoring_hold_risk を low/medium/high/unknown、needs_long_term_carry_check を boolean で返し、毎日見られないなら危険な銘柄を抽出する。",
    "5.5": "【5.5. 中長期持ち越し・非監視期間リスク】ユーザーは毎日相場を見られるとは限らない。短期チャート判断とは別に、数日〜数週間、場合によっては1か月以上見られない前提で持ち越してよいかを必ず評価する。毎日見られる短期売買向き、数日保有可、1〜2週間保有可、1〜3か月保有可、決算や重要イベント前だけ確認すればよい、毎日監視できないなら不向き、に分類する。事業仮説の強さ、売上/利益/EPS/営業利益率/営業CF/FCF/財務安全性、構造テーマが業績に落ちているか、一時テーマ株ではないか、勢いだけの中長期保有になっていないかを確認する。非監視期間に起き得る決算、月次、ガイダンス修正、受注、重要IR、大型イベント、米国関連株決算、マクロ、金利/為替、規制/政策、セクター急落、信用需給悪化、機関空売り増加、流動性低下を確認する。現在サイズ、含み益/含み損の許容、1営業日/3営業日/1〜2週間の想定損失、決算跨ぎ放置可否、逆指値/アラート/サイズ縮小/コア玉だけ残す条件を出す。中長期で持ってよい条件、コア玉/短期玉/追加玉/イベント前縮小/決算前見直し/価格割れ再点検/機械的縮小/継続自信上昇/中長期対象外条件を明確化する。最終判断は long_term_hold_ok=中長期持ち越し可 / hold_if_reduced=サイズ縮小なら持ち越し可 / hold_with_alerts=アラート必須で持ち越し可 / reduce_before_event=イベント前に縮小 / not_suitable_without_daily_monitoring=毎日見られないなら非推奨 / exit_or_rotate_candidate=撤退/入れ替え候補 / unknown=不明 のいずれかに分類する。この章は翌営業日のギャップ要因を見る持ち越しイベント判定とは別物として扱う。",
    "6": "【6. 需給】出来高、出来高移動平均、信用倍率、信用買残、信用売残、信用残÷出来高、空売り残高、機関空売り、大口動向、利確売り、投げ売り、踏み上げ余地、現物主導/信用買い主導/買い戻し主導、決算後/材料後/急騰後の需給悪化を確認する。信用倍率だけで判断せず出来高対比で消化負荷を見る。",
    "7": "【7. テクニカル】月足/週足/日足/15分足/5分足、5/25/75/200日線、移動平均の傾き、株価位置、高値安値、VWAP、RSI、ボリンジャー、ATR、支持抵抗、価格帯別出来高、ローソク足、チャートパターン、窓を確認する。高値安値とヒゲを先に見て、終値/出来高/VWAP維持でブレイクを確認する。",
    "8": "【8. 建玉・ポートフォリオ影響】既存保有との相関、テーマ/セクター集中、追加買い時の資金拘束、資金効率、現金余力、他銘柄を減らして入るべきか、コア玉と短期追加玉、決算跨ぎ玉、損益・税金・心理バイアス、ポートフォリオ全体の期待値を確認する。",
    "9": "【9. 総合判断】全体市況、テーマ、個別材料、中長期投資仮説、需給、テクニカル、建玉/資金効率、イベントリスク、総合判断を統合し、短期で攻める価値、中期で持つ価値、長期で分割買い対象か、押し目/高値ブレイク/利確/損切り/保有/入れ替えを明確にする。",
    "10": "【10. 具体的な執行案】今すぐ買う/売るか、引け/翌営業日まで待つか、指値/逆指値/成行、買い候補価格、撤退候補価格、押し目買い候補、VWAP、直近高値安値、25/75/200日線、窓、支持抵抗線、ATR、一括か分割か、短期玉と中長期玉の損切り/利確条件、決算前後の扱い、逆指値位置を具体化する。",
    "11": "【11. 反証条件・失敗シナリオ】短期判断の反証条件と中長期投資仮説の反証条件を必ず出す。価格、出来高、ローソク足、VWAP、高値更新失敗、窓、持ち合い失敗、売上/利益率/EPS/会社計画/受注/月次/競争優位/市場成長/バリュエーション/テーマ/経営陣/財務/還元悪化を分ける。",
    "12": "【12. シナリオ分析】強気・中立・弱気の3シナリオを、短期強気/短期弱気/中長期強気/中長期弱気に分け、条件、想定株価反応、取るべき行動を出す。",
    "13_short": "【13. 最終アクション 短縮版】今やるべきこと、今やらない方がよいこと、次に確認すべき情報、自信度、最大リスク、最大の反証条件を短く出す。",
    "13": "【13. 最終アクション】現時点の推奨行動、超短期/短期/中期/長期判断、短期玉/中期玉/長期玉/コア玉/追加玉、新規買い条件、追加買い条件、利確条件、損切り/撤退条件、中長期投資仮説、仮説が崩れる条件、決算・イベント跨ぎ判断、入れ替え候補、次に確認すべき情報、自信度、最大の短期/中長期リスク、最大の反証条件をまとめる。最後に「今やるべきこと」「今やらない方がよいこと」を明確に書く。",
    "14_short": "【14. 辛口チェック 短縮版】高値掴み、損切り条件不明、テーマ集中、需給軽視、決算跨ぎ軽視、短期反発狙いの中長期化などを短く指摘する。",
    "14": "【14. 辛口チェック】短期反発狙いを中長期投資のふりにしていないか、長期で良い銘柄だから短期高値掴みを正当化していないか、含み損正当化、テーマ偏重、信用需給軽視、決算跨ぎ軽視、飛び乗り、損切り条件不明、テーマ集中、資金拘束軽視、チャートパターン決め打ち、窓埋めや三角持ち合いの都合よい解釈を忖度なく指摘する。",
}

WEB_SEARCH_SOURCE_PRIORITY = [
    "会社IR",
    "決算短信",
    "決算説明資料",
    "適時開示",
    "取引所",
    "公式統計",
    "企業発表",
    "証券会社レポート・アナリスト評価",
    "信頼できるニュース",
    "SNS、YouTube、個人投資家情報は補助扱い",
]

RISK_LEVELS = ["low", "medium", "high", "unknown"]
JUDGEMENT_CODES = [
    "hold",
    "buy_more_candidate",
    "take_profit_candidate",
    "reduce_risk",
    "watch",
    "avoid_new_buy",
    "urgent_review",
]
BUSINESS_THESIS_STRENGTHS = ["strong", "normal", "weak", "unknown"]
HOLD_WITHOUT_DAILY_MONITORING_DECISIONS = [
    "yes",
    "with_reduction",
    "with_alerts",
    "before_event_reduce",
    "no",
    "unknown",
]
CORE_POSITION_SUITABILITY_LEVELS = ["high", "medium", "low", "unknown"]
MONITORING_INTERVALS = ["1_business_day", "3_business_days", "1_week", "2_weeks", "1_month_or_more"]
MONITORING_HOLDABILITY_LEVELS = ["ok", "with_alerts", "with_reduction", "not_recommended", "unknown"]
FINAL_LONG_TERM_CARRY_DECISIONS = [
    "long_term_hold_ok",
    "hold_if_reduced",
    "hold_with_alerts",
    "reduce_before_event",
    "not_suitable_without_daily_monitoring",
    "exit_or_rotate_candidate",
    "unknown",
]


@dataclass(frozen=True)
class ModeProfile:
    mode: AiReviewMode
    section_ids: tuple[str, ...]
    web_search_policy: WebSearchPolicy
    default_include_web_search: bool
    verbosity: str
    notes: tuple[str, ...] = ()


MODE_PROFILES: dict[AiReviewMode, ModeProfile] = {
    "scanner": ModeProfile(
        mode="scanner",
        section_ids=("0", "1", "2_summary", "3_summary", "5.5_short", "9", "13_short", "14_short"),
        web_search_policy="optional",
        default_include_web_search=False,
        verbosity="short",
        notes=("複数銘柄を軽量分類し、毎日見られないなら危険な銘柄を抽出する。",),
    ),
    "analyst": ModeProfile(
        mode="analyst",
        section_ids=("0", "1", "2", "3", "4", "5", "5.5", "6", "7", "8", "9", "10", "11", "12", "13", "14"),
        web_search_policy="required",
        default_include_web_search=True,
        verbosity="detailed",
        notes=("個別銘柄では中長期持ち越し可否を必ず返し、短期玉/中期玉/長期玉/コア玉/追加玉を分ける。",),
    ),
    "judge": ModeProfile(
        mode="judge",
        section_ids=("0", "1", "2", "3", "5", "5.5", "8", "9", "10", "11", "12", "13", "14"),
        web_search_policy="required",
        default_include_web_search=True,
        verbosity="normal",
        notes=("毎日監視できない前提で、縮小すべき銘柄、コア玉として残せる銘柄、入れ替え候補を比較する。",),
    ),
    "critical": ModeProfile(
        mode="critical",
        section_ids=("0", "1", "2", "3", "4", "5", "5.5", "6", "7", "8", "9", "10", "11", "12", "13", "14"),
        web_search_policy="strongly_recommended",
        default_include_web_search=True,
        verbosity="detailed",
        notes=("決算跨ぎ、大型ポジション、急騰急落では非監視期間リスクを重く評価する。",),
    ),
    "prompt_only": ModeProfile(
        mode="prompt_only",
        section_ids=tuple(section_id for section_id in ANALYSIS_SECTIONS if section_id != "5.5_short"),
        web_search_policy="manual_only",
        default_include_web_search=False,
        verbosity="full",
        notes=("OpenAI APIは呼ばず、ChatGPTへ手動投入するため全文プロンプトを使う。",),
    ),
}


def get_base_policy_prompt() -> str:
    return BASE_POLICY_PROMPT


def get_full_user_stock_analysis_prompt() -> str:
    return USER_STOCK_ANALYSIS_PROMPT_FULL


def get_mode_profile(mode: AiReviewMode) -> ModeProfile:
    return MODE_PROFILES[mode]


def _long_term_carry_check_schema() -> dict[str, Any]:
    return {
        "type": "object",
        "properties": {
            "can_hold_without_daily_monitoring": {
                "type": "string",
                "enum": HOLD_WITHOUT_DAILY_MONITORING_DECISIONS,
            },
            "non_monitoring_hold_risk": {"type": "string", "enum": RISK_LEVELS},
            "business_thesis_strength": {"type": "string", "enum": BUSINESS_THESIS_STRENGTHS},
            "event_risk_while_unmonitored": {"type": "string", "enum": RISK_LEVELS},
            "liquidity_risk": {"type": "string", "enum": RISK_LEVELS},
            "volatility_risk": {"type": "string", "enum": RISK_LEVELS},
            "position_size_view": {"type": "string"},
            "core_position_suitability": {"type": "string", "enum": CORE_POSITION_SUITABILITY_LEVELS},
            "short_term_position_should_be_removed": {
                "anyOf": [{"type": "boolean"}, {"type": "null"}],
            },
            "required_alerts": {"type": "array", "items": {"type": "string"}},
            "must_check_dates_or_events": {"type": "array", "items": {"type": "string"}},
            "reduce_before_events": {"type": "array", "items": {"type": "string"}},
            "stop_or_reduce_conditions": {"type": "array", "items": {"type": "string"}},
            "long_term_thesis_break_conditions": {"type": "array", "items": {"type": "string"}},
            "monitoring_interval_view": {
                "type": "array",
                "items": {
                    "type": "object",
                    "properties": {
                        "interval": {"type": "string", "enum": MONITORING_INTERVALS},
                        "holdability": {"type": "string", "enum": MONITORING_HOLDABILITY_LEVELS},
                        "required_conditions": {"type": "array", "items": {"type": "string"}},
                        "pre_actions": {"type": "array", "items": {"type": "string"}},
                    },
                    "required": ["interval", "holdability", "required_conditions", "pre_actions"],
                    "additionalProperties": False,
                },
            },
            "final_long_term_carry_decision": {
                "type": "string",
                "enum": FINAL_LONG_TERM_CARRY_DECISIONS,
            },
            "final_note": {"type": "string"},
        },
        "required": [
            "can_hold_without_daily_monitoring",
            "non_monitoring_hold_risk",
            "business_thesis_strength",
            "event_risk_while_unmonitored",
            "liquidity_risk",
            "volatility_risk",
            "position_size_view",
            "core_position_suitability",
            "short_term_position_should_be_removed",
            "required_alerts",
            "must_check_dates_or_events",
            "reduce_before_events",
            "stop_or_reduce_conditions",
            "long_term_thesis_break_conditions",
            "monitoring_interval_view",
            "final_long_term_carry_decision",
            "final_note",
        ],
        "additionalProperties": False,
    }


def get_output_schema_for_mode(mode: AiReviewMode) -> dict[str, Any]:
    stock_properties: dict[str, Any] = {
        "ticker": {"type": "string"},
        "name": {"type": "string"},
        "judgement": {"type": "string", "enum": JUDGEMENT_CODES},
        "judgement_label": {"type": "string"},
        "confidence": {"type": "number"},
        "time_horizon_views": {
            "type": "object",
            "properties": {
                "very_short": {"type": "string"},
                "short": {"type": "string"},
                "mid": {"type": "string"},
                "long": {"type": "string"},
            },
            "additionalProperties": True,
        },
        "short_reason": {"type": "string"},
        "key_risks": {"type": "array", "items": {"type": "string"}},
        "invalidation": {"type": "string"},
        "needs_analyst_mode": {"type": "boolean"},
        "needs_judge_mode": {"type": "boolean"},
        "needs_long_term_carry_check": {"type": "boolean"},
        "non_monitoring_hold_risk": {"type": "string", "enum": RISK_LEVELS},
        "long_term_carry_check": _long_term_carry_check_schema(),
        "verification_labels": {"type": "array", "items": {"type": "string"}},
        "watch_points": {"type": "array", "items": {"type": "string"}},
        "risk_flags": {"type": "array", "items": {"type": "string"}},
        "needs_detail_analysis": {"type": "boolean"},
        "key_points": {"type": "array", "items": {"type": "string"}},
        "technical_view": {"type": "string"},
        "news_view": {"type": "string"},
        "market_context_view": {"type": "string"},
        "supply_demand_view": {"type": "string"},
        "holder_action": {"type": "string"},
        "buy_more_condition": {"type": "string"},
        "take_profit_condition": {"type": "string"},
        "stop_or_reduce_condition": {"type": "string"},
        "next_price_levels": {"type": "array", "items": {"type": "string"}},
        "risks": {"type": "array", "items": {"type": "string"}},
        "bullish_case": {"type": "string"},
        "bearish_case": {"type": "string"},
        "base_case": {"type": "string"},
        "expected_value_view": {"type": "string"},
        "position_size_risk": {"type": "string"},
        "event_risk": {"type": "string"},
        "gap_risk": {"type": "string"},
        "decision_deadline": {"type": "string"},
        "what_would_change_my_mind": {"type": "string"},
        "final_recommendation_for_holder": {"type": "string"},
        "uncertainty_notes": {"type": "string"},
        "execution_plan": {"type": "array", "items": {"type": "string"}},
        "critical_check": {"type": "array", "items": {"type": "string"}},
        "sources": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {"title": {"type": "string"}, "url": {"type": "string"}},
                "required": ["title", "url"],
                "additionalProperties": False,
            },
        },
    }
    required = [
        "ticker",
        "name",
        "judgement",
        "judgement_label",
        "confidence",
        "time_horizon_views",
        "short_reason",
        "key_risks",
        "invalidation",
        "needs_analyst_mode",
        "needs_judge_mode",
        "verification_labels",
    ]
    if mode in {"analyst", "critical"}:
        required.extend(["technical_view", "news_view", "supply_demand_view", "holder_action", "execution_plan"])
    if mode == "scanner":
        required.extend(["non_monitoring_hold_risk", "needs_long_term_carry_check"])
    if mode in {"analyst", "judge", "critical"}:
        required.extend(["long_term_carry_check"])
    if mode == "critical":
        required.extend(["bullish_case", "bearish_case", "base_case", "position_size_risk", "event_risk", "gap_risk", "critical_check"])

    if mode == "scanner":
        scanner_stock_fields = {
            "ticker",
            "name",
            "judgement",
            "judgement_label",
            "confidence",
            "time_horizon_views",
            "short_reason",
            "key_risks",
            "invalidation",
            "needs_analyst_mode",
            "needs_judge_mode",
            "needs_long_term_carry_check",
            "non_monitoring_hold_risk",
            "verification_labels",
            "watch_points",
            "risk_flags",
            "needs_detail_analysis",
            "key_points",
            "holder_action",
            "stop_or_reduce_condition",
            "execution_plan",
            "critical_check",
            "sources",
        }
        stock_properties = {
            key: value for key, value in stock_properties.items() if key in scanner_stock_fields
        }

    portfolio_summary_properties = {
        "overall_view": {"type": "string"},
        "portfolio_summary": {"type": "string"},
        "market_temperature": {"type": "string"},
        "overall_risk": {"type": "string", "enum": ["low", "medium", "high"]},
        "buy_candidates": {"type": "array", "items": {"type": "string"}},
        "sell_or_reduce_candidates": {"type": "array", "items": {"type": "string"}},
        "hold_priority": {"type": "array", "items": {"type": "string"}},
        "cash_allocation_view": {"type": "string"},
        "concentration_risk": {"type": "string"},
        "theme_exposure": {"type": "array", "items": {"type": "string"}},
        "non_monitoring_reduce_candidates": {"type": "array", "items": {"type": "string"}},
        "core_position_candidates": {"type": "array", "items": {"type": "string"}},
        "exit_or_rotate_candidates": {"type": "array", "items": {"type": "string"}},
        "action_plan_today": {"type": "array", "items": {"type": "string"}},
        "invalidation_for_portfolio": {"type": "string"},
        "top_risks": {"type": "array", "items": {"type": "string"}},
    }
    if mode == "scanner":
        scanner_summary_fields = {
            "overall_view",
            "portfolio_summary",
            "market_temperature",
            "overall_risk",
            "concentration_risk",
            "non_monitoring_reduce_candidates",
            "core_position_candidates",
            "exit_or_rotate_candidates",
            "action_plan_today",
            "top_risks",
        }
        portfolio_summary_properties = {
            key: value
            for key, value in portfolio_summary_properties.items()
            if key in scanner_summary_fields
        }

    return {
        "type": "object",
        "properties": {
            "generated_at": {"type": "string"},
            "mode": {"type": "string", "enum": ["scanner", "analyst", "judge", "critical", "prompt_only"]},
            "input_summary": {"type": "object", "additionalProperties": True},
            "market_summary": {"type": "object", "additionalProperties": True},
            "portfolio_summary": {
                "type": "object",
                "properties": portfolio_summary_properties,
                "additionalProperties": False,
            },
            "stocks": {
                "type": "array",
                "items": {
                    "type": "object",
                    "properties": stock_properties,
                    "required": required,
                    "additionalProperties": False,
                },
            },
            "action_plan": {"type": "array", "items": {"type": "string"}},
            "critical_warnings": {"type": "array", "items": {"type": "string"}},
            "sources": {
                "type": "array",
                "items": {
                    "type": "object",
                    "properties": {"title": {"type": "string"}, "url": {"type": "string"}},
                    "required": ["title", "url"],
                    "additionalProperties": False,
                },
            },
            "warnings": {"type": "array", "items": {"type": "string"}},
            "raw_model_output": {"anyOf": [{"type": "string"}, {"type": "null"}]},
        },
        "required": [
            "generated_at",
            "mode",
            "input_summary",
            "market_summary",
            "portfolio_summary",
            "stocks",
            "action_plan",
            "critical_warnings",
            "sources",
            "warnings",
            "raw_model_output",
        ],
        "additionalProperties": False,
    }


def build_stock_analysis_prompt(
    request: Any,
    holdings: list[Any],
    candidates: list[Any],
    market_snapshots: list[Any],
    news_snapshots: dict[str, Any] | list[Any] | None,
    technical_snapshots: dict[str, Any] | list[Any] | None,
    portfolio_snapshot: dict[str, Any] | None,
) -> dict[str, Any]:
    mode = request.mode
    profile = get_mode_profile(mode)
    include_web_search = _resolve_include_web_search(request, profile)
    section_text = "\n".join(ANALYSIS_SECTIONS[section_id] for section_id in profile.section_ids)
    warnings = _web_search_warnings(mode, include_web_search)
    payload = {
        "generated_at": _tokyo_now().isoformat(),
        "mode": mode,
        "target": request.target,
        "risk_preference": request.risk_preference,
        "position_intent": getattr(request, "position_intent", None) or "未入力",
        "user_hypothesis": getattr(request, "user_hypothesis", None) or "未入力",
        "include_web_search": include_web_search,
        "web_search_policy": profile.web_search_policy,
        "max_web_search_calls": request.max_web_search_calls,
        "source_priority": WEB_SEARCH_SOURCE_PRIORITY,
        "holdings": [_dump(item) for item in holdings],
        "candidates": [_dump(item) for item in candidates],
        "market_snapshots": [_dump(item) for item in market_snapshots],
        "news_snapshots": _dump(news_snapshots or {}),
        "technical_snapshots": _dump(technical_snapshots or {}),
        "portfolio_snapshot": _dump(portfolio_snapshot or {}),
        "output_schema": get_output_schema_for_mode(mode),
    }
    system_prompt = (
        get_base_policy_prompt()
        + "\nWeb Search Policy:\n"
        + _web_search_policy_prompt(profile, include_web_search)
        + "\nOutput Policy:\n"
        + "- JSON Schemaに従ってJSONだけを返す。\n"
        + "- 検証ラベル、反証条件、短期/中期/長期分離、辛口チェックを必ず含める。\n"
    )
    user_prompt = (
        "Mode Profile:\n"
        f"- mode: {mode}\n"
        f"- web_search_policy: {profile.web_search_policy}\n"
        f"- notes: {' / '.join(profile.notes)}\n"
        f"- sections: {', '.join(profile.section_ids)}\n"
        + "\nAnalysis Sections:\n"
        + section_text
        + "\n\nInput JSON:\n"
        + json.dumps(payload, ensure_ascii=False, indent=2)
    )
    return {
        "system_prompt": system_prompt,
        "user_prompt": user_prompt,
        "prompt_payload": payload,
        "warnings": warnings,
        "web_search_policy": profile.web_search_policy,
        "output_schema": get_output_schema_for_mode(mode),
    }


def build_prompt_only_text(
    request: Any,
    holdings: list[Any],
    candidates: list[Any],
    market_snapshots: list[Any],
    news_snapshots: dict[str, Any] | list[Any] | None,
    technical_snapshots: dict[str, Any] | list[Any] | None,
    portfolio_snapshot: dict[str, Any] | None,
) -> str:
    payload = {
        "generated_at": _tokyo_now().isoformat(),
        "mode": request.mode,
        "target": request.target,
        "risk_preference": request.risk_preference,
        "position_intent": getattr(request, "position_intent", None) or "未入力",
        "user_hypothesis": getattr(request, "user_hypothesis", None) or "未入力",
        "holdings": [_dump(item) for item in holdings],
        "candidates": [_dump(item) for item in candidates],
        "market_snapshots": [_dump(item) for item in market_snapshots],
        "news_snapshots": _dump(news_snapshots or {}),
        "technical_snapshots": _dump(technical_snapshots or {}),
        "portfolio_snapshot": _dump(portfolio_snapshot or {}),
        "output_schema": get_output_schema_for_mode("prompt_only"),
    }
    return (
        get_full_user_stock_analysis_prompt().strip()
        + "\n\n--- アプリ側入力データ ---\n"
        + json.dumps(payload, ensure_ascii=False, indent=2)
        + "\n\n自動投稿や回答の自動取得は行わない。必要に応じてWebで最新確認し、重要主張には検証ラベルを付ける。"
    )


def validate_stock_analysis_response(payload: dict[str, Any], mode: AiReviewMode) -> list[str]:
    warnings: list[str] = []
    schema = get_output_schema_for_mode(mode)
    for field in schema["required"]:
        if field not in payload:
            warnings.append(f"validation warning: required field '{field}' is missing")
    for index, stock in enumerate(payload.get("stocks") or []):
        if not isinstance(stock, dict):
            warnings.append(f"validation warning: stocks[{index}] is not an object")
            continue
        for field in ("verification_labels", "invalidation"):
            if field not in stock:
                warnings.append(f"validation warning: stocks[{index}].{field} is missing")
        if mode == "scanner":
            for field in ("non_monitoring_hold_risk", "needs_long_term_carry_check"):
                if field not in stock:
                    warnings.append(f"validation warning: stocks[{index}].{field} is missing")
        if mode in {"analyst", "judge", "critical"} and "long_term_carry_check" not in stock:
            warnings.append(f"validation warning: stocks[{index}].long_term_carry_check is missing")
    return warnings


def estimate_openai_cost(mode: AiReviewMode, stock_count: int, include_web_search: bool, max_web_search_calls: int) -> float:
    if mode == "prompt_only":
        return 0
    base_by_mode = {"scanner": 0.006, "analyst": 0.02, "judge": 0.045, "critical": 0.075}
    per_stock_by_mode = {"scanner": 0.002, "analyst": 0.007, "judge": 0.005, "critical": 0.012}
    estimate = base_by_mode.get(mode, 0.02) + per_stock_by_mode.get(mode, 0.004) * stock_count
    if include_web_search:
        estimate += 0.01 * max_web_search_calls
    return round(estimate, 4)


def _web_search_warnings(mode: AiReviewMode, include_web_search: bool) -> list[str]:
    if include_web_search or mode == "prompt_only":
        return []
    if mode == "scanner":
        return ["最新Web確認なし。重要主張には【U】または【E】を付けてください。"]
    if mode in {"analyst", "judge"}:
        return [f"{mode} mode はWeb検索ONを標準とします。include_web_search=false のため最新確認不足として扱います。"]
    if mode == "critical":
        return ["critical mode ではWeb検索ONを強く推奨します。include_web_search=false のため高リスク判断の不確実性が高いです。"]
    return []


def _resolve_include_web_search(request: Any, profile: ModeProfile) -> bool:
    requested = getattr(request, "include_web_search", None)
    if requested is None:
        return profile.default_include_web_search
    return bool(requested)


def _web_search_policy_prompt(profile: ModeProfile, include_web_search: bool) -> str:
    if profile.mode == "prompt_only":
        return "- API検索は実行しない。手動投入先のChatGPTにWeb確認を依頼する。\n"
    lines = [
        f"- policy: {profile.web_search_policy}",
        f"- include_web_search: {include_web_search}",
        "- 優先ソース: " + "、".join(WEB_SEARCH_SOURCE_PRIORITY),
        "- 全銘柄に無制限検索しない。アプリ側で取得済みの最新データがある場合はそれを優先する。",
    ]
    if not include_web_search:
        lines.append("- Web検索OFF時は「最新Web確認なし」と明示し、【U】または【E】を使う。")
    return "\n".join(lines) + "\n"


def _dump(value: Any) -> Any:
    if hasattr(value, "model_dump"):
        return value.model_dump(mode="json")
    if isinstance(value, dict):
        return {key: _dump(item) for key, item in value.items()}
    if isinstance(value, list):
        return [_dump(item) for item in value]
    return value


def _tokyo_now() -> datetime:
    return datetime.now(TOKYO_TIMEZONE)
