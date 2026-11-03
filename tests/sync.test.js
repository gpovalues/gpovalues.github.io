const { test } = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const vm = require('node:vm');
const { buildCatalog } = require('../sync_tierlist');

const baseline = Array.from({ length: 201 }, (_, i) => ({
  id: `test_${i}`, name: i === 199 ? 'Legendary Fruit Chest' : i === 200 ? 'SP Reset Essence' : `Item ${i}`,
  value: 202 - i, category: 'misc', tier: 'Tier A', rankInTier: i + 1,
}));

function fixture(text, extraFiles = {}) {
  const files = new Map([['/repo/data/catalog.json', JSON.stringify({ source: { revision: 'fixture' }, items: baseline })], ...Object.entries(extraFiles)]);
  const disk = {
    existsSync: p => files.has(p) || p === '/repo' || p === '/repo/data',
    mkdirSync() {},
    readFileSync: p => { if (!files.has(p)) throw new Error(`Missing fixture: ${p}`); return files.get(p); },
    writeFileSync: (p, text) => files.set(p, text),
    renameSync: (from, to) => { files.set(to, files.get(from)); files.delete(from); },
  };
  const context = {
    require: name => name === 'fs' || name === 'node:fs' ? disk : require(name),
    module: { exports: {} }, __dirname: '/repo', URL,
    console: { log() {}, warn() {}, error() {} },
  };
  vm.runInNewContext(fs.readFileSync(path.join(__dirname, '../sync_tierlist.js'), 'utf8'), context);
  context.fetchUrl = async () => {
    if (text === null) throw new Error('Official document unavailable');
    return `{"ty":"is","ibi":0,"s":${JSON.stringify(text)}}`;
  };
  return { files, run: context.module.exports.syncTierList };
}

async function sync(text) {
  const { files, run } = fixture(text);
  await run();
  const output = JSON.parse(files.get('/repo/data/catalog.json'));
  return output.items || output;
}

test('a newly listed item is added without changing existing IDs', async () => {
  const text = 'Last Time Update: 11/01/2026\n⚜ Tier A ⚜\n' +
    baseline.map(item => `* ${item.name} *`).join('\n') + '\n⚜ New Items ⚜\n* Moonreaver *';
  const items = await sync(text);
  assert.equal(items.length, 202);
  assert.equal(items.find(item => item.name === 'Item 0').id, 'test_0');
  assert.ok(items.some(item => item.name === 'Moonreaver'));
});

test('an incomplete document cannot replace a known catalogue', async () => {
  const text = 'Description '.repeat(150) + '\n⚜ Tier A ⚜\n* Item 0 *';
  await assert.rejects(sync(text), /incomplete|missing|coverage|корот|непол|anchor/i);
});

test('verified game rarity survives an older collector catalogue without changing the trading tier', () => {
  const text = '⚜ Tier A ⚜\n' + baseline.map(item => `* ${item.name} *`).join('\n');
  const result = buildCatalog(text, { items: baseline }, {
    test_0: { rarity: 'Collectable', wiki: 'Cool_Shades', source: 'Rarities' },
  });
  assert.equal(result.items[0].rarity, 'Collectable');
  assert.equal(result.items[0].tier, 'Tier A');
  assert.equal(result.items[0].official_rank, 1);
  assert.equal(result.items[0].wikiUrl, 'https://grand-piece-online.fandom.com/wiki/Cool_Shades');
  assert.equal(result.items[0].rarity_source, 'https://grand-piece-online.fandom.com/wiki/Rarities');
  assert.equal(result.items[1].rarity, null, 'An unknown rarity must not be inferred from the trading tier');
});

test('the importer rejects made-up rarities and unsafe source paths', () => {
  const text = '⚜ Tier A ⚜\n' + baseline.map(item => `* ${item.name} *`).join('\n');
  assert.throws(() => buildCatalog(text, { items: baseline }, {
    test_0: { rarity: 'Tier SS', wiki: 'Cool_Shades' },
  }), /rarity/i);
  assert.throws(() => buildCatalog(text, { items: baseline }, {
    test_0: { rarity: 'Collectable', wiki: 'https://wrong.example/' },
  }), /wiki/i);
});

test('a Google outage retains reviewed rarities when restoring an older checkpoint', async () => {
  const { files, run } = fixture(null, {
    '/repo/.state/catalog.json': JSON.stringify({ source: { revision: 'checkpoint' }, items: baseline }),
    '/repo/data/rarities.json': JSON.stringify({ items: { test_0: { rarity: 'Collectable', wiki: 'Cool_Shades' } } }),
  });
  await assert.rejects(run(), /unavailable/);
  const retained = JSON.parse(files.get('/repo/data/catalog.json'));
  assert.equal(retained.items[0].rarity, 'Collectable');
  assert.equal(retained.items[0].wikiUrl, 'https://grand-piece-online.fandom.com/wiki/Cool_Shades');
  assert.equal(retained.source.revision, 'checkpoint');
  assert.equal(retained.items.length, 201);
});
