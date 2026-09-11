// Execute the dashboard's actual functions with deferred API promises. No network,
// browser globals, production database, or third-party test dependencies are used.
const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const vm = require('node:vm');
const { test } = require('node:test');

const source = fs.readFileSync(path.join(__dirname, '../../app/api/routes/ui.py'), 'utf8');
const declaration = (name) => {
  const start = source.indexOf(`      const ${name} = `);
  assert.ok(start >= 0, `dashboard declaration exists: ${name}`);
  const remaining = source.slice(start);
  const next = remaining.slice(1).search(/\r?\n      (?:const |window\.)/);
  return next < 0 ? remaining : remaining.slice(0, next + 1);
};
const deferred = () => {
  let resolve;
  let reject;
  const promise = new Promise((yes, no) => { resolve = yes; reject = no; });
  return { promise, resolve, reject };
};
const successfulReview = { status: 'success', manual_prompt: 'current prompt', stocks: [] };

function harness() {
  const elements = new Map();
  const element = (id) => {
    if (!elements.has(id)) elements.set(id, {
      id, value: '', checked: false, disabled: false, hidden: true, textContent: '',
      listeners: new Map(),
      addEventListener(event, fn) {
        if (!this.listeners.has(event)) this.listeners.set(event, []);
        this.listeners.get(event).push(fn);
      },
      dispatch(event) { for (const fn of this.listeners.get(event) || []) fn({ target: this }); },
      removeAttribute(name) { delete this[name]; },
      setAttribute(name, value) { this[name] = value; },
      focus() {}, select() {},
    });
    return elements.get(id);
  };
  const buttons = Array.from({ length: 5 }, (_, index) => element(`run-${index}`));
  const calls = [];
  const queues = { post: [], delete: [], patch: [], fetch: [] };
  const api = (kind) => async (...args) => {
    calls.push({ kind, args });
    const next = queues[kind].shift();
    if (next instanceof Error) throw next;
    return next?.promise || next || {};
  };
  const revoked = [];
  const ctx = vm.createContext({
    Map, Set, URLSearchParams, INITIAL_WATCHLIST_ID: null, PAGE_MODE: 'top',
    URL: { revokeObjectURL: (url) => revoked.push(url) },
    document: {
      getElementById: element,
      querySelectorAll: () => buttons,
    },
    window: { confirm: () => true },
    postJson: api('post'), deleteJson: api('delete'), patchJson: api('patch'), fetchJson: api('fetch'),
    renderAll() {}, renderManagementSpace() {}, renderPortfolio() {}, renderWatchlistAiReview() {},
    renderSearchResults() {}, restoreManualFeedback() {},
    loadStockAiUsage: async () => {}, loadStockAiHistory: async () => {},
    fill: (id, value) => { element(id).textContent = value; },
    text: (id, value) => { element(id).textContent = value; },
    setAiResultBusy: (id, busy) => { element(id).busy = busy; },
    escapeHtml: (value) => String(value), aiReviewResultStatusLabel: (value) => value.status,
    renderAiStockCard: () => '', renderAiReviewSummary: () => 'answer',
    renderAiRawFallback: (value) => value || '', renderAiParagraph: (value) => value,
    aiHoldingsSourceLabel: (value) => value,
    aiModeLabel: (value) => value, aiHistoryTargetLabel: (value) => value,
    formatDateTime: (value) => String(value), renderCompactList: (items) => items.join('\n'),
    setPortfolioFeedback: (message) => { element('portfolio-feedback').textContent = message; },
    setManagementSpaceFeedback: (message) => { element('space-feedback').textContent = message; },
    prepareAiReviewReader: (key, review) => {
      if (review.data) element('portfolio-ai-review-reader-link').hidden = false;
    },
  });
  const names = [
    'state', 'AI_REVIEW_READER_CONFIG', 'aiReviewReaderObjectUrls', 'publicSecurityCode',
    'watchlistSpaceKey', 'activeWatchlistId', 'activeWatchlistCollection', 'activeWatchlistSelection',
    'clearAiReviewReader', 'setPortfolioAiButtonsDisabled', 'parseTickerInput',
    'aiWebSearchEvidenceLabel', 'aiWebSearchSettingLabel',
    'renderAiRequestSnapshot', 'renderAiDataBasis',
    'selectedWatchlistItems', 'selectedStockAiHoldings', 'estimateStockAiCost', 'updateStockAiCost',
    'syncStockAiPrompt', 'buildStockAiRequest', 'stockAiReviewContext', 'isHighCostStockAiRequest',
    'renderPortfolioAiReview', 'runPortfolioAiReview', 'invalidateStockAiReview',
    'syncWatchlistSelectionToAiTarget', 'setupStockAiControls', 'loadDashboard',
    'selectManagementSpace', 'closeWatchlistCollectionForm', 'saveWatchlistCollection',
    'deleteActiveWatchlistCollection', 'addSearchResultToActiveWatchlist', 'removeActiveWatchlistItem',
    'savePortfolioHolding', 'removePortfolioHolding',
  ];
  // New state helpers remain production code, also executed when present.
  for (const name of ['stockAiInputIdentity', 'syncStockAiExecutionState', 'markStockAiDataUnsynced', 'invalidateStockAiForDataMutation']) {
    if (source.includes(`      const ${name} = `)) names.push(name);
  }
  vm.runInContext(names.map(declaration).join('\n') + '\n globalThis.ui = { ' + names.join(', ') + ' };', ctx);
  const ui = ctx.ui;
  ui.state.data = {
    portfolio_items: [{ ticker_code: '7011', name: '三菱重工業', quantity: 5, average_cost: 2000 }],
    watchlist_items: [{ ticker_code: '8035', name: '東京エレクトロン' }],
    watchlist_collections: [{ id: 2, name: '検証リスト', is_default: false }],
  };
  element('stock-ai-mode').value = 'judge';
  element('stock-ai-target').value = 'holdings';
  element('stock-ai-position-intent').value = 'core';
  element('stock-ai-max-web-search').value = '2';
  element('stock-ai-save-result').checked = true;
  element('stock-ai-use-cache').checked = true;
  element('portfolio-ticker-input').value = '7011';
  element('portfolio-quantity-input').value = '10';
  ui.setupStockAiControls();
  const change = (id, value, event = 'change') => {
    if (typeof value === 'boolean') element(id).checked = value;
    else element(id).value = value;
    element(id).dispatch(event);
  };
  const assertCleared = () => {
    assert.notEqual(ui.state.portfolioAiReview.status, 'success');
    assert.equal(ui.state.portfolioAiReview.data, null);
    assert.equal(ui.state.lastManualPrompt, '');
    assert.equal(element('stock-ai-prompt-output').value, '');
    assert.equal(element('stock-ai-copy-prompt').disabled, true);
    assert.equal(element('portfolio-ai-review-reader-link').hidden, true);
  };
  return { ui, element, buttons, calls, queues, change, assertCleared, revoked,
    setConfirmation: (value) => { ctx.window.confirm = () => value; } };
}

for (const completion of ['success', 'failure']) {
  test(`input change rejects old ${completion}, keeps busy until settled, then permits a new run`, async () => {
    const h = harness();
    const old = deferred();
    h.queues.post.push(old);
    const pending = h.ui.runPortfolioAiReview();
    h.change('stock-ai-target', 'candidates');
    h.assertCleared();
    assert.ok(h.buttons.every((button) => button.disabled));
    await h.ui.runPortfolioAiReview('analyst');
    assert.equal(h.calls.filter((call) => call.kind === 'post').length, 1);
    assert.equal(h.element('stock-ai-mode').value, 'judge');
    if (completion === 'success') old.resolve(successfulReview);
    else old.reject(new Error('old provider failure'));
    await pending;
    h.assertCleared();
    assert.ok(h.buttons.every((button) => !button.disabled));
    h.queues.post.push(successfulReview);
    await h.ui.runPortfolioAiReview();
    assert.equal(h.ui.state.portfolioAiReview.status, 'success');
    assert.equal(h.ui.state.portfolioAiReview.contextLabel, '狙い中銘柄');
  });
}

test('each analysis input clears result, reader and prompt; duplicate events are idempotent', async () => {
  for (const [id, value] of [
    ['stock-ai-mode', 'critical'], ['stock-ai-target', 'selected'], ['stock-ai-tickers', '8035'],
    ['stock-ai-user-hypothesis', '長期の仮説'], ['stock-ai-position-intent', 'short'],
    ['stock-ai-max-web-search', '1'], ['portfolio-ai-web-search', false], ['portfolio-ai-mock-response', true],
  ]) {
    const h = harness();
    h.queues.post.push(successfulReview);
    await h.ui.runPortfolioAiReview();
    assert.equal(h.element('stock-ai-copy-prompt').disabled, false);
    h.ui.aiReviewReaderObjectUrls.set('portfolio', 'blob:previous');
    h.change(id, value, 'input');
    h.assertCleared();
    assert.deepEqual(h.revoked, ['blob:previous']);
    const generation = h.ui.state.stockAiRequestId;
    h.change(id, value, 'change');
    assert.equal(h.ui.state.stockAiRequestId, generation, id);
  }
});

test('save/cache operational settings preserve current answer', async () => {
  const h = harness();
  h.queues.post.push(successfulReview);
  await h.ui.runPortfolioAiReview();
  for (const id of ['stock-ai-save-result', 'stock-ai-use-cache']) h.change(id, false);
  assert.equal(h.ui.state.portfolioAiReview.status, 'success');
  assert.equal(h.element('stock-ai-copy-prompt').disabled, false);
});

for (const operation of ['savePortfolioHolding', 'removePortfolioHolding']) {
  test(`${operation}: successful mutation invalidates before refresh; empty holdings cannot revive answer`, async () => {
    const h = harness();
    h.queues.post.push(successfulReview);
    await h.ui.runPortfolioAiReview();
    const refresh = deferred();
    h.queues.fetch.push(refresh);
    const pending = h.ui[operation]('7011');
    await new Promise(setImmediate);
    h.assertCleared();
    assert.ok(h.buttons.every((button) => button.disabled));
    refresh.resolve({ ...h.ui.state.data, portfolio_items: [] });
    await pending;
    h.assertCleared();
    assert.equal(h.ui.state.data.portfolio_items.length, 0);
    assert.ok(h.buttons.every((button) => !button.disabled));
  });

  test(`${operation}: mutation failure preserves valid answer`, async () => {
    const h = harness();
    h.queues.post.push(successfulReview);
    await h.ui.runPortfolioAiReview();
    h.queues[operation.startsWith('save') ? 'post' : 'delete'].push(new Error('write failed'));
    await h.ui[operation]('7011');
    assert.equal(h.ui.state.portfolioAiReview.status, 'success');
    assert.equal(h.calls.filter((call) => call.kind === 'fetch').length, 0);
  });

  test(`${operation}: write success + refresh failure blocks stale-state analysis until resynchronized`, async () => {
    const h = harness();
    h.queues.post.push(successfulReview);
    await h.ui.runPortfolioAiReview();
    h.queues.fetch.push(new Error('refresh unavailable'));
    await h.ui[operation]('7011');
    h.assertCleared();
    assert.match(h.element('portfolio-feedback').textContent, /保存|削除/);
    assert.match(h.element('portfolio-ai-review-feedback').textContent, /未同期|再取得/);
    const callsBefore = h.calls.length;
    await h.ui.runPortfolioAiReview();
    assert.equal(h.calls.length, callsBefore);
    assert.ok(h.buttons.every((button) => button.disabled));
    h.queues.fetch.push({ ...h.ui.state.data, portfolio_items: [] });
    await h.ui.loadDashboard();
    assert.ok(h.buttons.every((button) => !button.disabled));
  });
}

test('a refresh started before a successful write cannot clear the unsynchronized guard', async () => {
  const h = harness();
  h.queues.post.push(successfulReview);
  await h.ui.runPortfolioAiReview();
  const oldRefresh = deferred();
  h.queues.fetch.push(oldRefresh, new Error('new refresh failed'));
  const oldPending = h.ui.loadDashboard();
  await h.ui.savePortfolioHolding();
  oldRefresh.resolve(h.ui.state.data);
  assert.equal(await oldPending, false);
  h.assertCleared();
  assert.ok(h.buttons.every((button) => button.disabled));
});

test('mock checkbox selection preserves synthetic origin; manual ticker cannot inherit mock quantities', () => {
  const h = harness();
  h.ui.state.data.mode = 'mock';
  h.ui.state.activeManagementSpace = 'watchlist:2';
  h.ui.activeWatchlistSelection().add('8035');
  h.change('stock-ai-target', 'selected');
  assert.equal(h.ui.buildStockAiRequest().use_mock_holdings, true);
  h.ui.activeWatchlistSelection().clear();
  h.change('stock-ai-tickers', '7011');
  const manual = h.ui.buildStockAiRequest();
  assert.equal(manual.use_mock_holdings, false);
  assert.equal(manual.holdings[0].quantity, 0);
  assert.equal(manual.holdings[0].average_price, null);
});

test('live empty-target estimates do not invent portfolio or candidate counts', () => {
  const h = harness();
  h.ui.state.data.portfolio_items = [];
  assert.equal(h.ui.estimateStockAiCost().count, 0);
  assert.equal(h.ui.estimateStockAiCost().estimate, 0);
  h.change('stock-ai-target', 'candidates');
  assert.equal(h.ui.estimateStockAiCost().count, 0);
  assert.equal(h.ui.estimateStockAiCost().estimate, 0);
  h.change('portfolio-ai-mock-response', true);
  assert.equal(h.ui.estimateStockAiCost().estimate, 0);
});

test('request snapshot retains sent major conditions independently of later controls', async () => {
  const h = harness();
  h.change('stock-ai-user-hypothesis', '送信前の仮説');
  h.queues.post.push(successfulReview);
  await h.ui.runPortfolioAiReview();
  const snapshot = h.ui.state.portfolioAiReview.requestSnapshot;
  assert.equal(snapshot.mode, 'judge');
  assert.equal(snapshot.user_hypothesis, '送信前の仮説');
  h.change('stock-ai-user-hypothesis', '別の仮説');
  assert.equal(snapshot.user_hypothesis, '送信前の仮説');
  h.assertCleared();
});

test('old provider finally cannot unlock analysis while a committed mutation remains unsynchronized', async () => {
  const h = harness();
  const provider = deferred();
  h.queues.post.push(provider);
  const pending = h.ui.runPortfolioAiReview();
  h.queues.fetch.push(new Error('refresh unavailable'));
  await h.ui.savePortfolioHolding();
  provider.resolve(successfulReview);
  await pending;
  h.assertCleared();
  assert.ok(h.buttons.every((button) => button.disabled));
  assert.match(h.element('portfolio-ai-review-feedback').textContent, /未同期/);
});

test('named-list snapshot is fixed while waiting; scope and checkbox invalidation retain busy guard', async () => {
  const h = harness();
  h.ui.state.activeManagementSpace = 'watchlist:2';
  h.change('stock-ai-target', 'watchlist');
  const response = deferred();
  h.queues.post.push(response);
  const pending = h.ui.runPortfolioAiReview();
  h.ui.state.data.watchlist_collections[0].name = '変更後の名前';
  response.resolve(successfulReview);
  await pending;
  assert.match(h.ui.state.portfolioAiReview.contextLabel, /検証リスト/);
  const next = deferred();
  h.queues.post.push(next);
  const running = h.ui.runPortfolioAiReview();
  h.ui.activeWatchlistSelection().add('8035');
  h.ui.invalidateStockAiReview();
  h.ui.syncWatchlistSelectionToAiTarget();
  assert.equal(h.element('stock-ai-target').value, 'selected');
  await h.ui.runPortfolioAiReview();
  assert.ok(h.buttons.every((button) => button.disabled));
  h.queues.fetch.push(h.ui.state.data);
  await h.ui.selectManagementSpace('portfolio');
  next.resolve(successfulReview);
  await running;
  h.assertCleared();
});

for (const operation of ['addSearchResultToActiveWatchlist', 'removeActiveWatchlistItem']) {
  test(`${operation}: list membership change invalidates and failed refresh blocks further execution`, async () => {
    const h = harness();
    h.ui.state.activeManagementSpace = 'watchlist:2';
    h.ui.state.searchResults = [{ ticker_code: '8035', name: '東京エレクトロン', market: 'TSE' }];
    h.change('stock-ai-target', 'watchlist');
    h.queues.post.push(successfulReview);
    await h.ui.runPortfolioAiReview();
    h.queues.fetch.push(new Error('refresh unavailable'));
    await h.ui[operation]('8035');
    h.assertCleared();
    const callsBefore = h.calls.length;
    await h.ui.runPortfolioAiReview();
    assert.equal(h.calls.length, callsBefore);
    assert.ok(h.buttons.every((button) => button.disabled));
  });
}

test('search render labels distinguish permission, observed execution, and unknown legacy data', () => {
  const h = harness();
  assert.match(h.ui.aiWebSearchEvidenceLabel({ include_web_search: true, web_search_status: 'not_run' }), /未実行.*裏取りなし/);
  assert.match(h.ui.aiWebSearchEvidenceLabel({ include_web_search: true, web_search_status: 'executed' }), /実行.*主張の裏付けは別確認/);
  assert.match(h.ui.aiWebSearchEvidenceLabel({ include_web_search: true, web_search_used: true }), /実績は未確認/);
  assert.match(h.ui.aiWebSearchSettingLabel({ web_search_requested: true, include_web_search: false }), /要求ON.*実効設定OFF/);
  assert.match(h.ui.aiWebSearchEvidenceLabel({ cache_hit: true, web_search_status: 'executed' }), /前回生成時/);
});

test('raw failure renderer and its reader source retain search evidence', () => {
  const h = harness();
  h.ui.state.portfolioAiReview = {
    status: 'json_parse_failed',
    data: {
      status: 'json_parse_failed', raw_model_output: 'stub raw response',
      web_search_requested: true, include_web_search: true, web_search_status: 'not_run',
    },
  };
  h.ui.renderPortfolioAiReview();
  const rendered = h.element('portfolio-ai-review-results').textContent;
  assert.match(rendered, /Web検索は未実行/);
  assert.match(rendered, /最新のWeb裏取りなし/);
  assert.match(rendered, /stub raw response/);
  assert.equal(h.element('portfolio-ai-review-reader-link').hidden, false);
});

test('canceling a mode-button confirmation cannot retain an answer under the changed mode', async () => {
  const h = harness();
  h.queues.post.push(successfulReview);
  await h.ui.runPortfolioAiReview();
  const callsBefore = h.calls.length;
  h.setConfirmation(false);
  await h.ui.runPortfolioAiReview('critical');
  assert.equal(h.calls.length, callsBefore);
  assert.equal(h.element('stock-ai-mode').value, 'critical');
  h.assertCleared();
  assert.ok(h.buttons.every((button) => !button.disabled));
});

test('manual selected ticker retains actual holding values when also on a watchlist', () => {
  const h = harness();
  h.ui.state.data.watchlist_items.push({ ticker_code: '7011', name: '三菱重工業' });
  h.change('stock-ai-target', 'selected');
  h.change('stock-ai-tickers', '7011');
  let holding = h.ui.buildStockAiRequest().holdings[0];
  assert.equal(holding.quantity, 5);
  assert.equal(holding.average_price, 2000);
  h.ui.state.data.portfolio_items[0].average_cost = 0;
  holding = h.ui.buildStockAiRequest().holdings[0];
  assert.equal(holding.average_price, 0);
});
