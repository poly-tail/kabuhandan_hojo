"""Independent browser shell for the minimal AI analysis vertical slice."""

from __future__ import annotations

import json
from uuid import UUID

from fastapi import APIRouter
from fastapi.responses import HTMLResponse


router = APIRouter(tags=["ai-analysis-ui"])


@router.get("/ui/analysis", response_class=HTMLResponse)
def analysis_page() -> HTMLResponse:
    """Serve a dependency-free page for one-security plain-text analysis."""

    return HTMLResponse(
        _analysis_shell_html(),
        headers={"Cache-Control": "no-store", "Referrer-Policy": "no-referrer"},
    )


@router.get("/ui/analysis/results/{request_id}", response_class=HTMLResponse)
def saved_analysis_page(request_id: UUID) -> HTMLResponse:
    """Serve a large plain-text reader for one locally saved response."""

    return HTMLResponse(
        _saved_analysis_shell_html(str(request_id)),
        headers={"Cache-Control": "no-store", "Referrer-Policy": "no-referrer"},
    )


def _analysis_shell_html() -> str:
    return """<!doctype html>
<html lang="ja">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>AI個別銘柄分析</title>
  <style>
    :root {
      color-scheme: light;
      font-family: system-ui, -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif;
      background: #f4f6f8;
      color: #17212b;
    }
    * { box-sizing: border-box; }
    body { margin: 0; padding: 24px; }
    main { max-width: 820px; margin: 0 auto; }
    h1 { margin: 0 0 8px; font-size: 1.65rem; }
    .lead { margin: 0 0 20px; color: #52606d; }
    .panel {
      margin-bottom: 16px;
      padding: 18px;
      border: 1px solid #d9e0e7;
      border-radius: 12px;
      background: #fff;
      box-shadow: 0 4px 16px rgba(23, 33, 43, 0.05);
    }
    label, .label { display: block; margin-bottom: 7px; font-weight: 700; }
    input, textarea, button { font: inherit; }
    input, textarea {
      width: 100%;
      border: 1px solid #aeb8c2;
      border-radius: 8px;
      padding: 10px 12px;
      background: #fff;
      color: inherit;
    }
    textarea { min-height: 130px; resize: vertical; }
    button {
      border: 0;
      border-radius: 8px;
      padding: 10px 16px;
      cursor: pointer;
      background: #1359c5;
      color: #fff;
      font-weight: 700;
    }
    button.secondary { background: #e8eef6; color: #17314f; }
    .button-link {
      display: inline-flex;
      align-items: center;
      border-radius: 8px;
      padding: 10px 16px;
      background: #1359c5;
      color: #fff;
      font-weight: 700;
      text-decoration: none;
    }
    button:disabled { cursor: not-allowed; opacity: 0.55; }
    .search-row { display: grid; grid-template-columns: 1fr auto; gap: 8px; }
    .results { display: grid; gap: 7px; margin-top: 10px; }
    .result-button { width: 100%; text-align: left; background: #edf3ff; color: #17314f; }
    .selected {
      margin-top: 12px;
      padding: 11px 12px;
      border-left: 4px solid #1359c5;
      border-radius: 6px;
      background: #f2f6fb;
    }
    .preset { display: inline-block; padding: 5px 9px; border-radius: 999px; background: #e8eef6; }
    .actions { display: flex; align-items: center; gap: 12px; margin-top: 14px; }
    .status { color: #415366; }
    .error {
      margin-top: 12px;
      padding: 10px 12px;
      border: 1px solid #d74343;
      border-radius: 8px;
      background: #fff1f1;
      color: #8a1717;
    }
    .answer {
      min-height: 80px;
      margin: 0;
      white-space: pre-wrap;
      overflow-wrap: anywhere;
      font-family: inherit;
      line-height: 1.65;
    }
    .answer-actions { display: flex; align-items: center; flex-wrap: wrap; gap: 12px; margin-top: 16px; }
    .saved-status { color: #236b3b; font-weight: 700; }
    .persistence-warning {
      margin-top: 14px;
      padding: 10px 12px;
      border: 1px solid #d99a25;
      border-radius: 8px;
      background: #fff8e6;
      color: #714b00;
    }
    details { margin-top: 12px; color: #52606d; font-size: 0.9rem; }
    [hidden] { display: none !important; }
    @media (max-width: 560px) {
      body { padding: 14px; }
      .search-row { grid-template-columns: 1fr; }
    }
  </style>
</head>
<body>
  <main>
    <h1>AI個別銘柄分析</h1>
    <p class="lead">登録済み銘柄を1件選び、OpenAIへ自由質問を送信します。回答は判断補助であり、投資助言ではありません。</p>

    <section class="panel" aria-labelledby="security-heading">
      <h2 id="security-heading">1. 銘柄選択</h2>
      <label for="security-query">銘柄コードまたは銘柄名</label>
      <div class="search-row">
        <input id="security-query" type="search" maxlength="100" autocomplete="off" placeholder="例: 7203 または トヨタ">
        <button id="security-search-button" class="secondary" type="button">検索</button>
      </div>
      <div id="security-search-results" class="results" aria-live="polite"></div>
      <div id="selected-security" class="selected" hidden></div>
    </section>

    <section class="panel" aria-labelledby="question-heading">
      <h2 id="question-heading">2. 質問</h2>
      <label for="question">自由質問</label>
      <textarea id="question" maxlength="4000" placeholder="この銘柄について確認したいことを入力してください。"></textarea>
      <p><span class="label">回答設定</span><span class="preset">STANDARD</span></p>
      <div class="actions">
        <button id="submit-analysis" type="button" disabled>STANDARDで送信</button>
        <span id="analysis-status" class="status" role="status" aria-live="polite"></span>
      </div>
      <div id="analysis-error" class="error" role="alert" hidden></div>
    </section>

    <section class="panel" aria-labelledby="answer-heading">
      <h2 id="answer-heading">3. 回答</h2>
      <pre id="answer-text" class="answer"></pre>
      <div id="analysis-persistence-warning" class="persistence-warning" role="alert" hidden></div>
      <div class="answer-actions">
        <span id="analysis-saved-status" class="saved-status" hidden>この回答はローカルに保存済みです</span>
        <a id="open-saved-analysis" class="button-link" target="_blank" rel="noopener noreferrer" hidden>別ウィンドウで大きく表示</a>
      </div>
      <details id="analysis-diagnostics" hidden>
        <summary>診断情報</summary>
        <div id="analysis-diagnostics-text"></div>
      </details>
    </section>
  </main>

  <script>
    (() => {
      const queryInput = document.getElementById("security-query");
      const searchButton = document.getElementById("security-search-button");
      const searchResults = document.getElementById("security-search-results");
      const selectedSecurityElement = document.getElementById("selected-security");
      const questionInput = document.getElementById("question");
      const submitButton = document.getElementById("submit-analysis");
      const statusElement = document.getElementById("analysis-status");
      const errorElement = document.getElementById("analysis-error");
      const answerElement = document.getElementById("answer-text");
      const persistenceWarningElement = document.getElementById("analysis-persistence-warning");
      const savedStatusElement = document.getElementById("analysis-saved-status");
      const openSavedAnalysisLink = document.getElementById("open-saved-analysis");
      const diagnosticsElement = document.getElementById("analysis-diagnostics");
      const diagnosticsText = document.getElementById("analysis-diagnostics-text");

      let selectedSecurity = null;
      let isSubmitting = false;
      let isSearching = false;

      function updateSubmitState() {
        submitButton.disabled = isSubmitting || isSearching || !selectedSecurity || !questionInput.value.trim();
        queryInput.disabled = isSubmitting;
        questionInput.disabled = isSubmitting;
        searchButton.disabled = isSubmitting || isSearching;
        for (const button of searchResults.querySelectorAll("button")) {
          button.disabled = isSubmitting;
        }
      }

      function setStatus(message) {
        statusElement.textContent = message;
      }

      function clearError() {
        errorElement.textContent = "";
        errorElement.hidden = true;
      }

      function clearPersistenceState() {
        persistenceWarningElement.textContent = "";
        persistenceWarningElement.hidden = true;
        savedStatusElement.hidden = true;
        openSavedAnalysisLink.hidden = true;
        openSavedAnalysisLink.removeAttribute("href");
      }

      function showError(message, requestId) {
        errorElement.textContent = message;
        errorElement.hidden = false;
        diagnosticsText.textContent = requestId ? `request_id: ${requestId}` : "";
        diagnosticsElement.hidden = !requestId;
      }

      function selectSecurity(item) {
        if (isSubmitting) {
          return;
        }
        selectedSecurity = item;
        const market = item.market || "市場未登録";
        selectedSecurityElement.textContent = `${item.name}（${item.ticker_code}） / ${market}`;
        selectedSecurityElement.hidden = false;
        searchResults.replaceChildren();
        answerElement.textContent = "";
        clearPersistenceState();
        diagnosticsElement.hidden = true;
        diagnosticsText.textContent = "";
        clearError();
        updateSubmitState();
      }

      function renderSearchResults(items) {
        searchResults.replaceChildren();
        if (!items.length) {
          searchResults.textContent = "該当する登録銘柄がありません。";
          return;
        }
        for (const item of items) {
          const button = document.createElement("button");
          button.type = "button";
          button.className = "result-button";
          button.textContent = `${item.name}（${item.ticker_code}） / ${item.market || "市場未登録"}`;
          button.addEventListener("click", () => selectSecurity(item));
          searchResults.appendChild(button);
        }
      }

      async function searchSecurities() {
        if (isSubmitting || isSearching) {
          return;
        }
        const query = queryInput.value.trim();
        clearError();
        if (!query) {
          showError("銘柄コードまたは銘柄名を入力してください。", null);
          return;
        }

        isSearching = true;
        updateSubmitState();
        setStatus("銘柄を検索中…");
        try {
          const response = await fetch(`/securities/search?q=${encodeURIComponent(query)}&limit=10`);
          if (!response.ok) {
            throw new Error("security search failed");
          }
          const items = await response.json();
          renderSearchResults(Array.isArray(items) ? items : []);
          setStatus("");
        } catch (_error) {
          showError("銘柄検索に失敗しました。", null);
          setStatus("");
        } finally {
          isSearching = false;
          updateSubmitState();
        }
      }

      async function submitAnalysis() {
        if (isSubmitting || !selectedSecurity) {
          return;
        }
        const question = questionInput.value.trim();
        if (!question) {
          showError("質問を入力してください。", null);
          return;
        }

        isSubmitting = true;
        updateSubmitState();
        clearError();
        answerElement.textContent = "";
        clearPersistenceState();
        diagnosticsElement.hidden = true;
        diagnosticsText.textContent = "";
        setStatus("OpenAIへ送信中…");

        try {
          const response = await fetch("/api/ai/analyses", {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({
              security_code: selectedSecurity.ticker_code,
              question,
              preset: "STANDARD"
            })
          });
          let payload = null;
          try {
            payload = await response.json();
          } catch (_parseError) {
            payload = null;
          }

          if (!response.ok || !payload || payload.status !== "success") {
            const code = payload?.error?.code || "REQUEST_FAILED";
            const message = payload?.error?.message || "AI分析に失敗しました。";
            showError(`${code}: ${message}`, payload?.request_id || null);
            setStatus("失敗しました");
            return;
          }

          const answerText = String(payload.answer_text || "").trim();
          if (!answerText) {
            showError("EMPTY_RESPONSE: 回答本文が空でした。", payload.request_id || null);
            setStatus("失敗しました");
            return;
          }

          answerElement.textContent = answerText;
          const requestId = String(payload.request_id || "").trim();
          if (payload.persistence_status === "saved" && requestId) {
            openSavedAnalysisLink.href = `/ui/analysis/results/${encodeURIComponent(requestId)}`;
            openSavedAnalysisLink.hidden = false;
            savedStatusElement.hidden = false;
          } else {
            const warning = String(payload.persistence_warning || "").trim()
              || "回答は生成されましたが、ローカルDBへ保存できませんでした。大画面での再表示は利用できません。";
            persistenceWarningElement.textContent = warning;
            persistenceWarningElement.hidden = false;
          }
          diagnosticsText.textContent = [
            `request_id: ${requestId || "未取得"}`,
            `openai_response_id: ${payload.openai_response_id || "未取得"}`
          ].join(" / ");
          diagnosticsElement.hidden = false;
          setStatus(payload.persistence_status === "saved"
            ? "回答を表示しました"
            : "回答を表示しました（保存できませんでした）");
        } catch (_error) {
          showError("NETWORK_ERROR: APIとの通信に失敗しました。", null);
          setStatus("失敗しました");
        } finally {
          isSubmitting = false;
          updateSubmitState();
        }
      }

      searchButton.addEventListener("click", searchSecurities);
      queryInput.addEventListener("keydown", (event) => {
        if (event.key === "Enter") {
          event.preventDefault();
          searchSecurities();
        }
      });
      questionInput.addEventListener("input", updateSubmitState);
      submitButton.addEventListener("click", submitAnalysis);
      updateSubmitState();
    })();
  </script>
</body>
</html>"""


def _saved_analysis_shell_html(request_id: str) -> str:
    encoded_request_id = json.dumps(request_id)
    return f"""<!doctype html>
<html lang="ja">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <meta name="referrer" content="no-referrer">
  <title>保存済みAI個別銘柄分析</title>
  <style>
    :root {{
      color-scheme: light;
      font-family: system-ui, -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif;
      background: #eef2f6;
      color: #17212b;
    }}
    * {{ box-sizing: border-box; }}
    body {{ margin: 0; padding: 24px; }}
    main {{ width: min(1380px, 100%); margin: 0 auto; }}
    header {{ margin-bottom: 18px; }}
    h1 {{ margin: 0 0 8px; font-size: clamp(1.55rem, 3vw, 2.15rem); }}
    .lead, .meta {{ color: #52606d; }}
    .panel {{
      margin-bottom: 16px;
      padding: clamp(18px, 3vw, 32px);
      border: 1px solid #d3dce5;
      border-radius: 14px;
      background: #fff;
      box-shadow: 0 7px 24px rgba(23, 33, 43, 0.07);
    }}
    .status {{ min-height: 1.5em; color: #415366; }}
    .error {{
      padding: 12px 14px;
      border: 1px solid #d74343;
      border-radius: 8px;
      background: #fff1f1;
      color: #8a1717;
    }}
    .question, .answer {{
      margin: 0;
      white-space: pre-wrap;
      overflow-wrap: anywhere;
      font-family: inherit;
    }}
    .question {{ line-height: 1.6; }}
    .answer {{ min-height: 280px; font-size: 1.05rem; line-height: 1.8; }}
    .back-link {{ color: #1359c5; font-weight: 700; }}
    [hidden] {{ display: none !important; }}
    @media (max-width: 640px) {{
      body {{ padding: 12px; }}
      .panel {{ border-radius: 10px; }}
      .answer {{ font-size: 1rem; }}
    }}
  </style>
</head>
<body>
  <main>
    <header>
      <h1>保存済みAI個別銘柄分析</h1>
      <p class="lead">回答は判断補助であり、投資助言ではありません。</p>
      <a class="back-link" href="/ui/analysis">分析画面へ戻る</a>
    </header>

    <p id="saved-analysis-status" class="status" role="status" aria-live="polite">保存済み回答を読み込み中…</p>
    <div id="saved-analysis-error" class="error" role="alert" hidden></div>

    <section id="saved-analysis-content" hidden>
      <div class="panel">
        <h2 id="saved-security"></h2>
        <p id="saved-meta" class="meta"></p>
      </div>
      <div class="panel">
        <h2>質問</h2>
        <pre id="saved-question" class="question"></pre>
      </div>
      <div class="panel">
        <h2>回答</h2>
        <pre id="saved-answer" class="answer"></pre>
      </div>
    </section>
  </main>

  <script>
    (() => {{
      const requestId = {encoded_request_id};
      const statusElement = document.getElementById("saved-analysis-status");
      const errorElement = document.getElementById("saved-analysis-error");
      const contentElement = document.getElementById("saved-analysis-content");
      const securityElement = document.getElementById("saved-security");
      const metaElement = document.getElementById("saved-meta");
      const questionElement = document.getElementById("saved-question");
      const answerElement = document.getElementById("saved-answer");

      function showError(message) {{
        statusElement.textContent = "読み込みに失敗しました";
        errorElement.textContent = message;
        errorElement.hidden = false;
        contentElement.hidden = true;
        questionElement.textContent = "";
        answerElement.textContent = "";
      }}

      async function loadSavedAnalysis() {{
        try {{
          const response = await fetch(`/api/ai/analyses/${{encodeURIComponent(requestId)}}`, {{
            cache: "no-store"
          }});
          let payload = null;
          try {{
            payload = await response.json();
          }} catch (_parseError) {{
            payload = null;
          }}
          if (!response.ok || !payload || payload.status !== "success") {{
            const code = payload?.error?.code || "REQUEST_FAILED";
            const message = payload?.error?.message || "保存済み回答を取得できませんでした。";
            showError(`${{code}}: ${{message}}`);
            return;
          }}

          const answerText = String(payload.answer_text || "").trim();
          const questionText = String(payload.question || "").trim();
          const securityCode = String(payload.security?.security_code || "").trim();
          const securityName = String(payload.security?.name || "").trim();
          if (!answerText || !questionText || !securityCode || !securityName) {{
            showError("INVALID_SAVED_RESPONSE: 保存済み回答の形式が不正です。");
            return;
          }}

          const market = payload.security?.market || "市場未登録";
          const savedAt = payload.saved_at ? new Date(payload.saved_at).toLocaleString("ja-JP") : "保存日時不明";
          securityElement.textContent = `${{securityName}}（${{securityCode}}）`;
          metaElement.textContent = `${{market}} / ${{payload.preset || "STANDARD"}} / ${{payload.model || "model不明"}} / ${{savedAt}}`;
          questionElement.textContent = questionText;
          answerElement.textContent = answerText;
          document.title = `${{securityName}}（${{securityCode}}）｜保存済みAI分析`;
          errorElement.hidden = true;
          contentElement.hidden = false;
          statusElement.textContent = "保存済み回答を表示しました";
        }} catch (_error) {{
          showError("NETWORK_ERROR: APIとの通信に失敗しました。");
        }}
      }}

      loadSavedAnalysis();
    }})();
  </script>
</body>
</html>"""
