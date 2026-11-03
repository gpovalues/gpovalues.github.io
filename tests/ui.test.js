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
