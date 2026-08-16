"""Independent browser shell for the minimal AI analysis vertical slice."""

from __future__ import annotations

from fastapi import APIRouter
from fastapi.responses import HTMLResponse


router = APIRouter(tags=["ai-analysis-ui"])


@router.get("/ui/analysis", response_class=HTMLResponse)
def analysis_page() -> HTMLResponse:
    """Serve a dependency-free page for one-security plain-text analysis."""

    return HTMLResponse(_analysis_shell_html())


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
      const diagnosticsElement = document.getElementById("analysis-diagnostics");
      const diagnosticsText = document.getElementById("analysis-diagnostics-text");

      let selectedSecurity = null;
      let isSubmitting = false;

      function updateSubmitState() {
        submitButton.disabled = isSubmitting || !selectedSecurity || !questionInput.value.trim();
      }

      function setStatus(message) {
        statusElement.textContent = message;
      }

      function clearError() {
        errorElement.textContent = "";
        errorElement.hidden = true;
      }

      function showError(message, requestId) {
        errorElement.textContent = message;
        errorElement.hidden = false;
        diagnosticsText.textContent = requestId ? `request_id: ${requestId}` : "";
        diagnosticsElement.hidden = !requestId;
      }

      function selectSecurity(item) {
        selectedSecurity = item;
        const market = item.market || "市場未登録";
        selectedSecurityElement.textContent = `${item.ticker_code} ${item.name} / ${market}`;
        selectedSecurityElement.hidden = false;
        searchResults.replaceChildren();
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
          button.textContent = `${item.ticker_code} ${item.name} / ${item.market || "市場未登録"}`;
          button.addEventListener("click", () => selectSecurity(item));
          searchResults.appendChild(button);
        }
      }

      async function searchSecurities() {
        const query = queryInput.value.trim();
        clearError();
        if (!query) {
          showError("銘柄コードまたは銘柄名を入力してください。", null);
          return;
        }

        searchButton.disabled = true;
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
          searchButton.disabled = false;
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
          diagnosticsText.textContent = [
            `request_id: ${payload.request_id}`,
            `openai_response_id: ${payload.openai_response_id || "未取得"}`
          ].join(" / ");
          diagnosticsElement.hidden = false;
          setStatus("回答を表示しました");
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

