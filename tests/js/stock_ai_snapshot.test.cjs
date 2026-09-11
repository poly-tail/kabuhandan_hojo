const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const vm = require('node:vm');
const { test } = require('node:test');

const source = fs.readFileSync(path.join(__dirname, '../../app/api/routes/ui.py'), 'utf8');
const extract = (name) => {
  const start = source.indexOf(`      const ${name} = `);
  assert.ok(start >= 0, name);
  const text = source.slice(start);
  const end = text.slice(1).search(/\r?\n      const /);
  return text.slice(0, end + 1);
};
const names = ['escapeHtml', 'escapeAttr', 'publicSecurityCode', 'uniqueAiItems',
  'renderAiText', 'renderCompactList', 'renderAiParagraph', 'aiModeLabel',
  'aiHistoryTargetLabel', 'renderAiRequestSnapshot', 'renderAiDataBasis'];
const ctx = vm.createContext({ formatDateTime: (value) => String(value) });
vm.runInContext(names.map(extract).join('\n') + '\nglobalThis.ui = {' + names.join(',') + '};', ctx);

test('frozen conditions render safely without reading live controls or guessing absent history conditions', () => {
  const output = ctx.ui.renderAiRequestSnapshot({
    contextLabel: 'ウォッチリスト「送信時の名前」',
    requestSnapshot: {
      mode: 'judge', target: 'watchlist', position_intent: 'core',
      user_hypothesis: '<script>not executable</script>', include_web_search: true,
      max_web_search_calls: 2, tickers: ['285A0'],
    },
  });
  assert.match(output, /送信時の名前/);
  assert.match(output, /全体売買判断/);
  assert.match(output, /コア玉/);
  assert.match(output, /&lt;script&gt;/);
  assert.doesNotMatch(output, /<script>/);
  assert.match(output, /285A/);
  assert.match(output, /Web検索要求: ON/);
  assert.equal(ctx.ui.renderAiRequestSnapshot({ data: { mode: 'judge' } }), '');
});

test('generation time and individual source dates remain distinct, including missing versus absent input', () => {
  const output = ctx.ui.renderAiDataBasis({
    generated_at: '2026-09-10T03:00:00Z',
    holdings_snapshot: [{ ticker: '7011', name: '三菱重工業' }],
    market_snapshot: [{
      ticker: '7011', price: 100, rsi: 0, recent_news: ['ニュース'], earnings_date: null,
      source_metadata: {
        price: [{ source: 'jquants', as_of: '2026-09-09', version: 'v1' }],
        technical: [{ source: 'technical_daily', as_of: '2026-09-08' }],
        news: [{ source: 'allowlisted_ir', as_of: null }],
        events: [{ source: 'unused_event_record', as_of: '2026-09-07' }],
      },
    }],
  });
  assert.match(output, /回答生成日時: 2026-09-10T03:00:00Z/);
  assert.match(output, /価格: 2026-09-09 \/ jquants \/ 更新版 v1/);
  assert.match(output, /テクニカル: 2026-09-08/);
  assert.match(output, /ニュース: 基準日時未取得/);
  assert.match(output, /需給: 未入力／未取得/);
  assert.match(output, /決算予定: 未入力／未取得/);
  assert.doesNotMatch(output, /unused_event_record/);
  assert.match(output, /三菱重工業（7011）/);
});

test('old records and unsafe source metadata remain explicit, escaped, and do not fabricate current time', () => {
  const output = ctx.ui.renderAiDataBasis({ market_snapshot: [{
    ticker: '9999', price: 10,
    source_metadata: { price: [{ source: '<img src=x onerror=alert(1)>', as_of: null }] },
  }] });
  assert.match(output, /回答生成日時: 未記録/);
  assert.match(output, /名称未登録（9999）/);
  assert.match(output, /価格: 基準日時未取得/);
  assert.match(output, /&lt;img/);
  assert.doesNotMatch(output, /<img/);
  assert.match(ctx.ui.renderAiDataBasis({}), /入力系列も未確認/);
});

test('support/resistance count as price input and missing metadata is not reported as absent', () => {
  const output = ctx.ui.renderAiDataBasis({ market_snapshot: [{ ticker: '7011', support_levels: [1] }] });
  assert.match(output, /価格: 基準日時未取得・由来未確認/);
  assert.match(output, /テクニカル: 未入力／未取得/);
});

test('unknown names already containing the public code do not duplicate it in data basis', () => {
  const output = ctx.ui.renderAiDataBasis({
    holdings_snapshot: [{ ticker: '9999', name: '名称未登録（9999）' }],
    market_snapshot: [{ ticker: '9999', price: 10 }],
  });
  assert.match(output, /名称未登録（9999）/);
  assert.doesNotMatch(output, /名称未登録（9999）（9999）/);
});

test('many price source records show a compact date span with full details retained', () => {
  const records = Array.from({ length: 25 }, (_, index) => ({
    source: 'jquants', as_of: `2026-08-${String(index + 1).padStart(2, '0')}`, version: `row-${index}`,
  }));
  const output = ctx.ui.renderAiDataBasis({ market_snapshot: [{
    ticker: '7011', price: 100, source_metadata: { price: records },
  }] });
  const beforeDetails = output.split('<details class="ai-source-details">')[0];
  assert.match(beforeDetails, /2026-08-01 ～ 2026-08-25 \/ jquants（25件）/);
  assert.doesNotMatch(beforeDetails, /更新版|2026-08-12/);
  assert.match(output, /出典・基準日時の詳細/);
  assert.match(output, /2026-08-12 \/ jquants \/ 更新版 row-11/);
});
