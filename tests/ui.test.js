const { test } = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const { JSDOM, VirtualConsole } = require('jsdom');

const root = path.resolve(__dirname, '..');
const item = (id, name, value, rank, extra = {}) => ({
  id, name, nameRu: name, value, official_rank: rank, display_rank: rank,
  tier: 'Tier A', rank_locked: true, category: 'misc', abbreviation: '',
  image: 'images/placeholder.svg', price_status: 'baseline', confidence: 0, rarity: null,
  lcValue: value === null ? null : value / 10, unit_id: id, unit_quantity: 1,
  ...extra,
});
const live = {
  schema_version: 2, revision: 'ui-fixture', currency: { anchor_id: 'item_194', lc_id: 'item_102' },
  meta: { updated_at_iso: '2026-11-03T12:00:00Z', total_trades_1h: 0, supported_observations: 0 },
  discord_source: { mode: 'offline', complete: false },
  items: [
    item('item_1', 'Cool Shades', 1000, 1, { rarity: 'Collectable' }),
    item('item_92', 'Kraken Armor Set (Azure)', 502, 20, { tier: 'Very Unstable', rank_locked: false }),
    item('item_60', '10x Legendary Fruit Chest', 100, 2, { unit_id: 'item_102', unit_quantity: 10 }),
    item('item_58', 'Mythical Fruit Chest', 80, 3),
    item('item_72', 'Mochi', 60, 4, { category: 'fruits', rarity: 'Mythical' }),
    item('item_86', 'Pika', 50, 5, { category: 'fruits', rarity: 'Legendary' }),
    item('item_102', 'Legendary Fruit Chest', 10, 6),
    item('item_194', 'SP Reset Essence', 1, 7, { tier: 'Tier F' }),
    item('item_verity', 'Verity', null, 21, { tier: 'New Items', rank_locked: false }),
  ],
  changes: [
    { id: 'item_102', old_value: 9, new_value: 10, delta_pts: 1, delta_pct: 11.11, reason: 'market' },
    { id: 'item_58', old_value: 90, new_value: 80, delta_pts: -10, delta_pct: -11.11, reason: 'market' },
  ],
};
const readFeed = [
  { id: 'latest', timestamp: '2026-11-03T11:59:00Z', offer: [['item_58', 1]], want: [['item_102', 8]], decision: 'used', independent_authors: 6 },
  { id: 'earlier', timestamp: '2026-11-03T11:40:00Z', offer: [['item_86', 1]], want: [['item_72', 1]], decision: 'waiting', independent_authors: 1 },
  { id: 'partial', timestamp: '2026-11-03T11:50:00Z', offer: [['item_72', 1]], want: [['item_86', 1]], want_markers: ['unknown', 'small_adds'], decision: 'incomplete', independent_authors: 0 },
  { id: 'offered-pika', timestamp: '2026-11-03T11:55:00Z', offer: [['item_86', 1]], want: [['item_102', 5]], decision: 'used', independent_authors: 9 },
];

async function boot(trade = { y: [], t: [] }, payload = live) {
  const errors = [];
  const vc = new VirtualConsole();
  vc.on('jsdomError', error => errors.push(error.message));
  const hash = Buffer.from(encodeURIComponent(JSON.stringify(trade))).toString('base64');
  const dom = new JSDOM(fs.readFileSync(path.join(root, 'index.html'), 'utf8'), {
    url: `https://gpo.test/#trade=${hash}`,
    runScripts: 'dangerously',
    virtualConsole: vc,
    beforeParse(window) {
      window.localStorage.setItem('gpo_audio', 'false');
      window.Audio = class { play() { return Promise.resolve(); } pause() {} };
      window.fetch = async url => ({
        ok: true,
        json: async () => String(url).includes('history') ? { items: {} } : structuredClone(payload),
        arrayBuffer: async () => new ArrayBuffer(0),
      });
    },
  });
  for (const file of [...dom.window.document.querySelectorAll('script[src]')].map(script => script.getAttribute('src'))) {
    if (fs.existsSync(path.join(root, file))) dom.window.eval(fs.readFileSync(path.join(root, file), 'utf8'));
  }
  await new Promise(resolve => setImmediate(resolve));
  return { dom, window: dom.window, document: dom.window.document, errors };
}

test('a shared trade cannot inject markup through quantity', async () => {
  const app = await boot({ y: [['item_102', '<img id=quantityProbe onerror=window.injected=true>']], t: [] });
  try {
    assert.equal(app.document.getElementById('quantityProbe'), null);
    assert.equal(app.document.querySelectorAll('#youSlotsGrid .trade-slot-card').length, 0);
    assert.deepEqual(app.errors, []);
  } finally { app.dom.window.close(); }
});

test('shared calculator uses the same loaded price as the catalogue', async () => {
  const app = await boot({ y: [['item_92', 1]], t: [] });
  try {
    const expected = live.items.find(item => item.id === 'item_92').value;
    const shown = app.document.getElementById('youTotalPts').textContent.replace(/[^\d.]/g, '');
    assert.equal(Number(shown), expected);
  } finally { app.dom.window.close(); }
});

test('one legendary chest is exactly one LC in the calculator', async () => {
  const app = await boot({ y: [['item_102', 1]], t: [] });
  try {
    assert.equal(Number(app.document.getElementById('youTotalLc').textContent.replace(/[^\d.]/g, '')), 1);
  } finally { app.dom.window.close(); }
});

test('the header chest conversion uses the loaded price snapshot', async () => {
  const app = await boot();
  try {
    assert.equal(app.document.getElementById('heroLcValue')?.textContent, '10 pts');
  } finally { app.dom.window.close(); }
});

test('game rarity is shown separately from the official trading tier', async () => {
  const app = await boot();
  try {
    const card = app.document.querySelector('#quickItemsCardsGrid [data-id="item_1"]').closest('article');
    assert.equal(card.querySelector('.rarity-label')?.textContent, 'Collectable');
    assert.equal(card.querySelector('.tier-tag').textContent, 'A');
    const unknown = app.document.querySelector('#quickItemsCardsGrid [data-id="item_verity"]').closest('article');
    assert.equal(unknown.dataset.rarity, 'unknown');
  } finally { app.dom.window.close(); }
});

test('a reviewed price exposes its source and is distinguished from market changes', async () => {
  const payload = structuredClone(live);
  Object.assign(payload.items.find(item => item.id === 'item_92'), {
    price_status: 'reviewed', reference_basis: 'lc',
    price_reference: { checked_at: '2026-11-03T12:00:00Z', source_updated_at: '2026-10-24', source_url: 'https://example.org/azure' },
  });
  payload.changes[0].reason = 'reviewed_reference';
  const app = await boot({ y: [], t: [] }, payload);
  try {
    app.document.querySelector('#quickItemsCardsGrid [data-action="detail"][data-id="item_92"]').click();
    const detail = app.document.getElementById('detailBody');
    assert.equal(detail.querySelector('.evidence-tag').textContent, 'Price-checked reference');
    const source = detail.querySelector('a[href="https://example.org/azure"]');
    assert.ok(source, 'The price-check source should be accessible from the item record');
    assert.equal(source.rel, 'noopener noreferrer');
    assert.ok(detail.querySelector('dl').textContent.includes('Oct'));
    const quoteDate = [...detail.querySelectorAll('.detail-fact')].find(fact => fact.querySelector('dt').textContent === 'Source quote date');
    assert.equal(quoteDate.querySelector('dd').textContent, 'Oct 24, 2026');
    app.document.querySelector('.main-nav [data-tab="hourly-changes"]').click();
    assert.equal(app.document.querySelector('#hourlyTableBody .reason-label').textContent, 'Price check');
    assert.deepEqual(app.errors, []);
  } finally { app.dom.window.close(); }
});

test('rarity filtering keeps the selected game rarity in the URL', async () => {
  const app = await boot();
  try {
    app.document.querySelector('.main-nav [data-tab="tierlist"]').click();
    const select = app.document.getElementById('raritySelect');
    assert.ok(select, 'Rarity filter is missing');
    select.value = 'Mythical';
    select.dispatchEvent(new app.window.Event('change', { bubbles: true }));
    assert.deepEqual([...app.document.querySelectorAll('#itemsCardsGrid .item-open-button')].map(node => node.dataset.id), ['item_72']);
    assert.equal(new URL(app.window.location.href).searchParams.get('rarity'), 'Mythical');
  } finally { app.dom.window.close(); }
});

test('gradient effects can be paused and the preference is saved', async () => {
  const app = await boot();
  try {
    const toggle = app.document.getElementById('effectsToggleBtn');
    assert.ok(toggle, 'Effects control is missing');
    toggle.click();
    assert.equal(app.document.documentElement.dataset.effects, 'off');
    assert.equal(toggle.getAttribute('aria-pressed'), 'false');
    assert.equal(app.window.localStorage.getItem('gpo_effects'), 'false');
  } finally { app.dom.window.close(); }
});

test('hidden catalogue and analytics are not built at startup', async () => {
  const app = await boot();
  try {
    assert.equal(app.document.getElementById('itemsCardsGrid').children.length, 0);
    assert.equal(app.document.getElementById('forecastTableBody')?.children.length || 0, 0);
  } finally { app.dom.window.close(); }
});

test('selecting a category filters items without losing keyboard focus', async () => {
  const app = await boot();
  try {
    const category = app.document.querySelector('[data-scope="quick"][data-category="fruits"]');
    category.focus();
    category.click();
    assert.deepEqual([...app.document.querySelectorAll('#quickItemsCardsGrid .item-open-button')].map(node => node.dataset.id), ['item_72', 'item_86']);
    assert.equal(app.document.activeElement.dataset.category, 'fruits');
    assert.equal(app.document.activeElement.getAttribute('aria-pressed'), 'true');
  } finally { app.dom.window.close(); }
});

test('search is saved in the URL before immediate navigation or reload', async () => {
  const app = await boot();
  try {
    const input = app.document.getElementById('quickSearchInput');
    input.value = 'SP Reset';
    input.dispatchEvent(new app.window.Event('input', { bubbles: true }));
    assert.equal(new URL(app.window.location.href).searchParams.get('q'), 'SP Reset');
  } finally { app.dom.window.close(); }
});

test('a failed first load shows an error status and can be retried', async () => {
  const app = await boot({ y: [], t: [] }, null);
  try {
    assert.equal(app.document.getElementById('loadError').hidden, false);
    assert.equal(app.document.getElementById('main').getAttribute('aria-busy'), 'false');
    assert.equal(app.document.getElementById('sourceIndicator').classList.contains('error'), true);
    app.window.fetch = async () => ({ ok: true, json: async () => structuredClone(live) });
    app.document.getElementById('refreshDataBtn').click();
    await new Promise(resolve => setImmediate(resolve));
    assert.equal(app.document.getElementById('loadError').hidden, true);
    assert.equal(app.document.getElementById('heroLcValue').textContent, '10 pts');
    assert.equal(app.document.querySelector('[data-action="picker"]').disabled, false);
  } finally { app.dom.window.close(); }
});

test('clearing the changes search restores all rows', async () => {
  const app = await boot();
  try {
    app.document.querySelector('.main-nav [data-tab="hourly-changes"]').click();
    const input = app.document.getElementById('hourlySearchInput');
    input.value = 'legendary';
    input.dispatchEvent(new app.window.Event('input', { bubbles: true }));
    await new Promise(resolve => setTimeout(resolve, 110));
    assert.equal(app.document.getElementById('hourlyTableBody').children.length, 1);
    assert.equal(app.document.getElementById('hourlySearchClearBtn').hidden, false);
    app.window.clearSearchInput('hourlySearchInput');
    assert.equal(app.document.getElementById('hourlyTableBody').children.length, 2);
    assert.equal(app.document.getElementById('hourlySearchClearBtn').hidden, true);
  } finally { app.dom.window.close(); }
});

test('Changes can show recent read trades as item icons with processing conclusions', async () => {
  const payload = structuredClone(live);
  const record = (id, timestamp, offer, want, decision = 'waiting') => ({
    id, timestamp, offer, want, decision, independent_authors: decision === 'used' ? 6 : 1,
  });
  payload.read_trades = [
    record('earlier', '2026-11-03T11:45:00Z', [['item_86', 1]], [['item_72', 1]]),
    record('latest', '2026-11-03T11:55:00Z', [['item_58', 1]], [['item_102', 8]], 'used'),
    record('old', '2026-11-03T10:00:00Z', [['item_92', 1]], [['item_102', 1]]),
    record('future', '2026-11-03T13:00:00Z', [['item_92', 1]], [['item_102', 1]]),
    record('unsafe', '2026-11-03T11:59:00Z', [['item_102', '<img id=tradeProbe onerror=window.injected=true>']], [['item_72', 1]]),
  ];
  const app = await boot({ y: [], t: [] }, payload);
  try {
    app.window.history.replaceState(null, '', '?tab=hourly-changes&direction=trades');
    app.window.dispatchEvent(new app.window.PopStateEvent('popstate'));
    const toggle = app.document.getElementById('hourlySubTabRead');
    assert.ok(toggle, 'Changes needs a read-trades sub-tab');
    assert.equal(toggle.getAttribute('aria-pressed'), 'true');
    assert.equal(app.document.getElementById('changesTablePanel').hidden, true);
    assert.equal(app.document.getElementById('readTradesPanel').hidden, false);
    const rows = [...app.document.querySelectorAll('#readTradesList .read-trade-row')];
    assert.deepEqual(rows.map(row => row.dataset.tradeId), ['latest', 'earlier']);
    assert.equal(rows[0].querySelector('.read-trade-for').textContent, '👉');
    assert.deepEqual([...rows[0].querySelectorAll('img')].map(img => img.alt), ['Mythical Fruit Chest', 'Legendary Fruit Chest']);
    assert.equal(rows[0].querySelector('.read-trade-quantity').textContent, '×8');
    assert.equal(rows[0].querySelector('.read-trade-decision').textContent, 'Used in pricing');
    assert.equal(rows[0].textContent.includes('Mythical Fruit Chest'), false);
    assert.equal(app.document.getElementById('tradeProbe'), null);
    const input = app.document.getElementById('hourlySearchInput');
    input.value = 'pika';
    input.dispatchEvent(new app.window.Event('input', { bubbles: true }));
    await new Promise(resolve => setTimeout(resolve, 110));
    assert.equal(app.document.querySelector('#readTradesList .read-trade-row').dataset.tradeId, 'earlier');
    app.document.getElementById('hourlySearchClearBtn').click();
    assert.equal(app.document.querySelectorAll('#readTradesList .read-trade-row').length, 2);
    app.document.getElementById('hourlySubTabAll').click();
    assert.equal(app.document.getElementById('readTradesPanel').hidden, true);
    assert.equal(app.document.getElementById('hourlyTableBody').children.length, 2);
    assert.deepEqual(app.errors, []);
  } finally { app.dom.window.close(); }
});

test('the read-trades tab has an empty state when Discord has not supplied trades', async () => {
  const app = await boot();
  try {
    app.document.querySelector('.main-nav [data-tab="hourly-changes"]').click();
    const toggle = app.document.getElementById('hourlySubTabRead');
    assert.ok(toggle, 'Changes needs a read-trades sub-tab');
    toggle.click();
    assert.equal(app.document.getElementById('readTradesEmpty').hidden, false);
    assert.equal(app.document.getElementById('readTradesList').children.length, 0);
    assert.equal(new URL(app.window.location.href).searchParams.get('direction'), 'trades');
  } finally { app.dom.window.close(); }
});

test('unread parts and each adds size remain visible on their own side of the exchange', async () => {
  const payload = structuredClone(live);
  payload.read_trades = [{
    id: 'partial', timestamp: '2026-11-03T11:55:00Z', offer: [['item_72', 1]], want: [['item_86', 1]],
    offer_markers: ['small_adds', 'unknown'], want_markers: ['adds', 'big_adds', 'offers'],
    decision: 'incomplete', independent_authors: 0,
  }];
  const app = await boot({ y: [], t: [] }, payload);
  try {
    app.document.querySelector('.main-nav [data-tab="hourly-changes"]').click();
    app.document.getElementById('hourlySubTabRead').click();
    const row = app.document.querySelector('#readTradesList .read-trade-row');
    assert.deepEqual([...row.querySelectorAll('.offer [data-marker]')].map(node => node.dataset.marker), ['small_adds', 'unknown']);
    assert.deepEqual([...row.querySelectorAll('.want [data-marker]')].map(node => node.dataset.marker), ['adds', 'big_adds', 'offers']);
    assert.ok(row.querySelector('[data-marker="unknown"] svg'), 'Unread content needs a question icon');
    assert.ok(row.querySelector('[data-marker="unknown"]').getAttribute('aria-label'));
    assert.ok(row.querySelector('[data-marker="adds"]').textContent.includes('ADDS'));
    assert.ok(row.querySelector('[data-marker="small_adds"]').textContent.includes('Small Adds'));
    assert.ok(row.querySelector('[data-marker="big_adds"]').textContent.includes('Big Adds'));
    assert.deepEqual([...row.querySelectorAll('.read-trade-item')].map(node => node.dataset.id), ['item_72', 'item_86']);
    app.document.getElementById('langToggleBtn').click();
    assert.equal(app.document.querySelectorAll('#readTradesList [data-marker]').length, 5);
    assert.deepEqual(app.errors, []);
  } finally { app.dom.window.close(); }
});

test('untrusted read-trade markers cannot be rendered as a recognized exchange', async () => {
  const payload = structuredClone(live);
  const record = {
    id: 'invalid', timestamp: '2026-11-03T11:55:00Z', offer: [['item_72', 1]], want: [['item_86', 1]],
    decision: 'incomplete', independent_authors: 0,
  };
  payload.read_trades = [
    { ...record, offer_markers: ['<img id=markerProbe onerror=window.injected=true>'] },
    { ...record, id: 'wrong-type', want_markers: 'adds' },
    { ...record, id: 'false-pricing', decision: 'used', offer_markers: ['adds'] },
    { ...record, id: 'object-marker', offer_markers: [{ toString: 0 }] },
    { ...record, id: 'object-time', timestamp: { toString: 0 } },
    { ...record, id: 'object-decision', decision: { toString: 0 } },
    { ...record, id: 'valid', decision: 'waiting', independent_authors: 1 },
  ];
  const app = await boot({ y: [], t: [] }, payload);
  try {
    app.document.querySelector('.main-nav [data-tab="hourly-changes"]').click();
    app.document.getElementById('hourlySubTabRead').click();
    assert.equal(app.document.querySelectorAll('#readTradesList .read-trade-row').length, 1);
    assert.equal(app.document.querySelector('#readTradesList .read-trade-row').dataset.tradeId, 'valid');
    assert.equal(app.document.getElementById('markerProbe'), null);
    assert.deepEqual(app.errors, []);
  } finally { app.dom.window.close(); }
});

test('an explicit unread exchange stays visible even when neither item is recognized', async () => {
  const payload = structuredClone(live);
  payload.read_trades = [{
    id: 'unread', timestamp: '2026-11-03T11:55:00Z', offer: [], want: [],
    offer_markers: ['unknown'], want_markers: ['unknown'], decision: 'incomplete', independent_authors: 0,
  }];
  const app = await boot({ y: [], t: [] }, payload);
  try {
    app.document.querySelector('.main-nav [data-tab="hourly-changes"]').click();
    app.document.getElementById('hourlySubTabRead').click();
    assert.equal(app.document.querySelectorAll('#readTradesList .read-trade-row').length, 1);
    assert.equal(app.document.querySelectorAll('#readTradesList [data-marker="unknown"]').length, 2);
    assert.equal(app.document.getElementById('readTradesEmpty').hidden, true);
    assert.deepEqual(app.errors, []);
  } finally { app.dom.window.close(); }
});

test('read-trade quantities of bait describe individual units rather than 300-item packs', async () => {
  const payload = structuredClone(live);
  payload.items.push(item('item_73', '300x Legendary Fish Bait', 15, 22, {
    unit_quantity: 300, rank_locked: false, tier: 'New Items',
  }));
  payload.read_trades = [{
    id: 'bait', timestamp: '2026-11-03T11:55:00Z', offer: [['item_73', 50]], want: [['item_72', 1]],
    decision: 'waiting', independent_authors: 1,
  }];
  const app = await boot({ y: [], t: [] }, payload);
  try {
    app.document.querySelector('.main-nav [data-tab="hourly-changes"]').click();
    app.document.getElementById('hourlySubTabRead').click();
    const bait = app.document.querySelector('#readTradesList [data-id="item_73"]');
    assert.equal(bait.getAttribute('aria-label'), 'Legendary Fish Bait ×50');
    assert.equal(bait.querySelector('.read-trade-quantity').textContent, '×50');
    assert.equal(bait.querySelector('img').alt, 'Legendary Fish Bait');
  } finally { app.dom.window.close(); }
});

test('read-trade filters compose with item search and distinguish offering from requesting', async () => {
  const app = await boot({ y: [], t: [] }, { ...structuredClone(live), read_trades: structuredClone(readFeed) });
  try {
    app.document.querySelector('.main-nav [data-tab="hourly-changes"]').click();
    app.document.getElementById('hourlySubTabRead').click();
    const status = app.document.getElementById('readTradeStatus');
    assert.ok(status, 'Read trades needs a processing-status filter');
    status.value = 'used';
    status.dispatchEvent(new app.window.Event('change', { bubbles: true }));
    const category = app.document.querySelector('[data-scope="changes"][data-category="fruits"]');
    assert.ok(category, 'Read trades needs category filters');
    category.click();
    const input = app.document.getElementById('hourlySearchInput');
    input.value = 'pika';
    input.dispatchEvent(new app.window.Event('input', { bubbles: true }));
    await new Promise(resolve => setTimeout(resolve, 110));
    assert.deepEqual([...app.document.querySelectorAll('#readTradesList .read-trade-row')].map(row => row.dataset.tradeId), ['offered-pika']);
    const side = app.document.getElementById('readTradeSide');
    side.value = 'want';
    side.dispatchEvent(new app.window.Event('change', { bubbles: true }));
    assert.equal(app.document.getElementById('readTradesEmpty').hidden, false);
    side.value = 'offer';
    side.dispatchEvent(new app.window.Event('change', { bubbles: true }));
    assert.equal(app.document.querySelector('#readTradesList .read-trade-row').dataset.tradeId, 'offered-pika');
    assert.equal(new URL(app.window.location.href).searchParams.get('trade_side'), 'offer');
    app.document.getElementById('readTradesResetBtn').click();
    assert.equal(status.value, 'all');
    assert.equal(side.value, 'either');
    assert.equal(input.value, '');
    assert.equal(app.document.querySelectorAll('#readTradesList .read-trade-row').length, 4);
    assert.equal(app.document.activeElement, input);
    assert.equal(new URL(app.window.location.href).searchParams.has('trade_status'), false);
    assert.deepEqual(app.errors, []);
  } finally { app.dom.window.close(); }
});

test('read-trade content filters find unread parts and adds without hiding known items', async () => {
  const app = await boot({ y: [], t: [] }, { ...structuredClone(live), read_trades: structuredClone(readFeed) });
  try {
    app.document.querySelector('.main-nav [data-tab="hourly-changes"]').click();
    app.document.getElementById('hourlySubTabRead').click();
    const content = app.document.getElementById('readTradeContent');
    assert.ok(content, 'Read trades needs a recognition/content filter');
    for (const [value, ids] of [
      ['unknown', ['partial']], ['adds', ['partial']], ['complete', ['latest', 'offered-pika', 'earlier']],
    ]) {
      content.value = value;
      content.dispatchEvent(new app.window.Event('change', { bubbles: true }));
      assert.deepEqual([...app.document.querySelectorAll('#readTradesList .read-trade-row')].map(row => row.dataset.tradeId), ids);
    }
    content.value = 'all';
    content.dispatchEvent(new app.window.Event('change', { bubbles: true }));
    const input = app.document.getElementById('hourlySearchInput');
    input.value = 'Small Adds';
    input.dispatchEvent(new app.window.Event('input', { bubbles: true }));
    await new Promise(resolve => setTimeout(resolve, 110));
    assert.deepEqual([...app.document.querySelectorAll('#readTradesList .read-trade-row')].map(row => row.dataset.tradeId), ['partial']);
    assert.equal(app.document.querySelector('#readTradesList [data-id="item_72"]').title, 'Mochi ×1');
    assert.deepEqual(app.errors, []);
  } finally { app.dom.window.close(); }
});

test('read trades sort by time or independent support and restore filters from the URL', async () => {
  const app = await boot({ y: [], t: [] }, { ...structuredClone(live), read_trades: structuredClone(readFeed) });
  try {
    app.document.querySelector('.main-nav [data-tab="hourly-changes"]').click();
    app.document.getElementById('hourlySubTabRead').click();
    const sort = app.document.getElementById('readTradeSort');
    assert.ok(sort, 'Read trades needs sorting');
    for (const [value, ids] of [
      ['oldest', ['earlier', 'partial', 'offered-pika', 'latest']],
      ['support', ['offered-pika', 'latest', 'earlier', 'partial']],
    ]) {
      sort.value = value;
      sort.dispatchEvent(new app.window.Event('change', { bubbles: true }));
      assert.deepEqual([...app.document.querySelectorAll('#readTradesList .read-trade-row')].map(row => row.dataset.tradeId), ids);
      assert.equal(new URL(app.window.location.href).searchParams.get('trade_sort'), value);
    }
    app.window.history.replaceState(null, '', '?tab=hourly-changes&direction=trades&q=Mochi&category=fruits&trade_status=waiting&trade_content=complete&trade_side=want&trade_sort=oldest');
    app.window.dispatchEvent(new app.window.PopStateEvent('popstate'));
    assert.equal(app.document.getElementById('readTradeStatus').value, 'waiting');
    assert.equal(app.document.getElementById('readTradeContent').value, 'complete');
    assert.equal(app.document.getElementById('readTradeSide').value, 'want');
    assert.equal(sort.value, 'oldest');
    assert.equal(app.document.querySelector('#readTradesList .read-trade-row').dataset.tradeId, 'earlier');
    app.window.history.replaceState(null, '', '?tab=hourly-changes&direction=trades&trade_status=invalid&trade_sort=invalid');
    app.window.dispatchEvent(new app.window.PopStateEvent('popstate'));
    assert.equal(app.document.getElementById('readTradeStatus').value, 'all');
    assert.equal(sort.value, 'newest');
    assert.equal(app.document.querySelector('#readTradesList .read-trade-row').dataset.tradeId, 'latest');
    assert.deepEqual(app.errors, []);
  } finally { app.dom.window.close(); }
});

test('changing read-trade filters resets pagination and never leaves rows from the previous view', async () => {
  const payload = structuredClone(live);
  payload.read_trades = Array.from({ length: 32 }, (_, index) => ({
    id: `trade-${index}`, timestamp: `2026-11-03T11:${String(index).padStart(2, '0')}:00Z`,
    offer: [['item_58', 1]], want: [['item_102', 8]],
    decision: index % 2 ? 'used' : 'waiting', independent_authors: index % 2 ? 6 : 1,
  }));
  const app = await boot({ y: [], t: [] }, payload);
  try {
    app.document.querySelector('.main-nav [data-tab="hourly-changes"]').click();
    app.document.getElementById('hourlySubTabRead').click();
    const more = app.document.querySelector('[data-action="more"][data-scope="changes"]');
    more.click();
    assert.equal(app.document.querySelectorAll('#readTradesList .read-trade-row').length, 32);
    const status = app.document.getElementById('readTradeStatus');
    assert.ok(status, 'Read trades needs filters that reset pagination');
    status.value = 'used';
    status.dispatchEvent(new app.window.Event('change', { bubbles: true }));
    assert.equal(app.document.querySelectorAll('#readTradesList .read-trade-row').length, 16);
    assert.equal(app.document.querySelectorAll('#readTradesList [data-decision="waiting"]').length, 0);
    assert.equal(more.hidden, true);
    app.document.getElementById('readTradesResetBtn').click();
    assert.equal(app.document.querySelectorAll('#readTradesList .read-trade-row').length, 24);
    assert.equal(more.hidden, false);
    app.document.getElementById('hourlySubTabAll').click();
    assert.equal(app.document.getElementById('readTradeControls').hidden, true);
    assert.equal(app.document.getElementById('hourlyTableBody').children.length, 2);
    assert.deepEqual(app.errors, []);
  } finally { app.dom.window.close(); }
});

test('a quantity step retains keyboard focus', async () => {
  const app = await boot({ y: [['item_102', 1]], t: [] });
  try {
    const plus = app.document.querySelector('#youSlotsGrid [data-action="quantity-step"][data-delta="1"]');
    plus.focus();
    plus.click();
    assert.equal(app.document.activeElement.dataset.action, 'quantity-step');
    assert.equal(app.document.activeElement.dataset.delta, '1');
    assert.equal(app.document.getElementById('youTotalPts').textContent, '20 pts');
  } finally { app.dom.window.close(); }
});

test('one-sided and unpriced trades do not receive a win or loss verdict', async () => {
  const app = await boot({ y: [['item_102', 1]], t: [] });
  try {
    assert.equal(app.document.getElementById('verdictStamp').dataset.state, 'empty');
    app.window.GPO_APP.quickAdd('they', 'item_verity');
    assert.equal(app.document.getElementById('verdictStamp').dataset.state, 'unknown');
    assert.equal(app.document.getElementById('theyTotalPts').textContent, '—');
  } finally { app.dom.window.close(); }
});

test('equal fractional values do not produce a negative zero difference', async () => {
  const payload = structuredClone(live);
  payload.items.find(item => item.id === 'item_92').value = 0.1;
  payload.items.find(item => item.id === 'item_verity').value = 0.2;
  payload.items.push(item('item_test', 'Test item', 0.3, 30, { rank_locked: false, tier: 'New Items' }));
  const app = await boot({ y: [['item_92', 1], ['item_verity', 1]], t: [['item_test', 1]] }, payload);
  try {
    assert.equal(app.document.getElementById('verdictDiffText').textContent.startsWith('−'), false);
  } finally { app.dom.window.close(); }
});
