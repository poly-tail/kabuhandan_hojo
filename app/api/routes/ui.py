"""Lightweight HTML dashboard for local verification and daily review."""

from __future__ import annotations

import json

from fastapi import APIRouter, Depends, Query
from fastapi.responses import HTMLResponse
from sqlalchemy.orm import Session

from app.db.session import get_db
from app.schemas.ui_dashboard import DashboardExperienceResponse
from app.services.dashboard_experience import dashboard_experience_service

router = APIRouter(tags=["ui"])


@router.get("/ui/dashboard/data", include_in_schema=False, response_model=DashboardExperienceResponse)
def dashboard_ui_data(
    ticker_code: str | None = Query(default=None, min_length=4, max_length=10),
    db: Session | None = Depends(get_db),
) -> DashboardExperienceResponse:
    """Return UI-focused dashboard data."""

    return dashboard_experience_service.build(session=db, selected_ticker_code=ticker_code)


@router.get("/ui/dashboard", include_in_schema=False, response_class=HTMLResponse)
def dashboard_ui() -> HTMLResponse:
    """Serve the top dashboard shell."""

    return HTMLResponse(_ui_shell_html(page_mode="top", initial_ticker=None))


@router.get("/ui/security/{ticker_code}", include_in_schema=False, response_class=HTMLResponse)
def security_detail_ui(ticker_code: str) -> HTMLResponse:
    """Serve the dedicated detail shell for a single security."""

    return HTMLResponse(_ui_shell_html(page_mode="detail", initial_ticker=ticker_code))


@router.get("/ui/security/{ticker_code}/chart", include_in_schema=False, response_class=HTMLResponse)
def security_chart_ui(ticker_code: str) -> HTMLResponse:
    """Serve the dedicated technical chart analysis shell for a single security."""

    return HTMLResponse(_ui_shell_html(page_mode="chart", initial_ticker=ticker_code))


@router.get("/ui/review", include_in_schema=False, response_class=HTMLResponse)
def review_ui() -> HTMLResponse:
    """Serve the review queue shell."""

    return HTMLResponse(_review_shell_html())


def _ui_shell_html(*, page_mode: str, initial_ticker: str | None) -> str:
    html = r"""<!doctype html>
<html lang="ja">
  <head>
    <meta charset="utf-8" />
    <meta name="viewport" content="width=device-width, initial-scale=1" />
    <title>Kabuhandan Hojo Dashboard</title>
    <style>
      :root {
        color-scheme: light;
        --bg: #f3efe7;
        --panel: rgba(255, 252, 246, 0.92);
        --panel-strong: #fffdf8;
        --ink: #1d2b2a;
        --muted: #5c6b67;
        --line: rgba(29, 43, 42, 0.1);
        --accent: #006d5b;
        --accent-soft: rgba(0, 109, 91, 0.12);
        --warn: #b85c2f;
        --warn-soft: rgba(184, 92, 47, 0.12);
        --good: #157347;
        --info: #2558a9;
        --shadow: 0 18px 50px rgba(36, 45, 49, 0.12);
        --radius: 24px;
      }

      * { box-sizing: border-box; }

      body {
        margin: 0;
        font-family: "Yu Gothic UI", "Hiragino Sans", "Meiryo", sans-serif;
        color: var(--ink);
        background:
          radial-gradient(circle at top left, rgba(255, 255, 255, 0.9), transparent 30%),
          linear-gradient(135deg, #f6f1e8 0%, #ddebe6 55%, #eff7f4 100%);
        min-height: 100vh;
      }

      body::before {
        content: "";
        position: fixed;
        inset: 0;
        background-image:
          linear-gradient(rgba(29, 43, 42, 0.03) 1px, transparent 1px),
          linear-gradient(90deg, rgba(29, 43, 42, 0.03) 1px, transparent 1px);
        background-size: 24px 24px;
        mask-image: linear-gradient(to bottom, rgba(0, 0, 0, 0.28), transparent 85%);
        pointer-events: none;
      }

      main {
        position: relative;
        max-width: 1240px;
        margin: 0 auto;
        padding: 32px 20px 56px;
      }

      .top-shell, .detail-shell {
        display: grid;
        gap: 24px;
      }

      .page-top .detail-shell,
      .page-detail .top-shell,
      .page-chart .top-shell {
        display: none;
      }

      .hero, .list-grid, .detail-grid {
        display: grid;
        gap: 18px;
      }

      .hero {
        grid-template-columns: 1.25fr 0.95fr;
      }

      .list-grid {
        grid-template-columns: 1fr 1fr;
      }

      .detail-grid {
        grid-template-columns: 1.1fr 0.9fr;
      }

      .panel {
        background: var(--panel);
        backdrop-filter: blur(18px);
        border: 1px solid var(--line);
        border-radius: var(--radius);
        box-shadow: var(--shadow);
        padding: 24px;
      }

      .hero-card {
        overflow: hidden;
        position: relative;
      }

      .hero-card::after {
        content: "";
        position: absolute;
        right: -32px;
        top: -32px;
        width: 180px;
        height: 180px;
        background: radial-gradient(circle, rgba(0, 109, 91, 0.16), transparent 70%);
      }

      .detail-page-header {
        display: grid;
        gap: 14px;
      }

      .eyebrow, .subtle {
        color: var(--muted);
        letter-spacing: 0.06em;
        text-transform: uppercase;
        font-size: 12px;
      }

      h1, h2, h3, p { margin: 0; }

      h1 {
        font-size: clamp(30px, 4vw, 52px);
        line-height: 1.02;
        max-width: 9ch;
        margin: 14px 0 16px;
      }

      h2 {
        font-size: 24px;
        line-height: 1.25;
      }

      h3 {
        font-size: 18px;
        line-height: 1.35;
      }

      .lede {
        max-width: 62ch;
        line-height: 1.7;
        color: #30423d;
      }

      .pill-row, .action-row, .section-head, .meta, .chips, .tags, .stack, .section-actions {
        display: flex;
        gap: 12px;
        flex-wrap: wrap;
      }

      .section-head {
        justify-content: space-between;
        align-items: baseline;
        margin-bottom: 16px;
      }

      .section-actions {
        align-items: center;
      }

      .pill, .chip, .score-chip, .tag {
        display: inline-flex;
        align-items: center;
        gap: 8px;
        padding: 8px 12px;
        border-radius: 999px;
        border: 1px solid var(--line);
        background: rgba(255, 255, 255, 0.8);
        font-size: 13px;
      }

      .chip, .tag {
        background: rgba(0, 109, 91, 0.08);
        color: var(--accent);
      }

      .tag.warn, .chip.warn {
        background: var(--warn-soft);
        color: var(--warn);
      }

      .chip.info {
        background: rgba(37, 88, 169, 0.1);
        color: var(--info);
      }

      .action-row { margin-top: 18px; }

      .action-link, .ghost-button {
        display: inline-flex;
        align-items: center;
        justify-content: center;
        min-height: 42px;
        padding: 0 16px;
        border-radius: 999px;
        text-decoration: none;
        color: var(--ink);
        background: var(--panel-strong);
        border: 1px solid var(--line);
        cursor: pointer;
        font: inherit;
      }

      .action-link.primary, .primary-button, .search-button, .save-button, .result-button {
        color: white;
        background: linear-gradient(135deg, #006d5b, #0b8d75);
        border: none;
      }

      .primary-button, .search-button, .save-button, .result-button {
        min-height: 46px;
        border-radius: 14px;
        padding: 0 16px;
        font: inherit;
        font-weight: 700;
        cursor: pointer;
      }

      .primary-button:disabled, .ghost-button:disabled, .search-button:disabled, .save-button:disabled, .result-button:disabled {
        opacity: 0.65;
        cursor: not-allowed;
      }

      .back-link {
        width: fit-content;
      }

      .score-chip {
        min-width: 78px;
        justify-content: center;
        background: var(--accent-soft);
        color: var(--accent);
        font-weight: 700;
      }

      .kpi-grid, .status-grid, .card-grid, .detail-stack, .metric-list, .timeline, .portfolio-grid, .ai-review-grid {
        display: grid;
        gap: 14px;
      }

      .kpi-grid, .status-grid {
        grid-template-columns: repeat(2, minmax(0, 1fr));
      }

      .card-grid {
        grid-template-columns: repeat(auto-fit, minmax(280px, 1fr));
      }

      .priority-card, .event-item, .watch-item, .alert-item, .screen-row, .detail-card, .status-card, .kpi, .search-result, .portfolio-card, .ai-review-card {
        padding: 18px;
        border: 1px solid var(--line);
        border-radius: 20px;
        background: rgba(255, 255, 255, 0.72);
      }

      .priority-card, .event-item, .watch-item, .alert-item, .screen-row, .search-result {
        cursor: pointer;
      }

      .company {
        display: grid;
        gap: 4px;
      }

      .ticker {
        color: var(--muted);
        font-size: 13px;
      }

      .watchlist-tools, .search-form, .form-grid {
        display: grid;
        gap: 12px;
      }

      .search-form, .detail-form {
        padding: 18px;
        border: 1px solid var(--line);
        border-radius: 20px;
        background: rgba(255, 255, 255, 0.62);
      }

      .search-row, .inline-grid {
        display: grid;
        gap: 10px;
        grid-template-columns: minmax(0, 1fr) auto;
      }

      .input, .textarea {
        min-height: 46px;
        padding: 10px 14px;
        border-radius: 14px;
        border: 1px solid var(--line);
        background: rgba(255, 255, 255, 0.92);
        color: var(--ink);
        font: inherit;
      }

      .textarea {
        min-height: 96px;
        resize: vertical;
      }

      .input:focus, .textarea:focus {
        outline: 2px solid rgba(0, 109, 91, 0.22);
        outline-offset: 1px;
      }

      .search-feedback {
        min-height: 18px;
        color: var(--muted);
        font-size: 13px;
      }

      .search-feedback.success { color: var(--good); }
      .search-feedback.error { color: var(--warn); }

      .ai-review-tools {
        display: grid;
        gap: 12px;
        margin: 14px 0;
        padding: 16px;
        border: 1px solid var(--line);
        border-radius: 18px;
        background: rgba(255, 255, 255, 0.62);
      }

      .ai-review-control-grid {
        display: grid;
        gap: 10px;
        grid-template-columns: repeat(auto-fit, minmax(170px, 1fr));
      }

      .stock-ai-usage-panel {
        display: grid;
        gap: 8px;
        padding: 12px 14px;
        border: 1px solid var(--line);
        border-radius: 16px;
        background: rgba(0, 109, 91, 0.05);
      }

      .stock-ai-usage-grid {
        display: grid;
        gap: 8px 14px;
        grid-template-columns: repeat(auto-fit, minmax(240px, 1fr));
      }

      .stock-ai-usage-value {
        color: var(--ink);
        font-size: 14px;
        line-height: 1.55;
      }

      .stock-ai-usage-warning {
        color: var(--warn);
        font-size: 12px;
        line-height: 1.55;
      }

      .ai-review-actions, .checkbox-row {
        display: flex;
        gap: 12px;
        flex-wrap: wrap;
        align-items: center;
      }

      .checkbox-row label {
        display: inline-flex;
        gap: 8px;
        align-items: center;
        color: var(--muted);
        font-size: 13px;
      }

      .watch-select {
        display: inline-flex;
        align-items: center;
        gap: 8px;
        color: var(--muted);
        font-size: 13px;
      }

      .prompt-output {
        min-height: 180px;
        font-family: ui-monospace, "Cascadia Mono", "SFMono-Regular", Consolas, monospace;
        font-size: 13px;
        line-height: 1.55;
      }

      .ai-review-grid {
        margin-top: 14px;
      }

      .ai-review-summary {
        border-color: rgba(0, 109, 91, 0.18);
        background: rgba(0, 109, 91, 0.06);
      }

      .judgement-badge {
        display: inline-flex;
        align-items: center;
        padding: 7px 10px;
        border-radius: 999px;
        border: 1px solid var(--line);
        font-size: 12px;
        font-weight: 700;
      }

      .judgement-badge.hold { color: var(--accent); background: var(--accent-soft); }
      .judgement-badge.buy_more_candidate { color: var(--good); background: rgba(21, 115, 71, 0.1); }
      .judgement-badge.take_profit_candidate { color: #8a5a00; background: rgba(138, 90, 0, 0.1); }
      .judgement-badge.reduce_risk { color: var(--warn); background: var(--warn-soft); }
      .judgement-badge.watch { color: var(--info); background: rgba(37, 88, 169, 0.1); }
      .judgement-badge.avoid_new_buy { color: #5b6470; background: rgba(91, 100, 112, 0.12); }
      .judgement-badge.urgent_review { color: #9d174d; background: rgba(157, 23, 77, 0.12); }

      .compact-list {
        margin: 8px 0 0;
        padding-left: 18px;
        color: #30423d;
        line-height: 1.55;
      }

      .screen-table, .split-bars, .split-bar {
        display: grid;
        gap: 12px;
      }

      .screen-row {
        display: grid;
        gap: 10px;
        grid-template-columns: 1.2fr 0.65fr 1fr;
        align-items: center;
      }

      .split-track {
        width: 100%;
        height: 10px;
        border-radius: 999px;
        background: rgba(29, 43, 42, 0.08);
        overflow: hidden;
      }

      .split-fill {
        height: 100%;
        border-radius: inherit;
        background: linear-gradient(135deg, #006d5b, #0b8d75);
      }

      .source-links {
        display: flex;
        gap: 10px;
        flex-wrap: wrap;
        margin-top: 12px;
      }

      .source-link {
        display: inline-flex;
        align-items: center;
        gap: 8px;
        padding: 7px 12px;
        border-radius: 999px;
        border: 1px solid rgba(0, 109, 91, 0.18);
        background: rgba(0, 109, 91, 0.08);
        color: var(--accent);
        text-decoration: none;
        font-size: 13px;
      }

      .detail-cta {
        display: grid;
        gap: 10px;
        margin-top: 16px;
      }

      .chart-panel, .chart-stats, .analysis-grid {
        display: grid;
        gap: 14px;
      }

      .chart-stats {
        grid-template-columns: repeat(auto-fit, minmax(140px, 1fr));
      }

      .analysis-grid {
        grid-template-columns: repeat(auto-fit, minmax(220px, 1fr));
      }

      .chart-stat {
        padding: 14px;
        border: 1px solid var(--line);
        border-radius: 18px;
        background: rgba(255, 255, 255, 0.82);
      }

      .analysis-card {
        padding: 16px;
        border: 1px solid var(--line);
        border-radius: 20px;
        background: rgba(255, 255, 255, 0.82);
      }

      .analysis-card strong {
        display: block;
        margin-top: 8px;
        font-size: 20px;
      }

      .chart-surface {
        padding: 16px;
        border: 1px solid var(--line);
        border-radius: 22px;
        background:
          linear-gradient(180deg, rgba(0, 109, 91, 0.06), rgba(255, 255, 255, 0.86)),
          rgba(255, 255, 255, 0.88);
      }

      .chart-svg {
        width: 100%;
        height: auto;
        display: block;
      }

      .chart-grid-line {
        stroke: rgba(29, 43, 42, 0.1);
        stroke-width: 1;
      }

      .chart-zero-line {
        stroke: rgba(29, 43, 42, 0.18);
        stroke-width: 1;
        stroke-dasharray: 4 4;
      }

      .chart-axis-label {
        fill: var(--muted);
        font-size: 12px;
      }

      .chart-price-guide {
        stroke: rgba(0, 109, 91, 0.22);
        stroke-width: 1.5;
        stroke-dasharray: 4 4;
      }

      .chart-wick {
        stroke-width: 1.5;
      }

      .chart-candle.up,
      .chart-wick.up {
        fill: rgba(21, 115, 71, 0.82);
        stroke: rgba(21, 115, 71, 0.96);
      }

      .chart-candle.down,
      .chart-wick.down {
        fill: rgba(184, 92, 47, 0.82);
        stroke: rgba(184, 92, 47, 0.96);
      }

      .chart-volume.up {
        fill: rgba(21, 115, 71, 0.24);
      }

      .chart-volume.down {
        fill: rgba(184, 92, 47, 0.24);
      }

      .chart-overlay {
        fill: none;
        stroke-width: 2.2;
        stroke-linecap: round;
        stroke-linejoin: round;
      }

      .chart-legend, .segmented-controls {
        display: flex;
        gap: 10px;
        flex-wrap: wrap;
      }

      .legend-item {
        display: inline-flex;
        align-items: center;
        gap: 8px;
        padding: 7px 12px;
        border-radius: 999px;
        border: 1px solid var(--line);
        background: rgba(255, 255, 255, 0.82);
        font-size: 13px;
        color: var(--muted);
      }

      .legend-swatch {
        width: 18px;
        height: 3px;
        border-radius: 999px;
      }

      .segment-button {
        min-height: 38px;
        padding: 0 14px;
        border-radius: 999px;
        border: 1px solid var(--line);
        background: rgba(255, 255, 255, 0.78);
        color: var(--ink);
        cursor: pointer;
        font: inherit;
        font-weight: 700;
      }

      .segment-button.active {
        border-color: rgba(0, 109, 91, 0.24);
        background: var(--accent-soft);
        color: var(--accent);
      }

      .chart-actions {
        display: flex;
        gap: 12px;
        flex-wrap: wrap;
      }

      .empty {
        padding: 18px;
        border-radius: 18px;
        border: 1px dashed var(--line);
        color: var(--muted);
        white-space: pre-wrap;
        overflow-wrap: anywhere;
        line-height: 1.7;
      }

      .error {
        border-color: rgba(184, 92, 47, 0.4);
        color: var(--warn);
        background: rgba(255, 248, 244, 0.86);
      }

      @media (max-width: 960px) {
        .hero, .list-grid, .detail-grid, .screen-row {
          grid-template-columns: 1fr;
        }
      }

      @media (max-width: 640px) {
        main { padding: 18px 14px 40px; }
        .panel { padding: 20px; }
        .kpi-grid, .status-grid, .metric-list, .search-row, .search-result, .inline-grid { grid-template-columns: 1fr; }
      }
    </style>
  </head>
  <body class="page-__PAGE_MODE__">
    <main>
      <div class="top-shell">
        <div class="hero">
          <article class="panel hero-card">
            <div class="eyebrow">Judgment Support Dashboard</div>
            <h1>判断補助ダッシュボード</h1>
            <p class="lede" id="hero-comment">
              市況とウォッチ中の銘柄を先に整理し、重要アラートと材料履歴から今日見る順番を決める画面です。
            </p>
            <div class="pill-row" id="hero-pills"></div>
            <div class="action-row">
              <a class="action-link primary" href="/docs">Swagger</a>
              <a class="action-link" href="/dashboard">Dashboard JSON</a>
              <a class="action-link" href="/screening?min_total_score=60">Screening JSON</a>
              <a class="action-link" href="/watchlist">Watchlist JSON</a>
            </div>
          </article>

          <aside class="panel hero-card">
            <div class="section-head">
              <div>
                <div class="eyebrow">Market Overview</div>
                <h2 id="market-label">読み込み中</h2>
              </div>
              <div class="score-chip" id="market-score">--</div>
            </div>
            <div class="stack">
              <p id="market-comment" class="lede"></p>
              <div class="action-row">
                <button
                  class="ghost-button"
                  id="market-proxy-sync-button"
                  type="button"
                  data-manual-update="market-proxy"
                  data-manual-feedback="market-proxy-sync-feedback"
                >市場価格更新</button>
              </div>
              <div class="search-feedback" id="market-proxy-sync-feedback"></div>
              <div class="chips" id="market-cautions"></div>
              <div class="status-grid" id="status-grid"></div>
            </div>
          </aside>
        </div>

        <section class="panel">
          <div class="section-head">
            <div>
              <div class="eyebrow">Focus Board</div>
              <h2>市況とウォッチの重要銘柄</h2>
            </div>
            <div class="section-actions">
              <button class="ghost-button" type="button" data-manual-update="watchlist-scores" data-manual-feedback="focus-refresh-feedback">スコア更新</button>
            </div>
          </div>
          <p class="subtle" id="disclaimer">読み込み中...</p>
          <div class="search-feedback" id="focus-refresh-feedback"></div>
          <div class="kpi-grid" id="metric-grid"></div>
          <div class="card-grid" id="priority-grid" style="margin-top: 16px;"></div>
        </section>

        <div class="list-grid">
          <section class="panel">
            <div class="section-head">
              <div>
                <div class="eyebrow">Portfolio</div>
                <h2>保有銘柄</h2>
              </div>
              <div class="section-actions">
                <button class="ghost-button" type="button" data-manual-update="portfolio-prices" data-manual-feedback="portfolio-feedback">評価価格更新</button>
              </div>
            </div>
            <div class="subtle" id="portfolio-note">broker 連携は使わず、手入力で保有銘柄を管理します。</div>
            <div class="search-feedback" id="portfolio-feedback"></div>
            <div class="ai-review-tools">
              <div class="section-head" style="margin-bottom: 0;">
                <div>
                  <div class="eyebrow">AI分析</div>
                  <h3>今日の保有銘柄レビュー</h3>
                </div>
                <div class="score-chip" id="stock-ai-cost">--</div>
              </div>
              <div class="stock-ai-usage-panel" id="stock-ai-usage" aria-live="polite">
                <div class="stock-ai-usage-grid">
                  <div>
                    <div class="eyebrow">アプリ内利用量（legacy stock-review）</div>
                    <div class="stock-ai-usage-value" id="stock-ai-usage-today">本日 成功レビュー -- / --回・残り --・OpenAI呼出 --回・概算 $--</div>
                  </div>
                  <div>
                    <div class="eyebrow">月間利用量</div>
                    <div class="stock-ai-usage-value" id="stock-ai-usage-month">今月 成功レビュー --回・OpenAI呼出 --回・概算 $--</div>
                  </div>
                </div>
                <div class="stock-ai-usage-warning" id="stock-ai-usage-unpriced" hidden></div>
                <div class="subtle" id="stock-ai-usage-history-note" hidden></div>
                <div class="subtle">1回＝正常完了した一括レビュー1件（銘柄数に関係なし）です。この集計は旧stock-review経路だけが対象です。金額はtoken使用量に基づく概算で、正式な請求額ではありません。OpenAI PlatformのUsage Dashboardを正本として確認してください。</div>
              </div>
              <div class="ai-review-control-grid">
                <select class="input" id="stock-ai-mode" aria-label="AI分析モード">
                  <option value="scanner">軽量スキャン</option>
                  <option value="analyst">個別詳細分析</option>
                  <option value="judge" selected>全体売買判断</option>
                  <option value="critical">重要局面分析</option>
                </select>
                <select class="input" id="stock-ai-target" aria-label="AI分析対象">
                  <option value="holdings">保有銘柄</option>
                  <option value="candidates">狙い中銘柄</option>
                  <option value="watchlist">監視銘柄</option>
                  <option value="selected">選択銘柄</option>
                  <option value="mock">テスト用仮保有銘柄</option>
                </select>
                <input class="input" id="stock-ai-tickers" placeholder="選択銘柄: 7203,7974" aria-label="選択銘柄コード" />
                <input class="input" id="stock-ai-max-web-search" type="number" min="0" max="10" value="5" aria-label="Web検索最大回数" />
                <select class="input" id="stock-ai-position-intent" aria-label="建玉意図">
                  <option value="">建玉意図: 未入力</option>
                  <option value="short">短期玉</option>
                  <option value="mid">中期玉</option>
                  <option value="long">長期玉</option>
                  <option value="short_and_mid">短期＋中期</option>
                  <option value="core">コア玉</option>
                  <option value="add">追加玉</option>
                </select>
                <input class="input" id="stock-ai-user-hypothesis" placeholder="仮説: 防衛テーマと決算期待、短期過熱など" aria-label="ユーザー仮説" />
              </div>
              <div class="ai-review-actions">
                <button class="primary-button" type="button" data-stock-ai-run="scanner">軽量スキャン</button>
                <button class="primary-button" type="button" data-stock-ai-run="analyst">個別詳細分析</button>
                <button class="primary-button" type="button" data-stock-ai-run="judge">全体売買判断</button>
                <button class="primary-button" type="button" data-stock-ai-run="critical">重要局面分析</button>
                <button class="ghost-button" type="button" data-stock-ai-run="prompt_only">ChatGPT投入用プロンプトを生成</button>
                <button class="ghost-button" type="button" id="stock-ai-copy-prompt" disabled>プロンプトをコピー</button>
              </div>
              <div class="checkbox-row">
                <label><input id="portfolio-ai-web-search" type="checkbox" /> Web検索ON</label>
                <label><input id="portfolio-ai-mock-response" type="checkbox" /> APIなしのサンプル表示（課金なし）</label>
                <label><input id="stock-ai-save-result" type="checkbox" checked /> 結果保存</label>
                <label><input id="stock-ai-use-cache" type="checkbox" checked /> 前回結果の再表示</label>
              </div>
              <div class="search-feedback" id="portfolio-ai-review-feedback">未実行</div>
              <textarea class="textarea prompt-output" id="stock-ai-prompt-output" readonly placeholder="ChatGPT投入用プロンプト"></textarea>
            </div>
            <div class="ai-review-grid" id="portfolio-ai-review-results"></div>
            <form class="search-row" id="portfolio-form" style="margin-top: 12px;">
              <input class="search-input" id="portfolio-ticker-input" name="ticker_code" placeholder="7203 / 285A" aria-label="保有銘柄コード" />
              <input class="search-input" id="portfolio-quantity-input" name="quantity" type="number" step="0.0001" min="0.0001" placeholder="100" aria-label="保有数量" />
              <input class="search-input" id="portfolio-average-cost-input" name="average_cost" type="number" step="0.0001" min="0.0001" placeholder="3200" aria-label="平均取得単価" />
              <input class="search-input" id="portfolio-note-input" name="note" placeholder="メモ" aria-label="保有メモ" />
              <button class="primary-button" type="submit">保有を保存</button>
            </form>
            <div class="portfolio-grid" id="portfolio-list"></div>
          </section>

          <section class="panel">
            <div class="section-head">
              <div>
                <div class="eyebrow">Watchlist</div>
                <h2>ウォッチリスト</h2>
              </div>
              <div class="section-actions">
                <button class="ghost-button" type="button" data-manual-update="watchlist-scores" data-manual-feedback="watchlist-refresh-feedback">再評価</button>
              </div>
            </div>
            <div class="search-feedback" id="watchlist-refresh-feedback"></div>
            <div class="ai-review-tools">
              <div class="ai-review-actions">
                <button class="ghost-button" type="button" data-watchlist-ai-select-all="true">全選択</button>
                <button class="ghost-button" type="button" data-watchlist-ai-clear="true">選択解除</button>
              </div>
              <div class="search-feedback" id="watchlist-ai-review-feedback">選択銘柄はAI分析パネルの「選択銘柄」で実行します。</div>
            </div>
            <div class="ai-review-grid" id="watchlist-ai-review-results"></div>
            <div class="stack" id="watchlist-list"></div>
          </section>
        </div>

        <div class="list-grid">
          <section class="panel">
            <div class="section-head">
              <div>
                <div class="eyebrow">Alerts</div>
                <h2>重要アラート</h2>
              </div>
              <div class="section-actions">
                <button class="ghost-button" type="button" data-manual-update="watchlist-scores" data-manual-feedback="alerts-refresh-feedback">アラート再計算</button>
              </div>
            </div>
            <div class="search-feedback" id="alerts-refresh-feedback"></div>
            <div class="stack" id="alerts-list"></div>
          </section>

          <section class="panel">
            <div class="section-head">
              <div>
                <div class="eyebrow">Materials</div>
                <h2>材料履歴</h2>
              </div>
              <div class="section-actions">
                <button class="ghost-button" type="button" data-manual-update="edinet" data-manual-feedback="materials-refresh-feedback">EDINET取得</button>
                <button class="ghost-button" type="button" data-manual-update="tdnet-all" data-manual-feedback="materials-refresh-feedback">TDnet取得</button>
                <button class="ghost-button" type="button" data-manual-update="sources" data-manual-feedback="materials-refresh-feedback">ソース登録確認</button>
              </div>
            </div>
            <div class="search-feedback" id="materials-refresh-feedback"></div>
            <div class="stack" id="events-list"></div>
          </section>
        </div>

        <section class="panel">
          <div class="section-head">
            <div>
              <div class="eyebrow">Screening</div>
              <h2>追加候補</h2>
            </div>
            <div class="section-actions">
              <button class="ghost-button" type="button" data-manual-update="screening-scores" data-manual-feedback="screening-refresh-feedback">候補スコア更新</button>
            </div>
          </div>
          <div class="search-feedback" id="screening-refresh-feedback"></div>
          <div class="screen-table" id="screening-list"></div>
        </section>

        <section class="panel">
          <div class="section-head">
            <div>
              <div class="eyebrow">Search</div>
              <h2>銘柄検索</h2>
            </div>
          </div>
          <div class="watchlist-tools">
            <form class="search-form" id="watchlist-search-form">
              <label class="search-label" for="watchlist-search-input">銘柄名か銘柄コード（数字・英字）で検索</label>
              <div class="search-row">
                <input
                  id="watchlist-search-input"
                  class="input"
                  type="search"
                  name="q"
                  placeholder="7203 / 285A / トヨタ / キオクシア"
                  autocomplete="off"
                />
                <button class="search-button" id="watchlist-search-button" type="submit">検索</button>
                <button
                  class="ghost-button"
                  id="security-master-sync-button"
                  type="button"
                  data-manual-update="security-master"
                  data-manual-feedback="watchlist-search-feedback"
                >東証全銘柄を同期</button>
              </div>
              <div class="subtle">検索結果から詳細画面を開くか、保有入力欄へ銘柄コードを反映できます。数量を入力するまで保有銘柄には保存されません。</div>
            </form>
            <div class="search-feedback" id="security-master-status" aria-live="polite">東証銘柄マスターの同期状態を確認しています...</div>
            <div class="search-feedback" id="watchlist-search-feedback"></div>
            <div class="stack" id="watchlist-search-results"></div>
            <div class="subtle">watchlist 未登録で、いまスコアが高い候補</div>
            <div class="stack" id="watchlist-score-candidates"></div>
          </div>
        </section>
      </div>

      <div class="detail-shell">
        <section class="panel detail-page-header">
          <a class="action-link back-link" href="/ui/dashboard">一覧へ戻る</a>
          <div class="section-head">
            <div>
              <div class="eyebrow">Security Detail</div>
              <h2 id="detail-page-title">銘柄詳細</h2>
            </div>
            <div class="chips" id="detail-header-tags"></div>
          </div>
          <p class="subtle" id="detail-page-subtitle">銘柄ごとの根拠、警戒点、仮説カードを確認します。</p>
        </section>

        <section class="panel">
          <div id="detail-view"></div>
        </section>
      </div>
    </main>

    <script>
      const PAGE_MODE = "__PAGE_MODE__";
      const INITIAL_TICKER = __INITIAL_TICKER__;
      const TOP_PAGE_URL = "/ui/dashboard";
      const TOKYO_TIME_ZONE = "Asia/Tokyo";

      const state = {
        data: null,
        searchResults: [],
        lastQuery: "",
        searchRequestId: 0,
        searchDebounceId: null,
        securityMasterStatus: {
          status: "loading",
          data: null,
          error: null,
        },
        chartRangeKey: "all",
        manualFeedback: {},
        portfolioAiReview: {
          status: "idle",
          data: null,
          error: null,
        },
        stockAiUsage: {
          status: "loading",
          data: null,
          error: null,
        },
        watchlistAiReview: {
          status: "idle",
          data: null,
          error: null,
        },
        lastManualPrompt: "",
        selectedWatchlistTickers: new Set(),
      };

      const detailPageUrl = (tickerCode) => `/ui/security/${encodeURIComponent(tickerCode)}`;
      const chartPageUrl = (tickerCode) => `/ui/security/${encodeURIComponent(tickerCode)}/chart`;

      const publicSecurityCode = (value) => {
        const normalized = String(value ?? "").trim();
        const isJquantsAlphanumericCode = /^[0-9A-Za-z]{4}0$/.test(normalized)
          && /[A-Za-z]/.test(normalized.slice(0, 4));
        return isJquantsAlphanumericCode ? normalized.slice(0, 4) : normalized;
      };

      const parseUiDate = (value) => {
        if (!value) return null;
        if (typeof value === "string" && /^\\d{4}-\\d{2}-\\d{2}$/.test(value)) {
          return new Date(`${value}T00:00:00+09:00`);
        }
        return new Date(value);
      };

      const formatDateTime = (value) => {
        if (!value) return "--";
        const parsed = parseUiDate(value);
        if (!parsed || Number.isNaN(parsed.getTime())) return "--";
        return `${new Intl.DateTimeFormat("ja-JP", {
          year: "numeric",
          month: "2-digit",
          day: "2-digit",
          hour: "2-digit",
          minute: "2-digit",
          hour12: false,
          timeZone: TOKYO_TIME_ZONE,
        }).format(parsed)} JST`;
      };

      const formatDate = (value) => {
        if (!value) return "--";
        const parsed = parseUiDate(value);
        if (!parsed || Number.isNaN(parsed.getTime())) return "--";
        return new Intl.DateTimeFormat("ja-JP", {
          year: "numeric",
          month: "2-digit",
          day: "2-digit",
          timeZone: TOKYO_TIME_ZONE,
        }).format(parsed);
      };

      const escapeHtml = (value) =>
        String(value ?? "")
          .replaceAll("&", "&amp;")
          .replaceAll("<", "&lt;")
          .replaceAll(">", "&gt;")
          .replaceAll('"', "&quot;")
          .replaceAll("'", "&#39;");

      const escapeAttr = (value) => escapeHtml(value).replaceAll("`", "&#96;");

      const renderSourceLinks = (links = []) => {
        if (!links.length) return "";
        return `<div class="source-links">${links.map((link) => `
          <a
            class="source-link"
            href="${escapeAttr(link.url)}"
            title="${escapeAttr(link.note || "")}"
            target="_blank"
            rel="noreferrer"
            data-source-link="true"
          >${escapeHtml(link.label)}</a>
        `).join("")}</div>`;
      };

      const fill = (id, html) => {
        const node = document.getElementById(id);
        if (node) {
          node.innerHTML = html;
        }
      };

      const text = (id, value) => {
        const node = document.getElementById(id);
        if (node) {
          node.textContent = value;
        }
      };

      const fetchJson = async (url, options = {}) => {
        const response = await fetch(url, options);
        if (!response.ok) {
          let detail = "";
          try {
            const payload = await response.json();
            detail = payload.detail || JSON.stringify(payload);
          } catch {
            detail = await response.text();
          }
          throw new Error(`${url} -> ${response.status}${detail ? ` ${detail}` : ""}`);
        }
        return response.json();
      };

      const postJson = (url, payload) =>
        fetchJson(url, {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify(payload),
        });

      const deleteJson = (url) =>
        fetchJson(url, {
          method: "DELETE",
        });

      const setSearchFeedback = (message = "", tone = "") => {
        const element = document.getElementById("watchlist-search-feedback");
        if (!element) return;
        element.className = tone ? `search-feedback ${tone}` : "search-feedback";
        element.textContent = message;
      };

      const renderSecurityMasterStatus = () => {
        const element = document.getElementById("security-master-status");
        if (!element) return;
        const status = state.securityMasterStatus;
        if (status.status === "loading") {
          element.className = "search-feedback";
          element.textContent = "東証銘柄マスターの同期状態を確認しています...";
          return;
        }
        if (status.status === "failed" || !status.data) {
          element.className = "search-feedback error";
          element.textContent = `同期状態を取得できませんでした: ${status.error || "unknown error"}`;
          return;
        }

        const data = status.data;
        const activeTotal = Number(data.active_total || 0).toLocaleString("ja-JP");
        const jquantsCount = Number(data.jquants_active_count || 0).toLocaleString("ja-JP");
        if (!data.complete) {
          element.className = "search-feedback";
          element.textContent = `東証全件同期は未確認です。ローカル有効銘柄 ${activeTotal}件。「東証全銘柄を同期」を実行し、失敗する場合はJ-Quants APIキーとエラー内容を確認してください。`;
          return;
        }

        const sourceAsOf = data.source_as_of ? formatDate(data.source_as_of) : "基準日未確認";
        const syncedAt = data.synced_at ? formatDateTime(data.synced_at) : "同期時刻未確認";
        element.className = "search-feedback success";
        element.textContent = `東証全件同期済み（J-Quants ${jquantsCount}件 / ローカル有効 ${activeTotal}件 / 情報基準日 ${sourceAsOf} / 同期 ${syncedAt}）`;
      };

      const loadSecurityMasterStatus = async () => {
        state.securityMasterStatus = { status: "loading", data: null, error: null };
        renderSecurityMasterStatus();
        try {
          const payload = await fetchJson("/securities/master/status");
          state.securityMasterStatus = { status: "success", data: payload, error: null };
        } catch (error) {
          state.securityMasterStatus = {
            status: "failed",
            data: null,
            error: error.message || String(error),
          };
        }
        renderSecurityMasterStatus();
      };

      const setPortfolioFeedback = (message = "", tone = "") => {
        const element = document.getElementById("portfolio-feedback");
        if (!element) return;
        element.className = tone ? `search-feedback ${tone}` : "search-feedback";
        element.textContent = message;
      };

      const statusChip = (score) => {
        if (score >= 70) return "warn";
        if (score >= 50) return "info";
        return "";
      };

      const aiReviewStatusLabel = (status) => ({
        idle: "未実行",
        loading: "実行中",
        success: "成功",
        failed: "失敗",
        missing_api_key: "APIキー未設定",
        json_parse_failed: "JSON parse失敗",
        openai_api_error: "OpenAI APIエラー",
        openai_sdk_missing: "OpenAI SDK未導入",
        no_holdings: "保有銘柄なし",
        target_limit_exceeded: "対象銘柄数上限",
        daily_limit_exceeded: "日次上限",
      }[status] || status || "未実行");

      const aiReviewResultStatusLabel = (data) => {
        const status = data?.status || "idle";
        if (status !== "json_parse_failed") return aiReviewStatusLabel(status);
        if (data?.parse_failure_kind === "schema_validation") return "JSON項目形式エラー";
        if (data?.parse_failure_kind === "root_shape") return "JSONルート形式エラー";
        return "JSON構文エラー";
      };

      const aiJudgementLabel = (judgement) => ({
        hold: "保有継続",
        buy_more_candidate: "買増し候補",
        take_profit_candidate: "一部利確候補",
        reduce_risk: "リスク低減",
        watch: "様子見",
        avoid_new_buy: "新規買い見送り",
        urgent_review: "緊急確認",
      }[judgement] || judgement || "-");

      const aiModeLabel = (mode) => ({
        scanner: "軽量スキャン",
        analyst: "個別詳細分析",
        judge: "全体売買判断",
        critical: "重要局面分析",
        prompt_only: "ChatGPT投入用プロンプト生成",
      }[mode] || mode || "-");

      const aiHoldingsSourceLabel = (source) => ({
        request: "対象: リクエスト指定銘柄",
        database: "対象: 実DB保有銘柄",
        watchlist: "対象: 監視銘柄",
        candidates: "対象: 狙い中銘柄",
        mock: "対象: テスト用仮保有銘柄",
        none: "対象: 未指定",
      }[source] || "対象: 未確認");

      const renderCompactList = (items = []) => {
        if (!items.length) return "";
        return `<ul class="compact-list">${items.map((item) => `<li>${escapeHtml(item)}</li>`).join("")}</ul>`;
      };

      const renderAiSources = (sources = []) => {
        if (!sources.length) return "";
        return renderSourceLinks(sources.map((source) => ({
          label: source.title || source.url,
          url: source.url,
          note: source.title || "",
        })));
      };

      const longTermCarryDecisionLabel = (value) => ({
        long_term_hold_ok: "中長期持ち越し可",
        hold_if_reduced: "サイズ縮小なら持ち越し可",
        hold_with_alerts: "アラート必須で持ち越し可",
        reduce_before_event: "イベント前に縮小",
        not_suitable_without_daily_monitoring: "毎日見られないなら非推奨",
        exit_or_rotate_candidate: "撤退/入れ替え候補",
        unknown: "不明",
      }[value] || value || "不明");

      const dailyMonitoringHoldLabel = (value) => ({
        yes: "持てる",
        with_reduction: "サイズ縮小なら可",
        with_alerts: "アラート必須",
        before_event_reduce: "イベント前に縮小",
        no: "非推奨",
        unknown: "不明",
      }[value] || value || "不明");

      const riskLevelLabel = (value) => ({
        low: "低",
        medium: "中",
        high: "高",
        unknown: "不明",
        strong: "強い",
        normal: "普通",
        weak: "弱い",
      }[value] || value || "不明");

      const holdabilityLabel = (value) => ({
        ok: "可",
        with_alerts: "アラート必須",
        with_reduction: "縮小なら可",
        not_recommended: "非推奨",
        unknown: "不明",
      }[value] || value || "不明");

      const monitoringIntervalLabel = (value) => ({
        "1_business_day": "1営業日",
        "3_business_days": "3営業日",
        "1_week": "1週間",
        "2_weeks": "2週間",
        "1_month_or_more": "1か月以上",
      }[value] || value || "-");

      const nullableBooleanLabel = (value) => (
        value === true ? "はい" : value === false ? "いいえ" : "不明"
      );

      const hasLongTermCarrySection = (stock) => {
        const check = stock.long_term_carry_check || {};
        return Boolean(
          stock.needs_long_term_carry_check
          || (stock.non_monitoring_hold_risk && stock.non_monitoring_hold_risk !== "unknown")
          || (check.final_long_term_carry_decision && check.final_long_term_carry_decision !== "unknown")
          || (check.required_alerts || []).length
          || (check.must_check_dates_or_events || []).length
          || (check.monitoring_interval_view || []).length
        );
      };

      const longTermCarryWarningChip = (stock) => {
        const check = stock.long_term_carry_check || {};
        const decision = check.final_long_term_carry_decision;
        const risk = stock.non_monitoring_hold_risk || check.non_monitoring_hold_risk;
        if (
          risk === "high"
          || ["not_suitable_without_daily_monitoring", "exit_or_rotate_candidate", "reduce_before_event"].includes(decision)
        ) {
          return '<span class="chip warn">非監視リスク高</span>';
        }
        return "";
      };

      const renderLongTermCarrySection = (stock) => {
        if (!hasLongTermCarrySection(stock)) return "";
        const check = stock.long_term_carry_check || {};
        const intervalRows = (check.monitoring_interval_view || []).map((item) => {
          const conditions = (item.required_conditions || []).join(" / ") || "条件未設定";
          const actions = (item.pre_actions || []).join(" / ") || "事前対応未設定";
          return `${monitoringIntervalLabel(item.interval)}: ${holdabilityLabel(item.holdability)} / 条件: ${conditions} / 事前対応: ${actions}`;
        });
        return `
          <div class="subtle">中長期持ち越し・非監視期間リスク</div>
          <div class="chips">
            <span class="chip ${check.can_hold_without_daily_monitoring === "no" ? "warn" : "info"}">毎日見られない前提: ${escapeHtml(dailyMonitoringHoldLabel(check.can_hold_without_daily_monitoring))}</span>
            <span class="chip ${check.non_monitoring_hold_risk === "high" ? "warn" : ""}">非監視期間リスク ${escapeHtml(riskLevelLabel(stock.non_monitoring_hold_risk || check.non_monitoring_hold_risk))}</span>
            <span class="chip">事業仮説 ${escapeHtml(riskLevelLabel(check.business_thesis_strength))}</span>
            <span class="chip ${check.event_risk_while_unmonitored === "high" ? "warn" : ""}">イベント ${escapeHtml(riskLevelLabel(check.event_risk_while_unmonitored))}</span>
            <span class="chip">流動性 ${escapeHtml(riskLevelLabel(check.liquidity_risk))}</span>
            <span class="chip">ボラ ${escapeHtml(riskLevelLabel(check.volatility_risk))}</span>
            <span class="chip">コア玉適性 ${escapeHtml(riskLevelLabel(check.core_position_suitability))}</span>
            <span class="chip">短期玉を外す ${escapeHtml(nullableBooleanLabel(check.short_term_position_should_be_removed))}</span>
          </div>
          ${check.position_size_view ? `<p>${escapeHtml(check.position_size_view)}</p>` : ""}
          ${check.required_alerts?.length ? `<div class="subtle">必要なアラート</div>${renderCompactList(check.required_alerts)}` : ""}
          ${check.must_check_dates_or_events?.length ? `<div class="subtle">必ず確認すべき日付・イベント</div>${renderCompactList(check.must_check_dates_or_events)}` : ""}
          ${check.reduce_before_events?.length ? `<div class="subtle">事前に縮小すべきイベント</div>${renderCompactList(check.reduce_before_events)}` : ""}
          ${check.stop_or_reduce_conditions?.length ? `<div class="subtle">縮小・停止条件</div>${renderCompactList(check.stop_or_reduce_conditions)}` : ""}
          ${check.long_term_thesis_break_conditions?.length ? `<div class="subtle">中長期仮説が崩れる条件</div>${renderCompactList(check.long_term_thesis_break_conditions)}` : ""}
          ${intervalRows.length ? `<div class="subtle">期間別の保有可否</div>${renderCompactList(intervalRows)}` : ""}
          <div class="subtle">最終中長期持ち越し判断</div>
          <p>${escapeHtml(longTermCarryDecisionLabel(check.final_long_term_carry_decision))}${check.final_note ? `：${escapeHtml(check.final_note)}` : ""}</p>
        `;
      };

      const setPortfolioAiButtonsDisabled = (disabled) => {
        document.querySelectorAll("[data-stock-ai-run]").forEach((button) => {
          button.disabled = disabled;
        });
      };

      const parseTickerInput = () => {
        const value = document.getElementById("stock-ai-tickers")?.value || "";
        return value
          .split(/[,\s]+/)
          .map((item) => item.trim())
          .filter(Boolean);
      };

      const selectedWatchlistItems = () => {
        const items = state.data?.watchlist_items || [];
        return items.filter((item) => state.selectedWatchlistTickers.has(item.ticker_code));
      };

      const selectedStockAiHoldings = () => {
        const selectedItems = selectedWatchlistItems();
        const selectedByCheckbox = selectedItems.map((item) => ({
          ticker: item.ticker_code,
          name: item.name,
          market: item.market,
          quantity: 0,
          average_price: null,
        }));
        const known = new Map([
          ...(state.data?.portfolio_items || []).map((item) => [item.ticker_code, item]),
          ...(state.data?.watchlist_items || []).map((item) => [item.ticker_code, item]),
        ]);
        const manual = parseTickerInput().map((ticker) => {
          const item = known.get(ticker);
          return {
            ticker,
            name: item?.name || ticker,
            market: item?.market || "TSE",
            quantity: Number(item?.quantity || 0),
            average_price: item?.average_cost ? Number(item.average_cost) : null,
          };
        });
        const merged = new Map();
        [...selectedByCheckbox, ...manual].forEach((item) => merged.set(item.ticker, item));
        return Array.from(merged.values());
      };

      const estimateStockAiCost = () => {
        const mode = document.getElementById("stock-ai-mode")?.value || "judge";
        const target = document.getElementById("stock-ai-target")?.value || "holdings";
        const includeWebSearch = document.getElementById("portfolio-ai-web-search")?.checked ?? false;
        const webCalls = Number(document.getElementById("stock-ai-max-web-search")?.value || 0);
        const counts = {
          holdings: (state.data?.portfolio_items || []).length || 7,
          watchlist: (state.data?.watchlist_items || []).length || 0,
          candidates: 2,
          selected: selectedStockAiHoldings().length,
          mock: 9,
        };
        const count = counts[target] ?? 0;
        if (target === "mock") {
          return { count, estimate: 0 };
        }
        const base = { scanner: 0.006, analyst: 0.02, judge: 0.045, critical: 0.075, prompt_only: 0 }[mode] ?? 0.02;
        const perStock = { scanner: 0.002, analyst: 0.007, judge: 0.005, critical: 0.012, prompt_only: 0 }[mode] ?? 0.004;
        const estimate = mode === "prompt_only" ? 0 : base + perStock * count + (includeWebSearch ? 0.01 * webCalls : 0);
        return { count, estimate };
      };

      const updateStockAiCost = () => {
        const element = document.getElementById("stock-ai-cost");
        if (!element) return;
        const { count, estimate } = estimateStockAiCost();
        element.textContent = `今回の事前概算 $${estimate.toFixed(3)} / ${count}銘柄`;
      };

      const nonNegativeInteger = (value) => {
        const parsed = Number(value);
        return Number.isFinite(parsed) ? Math.max(0, Math.trunc(parsed)) : 0;
      };

      const estimatedUsd = (value) => {
        const parsed = Number(value);
        return Number.isFinite(parsed) && parsed >= 0 ? `$${parsed.toFixed(4)}` : "$--";
      };

      const renderStockAiUsage = () => {
        const usage = state.stockAiUsage;
        const unpricedElement = document.getElementById("stock-ai-usage-unpriced");
        const historyElement = document.getElementById("stock-ai-usage-history-note");
        if (usage.status === "loading" && !usage.data) {
          text("stock-ai-usage-today", "本日の利用量を読み込み中...");
          text("stock-ai-usage-month", "今月の利用量を読み込み中...");
          if (unpricedElement) unpricedElement.hidden = true;
          if (historyElement) historyElement.hidden = true;
          return;
        }
        if (!usage.data) {
          text("stock-ai-usage-today", "本日の利用量を取得できませんでした。");
          text("stock-ai-usage-month", "今月の利用量を取得できませんでした。");
          if (unpricedElement) {
            unpricedElement.textContent = "利用量APIを確認してください。AI分析そのものの結果とは別の表示エラーです。";
            unpricedElement.hidden = false;
          }
          if (historyElement) historyElement.hidden = true;
          return;
        }

        const summary = usage.data;
        const dailyLimit = nonNegativeInteger(summary.daily_limit);
        const todayRuns = nonNegativeInteger(summary.today?.review_runs);
        const todayApiCalls = nonNegativeInteger(summary.today?.api_calls);
        const monthRuns = nonNegativeInteger(summary.month?.review_runs);
        const monthApiCalls = nonNegativeInteger(summary.month?.api_calls);
        const remaining = Number.isFinite(Number(summary.remaining_today))
          ? nonNegativeInteger(summary.remaining_today)
          : Math.max(0, dailyLimit - todayRuns);
        text(
          "stock-ai-usage-today",
          `本日 成功レビュー ${todayRuns} / ${dailyLimit}回・残り ${remaining}・OpenAI呼出 ${todayApiCalls}回・概算 ${estimatedUsd(summary.today?.estimated_cost_usd)}`,
        );
        text(
          "stock-ai-usage-month",
          `今月 成功レビュー ${monthRuns}回・OpenAI呼出 ${monthApiCalls}回・概算 ${estimatedUsd(summary.month?.estimated_cost_usd)}`,
        );

        const todayUnpriced = nonNegativeInteger(summary.today?.unpriced_api_calls);
        const monthUnpriced = nonNegativeInteger(summary.month?.unpriced_api_calls);
        if (unpricedElement) {
          unpricedElement.textContent = todayUnpriced || monthUnpriced
            ? `金額未算定のAPI呼び出し: 本日 ${todayUnpriced}回・今月 ${monthUnpriced}回`
            : "";
          unpricedElement.hidden = !(todayUnpriced || monthUnpriced);
        }
        if (historyElement) {
          historyElement.textContent = summary.incomplete_pre_v2_history
            ? "旧形式のカウンターは新集計へ移行していません。更新前の回数・金額は含まれません。"
            : "";
          historyElement.hidden = !summary.incomplete_pre_v2_history;
        }
      };

      const loadStockAiUsage = async () => {
        state.stockAiUsage = { ...state.stockAiUsage, status: "loading", error: null };
        renderStockAiUsage();
        try {
          const payload = await fetchJson("/api/ai/stock-review/usage");
          state.stockAiUsage = { status: "success", data: payload, error: null };
        } catch (error) {
          state.stockAiUsage = {
            status: "failed",
            data: null,
            error: error.message || String(error),
          };
        }
        renderStockAiUsage();
      };

      const syncStockAiPrompt = (prompt = "") => {
        state.lastManualPrompt = prompt || "";
        const output = document.getElementById("stock-ai-prompt-output");
        const copyButton = document.getElementById("stock-ai-copy-prompt");
        if (output) output.value = state.lastManualPrompt;
        if (copyButton) copyButton.disabled = !state.lastManualPrompt;
      };

      const buildStockAiRequest = (modeOverride = null) => {
        const modeInput = document.getElementById("stock-ai-mode");
        if (modeOverride && modeOverride !== "prompt_only" && modeInput) {
          modeInput.value = modeOverride;
        }
        const mode = modeOverride === "prompt_only" ? "prompt_only" : (modeInput?.value || "judge");
        const target = document.getElementById("stock-ai-target")?.value || "holdings";
        const webSearchInput = document.getElementById("portfolio-ai-web-search");
        if (mode === "scanner" || target === "mock") {
          if (webSearchInput) webSearchInput.checked = false;
        }
        const includeWebSearch = target === "mock" ? false : (webSearchInput?.checked ?? false);
        const mockResponse = document.getElementById("portfolio-ai-mock-response")?.checked ?? false;
        const maxWebSearchCalls = Number(document.getElementById("stock-ai-max-web-search")?.value || 0);
        const saveResult = document.getElementById("stock-ai-save-result")?.checked ?? true;
        const useCache = document.getElementById("stock-ai-use-cache")?.checked ?? true;
        const userHypothesis = document.getElementById("stock-ai-user-hypothesis")?.value?.trim() || null;
        const positionIntent = document.getElementById("stock-ai-position-intent")?.value || null;
        const holdings = target === "selected" ? selectedStockAiHoldings() : [];
        const tickers = target === "selected" ? holdings.map((item) => item.ticker) : parseTickerInput();
        return {
          mode,
          target,
          tickers,
          use_mock_holdings: target === "mock",
          holdings,
          include_web_search: includeWebSearch,
          risk_preference: "balanced",
          max_web_search_calls: maxWebSearchCalls,
          save_result: saveResult,
          use_cache: useCache,
          mock_response: mockResponse,
          verbosity: mode === "scanner" ? "short" : mode === "critical" ? "detailed" : "normal",
          user_hypothesis: userHypothesis,
          position_intent: positionIntent,
        };
      };

      const isHighCostStockAiRequest = (payload) => (
        payload.target !== "mock" && (["judge", "critical"].includes(payload.mode)
        || payload.include_web_search
        || estimateStockAiCost().count > 10)
      );

      const renderPortfolioAiReview = () => {
        const feedback = document.getElementById("portfolio-ai-review-feedback");
        const review = state.portfolioAiReview;
        if (feedback) {
          const tone = ["missing_api_key", "json_parse_failed", "openai_api_error", "openai_sdk_missing", "no_holdings", "target_limit_exceeded", "daily_limit_exceeded", "failed"].includes(review.status)
            ? "error"
            : review.status === "success"
              ? "success"
              : "";
          feedback.className = tone ? `search-feedback ${tone}` : "search-feedback";
          feedback.textContent = aiReviewResultStatusLabel(review.data || { status: review.status });
        }

        if (review.status === "idle") {
          fill("portfolio-ai-review-results", "");
          return;
        }
        if (review.status === "loading") {
          fill("portfolio-ai-review-results", '<article class="ai-review-card">保有銘柄を分析中...</article>');
          syncStockAiPrompt("");
          return;
        }
        if (review.status === "failed") {
          fill("portfolio-ai-review-results", `<article class="ai-review-card error">分析に失敗しました: ${escapeHtml(review.error || "")}</article>`);
          return;
        }

        const data = review.data;
        if (!data) {
          fill("portfolio-ai-review-results", "");
          return;
        }
        syncStockAiPrompt(data.manual_prompt || "");
        const status = data.status || "success";
        if (status !== "success") {
          const rawOutput = data.raw_model_output
            ? `<div class="subtle" style="margin-top: 10px;">OpenAI生応答</div><pre class="empty">${escapeHtml(String(data.raw_model_output).slice(0, 20000))}</pre>`
            : "";
          fill("portfolio-ai-review-results", `
            <article class="ai-review-card error">
              <div class="meta">
                <strong>${escapeHtml(aiReviewResultStatusLabel(data))}</strong>
                <span class="chip warn">${escapeHtml(aiHoldingsSourceLabel(data.holdings_source))}</span>
              </div>
              <p>${escapeHtml(data.error?.message || data.portfolio_summary?.overall_view || "分析できませんでした。")}</p>
              ${rawOutput}
            </article>
          `);
          updateStockAiCost();
          return;
        }

        const summary = data.portfolio_summary || {};
        const chips = [
          data.mode ? aiModeLabel(data.mode) : "",
          data.web_search_used ? "Web検索あり" : "Web検索なしの簡易分析",
          data.mock_response ? "API非呼び出しmock" : "OpenAI API",
          data.model ? `model ${data.model}` : "",
          data.reasoning_effort ? `reasoning ${data.reasoning_effort}` : "",
          data.web_search_policy ? `web policy ${data.web_search_policy}` : "",
          data.estimated_cost_usd != null ? `今回の事前概算 $${Number(data.estimated_cost_usd || 0).toFixed(4)}` : "",
          data.actual_usage?.web_search_calls ? `Web検索 ${data.actual_usage.web_search_calls}回` : "",
          data.cache_hit ? "前回結果" : "",
          aiHoldingsSourceLabel(data.holdings_source),
        ].filter(Boolean);
        const stockCards = (data.stocks || []).map((stock) => `
          <article class="ai-review-card">
            <div class="meta">
              <div>
                <strong>${escapeHtml(stock.name)}</strong>
                <div class="subtle">${escapeHtml(stock.ticker)}</div>
              </div>
              <span class="judgement-badge ${escapeAttr(stock.judgement)}">${escapeHtml(stock.judgement_label || aiJudgementLabel(stock.judgement))}</span>
            </div>
            <div class="chips">
              <span class="chip">${escapeHtml(stock.judgement)}</span>
              <span class="chip info">confidence ${escapeHtml(formatNumber(Number(stock.confidence || 0) * 100, 0))}%</span>
              ${stock.needs_detail_analysis ? '<span class="chip warn">詳細分析候補</span>' : ""}
              ${stock.needs_analyst_mode ? '<span class="chip warn">analyst推奨</span>' : ""}
              ${stock.needs_judge_mode ? '<span class="chip warn">judge推奨</span>' : ""}
              ${longTermCarryWarningChip(stock)}
              ${(stock.verification_labels || []).map((label) => `<span class="chip">${escapeHtml(label)}</span>`).join("")}
            </div>
            ${stock.time_horizon_views && Object.keys(stock.time_horizon_views).length ? `<div class="subtle">時間軸別判断</div>${renderCompactList(Object.entries(stock.time_horizon_views).map(([key, value]) => `${key}: ${value}`))}` : ""}
            ${stock.short_reason ? `<div class="subtle">短評</div><p>${escapeHtml(stock.short_reason)}</p>` : ""}
            ${stock.key_risks?.length ? `<div class="subtle">主要リスク</div>${renderCompactList(stock.key_risks)}` : ""}
            <div class="subtle">今日見るべきポイント</div>
            ${renderCompactList([...(stock.key_points || []), ...(stock.watch_points || [])])}
            ${stock.risk_flags?.length ? `<div class="subtle">警戒フラグ</div>${renderCompactList(stock.risk_flags)}` : ""}
            ${renderLongTermCarrySection(stock)}
            ${stock.technical_view ? `<div class="subtle">テクニカル所見</div><p>${escapeHtml(stock.technical_view)}</p>` : ""}
            ${stock.news_view ? `<div class="subtle">材料・ニュース所見</div><p>${escapeHtml(stock.news_view)}</p>` : ""}
            ${stock.market_context_view ? `<div class="subtle">地合い</div><p>${escapeHtml(stock.market_context_view)}</p>` : ""}
            ${stock.supply_demand_view ? `<div class="subtle">需給</div><p>${escapeHtml(stock.supply_demand_view)}</p>` : ""}
            ${stock.holder_action ? `<div class="subtle">保有者向けアクション</div><p>${escapeHtml(stock.holder_action)}</p>` : ""}
            ${stock.buy_more_condition ? `<div class="subtle">買増し条件</div><p>${escapeHtml(stock.buy_more_condition)}</p>` : ""}
            ${stock.take_profit_condition ? `<div class="subtle">利確条件</div><p>${escapeHtml(stock.take_profit_condition)}</p>` : ""}
            ${stock.stop_or_reduce_condition ? `<div class="subtle">縮小・撤退条件</div><p>${escapeHtml(stock.stop_or_reduce_condition)}</p>` : ""}
            ${stock.invalidation ? `<div class="subtle">反証条件</div><p>${escapeHtml(stock.invalidation)}</p>` : ""}
            ${stock.next_price_levels?.length ? `<div class="subtle">次に見る価格帯</div>${renderCompactList(stock.next_price_levels)}` : ""}
            ${stock.bullish_case ? `<div class="subtle">強気シナリオ</div><p>${escapeHtml(stock.bullish_case)}</p>` : ""}
            ${stock.bearish_case ? `<div class="subtle">弱気シナリオ</div><p>${escapeHtml(stock.bearish_case)}</p>` : ""}
            ${stock.base_case ? `<div class="subtle">中立シナリオ</div><p>${escapeHtml(stock.base_case)}</p>` : ""}
            ${stock.expected_value_view ? `<div class="subtle">期待値</div><p>${escapeHtml(stock.expected_value_view)}</p>` : ""}
            ${stock.position_size_risk ? `<div class="subtle">ポジションサイズ</div><p>${escapeHtml(stock.position_size_risk)}</p>` : ""}
            ${stock.event_risk ? `<div class="subtle">イベントリスク</div><p>${escapeHtml(stock.event_risk)}</p>` : ""}
            ${stock.gap_risk ? `<div class="subtle">ギャップリスク</div><p>${escapeHtml(stock.gap_risk)}</p>` : ""}
            ${stock.decision_deadline ? `<div class="subtle">判断期限</div><p>${escapeHtml(stock.decision_deadline)}</p>` : ""}
            ${stock.what_would_change_my_mind ? `<div class="subtle">見立て変更条件</div><p>${escapeHtml(stock.what_would_change_my_mind)}</p>` : ""}
            ${stock.final_recommendation_for_holder ? `<div class="subtle">保有者向け最終整理</div><p>${escapeHtml(stock.final_recommendation_for_holder)}</p>` : ""}
            ${stock.uncertainty_notes ? `<div class="subtle">不確実性</div><p>${escapeHtml(stock.uncertainty_notes)}</p>` : ""}
            ${stock.execution_plan?.length ? `<div class="subtle">具体的な執行案</div>${renderCompactList(stock.execution_plan)}` : ""}
            ${stock.critical_check?.length ? `<div class="subtle">辛口チェック</div>${renderCompactList(stock.critical_check)}` : ""}
            ${(stock.risks || []).length ? `<div class="subtle">リスク</div>${renderCompactList(stock.risks || [])}` : ""}
            ${renderAiSources(stock.sources || [])}
          </article>
        `).join("");

        fill("portfolio-ai-review-results", `
          <article class="ai-review-card ai-review-summary">
            <div class="meta">
              <strong>${escapeHtml(aiModeLabel(data.mode))}</strong>
              <span class="subtle">${escapeHtml(formatDateTime(data.generated_at))}</span>
            </div>
            <p>${escapeHtml(summary.overall_view || summary.portfolio_summary || "")}</p>
            <div class="chips">
              ${chips.map((chip) => `<span class="chip">${escapeHtml(chip)}</span>`).join("")}
              <span class="chip ${summary.overall_risk === "high" ? "warn" : "info"}">risk ${escapeHtml(summary.overall_risk || "-")}</span>
              <span class="chip">${escapeHtml(summary.market_temperature || "-")}</span>
            </div>
            ${renderCompactList(summary.top_risks || [])}
            ${renderCompactList(summary.action_plan_today || [])}
            ${summary.non_monitoring_reduce_candidates?.length ? `<div class="subtle">毎日見られないなら縮小すべき銘柄</div>${renderCompactList(summary.non_monitoring_reduce_candidates)}` : ""}
            ${summary.core_position_candidates?.length ? `<div class="subtle">コア玉として残せる銘柄</div>${renderCompactList(summary.core_position_candidates)}` : ""}
            ${summary.exit_or_rotate_candidates?.length ? `<div class="subtle">入れ替え候補</div>${renderCompactList(summary.exit_or_rotate_candidates)}` : ""}
            ${data.action_plan?.length ? `<div class="subtle">具体的な執行案</div>${renderCompactList(data.action_plan)}` : ""}
            ${data.critical_warnings?.length ? `<div class="subtle">重要警告</div>${renderCompactList(data.critical_warnings)}` : ""}
            ${summary.cash_allocation_view ? `<div class="subtle">資金配分</div><p>${escapeHtml(summary.cash_allocation_view)}</p>` : ""}
            ${summary.concentration_risk ? `<div class="subtle">集中リスク</div><p>${escapeHtml(summary.concentration_risk)}</p>` : ""}
            ${summary.invalidation_for_portfolio ? `<div class="subtle">全体の反証条件</div><p>${escapeHtml(summary.invalidation_for_portfolio)}</p>` : ""}
            ${data.warnings?.length ? `<div class="subtle">警告</div>${renderCompactList(data.warnings)}` : ""}
            ${data.raw_model_output ? `<div class="subtle">OpenAI生応答</div><pre class="empty">${escapeHtml(String(data.raw_model_output).slice(0, 20000))}</pre>` : ""}
            ${renderAiSources(data.sources || [])}
          </article>
          ${stockCards}
        `);
        updateStockAiCost();
      };

      const runPortfolioAiReview = async (modeOverride = null) => {
        const payloadBody = buildStockAiRequest(modeOverride);
        if (payloadBody.target === "selected" && !payloadBody.holdings.length && !payloadBody.tickers.length) {
          state.portfolioAiReview = { status: "failed", data: null, error: "AI分析する選択銘柄を指定してください。" };
          renderPortfolioAiReview();
          return;
        }
        if (!payloadBody.mock_response && payloadBody.mode !== "prompt_only" && isHighCostStockAiRequest(payloadBody)) {
          const ok = window.confirm("高コスト設定です。対象銘柄数、Web検索、モードを確認して実行しますか。");
          if (!ok) return;
        }
        state.portfolioAiReview = { status: "loading", data: null, error: null };
        setPortfolioAiButtonsDisabled(true);
        renderPortfolioAiReview();
        try {
          const payload = await postJson("/api/ai/stock-review", payloadBody);
          state.portfolioAiReview = {
            status: payload.status || "success",
            data: payload,
            error: null,
          };
        } catch (error) {
          state.portfolioAiReview = {
            status: "failed",
            data: null,
            error: error.message || String(error),
          };
        } finally {
          setPortfolioAiButtonsDisabled(false);
          renderPortfolioAiReview();
          await loadStockAiUsage();
        }
      };

      const setupStockAiControls = () => {
        const syncWebSearchDefaultForMode = () => {
          const mode = document.getElementById("stock-ai-mode")?.value || "judge";
          const target = document.getElementById("stock-ai-target")?.value || "holdings";
          const webSearch = document.getElementById("portfolio-ai-web-search");
          if (!webSearch) return;
          webSearch.checked = target !== "mock" && ["analyst", "judge", "critical"].includes(mode);
          updateStockAiCost();
        };
        [
          "stock-ai-mode",
          "stock-ai-target",
          "stock-ai-tickers",
          "stock-ai-max-web-search",
          "stock-ai-user-hypothesis",
          "stock-ai-position-intent",
          "portfolio-ai-web-search",
          "portfolio-ai-mock-response",
          "stock-ai-save-result",
          "stock-ai-use-cache",
        ].forEach((id) => {
          const element = document.getElementById(id);
          if (!element) return;
          element.addEventListener("input", updateStockAiCost);
          element.addEventListener("change", updateStockAiCost);
        });
        document.getElementById("stock-ai-mode")?.addEventListener("change", syncWebSearchDefaultForMode);
        document.getElementById("stock-ai-target")?.addEventListener("change", syncWebSearchDefaultForMode);
        syncWebSearchDefaultForMode();
        updateStockAiCost();
      };

      const setWatchlistAiButtonsDisabled = (disabled) => {
        document.querySelectorAll("[data-watchlist-ai-review], [data-watchlist-ai-select-all], [data-watchlist-ai-clear]").forEach((button) => {
          button.disabled = disabled;
        });
      };

      const renderWatchlistAiReview = () => {
        const feedback = document.getElementById("watchlist-ai-review-feedback");
        const review = state.watchlistAiReview;
        if (feedback) {
          const tone = ["missing_api_key", "json_parse_failed", "openai_api_error", "openai_sdk_missing", "no_holdings", "failed"].includes(review.status)
            ? "error"
            : review.status === "success"
              ? "success"
              : "";
          feedback.className = tone ? `search-feedback ${tone}` : "search-feedback";
          feedback.textContent = aiReviewResultStatusLabel(review.data || { status: review.status });
        }

        if (review.status === "idle") {
          fill("watchlist-ai-review-results", "");
          return;
        }
        if (review.status === "loading") {
          fill("watchlist-ai-review-results", '<article class="ai-review-card">選択ウォッチリストを分析中...</article>');
          return;
        }
        if (review.status === "failed") {
          fill("watchlist-ai-review-results", `<article class="ai-review-card error">分析に失敗しました: ${escapeHtml(review.error || "")}</article>`);
          return;
        }

        const data = review.data;
        if (!data) {
          fill("watchlist-ai-review-results", "");
          return;
        }
        const status = data.status || "success";
        if (status !== "success") {
          const rawOutput = data.raw_model_output
            ? `<div class="subtle" style="margin-top: 10px;">raw_model_output</div><pre class="empty">${escapeHtml(String(data.raw_model_output).slice(0, 1200))}</pre>`
            : "";
          fill("watchlist-ai-review-results", `
            <article class="ai-review-card error">
              <div class="meta">
                <strong>${escapeHtml(aiReviewResultStatusLabel(data))}</strong>
                <span class="chip warn">${escapeHtml(aiHoldingsSourceLabel(data.holdings_source))}</span>
              </div>
              <p>${escapeHtml(data.error?.message || data.portfolio_summary?.overall_view || "分析できませんでした。")}</p>
              ${rawOutput}
            </article>
          `);
          return;
        }

        const summary = data.portfolio_summary || {};
        const chips = [
          data.web_search_used ? "Web検索あり" : "Web検索なしの簡易分析",
          data.mock_response ? "API非呼び出しmock" : "OpenAI API",
          data.model ? `model ${data.model}` : "",
          data.reasoning_effort ? `reasoning ${data.reasoning_effort}` : "",
          data.estimated_cost_usd != null ? `今回の事前概算 $${Number(data.estimated_cost_usd || 0).toFixed(4)}` : "",
          data.actual_usage?.web_search_calls ? `Web検索 ${data.actual_usage.web_search_calls}回` : "",
          aiHoldingsSourceLabel(data.holdings_source),
          "選択ウォッチリスト",
        ].filter(Boolean);
        const stockCards = (data.stocks || []).map((stock) => `
          <article class="ai-review-card">
            <div class="meta">
              <div>
                <strong>${escapeHtml(stock.name)}</strong>
                <div class="subtle">${escapeHtml(stock.ticker)}</div>
              </div>
              <span class="judgement-badge ${escapeAttr(stock.judgement)}">${escapeHtml(stock.judgement_label || aiJudgementLabel(stock.judgement))}</span>
            </div>
            <div class="chips">
              <span class="chip">${escapeHtml(stock.judgement)}</span>
              <span class="chip info">confidence ${escapeHtml(formatNumber(Number(stock.confidence || 0) * 100, 0))}%</span>
              ${longTermCarryWarningChip(stock)}
            </div>
            <div class="subtle">今日見るべきポイント</div>
            ${renderCompactList(stock.key_points || [])}
            ${renderLongTermCarrySection(stock)}
            <div class="subtle">テクニカル所見</div>
            <p>${escapeHtml(stock.technical_view)}</p>
            <div class="subtle">材料・ニュース所見</div>
            <p>${escapeHtml(stock.news_view)}</p>
            <div class="subtle">保有者向けアクション</div>
            <p>${escapeHtml(stock.holder_action)}</p>
            <div class="subtle">反証条件</div>
            <p>${escapeHtml(stock.invalidation)}</p>
            <div class="subtle">リスク</div>
            ${renderCompactList(stock.risks || [])}
            ${renderAiSources(stock.sources || [])}
          </article>
        `).join("");

        fill("watchlist-ai-review-results", `
          <article class="ai-review-card ai-review-summary">
            <div class="meta">
              <strong>Watchlist AI Review</strong>
              <span class="subtle">${escapeHtml(formatDateTime(data.generated_at))}</span>
            </div>
            <p>${escapeHtml(summary.overall_view || "")}</p>
            <div class="chips">
              ${chips.map((chip) => `<span class="chip">${escapeHtml(chip)}</span>`).join("")}
              <span class="chip ${summary.overall_risk === "high" ? "warn" : "info"}">risk ${escapeHtml(summary.overall_risk || "-")}</span>
              <span class="chip">${escapeHtml(summary.market_temperature || "-")}</span>
            </div>
            ${renderCompactList(summary.top_risks || [])}
          </article>
          ${stockCards}
        `);
      };

      const runWatchlistAiReview = async () => {
        const selectedItems = selectedWatchlistItems();
        if (!selectedItems.length) {
          state.watchlistAiReview = { status: "failed", data: null, error: "AI分析するウォッチリスト銘柄を選択してください。" };
          renderWatchlistAiReview();
          return;
        }

        const includeWebSearch = document.getElementById("watchlist-ai-web-search")?.checked ?? true;
        const mockResponse = document.getElementById("watchlist-ai-mock-response")?.checked ?? false;
        state.watchlistAiReview = { status: "loading", data: null, error: null };
        setWatchlistAiButtonsDisabled(true);
        renderWatchlistAiReview();
        try {
          const payload = await postJson("/portfolio/ai-review", {
            use_mock_holdings: false,
            holdings: selectedItems.map((item) => ({
              ticker: item.ticker_code,
              name: item.name,
              market: item.market,
              quantity: 1,
              average_price: null,
            })),
            analysis_mode: "daily",
            risk_preference: "balanced",
            include_web_search: includeWebSearch,
            mock_response: mockResponse,
          });
          state.watchlistAiReview = {
            status: payload.status || "success",
            data: payload,
            error: null,
          };
        } catch (error) {
          state.watchlistAiReview = {
            status: "failed",
            data: null,
            error: error.message || String(error),
          };
        } finally {
          setWatchlistAiButtonsDisabled(false);
          renderWatchlistAiReview();
          await loadStockAiUsage();
        }
      };

      const notifyNewTabBlocked = () => {
        const message = "新しいタブの表示がブロックされました。ブラウザのポップアップ設定を確認してください。";
        if (PAGE_MODE === "top") {
          setSearchFeedback(message, "error");
          return;
        }
        console.warn(message);
      };

      const openSecurityDetail = (tickerCode) => {
        if (!tickerCode) return;
        const detailWindow = window.open(detailPageUrl(tickerCode), "_blank", "noopener");
        if (detailWindow) {
          detailWindow.opener = null;
          return;
        }
        notifyNewTabBlocked();
      };

      const renderHero = (data) => {
        text("hero-comment", data.market_overview.separation_hint);
        text("market-label", `${data.market_overview.label} (${data.market_overview.breadth})`);
        text("market-score", `${data.market_overview.score}`);
        text("market-comment", data.market_overview.comment);
        text("disclaimer", `${data.disclaimer} / 更新 ${formatDateTime(data.generated_at)}`);

        fill("hero-pills", `
          <div class="pill"><strong>${escapeHtml(data.mode === "mock" ? "mock" : "live")}</strong><span>mode</span></div>
          <div class="pill"><strong>${escapeHtml(formatDate(data.target_date))}</strong><span>target date</span></div>
          <div class="pill"><strong>${escapeHtml(data.market_overview.breadth_ratio)}</strong><span>breadth</span></div>
        `);

        fill("metric-grid", (data.metrics || []).map((item) => `
          <article class="kpi">
            <div class="subtle">${escapeHtml(item.label)}</div>
            <strong>${escapeHtml(item.value)}</strong>
            <div class="subtle">${escapeHtml(item.note)}</div>
          </article>
        `).join(""));

        fill("status-grid", (data.status_counts || []).map((item) => `
          <article class="status-card">
            <div class="subtle">${escapeHtml(item.status)}</div>
            <strong>${escapeHtml(item.count)}</strong>
            <div class="subtle">${escapeHtml(item.note)}</div>
          </article>
        `).join(""));

        fill("market-cautions", (data.market_overview.caution_tags || []).map((tag) => `
          <span class="chip ${tag.includes("警戒") ? "warn" : ""}">${escapeHtml(tag)}</span>
        `).join(""));
      };

      const renderPriority = (items) => {
        if (!items.length) {
          fill("priority-grid", `<div class="empty">watchlist に登録済みの銘柄があると、ここに重要度順で並びます。</div>`);
          return;
        }
        fill("priority-grid", items.map((item) => `
          <article class="priority-card" data-select-ticker="${escapeAttr(item.ticker_code)}">
            <div class="meta">
              <div class="company">
                <h3>${escapeHtml(item.name)}</h3>
                <div class="ticker">${escapeHtml(item.ticker_code)} / ${escapeHtml(item.market ?? "-")}</div>
              </div>
              <div class="score-chip">${escapeHtml(item.attention.score)}</div>
            </div>
            <div class="chips">
              <span class="chip">${escapeHtml(item.status)}</span>
              <span class="chip ${statusChip(item.risk.score)}">リスク ${escapeHtml(item.risk.label)}</span>
            </div>
            <p>${escapeHtml(item.status_note)}</p>
            <div class="tags">
              ${(item.why_now_tags || []).map((tag) => `<span class="tag">${escapeHtml(tag)}</span>`).join("")}
              ${(item.alert_tags || []).slice(0, 2).map((tag) => `<span class="tag warn">${escapeHtml(tag)}</span>`).join("")}
            </div>
            <div class="subtle">材料: ${escapeHtml(item.material_summary)}</div>
            <div class="subtle">地合い/個別: ${escapeHtml(item.factor_summary)}</div>
            <div class="subtle">反証: ${escapeHtml(item.rebuttal_summary)}</div>
          </article>
        `).join(""));
      };

      const renderPortfolio = (items) => {
        if (!items.length) {
          fill("portfolio-list", `
            <article class="portfolio-card">
              <strong>保有銘柄はまだ登録されていません。</strong>
              <div class="subtle">ticker、数量、平均取得単価を入れると評価額をここに表示します。</div>
            </article>
          `);
          return;
        }
        fill("portfolio-list", items.map((item) => {
          const quantity = Number(item.quantity);
          const averageCost = Number(item.average_cost);
          const lastPrice = Number(item.last_price);
          const marketValue = Number(item.market_value);
          const unrealizedPnl = Number(item.unrealized_pnl);
          const unrealizedReturnPct = Number(item.unrealized_return_pct);
          return `
            <article class="portfolio-card">
              <div class="meta">
                <div>
                  <strong>${escapeHtml(item.name)}</strong>
                  <div class="subtle">${escapeHtml(item.ticker_code)} / ${escapeHtml(item.market ?? "-")}</div>
                </div>
                <button class="ghost-button" type="button" data-remove-portfolio="${escapeAttr(item.ticker_code)}">削除</button>
              </div>
              <div class="subtle">数量 ${escapeHtml(formatNumber(quantity, quantity % 1 === 0 ? 0 : 4))} / 平均取得 ${escapeHtml(formatNumber(averageCost, 2))} 円</div>
              <div class="subtle">現在値 ${escapeHtml(formatNumber(lastPrice, 2))} 円 / 評価額 ${escapeHtml(formatNumber(marketValue, 0))} 円</div>
              <div class="subtle">評価損益 ${escapeHtml(formatSignedNumber(unrealizedPnl, 0, " 円"))} / ${escapeHtml(formatSignedNumber(unrealizedReturnPct, 2, "%"))}</div>
              <div class="subtle">${escapeHtml(item.note ?? "メモなし")} / 更新 ${escapeHtml(formatDateTime(item.updated_at))}</div>
            </article>
          `;
        }).join(""));
      };

      const renderEvents = (items) => {
        if (!items.length) {
          fill("events-list", `<div class="empty">材料履歴はまだありません。</div>`);
          return;
        }
        fill("events-list", items.map((item) => `
          <article class="event-item" ${item.ticker_code ? `data-select-ticker="${escapeAttr(item.ticker_code)}"` : ""}>
            <div class="meta">
              <strong>${escapeHtml(item.summary)}</strong>
              <span class="chip ${item.stance === "ネガティブ" ? "warn" : ""}">${escapeHtml(item.importance)}</span>
            </div>
            <div class="subtle">${escapeHtml(item.category)} / ${escapeHtml(item.stance)} / ${escapeHtml(item.security_name ?? item.ticker_code ?? "-")}</div>
            <div>${escapeHtml(item.what_changed)}</div>
            <div class="subtle">${escapeHtml(formatDateTime(item.published_at))} / ${escapeHtml(item.source_name)}</div>
            ${renderSourceLinks(item.source_links || [])}
          </article>
        `).join(""));
      };

      const renderAlerts = (items) => {
        if (!items.length) {
          fill("alerts-list", `<div class="empty">重要アラートはありません。</div>`);
          return;
        }
        fill("alerts-list", items.map((item) => `
          <article class="alert-item" data-select-ticker="${escapeAttr(item.ticker_code)}">
            <div class="meta">
              <strong>${escapeHtml(item.title)}</strong>
              <span class="chip ${item.severity === "high" ? "warn" : "info"}">${escapeHtml(item.severity)}</span>
            </div>
            <div>${escapeHtml(item.message)}</div>
            <div class="subtle">${escapeHtml(item.security_name)} / ${escapeHtml(item.action_hint)}</div>
            ${renderSourceLinks(item.source_links || [])}
          </article>
        `).join(""));
      };

      const renderWatchlist = (items) => {
        if (!items.length) {
          fill("watchlist-list", `<div class="empty">watchlist が空です。</div>`);
          return;
        }
        fill("watchlist-list", items.map((item) => `
          <article class="watch-item" data-select-ticker="${escapeAttr(item.ticker_code)}">
            <div class="meta">
              <div class="company">
                <strong>${escapeHtml(item.name)}</strong>
                <div class="subtle">${escapeHtml(item.ticker_code)} / ${escapeHtml(item.market ?? "-")}</div>
              </div>
              <div class="chips">
                <label class="watch-select" data-watchlist-ai-select-label="true">
                  <input
                    type="checkbox"
                    data-watchlist-ai-select="${escapeAttr(item.ticker_code)}"
                    ${state.selectedWatchlistTickers.has(item.ticker_code) ? "checked" : ""}
                  />
                  AI分析
                </label>
                <span class="chip ${item.status === "要警戒" ? "warn" : ""}">${escapeHtml(item.status)}</span>
              </div>
            </div>
            <div>${escapeHtml(item.next_action)}</div>
            <div class="subtle">${escapeHtml(item.thesis_state)} / 更新 ${escapeHtml(formatDateTime(item.updated_at))}</div>
            <div class="subtle">${escapeHtml(item.memo ?? "メモ未記入")}</div>
          </article>
        `).join(""));
      };

      const renderScreening = (items) => {
        if (!items.length) {
          fill("screening-list", `<div class="empty">追加候補はありません。</div>`);
          return;
        }
        fill("screening-list", items.map((item) => `
          <article class="screen-row" data-select-ticker="${escapeAttr(item.ticker_code)}">
            <div>
              <strong>${escapeHtml(item.name)}</strong>
              <div class="subtle">${escapeHtml(publicSecurityCode(item.ticker_code))} / ${escapeHtml(item.market ?? "-")}</div>
            </div>
            <div><span class="score-chip">${escapeHtml(item.total_score.score)}</span></div>
            <div class="subtle">${escapeHtml(item.reason_summary)} / ${escapeHtml(item.caution)}</div>
          </article>
        `).join(""));
      };

      const renderSearchResults = (results, query) => {
        if (!query) {
          fill("watchlist-search-results", `<div class="empty">銘柄名か銘柄コード（数字・英字）で検索してください。</div>`);
          return;
        }
        if (!results.length) {
          fill("watchlist-search-results", `<div class="empty">候補がありません。同期済みの銘柄マスタにある銘柄だけ表示します。</div>`);
          return;
        }
        fill("watchlist-search-results", results.map((item) => `
          <article class="search-result" data-open-ticker="${escapeAttr(item.ticker_code)}">
            <div>
              <strong>${escapeHtml(item.name)}</strong>
              <div class="subtle">${escapeHtml(publicSecurityCode(item.ticker_code))} / ${escapeHtml(item.market ?? "-")}</div>
              ${item.in_watchlist ? `<div class="subtle">watchlist 登録済み</div>` : ""}
            </div>
            <div class="action-row">
              <button
                class="ghost-button"
                type="button"
                data-prepare-portfolio="${escapeAttr(item.ticker_code)}"
              >保有入力へ</button>
              <button
                class="result-button"
                type="button"
                data-open-ticker="${escapeAttr(item.ticker_code)}"
              >詳細を見る</button>
            </div>
          </article>
        `).join(""));
      };

      const renderSearchCandidates = (screeningItems, watchlistItems) => {
        const watchlistTickerSet = new Set((watchlistItems || []).map((item) => item.ticker_code));
        const candidates = (screeningItems || []).filter((item) => !watchlistTickerSet.has(item.ticker_code)).slice(0, 4);
        if (!candidates.length) {
          fill("watchlist-score-candidates", `<div class="empty">watchlist 未登録の高スコア候補はありません。</div>`);
          return;
        }
        fill("watchlist-score-candidates", candidates.map((item) => `
          <article class="search-result" data-select-ticker="${escapeAttr(item.ticker_code)}">
            <div>
              <strong>${escapeHtml(item.name)}</strong>
              <div class="subtle">${escapeHtml(item.ticker_code)} / ${escapeHtml(item.market ?? "-")}</div>
              <div class="subtle">${escapeHtml(item.reason_summary)}</div>
              <div class="subtle">${escapeHtml(item.caution)}</div>
            </div>
            <div class="score-chip">${escapeHtml(item.total_score.score)}</div>
          </article>
        `).join(""));
      };

      const renderSplitBars = (detail) => `
        <div class="split-bars">
          <div class="split-bar">
            <div class="meta"><strong>市場要因</strong><span>${escapeHtml(detail.factor_split.market)}%</span></div>
            <div class="split-track"><div class="split-fill" style="width:${escapeAttr(detail.factor_split.market)}%"></div></div>
          </div>
          <div class="split-bar">
            <div class="meta"><strong>セクター要因</strong><span>${escapeHtml(detail.factor_split.sector)}%</span></div>
            <div class="split-track"><div class="split-fill" style="width:${escapeAttr(detail.factor_split.sector)}%"></div></div>
          </div>
          <div class="split-bar">
            <div class="meta"><strong>個別要因</strong><span>${escapeHtml(detail.factor_split.company)}%</span></div>
            <div class="split-track"><div class="split-fill" style="width:${escapeAttr(detail.factor_split.company)}%"></div></div>
          </div>
        </div>
      `;

      const renderMetricCards = (items) => {
        if (!items.length) {
          return `<div class="empty">指標データはまだありません。</div>`;
        }
        return `<div class="metric-list">${items.map((item) => `
          <article class="detail-card">
            <div class="subtle">${escapeHtml(item.label)}</div>
            <strong>${escapeHtml(item.value)}</strong>
            <div class="subtle">${escapeHtml(item.interpretation)}</div>
          </article>
        `).join("")}</div>`;
      };

      const renderTimeline = (items) => {
        if (!items.length) {
          return `<div class="empty">履歴はまだありません。</div>`;
        }
        return `<div class="timeline">${items.map((item) => `
          <article class="timeline-item detail-card">
            <div class="subtle">${escapeHtml(item.kind)} / ${escapeHtml(formatDateTime(item.occurred_at))}</div>
            <strong>${escapeHtml(item.title)}</strong>
            <div>${escapeHtml(item.detail)}</div>
          </article>
        `).join("")}</div>`;
      };

      const toNumber = (value) => {
        if (typeof value === "number") {
          return Number.isFinite(value) ? value : null;
        }
        if (typeof value === "string" && value.trim()) {
          const parsed = Number(value);
          return Number.isFinite(parsed) ? parsed : null;
        }
        return null;
      };

      const formatNumber = (value, digits = 0) => {
        if (!Number.isFinite(value)) {
          return "--";
        }
        return new Intl.NumberFormat("ja-JP", {
          minimumFractionDigits: digits,
          maximumFractionDigits: digits,
        }).format(value);
      };

      const formatSignedNumber = (value, digits = 0, suffix = "") => {
        if (!Number.isFinite(value)) {
          return "--";
        }
        const prefix = value > 0 ? "+" : "";
        return `${prefix}${formatNumber(value, digits)}${suffix}`;
      };

      const formatChartDate = (value) => {
        if (!value) {
          return "--";
        }
        return String(value).slice(0, 10).replace(/-/g, "/");
      };

      const normalizeChartPoints = (points) => {
        if (!Array.isArray(points)) {
          return [];
        }
        return points.map((item) => {
          const open = toNumber(item.open);
          const high = toNumber(item.high);
          const low = toNumber(item.low);
          const close = toNumber(item.close ?? item.adjusted_close);
          const volume = toNumber(item.volume) ?? 0;
          if ([open, high, low, close].some((value) => value === null)) {
            return null;
          }
          return {
            date: item.target_date ?? item.date,
            open,
            high,
            low,
            close,
            volume,
            direction: close >= open ? "up" : "down",
          };
        }).filter(Boolean);
      };

      const buildChartStats = (points) => {
        if (!points.length) {
          return [];
        }
        const latest = points[points.length - 1];
        const previous = points.length > 1 ? points[points.length - 2] : null;
        const delta = previous ? latest.close - previous.close : null;
        const deltaRate = previous && previous.close ? (delta / previous.close) * 100 : null;
        const highest = Math.max(...points.map((item) => item.high));
        const lowest = Math.min(...points.map((item) => item.low));
        const averageVolume = points.reduce((sum, item) => sum + item.volume, 0) / points.length;
        return [
          {
            label: "\u76f4\u8fd1\u7d42\u5024",
            value: `${formatNumber(latest.close)}\u5186`,
            note: formatChartDate(latest.date),
          },
          {
            label: "\u524d\u65e5\u6bd4",
            value: delta === null ? "--" : `${formatSignedNumber(delta)}\u5186`,
            note: deltaRate === null ? "--" : `${formatSignedNumber(deltaRate, 2, "%")}`,
          },
          {
            label: "\u30ec\u30f3\u30b8",
            value: `${formatNumber(lowest)} - ${formatNumber(highest)}\u5186`,
            note: `${points.length}\u672c`,
          },
          {
            label: "\u5e73\u5747\u51fa\u6765\u9ad8",
            value: formatNumber(averageVolume),
            note: `\u76f4\u8fd1${points.length}\u672c\u5e73\u5747`,
          },
        ];
      };

      const buildSimpleMovingAverageSeries = (points, period) => {
        let rollingSum = 0;
        return points.map((item, index) => {
          rollingSum += item.close;
          if (index >= period) {
            rollingSum -= points[index - period].close;
          }
          if (index + 1 < period) {
            return null;
          }
          return rollingSum / period;
        });
      };

      const buildExponentialMovingAverageSeries = (values, period) => {
        const multiplier = 2 / (period + 1);
        let ema = null;
        return values.map((value) => {
          if (!Number.isFinite(value)) {
            return null;
          }
          if (ema === null) {
            ema = value;
            return ema;
          }
          ema = value * multiplier + ema * (1 - multiplier);
          return ema;
        });
      };

      const buildRsiSeries = (points, period = 14) => {
        if (points.length <= period) {
          return points.map(() => null);
        }
        const result = points.map(() => null);
        let gainSum = 0;
        let lossSum = 0;
        for (let index = 1; index <= period; index += 1) {
          const delta = points[index].close - points[index - 1].close;
          gainSum += delta > 0 ? delta : 0;
          lossSum += delta < 0 ? Math.abs(delta) : 0;
        }
        let averageGain = gainSum / period;
        let averageLoss = lossSum / period;
        result[period] = averageLoss === 0 ? 100 : 100 - (100 / (1 + averageGain / averageLoss));
        for (let index = period + 1; index < points.length; index += 1) {
          const delta = points[index].close - points[index - 1].close;
          const gain = delta > 0 ? delta : 0;
          const loss = delta < 0 ? Math.abs(delta) : 0;
          averageGain = ((averageGain * (period - 1)) + gain) / period;
          averageLoss = ((averageLoss * (period - 1)) + loss) / period;
          result[index] = averageLoss === 0 ? 100 : 100 - (100 / (1 + averageGain / averageLoss));
        }
        return result;
      };

      const buildMacdSeries = (points) => {
        const closes = points.map((item) => item.close);
        const fastEma = buildExponentialMovingAverageSeries(closes, 12);
        const slowEma = buildExponentialMovingAverageSeries(closes, 26);
        const line = closes.map((_, index) => {
          const fast = fastEma[index];
          const slow = slowEma[index];
          if (!Number.isFinite(fast) || !Number.isFinite(slow)) {
            return null;
          }
          return fast - slow;
        });
        const signal = buildExponentialMovingAverageSeries(line, 9);
        const histogram = line.map((value, index) => (
          Number.isFinite(value) && Number.isFinite(signal[index]) ? value - signal[index] : null
        ));
        return { line, signal, histogram };
      };

      const latestFiniteValue = (values) => {
        for (let index = values.length - 1; index >= 0; index -= 1) {
          if (Number.isFinite(values[index])) {
            return values[index];
          }
        }
        return null;
      };

      const sliceChartRange = (points, rangeKey) => {
        const limits = { "20d": 20, "40d": 40 };
        const limit = limits[rangeKey] ?? null;
        const startIndex = limit && points.length > limit ? points.length - limit : 0;
        return {
          rangeKey: rangeKey in limits || rangeKey === "all" ? rangeKey : "all",
          points: points.slice(startIndex),
          startIndex,
          label: rangeKey === "20d" ? "20日" : rangeKey === "40d" ? "40日" : "全期間",
        };
      };

      const describeRsi = (value) => {
        if (!Number.isFinite(value)) {
          return "RSI の計算に必要な本数が不足しています。";
        }
        if (value >= 70) {
          return "買われ過ぎ圏に入りつつあり、上昇継続なら過熱の確認が必要です。";
        }
        if (value <= 30) {
          return "売られ過ぎ圏です。自律反発候補ですが、出来高確認は必要です。";
        }
        if (value >= 55) {
          return "モメンタムはやや強めです。押し目待ちか継続を見ます。";
        }
        if (value <= 45) {
          return "モメンタムは弱めです。反転材料がないと戻り売りに押されやすいです。";
        }
        return "過熱でも売られ過ぎでもなく、中立圏で推移しています。";
      };

      const describeMacd = (line, signal, histogram) => {
        if (![line, signal, histogram].every((value) => Number.isFinite(value))) {
          return "MACD の計算に必要な本数が不足しています。";
        }
        if (line >= signal && histogram > 0) {
          return "MACD はシグナルを上回り、上向きの勢いが残っています。";
        }
        if (line < signal && histogram < 0) {
          return "MACD はシグナルを下回り、下向きの勢いが優勢です。";
        }
        return "MACD は方向感が鈍く、クロス待ちの状態です。";
      };

      const describeMovingAverageStack = (price, ma25, ma75) => {
        if (![price, ma25, ma75].every((value) => Number.isFinite(value))) {
          return "移動平均線の比較に必要な本数が不足しています。";
        }
        if (price >= ma25 && ma25 >= ma75) {
          return "終値が 25 日線・75 日線の上で推移しており、中期トレンドは上向きです。";
        }
        if (price >= ma75 && ma25 < ma75) {
          return "長期線は維持していますが、中期線は未回復です。戻り局面として確認します。";
        }
        if (price < ma25 && ma25 >= ma75) {
          return "25 日線を下回り、中期上昇トレンドが鈍化しています。";
        }
        return "終値が中長期線の下にあり、反転シグナル待ちの配置です。";
      };

      const renderChartRangeControls = (currentRangeKey) => {
        const options = [
          { key: "20d", label: "20日" },
          { key: "40d", label: "40日" },
          { key: "all", label: "全期間" },
        ];
        return `
          <div class="segmented-controls">
            ${options.map((option) => `
              <button
                class="segment-button ${option.key === currentRangeKey ? "active" : ""}"
                type="button"
                data-chart-range="${option.key}"
              >${escapeHtml(option.label)}</button>
            `).join("")}
          </div>
        `;
      };

      const renderChartLegend = (items = []) => {
        if (!items.length) {
          return "";
        }
        return `
          <div class="chart-legend">
            ${items.map((item) => `
              <div class="legend-item">
                <span class="legend-swatch" style="background:${escapeAttr(item.color)}"></span>
                <span>${escapeHtml(item.label)}</span>
              </div>
            `).join("")}
          </div>
        `;
      };

      const renderTechnicalAnalysisCards = ({
        points,
        rangeLabel,
        ma5,
        ma25,
        ma75,
        rsiSeries,
        macdSeries,
      }) => {
        if (!points.length) {
          return `<div class="empty">分析カードを表示するだけのチャートデータが未取得です。</div>`;
        }
        const latest = points[points.length - 1];
        const latestMa5 = latestFiniteValue(ma5);
        const latestMa25 = latestFiniteValue(ma25);
        const latestMa75 = latestFiniteValue(ma75);
        const latestRsi = latestFiniteValue(rsiSeries);
        const latestMacd = latestFiniteValue(macdSeries.line);
        const latestSignal = latestFiniteValue(macdSeries.signal);
        const latestHistogram = latestFiniteValue(macdSeries.histogram);
        return `
          <div class="analysis-grid">
            <article class="analysis-card">
              <div class="subtle">移動平均線 / ${escapeHtml(rangeLabel)}</div>
              <strong>${escapeHtml(formatNumber(latest.close))} 円</strong>
              <div class="subtle">MA5 ${escapeHtml(formatNumber(latestMa5, 1))} / MA25 ${escapeHtml(formatNumber(latestMa25, 1))} / MA75 ${escapeHtml(formatNumber(latestMa75, 1))}</div>
              <p>${escapeHtml(describeMovingAverageStack(latest.close, latestMa25, latestMa75))}</p>
            </article>
            <article class="analysis-card">
              <div class="subtle">RSI 14</div>
              <strong>${escapeHtml(formatNumber(latestRsi, 1))}</strong>
              <div class="subtle">70 以上は過熱、30 以下は売られ過ぎの目安</div>
              <p>${escapeHtml(describeRsi(latestRsi))}</p>
            </article>
            <article class="analysis-card">
              <div class="subtle">MACD</div>
              <strong>${escapeHtml(formatSignedNumber(latestMacd, 2))}</strong>
              <div class="subtle">signal ${escapeHtml(formatSignedNumber(latestSignal, 2))} / hist ${escapeHtml(formatSignedNumber(latestHistogram, 2))}</div>
              <p>${escapeHtml(describeMacd(latestMacd, latestSignal, latestHistogram))}</p>
            </article>
          </div>
        `;
      };

      const buildPolylinePoints = (values, xForIndex, yForPrice) => values
        .map((value, index) => (
          Number.isFinite(value) ? `${xForIndex(index)},${yForPrice(value)}` : null
        ))
        .filter(Boolean)
        .join(" ");

      const renderChartStats = (points) => {
        const stats = buildChartStats(points);
        if (!stats.length) {
          return "";
        }
        return `<div class="chart-stats">${stats.map((item) => `
          <article class="chart-stat">
            <div class="subtle">${escapeHtml(item.label)}</div>
            <strong>${escapeHtml(item.value)}</strong>
            <div class="subtle">${escapeHtml(item.note)}</div>
          </article>
        `).join("")}</div>`;
      };

      const renderPriceChart = (rawPoints, options = {}) => {
        const points = normalizeChartPoints(rawPoints);
        if (!points.length) {
          return `<div class="empty">\u30c1\u30e3\u30fc\u30c8\u30c7\u30fc\u30bf\u306f\u672a\u53d6\u5f97\u3067\u3059\u3002</div>`;
        }

        const width = 860;
        const height = options.height ?? 280;
        const left = 18;
        const right = 64;
        const top = 18;
        const bottom = 26;
        const showVolume = options.showVolume !== false;
        const volumeHeight = showVolume ? Math.max(54, Math.round(height * 0.22)) : 0;
        const volumeGap = showVolume ? 14 : 0;
        const plotWidth = width - left - right;
        const plotHeight = height - top - bottom - volumeHeight - volumeGap;
        const volumeTop = top + plotHeight + volumeGap;
        const highs = points.map((item) => item.high);
        const lows = points.map((item) => item.low);
        const volumes = points.map((item) => item.volume);
        const overlaySeries = Array.isArray(options.overlaySeries) ? options.overlaySeries : [];
        const overlayValues = overlaySeries.flatMap((series) => (
          Array.isArray(series.values) ? series.values.filter((value) => Number.isFinite(value)) : []
        ));
        const maxHigh = Math.max(...highs, ...(overlayValues.length ? overlayValues : [Number.NEGATIVE_INFINITY]));
        const minLow = Math.min(...lows, ...(overlayValues.length ? overlayValues : [Number.POSITIVE_INFINITY]));
        const pricePadding = Math.max((maxHigh - minLow) * 0.06, 1);
        const priceMax = maxHigh + pricePadding;
        const priceMin = minLow - pricePadding;
        const priceSpan = Math.max(priceMax - priceMin, 1);
        const volumeMax = Math.max(...volumes, 1);
        const step = points.length > 1 ? plotWidth / (points.length - 1) : plotWidth;
        const candleWidth = Math.max(4, Math.min(12, step * 0.56));
        const xForIndex = (index) => left + (points.length === 1 ? plotWidth / 2 : step * index);
        const yForPrice = (price) => top + ((priceMax - price) / priceSpan) * plotHeight;
        const startLabel = points[0];
        const midLabel = points[Math.floor((points.length - 1) / 2)];
        const endLabel = points[points.length - 1];
        const latest = points[points.length - 1];

        const gridLines = Array.from({ length: 5 }, (_, index) => {
          const ratio = index / 4;
          const price = priceMax - priceSpan * ratio;
          const y = yForPrice(price);
          return `
            <line class="chart-grid-line" x1="${left}" y1="${y}" x2="${left + plotWidth}" y2="${y}"></line>
            <text class="chart-axis-label" x="${width - 4}" y="${y - 4}" text-anchor="end">${escapeHtml(formatNumber(price))}</text>
          `;
        }).join("");

        const candles = points.map((item, index) => {
          const x = xForIndex(index);
          const openY = yForPrice(item.open);
          const closeY = yForPrice(item.close);
          const highY = yForPrice(item.high);
          const lowY = yForPrice(item.low);
          const bodyY = Math.min(openY, closeY);
          const bodyHeight = Math.max(Math.abs(closeY - openY), 1.5);
          return `
            <line class="chart-wick ${item.direction}" x1="${x}" y1="${highY}" x2="${x}" y2="${lowY}"></line>
            <rect class="chart-candle ${item.direction}" x="${x - candleWidth / 2}" y="${bodyY}" width="${candleWidth}" height="${bodyHeight}" rx="1.5"></rect>
          `;
        }).join("");

        const volumeBars = showVolume ? points.map((item, index) => {
          const x = xForIndex(index);
          const heightValue = (item.volume / volumeMax) * volumeHeight;
          const y = volumeTop + (volumeHeight - heightValue);
          return `
            <rect class="chart-volume ${item.direction}" x="${x - candleWidth / 2}" y="${y}" width="${candleWidth}" height="${Math.max(heightValue, 1.5)}" rx="1.5"></rect>
          `;
        }).join("") : "";

        const overlays = overlaySeries.map((series) => {
          const polylinePoints = buildPolylinePoints(series.values || [], xForIndex, yForPrice);
          if (!polylinePoints) {
            return "";
          }
          return `<polyline class="chart-overlay" points="${polylinePoints}" stroke="${escapeAttr(series.color)}"></polyline>`;
        }).join("");

        return `
          <div class="chart-panel">
            <div class="chart-surface">
              <svg class="chart-svg" viewBox="0 0 ${width} ${height}" role="img" aria-label="\u682a\u4fa1\u30c1\u30e3\u30fc\u30c8">
                ${gridLines}
                <line class="chart-price-guide" x1="${left}" y1="${yForPrice(latest.close)}" x2="${left + plotWidth}" y2="${yForPrice(latest.close)}"></line>
                ${candles}
                ${overlays}
                ${volumeBars}
                <text class="chart-axis-label" x="${left}" y="${height - 4}">${escapeHtml(formatChartDate(startLabel.date))}</text>
                <text class="chart-axis-label" x="${left + plotWidth / 2}" y="${height - 4}" text-anchor="middle">${escapeHtml(formatChartDate(midLabel.date))}</text>
                <text class="chart-axis-label" x="${left + plotWidth}" y="${height - 4}" text-anchor="end">${escapeHtml(formatChartDate(endLabel.date))}</text>
                <text class="chart-axis-label" x="${width - 4}" y="${top + 12}" text-anchor="end">\u7d42\u5024 ${escapeHtml(formatNumber(latest.close))}</text>
              </svg>
            </div>
            ${renderChartLegend(overlaySeries)}
            ${renderChartStats(points)}
          </div>
        `;
      };

      const renderDetail = (detail) => {
        if (!detail) {
          fill("detail-header-tags", "");
          text("detail-page-title", "銘柄詳細");
          text("detail-page-subtitle", "表示できる銘柄詳細がありません。");
          fill("detail-view", `<div class="empty">表示できる銘柄詳細がありません。</div>`);
          return;
        }

        text("detail-page-title", `${detail.name} (${detail.ticker_code})`);
        text("detail-page-subtitle", `${detail.market ?? "-"} / 更新 ${formatDateTime(detail.hypothesis.updated_at || state.data?.generated_at)}`);

        fill("detail-header-tags", `
          <span class="chip">${escapeHtml(detail.status)}</span>
          <span class="chip">注目度 ${escapeHtml(detail.attention.label)}</span>
          <span class="chip ${statusChip(detail.risk.score)}">リスク ${escapeHtml(detail.risk.label)}</span>
        `);

        fill("detail-view", `
          <div class="detail-grid">
            <div class="detail-stack">
              <article class="detail-card">
                <div class="meta">
                  <div class="company">
                    <h3>${escapeHtml(detail.name)}</h3>
                    <div class="ticker">${escapeHtml(detail.ticker_code)} / ${escapeHtml(detail.market ?? "-")}</div>
                  </div>
                  <span class="score-chip">${escapeHtml(detail.attention.score)}</span>
                </div>
                <p style="margin-top: 12px;">${escapeHtml(detail.summary_comment)}</p>
                <div class="detail-cta">
                  <div class="action-row">
                    <button
                      class="primary-button"
                      type="button"
                      data-detail-add-watchlist="${escapeAttr(detail.ticker_code)}"
                      ${detail.is_in_watchlist ? "disabled" : ""}
                    >${detail.is_in_watchlist ? "watchlist登録済み" : "watchlistに追加"}</button>
                    <a class="ghost-button" href="/securities/${escapeAttr(detail.ticker_code)}" target="_blank" rel="noreferrer">JSONを見る</a>
                    <button
                      class="ghost-button"
                      type="button"
                      data-manual-update="selected-score"
                      data-manual-feedback="detail-score-refresh-feedback"
                    >スコア再計算</button>
                  </div>
                  <div class="search-feedback" id="detail-score-refresh-feedback"></div>
                  ${detail.reference_links?.length ? `
                    <div>
                      <div class="subtle">主要参照先</div>
                      ${renderSourceLinks(detail.reference_links || [])}
                    </div>
                  ` : ""}
                  <div class="search-feedback" id="detail-watchlist-feedback"></div>
                </div>
                <div class="metric-list" style="margin-top: 14px;">
                  <article class="detail-card">
                    <div class="subtle">注目度</div>
                    <strong>${escapeHtml(detail.attention.label)} ${escapeHtml(detail.attention.score)}</strong>
                    <div class="subtle">${escapeHtml(detail.attention.note)}</div>
                  </article>
                  <article class="detail-card">
                    <div class="subtle">仮説強度</div>
                    <strong>${escapeHtml(detail.hypothesis_strength.label)} ${escapeHtml(detail.hypothesis_strength.score)}</strong>
                    <div class="subtle">${escapeHtml(detail.hypothesis_strength.note)}</div>
                  </article>
                  <article class="detail-card">
                    <div class="subtle">地合い逆風</div>
                    <strong>${escapeHtml(detail.market_headwind.label)} ${escapeHtml(detail.market_headwind.score)}</strong>
                    <div class="subtle">${escapeHtml(detail.market_headwind.note)}</div>
                  </article>
                  <article class="detail-card">
                    <div class="subtle">リスク</div>
                    <strong>${escapeHtml(detail.risk.label)} ${escapeHtml(detail.risk.score)}</strong>
                    <div class="subtle">${escapeHtml(detail.risk.note)}</div>
                  </article>
                </div>
              </article>

              <article class="detail-card">
                <div class="section-head">
                  <div>
                    <div class="eyebrow">Hypothesis</div>
                    <h3>投資仮説カード</h3>
                  </div>
                  <span class="subtle">${escapeHtml(detail.hypothesis.source_label)} / 更新 ${escapeHtml(formatDateTime(detail.hypothesis.updated_at))}</span>
                </div>
                <div class="stack">
                  <div><strong>主仮説</strong><p>${escapeHtml(detail.hypothesis.primary)}</p></div>
                  <div><strong>補助仮説</strong><p>${escapeHtml(detail.hypothesis.secondary ?? "未設定")}</p></div>
                  <div><strong>期待カタリスト</strong><p>${escapeHtml(detail.hypothesis.catalyst ?? "未設定")}</p></div>
                  <div><strong>想定時間軸</strong><p>${escapeHtml(detail.hypothesis.time_horizon)}</p></div>
                  <div><strong>反証条件</strong><p>${escapeHtml(detail.hypothesis.invalidation)}</p></div>
                  <div><strong>撤退条件</strong><p>${escapeHtml(detail.hypothesis.exit_condition)}</p></div>
                </div>
              </article>

              <article class="detail-card">
                <div class="section-head">
                  <div>
                    <div class="eyebrow">Factor Split</div>
                    <h3>地合い分離</h3>
                  </div>
                  <div class="section-actions">
                    <button
                      class="ghost-button"
                      type="button"
                      data-manual-update="selected-factor"
                      data-manual-feedback="detail-factor-refresh-feedback"
                    >地合いデータ更新</button>
                  </div>
                </div>
                <div class="search-feedback" id="detail-factor-refresh-feedback"></div>
                ${renderSplitBars(detail)}
                <p style="margin-top: 12px;">${escapeHtml(detail.factor_split.summary)}</p>
                <div class="subtle">${escapeHtml(detail.factor_split.note)}</div>
              </article>

              <article class="detail-card">
                <div class="section-head">
                  <div>
                    <div class="eyebrow">Materials</div>
                    <h3>材料履歴</h3>
                  </div>
                  <div class="section-actions">
                    <button
                      class="ghost-button"
                      type="button"
                      data-manual-update="selected-tdnet"
                      data-manual-feedback="detail-materials-refresh-feedback"
                    >TDnet取得</button>
                    <button
                      class="ghost-button"
                      type="button"
                      data-manual-update="selected-youtube"
                      data-manual-feedback="detail-materials-refresh-feedback"
                    >YouTube取得</button>
                  </div>
                </div>
                <div class="search-feedback" id="detail-materials-refresh-feedback"></div>
                ${detail.materials.length ? `<div class="timeline">${detail.materials.map((item) => `
                  <article class="timeline-item detail-card">
                    <div class="subtle">${escapeHtml(item.category)} / ${escapeHtml(item.importance)} / ${escapeHtml(formatDateTime(item.event_time))}</div>
                    <strong>${escapeHtml(item.summary)}</strong>
                    <div>${escapeHtml(item.what_changed)}</div>
                    ${renderSourceLinks(item.source_links || [])}
                  </article>
                `).join("")}</div>` : `<div class="empty">材料履歴はまだありません。</div>`}
              </article>
            </div>

            <div class="detail-stack">
              <article class="detail-card">
                <div class="section-head">
                  <div>
                    <div class="eyebrow">Memo</div>
                    <h3>仮説メモ</h3>
                  </div>
                </div>
                <form class="detail-form" id="detail-hypothesis-form">
                  <div class="form-grid">
                    <label>
                      <div class="subtle">主仮説</div>
                      <textarea class="textarea" id="detail-primary-input" name="primary">${escapeHtml(detail.draft_primary ?? "")}</textarea>
                    </label>
                    <label>
                      <div class="subtle">反証条件 / 撤退条件</div>
                      <textarea class="textarea" id="detail-invalidation-input" name="invalidation">${escapeHtml(detail.draft_invalidation ?? "")}</textarea>
                    </label>
                    <label>
                      <div class="subtle">メモ</div>
                      <textarea class="textarea" id="detail-memo-input" name="memo">${escapeHtml(detail.draft_memo ?? "")}</textarea>
                    </label>
                  </div>
                  <div class="inline-grid">
                    <div class="subtle">watchlist 経由で保存します。あとから都合よく解釈し直しにくいよう、買い理由と反証条件を固定してください。</div>
                    <button class="save-button" type="submit">仮説カードを保存</button>
                  </div>
                  <div class="search-feedback" id="detail-save-feedback"></div>
                </form>
              </article>

              <article class="detail-card">
                <div class="section-head">
                  <div>
                    <div class="eyebrow">Technical</div>
                    <h3>テクニカル解釈</h3>
                  </div>
                  <div class="section-actions">
                    <button
                      class="ghost-button"
                      type="button"
                      data-manual-update="selected-prices"
                      data-manual-feedback="detail-technical-refresh-feedback"
                    >価格取得</button>
                    <button
                      class="ghost-button"
                      type="button"
                      data-manual-update="selected-technical"
                      data-manual-feedback="detail-technical-refresh-feedback"
                    >テクニカル再計算</button>
                  </div>
                </div>
                <div class="search-feedback" id="detail-technical-refresh-feedback"></div>
                <div>${escapeHtml(detail.technical_summary ?? "テクニカル情報は未取得です。")}</div>
                <div class="stack" style="margin-top: 12px;">
                  ${(detail.technical_interpretations || []).map((item) => `<div class="subtle">${escapeHtml(item)}</div>`).join("")}
                </div>
                <div style="margin-top: 14px;">${renderMetricCards(detail.technical_metrics || [])}</div>
                <div class="chart-actions" style="margin-top: 16px;">
                  <a class="ghost-button" href="${chartPageUrl(detail.ticker_code)}">\u30c1\u30e3\u30fc\u30c8\u5206\u6790\u8a73\u7d30</a>
                </div>
                <div class="subtle" style="margin-top: 10px;">直近チャートプレビュー</div>
                <div style="margin-top: 12px;">${renderPriceChart(detail.price_chart || [], { height: 260 })}</div>
                ${renderSourceLinks(detail.technical_source_links || [])}
              </article>

              <article class="detail-card">
                <div class="section-head">
                  <div>
                    <div class="eyebrow">Flow</div>
                    <h3>信用需給の状態</h3>
                  </div>
                  <div class="section-actions">
                    <button
                      class="ghost-button"
                      type="button"
                      data-manual-update="selected-flow"
                      data-manual-feedback="detail-flow-refresh-feedback"
                    >信用需給取得</button>
                  </div>
                </div>
                <div class="search-feedback" id="detail-flow-refresh-feedback"></div>
                <div>${escapeHtml(detail.flow_summary ?? "信用需給データは未取得です。")}</div>
                <div class="stack" style="margin-top: 12px;">
                  ${(detail.flow_interpretations || []).map((item) => `<div class="subtle">${escapeHtml(item)}</div>`).join("")}
                </div>
                <div style="margin-top: 14px;">${renderMetricCards(detail.flow_metrics || [])}</div>
                ${renderSourceLinks(detail.flow_source_links || [])}
              </article>

              <article class="detail-card">
                <div class="section-head">
                  <div>
                    <div class="eyebrow">Warnings</div>
                    <h3>リスク・警戒点</h3>
                  </div>
                </div>
                ${detail.warnings.length ? `<div class="timeline">${detail.warnings.map((item) => `
                  <article class="timeline-item detail-card">
                    <div class="subtle">${escapeHtml(item.severity)}</div>
                    <strong>${escapeHtml(item.title)}</strong>
                    <div>${escapeHtml(item.detail)}</div>
                  </article>
                `).join("")}</div>` : `<div class="empty">直近で強い警戒点はありません。</div>`}
              </article>

              <article class="detail-card">
                <div class="section-head">
                  <div>
                    <div class="eyebrow">History</div>
                    <h3>レビュー / 材料の履歴</h3>
                  </div>
                </div>
                ${renderTimeline(detail.history || [])}
              </article>
            </div>
          </div>
        `);
      };

      const renderChartPage = (detail) => {
        if (!detail) {
          fill("detail-header-tags", "");
          text("detail-page-title", "\u30c1\u30e3\u30fc\u30c8\u5206\u6790");
          text("detail-page-subtitle", "\u8868\u793a\u3067\u304d\u308b\u9280\u67c4\u8a73\u7d30\u304c\u3042\u308a\u307e\u305b\u3093\u3002");
          fill("detail-view", `<div class="empty">\u30c1\u30e3\u30fc\u30c8\u5206\u6790\u30c7\u30fc\u30bf\u304c\u3042\u308a\u307e\u305b\u3093\u3002</div>`);
          return;
        }

        const points = normalizeChartPoints(detail.price_chart || []);
        const rangeSelection = sliceChartRange(points, state.chartRangeKey);
        const ma5SeriesAll = buildSimpleMovingAverageSeries(points, 5);
        const ma25SeriesAll = buildSimpleMovingAverageSeries(points, 25);
        const ma75SeriesAll = buildSimpleMovingAverageSeries(points, 75);
        const rsiSeriesAll = buildRsiSeries(points, 14);
        const macdSeriesAll = buildMacdSeries(points);
        const ma5Series = ma5SeriesAll.slice(rangeSelection.startIndex);
        const ma25Series = ma25SeriesAll.slice(rangeSelection.startIndex);
        const ma75Series = ma75SeriesAll.slice(rangeSelection.startIndex);
        const rsiSeries = rsiSeriesAll.slice(rangeSelection.startIndex);
        const macdSeries = {
          line: macdSeriesAll.line.slice(rangeSelection.startIndex),
          signal: macdSeriesAll.signal.slice(rangeSelection.startIndex),
          histogram: macdSeriesAll.histogram.slice(rangeSelection.startIndex),
        };
        text("detail-page-title", `${detail.name} (${detail.ticker_code})`);
        text("detail-page-subtitle", `${detail.market ?? "-"} / \u30c1\u30e3\u30fc\u30c8\u5206\u6790`);
        fill("detail-header-tags", `
          <span class="chip">\u30c6\u30af\u30cb\u30ab\u30eb</span>
          <span class="chip">${escapeHtml(detail.status)}</span>
          <span class="chip">${escapeHtml(rangeSelection.label)}</span>
          <span class="chip">${escapeHtml(String(rangeSelection.points.length))}\u672c</span>
        `);

        fill("detail-view", `
          <div class="detail-grid">
            <div class="detail-stack">
              <article class="detail-card">
                <div class="section-head">
                  <div>
                    <div class="eyebrow">Chart</div>
                    <h3>\u30ed\u30fc\u30bd\u30af\u8db3\u3068\u51fa\u6765\u9ad8</h3>
                  </div>
                  <div class="section-actions">
                    <a class="ghost-button" href="${detailPageUrl(detail.ticker_code)}" target="_blank" rel="noopener noreferrer">\u500b\u5225\u9280\u67c4\u30da\u30fc\u30b8\u306b\u623b\u308b</a>
                    <a class="ghost-button" href="/securities/${escapeAttr(detail.ticker_code)}" target="_blank" rel="noreferrer">JSON</a>
                    <button
                      class="ghost-button"
                      type="button"
                      data-manual-update="selected-prices"
                      data-manual-feedback="detail-chart-refresh-feedback"
                    >価格取得</button>
                    <button
                      class="ghost-button"
                      type="button"
                      data-manual-update="selected-technical"
                      data-manual-feedback="detail-chart-refresh-feedback"
                    >テクニカル再計算</button>
                  </div>
                </div>
                <div class="search-feedback" id="detail-chart-refresh-feedback"></div>
                <p>${escapeHtml(detail.technical_summary ?? "\u30c6\u30af\u30cb\u30ab\u30eb\u8981\u7d04\u306f\u672a\u53d6\u5f97\u3067\u3059\u3002")}</p>
                <div style="margin-top: 16px;">${renderChartRangeControls(rangeSelection.rangeKey)}</div>
                <div class="subtle">移動平均線 5 / 25 / 75 日を重ね、期間は client-side で切り替えます。</div>
                <div style="margin-top: 18px;">${renderPriceChart(rangeSelection.points, {
                  height: 380,
                  overlaySeries: [
                    { label: "MA 5", color: "#157347", values: ma5Series },
                    { label: "MA 25", color: "#2558a9", values: ma25Series },
                    { label: "MA 75", color: "#b85c2f", values: ma75Series },
                  ],
                })}</div>
                <div style="margin-top: 18px;">${renderTechnicalAnalysisCards({
                  points: rangeSelection.points,
                  rangeLabel: rangeSelection.label,
                  ma5: ma5Series,
                  ma25: ma25Series,
                  ma75: ma75Series,
                  rsiSeries,
                  macdSeries,
                })}</div>
              </article>

              <article class="detail-card">
                <div class="section-head">
                  <div>
                    <div class="eyebrow">Interpretation</div>
                    <h3>\u8aad\u307f\u53d6\u308a</h3>
                  </div>
                </div>
                <div class="stack">
                  ${(detail.technical_interpretations || []).length ? (detail.technical_interpretations || []).map((item) => `<div class="subtle">${escapeHtml(item)}</div>`).join("") : `<div class="empty">\u89e3\u91c8\u30e1\u30e2\u306f\u307e\u3060\u3042\u308a\u307e\u305b\u3093\u3002</div>`}
                </div>
                ${renderSourceLinks(detail.technical_source_links || [])}
              </article>
            </div>

            <div class="detail-stack">
              <article class="detail-card">
                <div class="section-head">
                  <div>
                    <div class="eyebrow">Technical</div>
                    <h3>\u6307\u6a19\u30b5\u30de\u30ea</h3>
                  </div>
                </div>
                ${renderMetricCards(detail.technical_metrics || [])}
              </article>

              <article class="detail-card">
                <div class="section-head">
                  <div>
                    <div class="eyebrow">References</div>
                    <h3>\u4e3b\u8981\u53c2\u7167\u5148</h3>
                  </div>
                </div>
                ${renderSourceLinks(detail.reference_links || [])}
              </article>

              <article class="detail-card">
                <div class="section-head">
                  <div>
                    <div class="eyebrow">History</div>
                    <h3>\u30ec\u30d3\u30e5\u30fc\u5c65\u6b74</h3>
                  </div>
                </div>
                ${renderTimeline(detail.history || [])}
              </article>
            </div>
          </div>
        `);
      };

      const renderTop = (data) => {
        renderHero(data);
        renderPriority(data.priority_items || []);
        renderPortfolio(data.portfolio_items || []);
        renderWatchlist(data.watchlist_items || []);
        renderAlerts(data.important_alerts || []);
        renderEvents(data.event_feed || []);
        renderScreening(data.screening_items || []);
        renderSearchCandidates(data.screening_items || [], data.watchlist_items || []);
        renderWatchlistAiReview();
      };

      const renderAll = (data) => {
        if (PAGE_MODE === "chart") {
          renderChartPage(data.detail || null);
          return;
        }
        if (PAGE_MODE === "detail" || PAGE_MODE === "chart") {
          renderDetail(data.detail || null);
          return;
        }
        renderTop(data);
      };

      const renderError = (error) => {
        const message = escapeHtml(error.message || String(error));
        if (PAGE_MODE === "detail") {
          text("detail-page-title", "銘柄詳細");
          text("detail-page-subtitle", "読み込みに失敗しました。");
          fill("detail-view", `<div class="error empty">読み込みに失敗しました: ${message}</div>`);
          return;
        }
        [
          "priority-grid",
          "events-list",
          "alerts-list",
          "watchlist-search-results",
          "watchlist-score-candidates",
          "watchlist-list",
          "screening-list",
          "metric-grid",
          "status-grid",
          "portfolio-list",
          "portfolio-ai-review-results",
          "watchlist-ai-review-results",
        ].forEach((id) => fill(id, `<div class="error empty">読み込みに失敗しました: ${message}</div>`));
        text("market-label", "error");
        text("market-score", "--");
        text("market-comment", "API 応答を確認してください。");
        text("disclaimer", "UI データの取得に失敗しました。");
      };

      const loadDashboard = async (tickerCode = null) => {
        const query = tickerCode ? `?ticker_code=${encodeURIComponent(tickerCode)}` : "";
        const data = await fetchJson(`/ui/dashboard/data${query}`);
        state.data = data;
        renderAll(data);
        renderPortfolioAiReview();
        renderWatchlistAiReview();
        updateStockAiCost();
        restoreManualFeedback();
      };

      const runSecuritySearch = async (query) => {
        const normalized = query.trim();
        const requestId = ++state.searchRequestId;
        state.lastQuery = normalized;
        if (!normalized) {
          state.searchResults = [];
          renderSearchResults([], "");
          setSearchFeedback("");
          return;
        }

        setSearchFeedback(`"${normalized}" を検索中...`);
        const results = await fetchJson(`/securities/search?q=${encodeURIComponent(normalized)}`);
        if (requestId !== state.searchRequestId) {
          return;
        }
        state.searchResults = results;
        renderSearchResults(results, normalized);
        if (results.length) {
          setSearchFeedback(`${results.length} 件見つかりました。詳細を開く銘柄を選んでください。`);
          return;
        }
        setSearchFeedback("候補がありません。同期済みの銘柄マスタにある銘柄だけ表示します。");
      };

      const shouldAutoSearch = (query) => {
        const normalized = query.trim();
        if (!normalized) return false;
        if (/^\d+$/.test(normalized)) return normalized.length >= 2;
        if (/[\u3040-\u30ff\u3400-\u9fff]/.test(normalized)) return normalized.length >= 1;
        return normalized.length >= 2;
      };

      const scheduleSecuritySearch = (query) => {
        if (state.searchDebounceId) {
          window.clearTimeout(state.searchDebounceId);
          state.searchDebounceId = null;
        }
        if (!shouldAutoSearch(query)) {
          state.searchRequestId += 1;
          state.searchResults = [];
          renderSearchResults([], query.trim() ? "" : "");
          setSearchFeedback("");
          return;
        }
        state.searchDebounceId = window.setTimeout(() => {
          state.searchDebounceId = null;
          runSecuritySearch(query).catch((error) => {
            setSearchFeedback(`検索に失敗しました: ${error.message || String(error)}`, "error");
            renderSearchResults([], query);
          });
        }, 180);
      };

      const syncMarketProxyPrices = async (button) => {
        if (!button || button.disabled) return;
        const feedback = document.getElementById("market-proxy-sync-feedback");
        button.disabled = true;
        if (feedback) {
          feedback.className = "search-feedback";
          feedback.textContent = "TOPIX(1306) / Nikkei225(1321) proxy価格を同期しています...";
        }
        try {
          const results = await Promise.all([
            postJson("/securities/1306/prices/sync?lookback_days=60", {}),
            postJson("/securities/1321/prices/sync?lookback_days=60", {}),
          ]);
          const total = results.reduce((sum, item) => sum + (item.processed_count || 0), 0);
          if (feedback) {
            feedback.className = "search-feedback success";
            feedback.textContent = `市場proxy価格を更新しました: ${total} bars`;
          }
          await loadDashboard(state.data?.selected_ticker_code || null);
        } catch (error) {
          if (feedback) {
            feedback.className = "search-feedback error";
            feedback.textContent = `市場proxy価格の更新に失敗しました: ${error.message || String(error)}`;
          }
        } finally {
          button.disabled = false;
        }
      };

      const selectedTickerCode = () =>
        state.data?.detail?.ticker_code || state.data?.selected_ticker_code || INITIAL_TICKER || "";

      const uniqueTickers = (...groups) => {
        const seen = new Set();
        const tickers = [];
        groups.flat().forEach((item) => {
          const ticker = typeof item === "string" ? item : item?.ticker_code;
          if (!ticker || seen.has(ticker)) return;
          seen.add(ticker);
          tickers.push(ticker);
        });
        return tickers;
      };

      const tickerTasks = (tickers, labelSuffix, urlBuilder) =>
        tickers.map((ticker) => ({
          label: `${ticker} ${labelSuffix}`,
          url: urlBuilder(ticker),
          zeroIsError: true,
        }));

      const manualUpdateTargets = (kind) => {
        const tickerCode = selectedTickerCode();
        const watchlistTickers = uniqueTickers(state.data?.watchlist_items || [], state.data?.priority_items || []);
        const screeningTickers = uniqueTickers(state.data?.screening_items || []);
        const portfolioTickers = uniqueTickers(state.data?.portfolio_items || []);
        const globalTasks = {
          sources: [{ label: "ソース登録", url: "/sources/bootstrap" }],
          "security-master": [{ label: "東証全銘柄（J-Quants）", url: "/securities/master/sync?require_jquants=true" }],
          "market-proxy": [
            { label: "市場価格 1306", url: "/securities/1306/prices/sync?lookback_days=60", zeroIsError: true },
            { label: "市場価格 1321", url: "/securities/1321/prices/sync?lookback_days=60", zeroIsError: true },
          ],
          edinet: [{ label: "EDINET", url: "/documents/sync/edinet" }],
          "tdnet-all": [{ label: "TDnet全体", url: "/documents/sync/tdnet" }],
        };
        if (globalTasks[kind]) {
          return globalTasks[kind];
        }
        if (kind === "watchlist-scores") {
          if (!watchlistTickers.length) {
            throw new Error("watchlist 登録銘柄がないため、スコア更新対象がありません。");
          }
          return tickerTasks(
            watchlistTickers,
            "スコア",
            (ticker) => `/securities/${encodeURIComponent(ticker)}/score/recalculate`,
          );
        }
        if (kind === "screening-scores") {
          if (!screeningTickers.length) {
            throw new Error("追加候補がないため、スコア更新対象がありません。");
          }
          return tickerTasks(
            screeningTickers,
            "スコア",
            (ticker) => `/securities/${encodeURIComponent(ticker)}/score/recalculate`,
          );
        }
        if (kind === "portfolio-prices") {
          if (!portfolioTickers.length) {
            throw new Error("portfolio 登録銘柄がないため、価格更新対象がありません。");
          }
          return tickerTasks(
            portfolioTickers,
            "価格",
            (ticker) => `/securities/${encodeURIComponent(ticker)}/prices/sync?lookback_days=120`,
          );
        }
        if (!tickerCode) {
          throw new Error("更新対象の銘柄が選択されていません。");
        }
        const selectedTasks = {
          "selected-prices": [{ label: `${tickerCode} 価格`, url: `/securities/${encodeURIComponent(tickerCode)}/prices/sync?lookback_days=120`, zeroIsError: true }],
          "selected-flow": [{ label: `${tickerCode} 信用需給`, url: `/securities/${encodeURIComponent(tickerCode)}/flow/sync`, zeroIsError: true }],
          "selected-technical": [{ label: `${tickerCode} テクニカル`, url: `/securities/${encodeURIComponent(tickerCode)}/technical/rebuild` }],
          "selected-score": [{ label: `${tickerCode} スコア`, url: `/securities/${encodeURIComponent(tickerCode)}/score/recalculate` }],
          "selected-tdnet": [{ label: `${tickerCode} TDnet`, url: `/documents/sync/tdnet?ticker_code=${encodeURIComponent(tickerCode)}` }],
          "selected-youtube": [{ label: `${tickerCode} YouTube`, url: `/documents/sync/youtube/monitored?ticker_code=${encodeURIComponent(tickerCode)}` }],
        };
        if (kind === "selected-factor") {
          return [
            ...globalTasks["market-proxy"],
            ...selectedTasks["selected-prices"],
            ...selectedTasks["selected-score"],
          ];
        }
        return selectedTasks[kind] || [];
      };

      const manualUpdateElements = (kind, button) => {
        const fallbackFeedbackId = kind.startsWith("selected") ? "detail-score-refresh-feedback" : "watchlist-search-feedback";
        const feedbackId = button?.dataset.manualFeedback || fallbackFeedbackId;
        const logId = button?.dataset.manualLog || "";
        return {
          feedbackId,
          feedback: document.getElementById(feedbackId),
          logId,
          log: logId ? document.getElementById(logId) : null,
        };
      };

      const renderManualUpdateLog = (node, results) => {
        if (!node) return;
        node.innerHTML = results.map((result) => `
          <article class="${result.ok ? "search-result" : "search-result error"}">
            <div>
              <strong>${escapeHtml(result.label)}</strong>
              <div class="subtle">${escapeHtml(result.message)}</div>
            </div>
          </article>
        `).join("");
      };

      const setManualFeedback = (feedbackId, message, tone = "", results = [], logId = "") => {
        if (!feedbackId) return;
        state.manualFeedback[feedbackId] = { message, tone, results, logId };
        const feedback = document.getElementById(feedbackId);
        if (feedback) {
          feedback.className = tone ? `search-feedback ${tone}` : "search-feedback";
          feedback.textContent = message;
        }
        if (logId) {
          renderManualUpdateLog(document.getElementById(logId), results);
        }
      };

      const restoreManualFeedback = () => {
        Object.entries(state.manualFeedback).forEach(([feedbackId, payload]) => {
          const feedback = document.getElementById(feedbackId);
          if (feedback) {
            feedback.className = payload.tone ? `search-feedback ${payload.tone}` : "search-feedback";
            feedback.textContent = payload.message;
          }
          if (payload.logId) {
            renderManualUpdateLog(document.getElementById(payload.logId), payload.results || []);
          }
        });
      };

      const manualResultFromPayload = (task, payload) => {
        const count = payload?.processed_count;
        const detail = payload?.detail || payload?.summary_text || "更新しました。";
        const zeroCountFailed = count === 0 && task.zeroIsError === true;
        if (payload?.fetched_count !== undefined && payload?.source === "jquants") {
          return {
            label: task.label,
            ok: payload.complete === true && !zeroCountFailed,
            message: `取得 ${payload.fetched_count}件・新規 ${payload.inserted_count}件・更新 ${payload.updated_count}件・再有効化 ${payload.reactivated_count}件・無効化 ${payload.deactivated_count}件・J-Quants有効 ${payload.jquants_active_count}件`,
          };
        }
        return {
          label: task.label,
          ok: !zeroCountFailed,
          message: count === undefined ? detail : `${count} 件 / ${detail}`,
        };
      };

      const formatManualError = (error) => {
        const message = error.message || String(error);
        if (message.includes("J-Quants API key")) {
          return `${message} .env または起動環境に JQUANTS_API_KEY を設定してください。`;
        }
        if (message.includes("status 429")) {
          return `${message} J-Quants 側の利用回数制限です。少し待ってから市場価格更新を再実行してください。`;
        }
        if (message.includes("EDINET API key")) {
          return `${message} .env または起動環境に EDINET_API_KEY を設定してください。`;
        }
        if (message.includes("TDnet API key")) {
          return `${message} .env または起動環境に TDNET_API_KEY を設定してください。`;
        }
        if (message.includes("YOUTUBE_API_KEY")) {
          return `${message} .env または起動環境に YOUTUBE_API_KEY を設定してください。`;
        }
        return message;
      };

      const runManualUpdate = async (kind, button) => {
        const { feedbackId, logId, feedback, log } = manualUpdateElements(kind, button);
        let tasks = [];
        try {
          tasks = manualUpdateTargets(kind);
        } catch (error) {
          setManualFeedback(feedbackId, error.message || String(error), "error", [], logId);
          return;
        }
        if (!tasks.length) return;

        if (button) button.disabled = true;
        setManualFeedback(
          feedbackId,
          kind === "security-master"
            ? "J-Quantsから東証全銘柄を同期しています..."
            : `${tasks.length} 件の更新を実行しています...`,
          "",
          [],
          logId,
        );

        const results = [];
        for (const task of tasks) {
          try {
            const payload = await postJson(task.url, {});
            results.push(manualResultFromPayload(task, payload));
          } catch (error) {
            results.push({
              label: task.label,
              ok: false,
              message: formatManualError(error),
            });
          }
          renderManualUpdateLog(log, results);
        }

        const failedCount = results.filter((result) => !result.ok).length;
        const failedSummary = results
          .filter((result) => !result.ok)
          .map((result) => `${result.label}: ${result.message}`)
          .join(" / ");
        const successSummary = results
          .map((result) => result.message)
          .join(" / ");
        setManualFeedback(
          feedbackId,
          failedCount
            ? `取得できませんでした: ${failedSummary}`
            : `更新しました: ${successSummary}`,
          failedCount ? "error" : "success",
          results,
          logId,
        );
        if (button) button.disabled = false;

        const query = document.getElementById("watchlist-search-input")?.value || state.lastQuery || "";
        await loadDashboard(state.data?.selected_ticker_code || selectedTickerCode() || null);
        if (kind === "security-master") {
          await loadSecurityMasterStatus();
        }
        if (kind === "security-master" && query.trim()) {
          await runSecuritySearch(query);
        }
      };

      const addCurrentToWatchlist = async (button) => {
        const detail = state.data?.detail;
        const feedback = document.getElementById("detail-watchlist-feedback");
        if (!detail || !button || button.disabled) return;
        button.disabled = true;
        if (feedback) {
          feedback.className = "search-feedback";
          feedback.textContent = "watchlist に追加中...";
        }
        try {
          await postJson("/watchlist", {
            ticker_code: detail.ticker_code,
            name: detail.name,
            market: detail.market,
            sort_order: detail.sort_order ?? 100,
          });
          if (feedback) {
            feedback.className = "search-feedback success";
            feedback.textContent = "watchlist に追加しました。";
          }
          await loadDashboard(detail.ticker_code);
        } catch (error) {
          button.disabled = false;
          if (feedback) {
            feedback.className = "search-feedback error";
            feedback.textContent = `追加に失敗しました: ${error.message || String(error)}`;
          }
        }
      };

      const saveHypothesisCard = async () => {
        const detail = state.data?.detail;
        const feedback = document.getElementById("detail-save-feedback");
        if (!detail || !feedback) return;
        feedback.className = "search-feedback";
        feedback.textContent = "保存中...";
        try {
          await postJson("/watchlist", {
            ticker_code: detail.ticker_code,
            name: detail.name,
            market: detail.market,
            memo: document.getElementById("detail-memo-input").value,
            thesis_bull: document.getElementById("detail-primary-input").value,
            thesis_bear: document.getElementById("detail-invalidation-input").value,
            sort_order: detail.sort_order ?? 100,
          });
          feedback.className = "search-feedback success";
          feedback.textContent = "仮説カードを保存しました。";
          await loadDashboard(detail.ticker_code);
        } catch (error) {
          feedback.className = "search-feedback error";
          feedback.textContent = `保存に失敗しました: ${error.message || String(error)}`;
        }
      };

      const savePortfolioHolding = async () => {
        const tickerInput = document.getElementById("portfolio-ticker-input");
        const quantityInput = document.getElementById("portfolio-quantity-input");
        const averageCostInput = document.getElementById("portfolio-average-cost-input");
        const noteInput = document.getElementById("portfolio-note-input");
        if (!tickerInput || !quantityInput || !averageCostInput || !noteInput) return;

        const tickerCode = tickerInput.value.trim();
        const quantity = quantityInput.value.trim();
        const averageCost = averageCostInput.value.trim();
        if (!tickerCode || !quantity) {
          setPortfolioFeedback("銘柄コードと数量は必須です。", "error");
          return;
        }

        setPortfolioFeedback("保有銘柄を保存中...");
        try {
          await postJson("/portfolio", {
            ticker_code: tickerCode,
            quantity,
            average_cost: averageCost || null,
            note: noteInput.value.trim() || null,
          });
          setPortfolioFeedback("保有銘柄を保存しました。", "success");
          await loadDashboard(state.data?.selected_ticker_code || null);
          quantityInput.value = "";
          averageCostInput.value = "";
          noteInput.value = "";
        } catch (error) {
          setPortfolioFeedback(`保有銘柄の保存に失敗しました: ${error.message || String(error)}`, "error");
        }
      };

      const preparePortfolioHolding = (tickerCode) => {
        if (!tickerCode) return;
        const form = document.getElementById("portfolio-form");
        const tickerInput = document.getElementById("portfolio-ticker-input");
        const quantityInput = document.getElementById("portfolio-quantity-input");
        if (!form || !tickerInput || !quantityInput) return;

        const publicTickerCode = publicSecurityCode(tickerCode);
        tickerInput.value = publicTickerCode;
        setPortfolioFeedback(`${publicTickerCode} を選択しました。数量を入力して「保有を保存」を押してください。`);
        form.scrollIntoView({ behavior: "smooth", block: "center" });
        quantityInput.focus({ preventScroll: true });
      };

      const removePortfolioHolding = async (tickerCode) => {
        if (!tickerCode) return;
        setPortfolioFeedback(`${tickerCode} を削除中...`);
        try {
          await deleteJson(`/portfolio/${encodeURIComponent(tickerCode)}`);
          setPortfolioFeedback(`${tickerCode} を portfolio から外しました。`, "success");
          await loadDashboard(state.data?.selected_ticker_code || null);
        } catch (error) {
          setPortfolioFeedback(`削除に失敗しました: ${error.message || String(error)}`, "error");
        }
      };

      const bootstrapTopPage = async () => {
        setupStockAiControls();
        const form = document.getElementById("watchlist-search-form");
        const input = document.getElementById("watchlist-search-input");

        if (form && input) {
          form.addEventListener("submit", async (event) => {
            event.preventDefault();
            if (state.searchDebounceId) {
              window.clearTimeout(state.searchDebounceId);
              state.searchDebounceId = null;
            }
            try {
              await runSecuritySearch(input.value);
            } catch (error) {
              setSearchFeedback(`検索に失敗しました: ${error.message || String(error)}`, "error");
              renderSearchResults([], input.value);
            }
          });

          input.addEventListener("input", () => {
            scheduleSecuritySearch(input.value);
          });
        }

        await Promise.all([loadDashboard(null), loadStockAiUsage(), loadSecurityMasterStatus()]);
        renderSearchResults([], "");
      };

      const bootstrapDetailPage = async () => {
        await loadDashboard(INITIAL_TICKER);
      };

      const main = document.querySelector("main");
      if (main) {
        main.addEventListener("click", async (event) => {
          if (event.target.closest("[data-source-link]")) {
            return;
          }

          const watchlistSelectInput = event.target.closest("input[data-watchlist-ai-select]");
          if (watchlistSelectInput) {
            event.stopPropagation();
            const ticker = watchlistSelectInput.dataset.watchlistAiSelect;
            if (ticker) {
              if (watchlistSelectInput.checked) {
                state.selectedWatchlistTickers.add(ticker);
              } else {
                state.selectedWatchlistTickers.delete(ticker);
              }
              updateStockAiCost();
            }
            return;
          }

          if (event.target.closest("[data-watchlist-ai-select-label]")) {
            event.stopPropagation();
            return;
          }

          const watchlistSelectAllButton = event.target.closest("[data-watchlist-ai-select-all]");
          if (watchlistSelectAllButton) {
            event.preventDefault();
            (state.data?.watchlist_items || []).forEach((item) => state.selectedWatchlistTickers.add(item.ticker_code));
            renderWatchlist(state.data?.watchlist_items || []);
            updateStockAiCost();
            return;
          }

          const watchlistClearButton = event.target.closest("[data-watchlist-ai-clear]");
          if (watchlistClearButton) {
            event.preventDefault();
            state.selectedWatchlistTickers.clear();
            renderWatchlist(state.data?.watchlist_items || []);
            updateStockAiCost();
            return;
          }

          const watchlistAiReviewButton = event.target.closest("[data-watchlist-ai-review]");
          if (watchlistAiReviewButton) {
            event.preventDefault();
            await runWatchlistAiReview();
            return;
          }

          const stockAiRunButton = event.target.closest("[data-stock-ai-run]");
          if (stockAiRunButton) {
            event.preventDefault();
            await runPortfolioAiReview(stockAiRunButton.dataset.stockAiRun || null);
            return;
          }

          const stockAiCopyButton = event.target.closest("#stock-ai-copy-prompt");
          if (stockAiCopyButton) {
            event.preventDefault();
            if (!state.lastManualPrompt) return;
            try {
              await navigator.clipboard.writeText(state.lastManualPrompt);
              const feedback = document.getElementById("portfolio-ai-review-feedback");
              if (feedback) {
                feedback.className = "search-feedback success";
                feedback.textContent = "プロンプトをコピーしました。";
              }
            } catch {
              const feedback = document.getElementById("portfolio-ai-review-feedback");
              if (feedback) {
                feedback.className = "search-feedback error";
                feedback.textContent = "プロンプトのコピーに失敗しました。";
              }
            }
            return;
          }

          const manualUpdateButton = event.target.closest("[data-manual-update]");
          if (manualUpdateButton) {
            event.preventDefault();
            await runManualUpdate(manualUpdateButton.dataset.manualUpdate, manualUpdateButton);
            return;
          }

          const addButton = event.target.closest("[data-detail-add-watchlist]");
          if (addButton) {
            await addCurrentToWatchlist(addButton);
            return;
          }

          const chartRangeButton = event.target.closest("[data-chart-range]");
          if (chartRangeButton) {
            const nextRangeKey = chartRangeButton.dataset.chartRange;
            if (nextRangeKey) {
              event.preventDefault();
              state.chartRangeKey = nextRangeKey;
              renderChartPage(state.data?.detail || null);
              restoreManualFeedback();
            }
            return;
          }

          const removePortfolioButton = event.target.closest("[data-remove-portfolio]");
          if (removePortfolioButton) {
            event.preventDefault();
            await removePortfolioHolding(removePortfolioButton.dataset.removePortfolio);
            return;
          }

          const preparePortfolioButton = event.target.closest("[data-prepare-portfolio]");
          if (preparePortfolioButton) {
            event.preventDefault();
            event.stopPropagation();
            preparePortfolioHolding(preparePortfolioButton.dataset.preparePortfolio);
            return;
          }

          const target = event.target.closest("[data-select-ticker], [data-open-ticker]");
          if (!target) {
            return;
          }
          const ticker = target.dataset.selectTicker || target.dataset.openTicker;
          if (!ticker) {
            return;
          }
          event.preventDefault();
          openSecurityDetail(ticker);
        });

        main.addEventListener("submit", async (event) => {
          if (event.target.id === "detail-hypothesis-form") {
            event.preventDefault();
            await saveHypothesisCard();
            return;
          }
          if (event.target.id === "portfolio-form") {
            event.preventDefault();
            await savePortfolioHolding();
            return;
          }
        });
      }

      const bootstrap = async () => {
        try {
          if (PAGE_MODE === "detail" || PAGE_MODE === "chart") {
            await bootstrapDetailPage();
          } else {
            await bootstrapTopPage();
          }
        } catch (error) {
          renderError(error);
        }
      };

      bootstrap();
    </script>
  </body>
</html>
"""
    return html.replace("__PAGE_MODE__", page_mode).replace("__INITIAL_TICKER__", json.dumps(initial_ticker))


def _review_shell_html() -> str:
    return r"""<!doctype html>
<html lang="ja">
  <head>
    <meta charset="utf-8" />
    <meta name="viewport" content="width=device-width, initial-scale=1" />
    <title>Kabuhandan Hojo Review</title>
    <style>
      :root {
        --bg: #f4f1ea;
        --panel: #fffdf8;
        --ink: #1f2a2d;
        --muted: #65716f;
        --line: rgba(31, 42, 45, 0.1);
        --accent: #0d6a58;
        --warn: #b85c2f;
        --shadow: 0 16px 40px rgba(30, 40, 45, 0.1);
        --radius: 20px;
      }
      * { box-sizing: border-box; }
      body {
        margin: 0;
        font-family: "Yu Gothic UI", "Hiragino Sans", "Meiryo", sans-serif;
        color: var(--ink);
        background:
          radial-gradient(circle at top left, rgba(255, 255, 255, 0.9), transparent 28%),
          linear-gradient(135deg, #f6f1e8 0%, #dce9e4 55%, #eef6f2 100%);
      }
      main { max-width: 1120px; margin: 0 auto; padding: 32px 20px 56px; }
      .hero, .grid { display: grid; gap: 20px; }
      .grid { grid-template-columns: 1.2fr 0.8fr; margin-top: 24px; }
      .panel {
        background: var(--panel);
        border: 1px solid var(--line);
        border-radius: var(--radius);
        box-shadow: var(--shadow);
        padding: 24px;
      }
      h1, h2, p { margin: 0; }
      h1 { font-size: clamp(28px, 4vw, 46px); line-height: 1.05; margin: 12px 0; }
      h2 { font-size: 22px; margin-bottom: 12px; }
      .eyebrow, .subtle { color: var(--muted); font-size: 12px; letter-spacing: 0.06em; text-transform: uppercase; }
      .lede { color: #30403d; line-height: 1.7; max-width: 64ch; }
      .stack { display: grid; gap: 14px; }
      .card {
        border: 1px solid var(--line);
        border-radius: 16px;
        padding: 16px;
        background: rgba(255,255,255,0.75);
      }
      .row, .meta, .tags { display: flex; gap: 10px; flex-wrap: wrap; }
      .row { justify-content: space-between; align-items: baseline; }
      .pill {
        display: inline-flex;
        align-items: center;
        padding: 6px 10px;
        border-radius: 999px;
        border: 1px solid var(--line);
        font-size: 12px;
        background: rgba(13, 106, 88, 0.08);
        color: var(--accent);
      }
      .pill.warn { background: rgba(184, 92, 47, 0.12); color: var(--warn); }
      .link { color: var(--accent); text-decoration: none; font-weight: 600; }
      .empty { color: var(--muted); padding: 12px 0; }
      @media (max-width: 860px) {
        .grid { grid-template-columns: 1fr; }
      }
    </style>
  </head>
  <body>
    <main>
      <section class="hero panel">
        <div class="eyebrow">Review</div>
        <h1>毎日の review queue</h1>
        <p class="lede">watchlist の優先順位、portfolio の保有有無、最新の alert / material をまとめて見直すための専用画面です。</p>
      </section>
      <section class="grid">
        <div class="panel">
          <div class="row">
            <h2>Review Queue</h2>
            <a class="link" href="/ui/dashboard">dashboard</a>
          </div>
          <div class="stack" id="review-queue"><div class="empty">loading...</div></div>
        </div>
        <div class="stack">
          <section class="panel">
            <h2>Portfolio</h2>
            <div class="stack" id="review-portfolio"><div class="empty">loading...</div></div>
          </section>
          <section class="panel">
            <h2>Market Overview</h2>
            <div class="stack" id="review-market"><div class="empty">loading...</div></div>
          </section>
        </div>
      </section>
    </main>
    <script>
      const escapeHtml = (value) => String(value ?? "")
        .replaceAll("&", "&amp;")
        .replaceAll("<", "&lt;")
        .replaceAll(">", "&gt;")
        .replaceAll('"', "&quot;")
        .replaceAll("'", "&#39;");

      const setHtml = (id, html) => {
        const element = document.getElementById(id);
        if (element) {
          element.innerHTML = html;
        }
      };

      const formatDateTime = (value) => {
        if (!value) return "未レビュー";
        const date = new Date(value);
        if (Number.isNaN(date.getTime())) return "未レビュー";
        return new Intl.DateTimeFormat("ja-JP", {
          year: "numeric",
          month: "2-digit",
          day: "2-digit",
          hour: "2-digit",
          minute: "2-digit",
          timeZone: "Asia/Tokyo",
        }).format(date);
      };

      const renderPortfolio = (items) => {
        if (!items.length) {
          setHtml("review-portfolio", '<div class="empty">portfolio は未登録です。</div>');
          return;
        }
        setHtml("review-portfolio", items.map((item) => `
          <article class="card">
            <div class="row">
              <strong>${escapeHtml(item.name)} <span class="subtle">${escapeHtml(item.ticker_code)}</span></strong>
              <span class="pill">${escapeHtml(item.quantity)} 株</span>
            </div>
            <div class="meta">
              <span>${escapeHtml(item.market || "市場未設定")}</span>
              <span>評価額 ${escapeHtml(item.market_value || "--")}</span>
            </div>
          </article>
        `).join(""));
      };

      const renderMarket = (overview) => {
        setHtml("review-market", `
          <article class="card">
            <div class="row">
              <strong>${escapeHtml(overview.label)}</strong>
              <span class="pill">${escapeHtml(overview.score)}</span>
            </div>
            <p>${escapeHtml(overview.comment)}</p>
          </article>
          ${(overview.sector_pulse || []).map((item) => `
            <article class="card">
              <div class="row">
                <strong>${escapeHtml(item.name)}</strong>
                <span class="pill">${escapeHtml(item.label)}</span>
              </div>
              <p>${escapeHtml(item.note)}</p>
            </article>
          `).join("")}
        `);
      };

      const renderQueue = (data) => {
        const portfolioSet = new Set((data.portfolio_items || []).map((item) => item.ticker_code));
        const priorityMap = new Map((data.priority_items || []).map((item) => [item.ticker_code, item]));
        const rows = (data.watchlist_items || []).map((item) => ({ item, priority: priorityMap.get(item.ticker_code) }));
        if (!rows.length) {
          setHtml("review-queue", '<div class="empty">watchlist が未登録です。</div>');
          return;
        }
        setHtml("review-queue", rows.map(({ item, priority }) => `
          <article class="card">
            <div class="row">
              <div>
                <strong>${escapeHtml(item.name)} <span class="subtle">${escapeHtml(item.ticker_code)}</span></strong>
                <div class="meta">
                  <span>${escapeHtml(item.market || "市場未設定")}</span>
                  <span>最終確認 ${escapeHtml(formatDateTime(item.updated_at))}</span>
                </div>
              </div>
              <a class="link" href="/ui/security/${encodeURIComponent(item.ticker_code)}" target="_blank" rel="noopener noreferrer">detail</a>
            </div>
            <div class="tags">
              <span class="pill">${escapeHtml(item.status)}</span>
              ${portfolioSet.has(item.ticker_code) ? '<span class="pill warn">portfolio 保有</span>' : ""}
              ${priority ? `<span class="pill">attention ${escapeHtml(priority.attention.score)}</span>` : ""}
            </div>
            <p style="margin-top: 10px;">${escapeHtml(item.next_action)}</p>
            ${priority ? `<p class="subtle" style="margin-top: 8px;">${escapeHtml(priority.material_summary)}</p>` : ""}
          </article>
        `).join(""));
      };

      fetch("/ui/dashboard/data")
        .then((response) => response.json())
        .then((data) => {
          renderQueue(data);
          renderPortfolio(data.portfolio_items || []);
          renderMarket(data.market_overview || { sector_pulse: [] });
        })
        .catch(() => {
          setHtml("review-queue", '<div class="empty">review queue の取得に失敗しました。</div>');
          setHtml("review-portfolio", '<div class="empty">portfolio の取得に失敗しました。</div>');
          setHtml("review-market", '<div class="empty">market overview の取得に失敗しました。</div>');
        });
    </script>
  </body>
</html>"""
