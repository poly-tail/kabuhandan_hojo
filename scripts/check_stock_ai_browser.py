"""Exercise dashboard layout and readers in Chromium with synthetic routed APIs.

Install optional QA tooling: pip install playwright; playwright install chromium.
No server is started. Every HTTP request is intercepted; neither application
services, the user's database, nor provider APIs are called.
"""

from __future__ import annotations

import argparse
import asyncio
import json
from pathlib import Path
import sys
from urllib.parse import urlsplit

REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(REPO_ROOT), str(REPO_ROOT / "src")]

from app.api.routes.ui import dashboard_ui  # noqa: E402
from app.schemas.portfolio_ai import PortfolioAiReviewResponse  # noqa: E402


ORIGIN = "http://127.0.0.1:8765"
FIXED_TIME = "2026-09-10T15:35:00+09:00"
HISTORY_ID = "a" * 64
WATCHLIST_HISTORY_ID = "b" * 64
LONG_TEXT = "画面検証用の長い日本語です。元データと仮説を別々に確認します。" * 24
LONG_URL = "https://example.com/" + "long-source-path-" * 24


def dashboard_fixture() -> dict:
    return {
        "generated_at": FIXED_TIME, "target_date": "2026-09-10", "mode": "live",
        "disclaimer": "画面検証専用の合成データです。",
        "market_overview": {
            "label": "検証用", "score": 50, "breadth": "中立", "breadth_ratio": "1:1",
            "separation_hint": "API接続なしの画面確認", "comment": "すべての値は検証用です。",
            "sector_pulse": [], "caution_tags": [],
        },
        "metrics": [], "status_counts": [], "priority_items": [], "important_alerts": [],
        "event_feed": [], "screening_items": [], "selected_ticker_code": None, "detail": None,
        "portfolio_items": [{
            "id": 1, "ticker_code": "7203", "name": "トヨタ自動車", "market": "TSE",
            "quantity": 5, "average_cost": 2000, "last_price": 2500,
            "market_value": 12500, "unrealized_pnl": 2500, "unrealized_return_pct": 25,
            "sort_order": 100, "updated_at": FIXED_TIME,
        }],
        "watchlist_collections": [{
            "id": 2, "name": "検証用の名前付きリスト", "is_default": False,
            "sort_order": 100, "item_count": 1, "created_at": FIXED_TIME, "updated_at": FIXED_TIME,
        }],
        "selected_watchlist_id": 2,
        "watchlist_items": [{
            "ticker_code": "8035", "name": "東京エレクトロン", "market": "TSE",
            "status": "watch", "next_action": "合成データの確認", "thesis_state": "draft",
        }],
    }


def review_fixture(kind: str = "success", *, mode: str = "scanner", target: str = "holdings") -> dict:
    selected = target in {"watchlist", "selected"}
    ticker, name = ("8035", "東京エレクトロン") if selected else ("7203", "トヨタ自動車")
    payload = {
        "generated_at": FIXED_TIME, "mode": mode, "model": "stub-provider",
        "include_web_search": False, "web_search_requested": False,
        "web_search_status": "not_run", "web_search_used": False,
        "holdings_source": "watchlist" if selected else "database",
        "actual_usage": {"api_calls": 0, "web_search_calls": 0, "web_search_calls_known": True},
        "portfolio_summary": {"overall_view": LONG_TEXT if kind == "long" else "検証用の分析結果です。"},
        "stocks": [{
            "ticker": ticker, "name": name, "judgement": "watch", "judgement_label": "様子見",
            "short_reason": LONG_TEXT if kind == "long" else "画面確認用です。",
            "key_points": [LONG_URL if kind == "long" else "入力と結果を確認する"],
        }],
        "holdings_snapshot": [{"ticker": ticker, "name": name, "quantity": 0 if selected else 5}],
        "market_snapshot": [{
            "ticker": ticker, "price": 2500,
            "source_metadata": {"price": [{"source": "QA synthetic", "as_of": "2026-09-09"}]},
        }],
        "request_payload": {"target": target, "watchlist_id": 2 if selected else None},
        "sources": [{"title": LONG_URL if kind == "long" else "検証用の参照先", "url": LONG_URL}],
    }
    if kind == "failure":
        payload.update({
            "status": "json_parse_failed", "parse_failure_kind": "json_syntax",
            "error": {"code": "json_parse_failed", "message": "検証用：JSONの構文解析に失敗しました。"},
            "raw_model_output": '<img src=x onerror="globalThis.rawExecuted=true">' + LONG_URL,
        })
    if mode == "prompt_only":
        payload["manual_prompt"] = "ChatGPT投入用の検証プロンプト\n" + LONG_TEXT
    return PortfolioAiReviewResponse.model_validate(payload).model_dump(mode="json")


class SyntheticRoutes:
    def __init__(self, html: str):
        self.html = html
        self.kind = "success"
        self.delay: asyncio.Event | None = None
        self.calls: list[dict] = []
        self.unexpected: list[str] = []

    async def handle(self, route):
        request = route.request
        path = urlsplit(request.url).path
        self.calls.append({"method": request.method, "path": path})
        if request.url == f"{ORIGIN}/ui/dashboard":
            await route.fulfill(body=self.html, content_type="text/html; charset=utf-8")
            return
        if not request.url.startswith(ORIGIN + "/"):
            self.unexpected.append(request.url)
            await route.abort()
            return
        if path == "/ui/dashboard/data":
            payload = dashboard_fixture()
        elif path == "/securities/master/status":
            payload = {"active_total": 0, "jquants_count": 0}
        elif path == "/api/ai/stock-review/usage":
            payload = {"daily_limit": 300, "remaining_today": 300, "today": {}, "month": {}}
        elif path == "/api/ai/stock-review/history":
            payload = {"items": [{
                "history_id": HISTORY_ID, "generated_at": FIXED_TIME, "mode": "scanner",
                "mode_label": "軽量スキャン", "target": "holdings", "target_label": "保有銘柄",
                "status": "success", "status_label": "成功", "holdings_source": "database",
                "stocks_preview": ["トヨタ自動車（7203）"], "web_search_status": "not_run",
            }, {
                "history_id": WATCHLIST_HISTORY_ID, "generated_at": FIXED_TIME, "mode": "analyst",
                "mode_label": "個別詳細分析", "target": "watchlist", "target_label": "検証用の名前付きリスト",
                "status": "success", "status_label": "成功", "holdings_source": "watchlist",
                "stocks_preview": ["東京エレクトロン（8035）"], "web_search_status": "not_run",
            }], "stored_count": 2, "retention_limit": 100}
        elif path == f"/api/ai/stock-review/history/{HISTORY_ID}":
            payload = {"history_id": HISTORY_ID, "review": review_fixture()}
        elif path == f"/api/ai/stock-review/history/{WATCHLIST_HISTORY_ID}":
            payload = {
                "history_id": WATCHLIST_HISTORY_ID,
                "review": review_fixture(mode="analyst", target="watchlist"),
            }
        elif path == f"/api/ai/stock-review/history/{HISTORY_ID}/export.md":
            await route.fulfill(
                body="# 合成データの履歴\n", content_type="text/markdown; charset=utf-8",
                headers={
                    "Content-Disposition": 'attachment; filename="stock-review.md"',
                    "Cache-Control": "no-store", "X-Content-Type-Options": "nosniff",
                },
            )
            return
        elif path in {"/api/ai/stock-review", "/portfolio/ai-review"}:
            body = request.post_data_json
            if self.delay is not None:
                await self.delay.wait()
            payload = review_fixture(self.kind, mode=body["mode"], target=body.get("target", "selected"))
            # Simulate a server with effective Web-search maximum zero.
            payload["web_search_requested"] = bool(body.get("include_web_search"))
            payload["request_payload"].update({"include_web_search": False, "max_web_search_calls": 0})
        else:
            self.unexpected.append(request.url)
            await route.abort()
            return
        await route.fulfill(json=payload)


async def capture_state(page, output: Path, width: int, label: str) -> dict:
    workbench = page.locator(".stock-ai-workbench")
    await workbench.scroll_into_view_if_needed()
    measurements = await page.evaluate("""() => {
      const rect = (selector) => {
        const box = document.querySelector(selector).getBoundingClientRect();
        return { x: box.x, y: box.y, width: box.width, height: box.height };
      };
      const root = document.documentElement;
      return { scrollWidth: root.scrollWidth, clientWidth: root.clientWidth,
        control: rect('.stock-ai-control-pane'), result: rect('.stock-ai-result-pane'),
        promptVisible: Boolean(document.querySelector('#stock-ai-prompt-output').getClientRects().length) };
    }""")
    assert measurements["scrollWidth"] <= measurements["clientWidth"], measurements
    if width > 960:
        assert 380 <= measurements["control"]["width"] <= 420, measurements
        assert measurements["result"]["x"] > measurements["control"]["x"], measurements
    else:
        control_bottom = measurements["control"]["y"] + measurements["control"]["height"]
        assert measurements["result"]["y"] >= control_bottom, measurements
    await workbench.screenshot(path=str(output / f"{width}-{label}.png"))
    return {"viewport": width, "state": label, **measurements}


async def run_analysis(page, routes: SyntheticRoutes, *, kind="success", mode="scanner"):
    routes.kind = kind
    await page.locator(f'[data-stock-ai-run="{mode}"]').click()
    expected = "json_parse_failed" if kind == "failure" else "success"
    await page.wait_for_function(
        "expected => state.portfolioAiReview.status === expected && state.stockAiBusyRequestId === null",
        arg=expected,
    )


async def check_reader(page, context, output: Path, label: str, reader_id="portfolio-ai-review-reader-link"):
    async with context.expect_page() as popup:
        await page.locator(f"#{reader_id}").click()
    reader = await popup.value
    await reader.wait_for_load_state()
    assert await reader.locator("script").count() == 0
    csp = await reader.locator('meta[http-equiv="Content-Security-Policy"]').get_attribute("content")
    assert "script-src 'none'" in csp
    assert "PDFに保存" in await reader.locator("body").inner_text()
    assert await reader.evaluate("globalThis.rawExecuted === true") is False
    await reader.screenshot(path=str(output / f"{label}-reader.png"), full_page=True)
    await reader.pdf(path=str(output / f"{label}-reader.pdf"), print_background=True)
    await reader.close()


async def check_keyboard(page) -> dict:
    details = page.locator("#stock-ai-details")
    if not await details.evaluate("node => node.open"):
        await details.locator("summary").focus()
        await page.keyboard.press("Enter")
    required = {
        "stock-ai-mode", "stock-ai-target", "stock-ai-position-intent", "stock-ai-user-hypothesis",
        "portfolio-ai-web-search", "scanner", "analyst", "judge", "critical", "details-summary",
        "portfolio-ai-review-reader-link",
    }
    await page.locator("#stock-ai-mode").focus()
    found = {}
    for _ in range(120):
        await page.keyboard.press("Tab")
        focused = await page.evaluate("""() => {
          const node = document.activeElement, css = getComputedStyle(node);
          const summary = node.matches('#stock-ai-details > summary') ? 'details-summary' : '';
          return {key: node.id || node.dataset.stockAiRun || summary, visible: node.matches(':focus-visible'),
            outline: css.outlineStyle, outlineWidth: css.outlineWidth, shadow: css.boxShadow};
        }""")
        if focused["key"] in required:
            found[focused["key"]] = focused
        if required <= found.keys():
            break
    assert required <= found.keys(), sorted(required - found.keys())
    for focus in found.values():
        assert focus["visible"] and (focus["outline"] != "none" or focus["shadow"] != "none"), focus
    return found


async def check_viewport(browser, html: str, output: Path, width: int) -> dict:
    context = await browser.new_context(viewport={"width": width, "height": 1000}, device_scale_factor=1)
    # Exercise the app's copy handler without replacing the user's OS clipboard.
    await context.add_init_script("""Object.defineProperty(navigator, 'clipboard', {
      value: {writeText: async (value) => {globalThis.qaCopiedPrompt = value;}}
    });""")
    routes = SyntheticRoutes(html)
    await context.route("**/*", routes.handle)
    page = await context.new_page()
    errors = []
    page.on("pageerror", lambda error: errors.append(str(error)))
    page.on("dialog", lambda dialog: dialog.accept())
    await page.goto(f"{ORIGIN}/ui/dashboard")
    await page.wait_for_function("state.data !== null && state.stockAiHistory.status === 'success'")
    for selector in (".stock-ai-workbench", ".stock-ai-control-pane", ".stock-ai-result-pane"):
        assert await page.locator(selector).count() == 1
    duplicate_ids = await page.evaluate("""() => {
      const ids = [...document.querySelectorAll('[id]')].map(node => node.id);
      return ids.filter((id, index) => ids.indexOf(id) !== index);
    }""")
    assert not duplicate_ids, duplicate_ids
    controls = page.locator(
        '.stock-ai-workbench input, .stock-ai-workbench button, '
        '.stock-ai-workbench select, .stock-ai-workbench textarea'
    )
    assert await controls.evaluate_all("nodes => nodes.every(node => node.closest('main'))")
    states = [await capture_state(page, output, width, "empty")]
    assert not states[0]["promptVisible"]
    routes.delay = asyncio.Event()
    await page.locator('[data-stock-ai-run="scanner"]').click()
    await page.wait_for_function("state.portfolioAiReview.status === 'loading'")
    states.append(await capture_state(page, output, width, "loading"))
    routes.delay.set()
    await page.wait_for_function("state.portfolioAiReview.status === 'success' && state.stockAiBusyRequestId === null")
    routes.delay = None
    await page.locator("#portfolio-ai-web-search").check()
    await run_analysis(page, routes, mode="analyst")
    current_text = await page.locator("#portfolio-ai-review-results").inner_text()
    assert "Web検索要求ON・実効設定OFF" in current_text
    assert "Web検索は未実行" in current_text
    states.append(await capture_state(page, output, width, "success"))
    if width == 1440:
        await check_reader(page, context, output, "portfolio-success")
    await run_analysis(page, routes, kind="failure")
    await page.locator("details.ai-raw-output").evaluate_all("nodes => nodes.forEach(node => node.open = true)")
    states.append(await capture_state(page, output, width, "failure"))
    assert await page.evaluate("globalThis.rawExecuted === true") is False
    if width == 1440:
        await check_reader(page, context, output, "portfolio-raw-failure")
    await run_analysis(page, routes, kind="long")
    states.append(await capture_state(page, output, width, "long"))
    await page.locator("#stock-ai-details").evaluate("node => node.open = true")
    await run_analysis(page, routes, mode="prompt_only")
    states.append(await capture_state(page, output, width, "prompt"))
    assert await page.locator("#stock-ai-copy-prompt").is_enabled()
    assert await page.locator("#stock-ai-details").evaluate("node => node.open")
    await page.locator("#stock-ai-copy-prompt").click()
    copied_prompt = await page.evaluate("globalThis.qaCopiedPrompt")
    assert copied_prompt == await page.locator("#stock-ai-prompt-output").input_value()
    await page.locator("#stock-ai-user-hypothesis").fill("回答後の条件変更")
    assert await page.locator("#stock-ai-copy-prompt").is_disabled()
    assert await page.locator("#stock-ai-prompt-output").input_value() == ""
    await page.locator("#management-space-select").select_option("watchlist:2")
    await page.wait_for_function("state.stockAiDataSynchronized && state.activeManagementSpace === 'watchlist:2'")
    await page.locator("#stock-ai-target").select_option("watchlist")
    await run_analysis(page, routes, mode="analyst")
    assert "検証用の名前付きリスト" in await page.locator("#portfolio-ai-review-results").inner_text()
    states.append(await capture_state(page, output, width, "named-watchlist"))
    await run_analysis(page, routes, kind="failure", mode="analyst")
    await page.locator("details.ai-raw-output").evaluate_all("nodes => nodes.forEach(node => node.open = true)")
    states.append(await capture_state(page, output, width, "named-watchlist-failure"))
    if width == 1440:
        await check_reader(page, context, output, "watchlist-raw-failure")
    await page.locator('[data-watchlist-ai-select="8035"]').check()
    assert await page.locator("#stock-ai-target").input_value() == "selected"
    await run_analysis(page, routes)
    assert "検証用の名前付きリスト" in await page.locator("#portfolio-ai-review-results").inner_text()
    states.append(await capture_state(page, output, width, "named-watchlist-selected"))
    if width == 1440:
        await check_reader(page, context, output, "watchlist-success")
    keyboard = await check_keyboard(page)
    await page.locator(f'[data-stock-ai-history-detail="{HISTORY_ID}"]').click()
    await page.wait_for_function("state.stockAiHistoryDetail.status === 'success'")
    if width == 1440:
        await check_reader(page, context, output, "saved-history", "stock-ai-history-reader-link")
        export_link = page.locator("#stock-ai-history-markdown-link")
        assert await export_link.get_attribute("download") is not None
        export_url = await export_link.get_attribute("href")
        assert export_url == f"/api/ai/stock-review/history/{HISTORY_ID}/export.md"
        # Chromium's native download request bypasses page routing in this
        # serverless setup. Check the link and intercepted export contract.
        markdown = await page.evaluate("async url => (await fetch(url)).text()", export_url)
        assert "合成データの履歴" in markdown
        (output / "saved-history-export.md").write_text(markdown, encoding="utf-8")
    await page.locator(f'[data-stock-ai-history-detail="{WATCHLIST_HISTORY_ID}"]').click()
    await page.wait_for_function(
        "historyId => state.stockAiHistoryDetail.status === 'success' && "
        "state.stockAiHistoryDetail.historyId === historyId", arg=WATCHLIST_HISTORY_ID,
    )
    if width == 1440:
        await check_reader(page, context, output, "saved-watchlist-history", "stock-ai-history-reader-link")
    assert not errors, errors
    assert not routes.unexpected, routes.unexpected
    await context.close()
    return {
        "states": states, "keyboard": keyboard, "javascript_errors": errors,
        "mocked_http_requests": routes.calls, "clipboard": "app handler checked with isolated clipboard stub",
        "markdown": "download link and intercepted export content checked; native download unverified",
        "effective_zero_search": "requested ON / effective OFF / not executed verified",
    }


async def main(output: Path):
    from playwright.async_api import async_playwright

    output.mkdir(parents=True, exist_ok=True)
    html = dashboard_ui().body.decode("utf-8")
    report = {"data": "synthetic only; all HTTP intercepted", "viewports": []}
    async with async_playwright() as playwright:
        browser = await playwright.chromium.launch(headless=True)
        report["browser_version"] = browser.version
        for width in (1440, 960, 390):
            report["viewports"].append(await check_viewport(browser, html, output, width))
        await browser.close()
    (output / "report.json").write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    state_count = sum(len(viewport["states"]) for viewport in report["viewports"])
    print(
        f"Chromium {report['browser_version']}: 3 viewports, {state_count} states, "
        f"readers/PDF/keyboard verified. {output / 'report.json'}"
    )


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, default=REPO_ROOT / "test-results" / "stock-ai")
    args = parser.parse_args()
    asyncio.run(main(args.output))
