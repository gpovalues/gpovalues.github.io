const { test } = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const vm = require('node:vm');

const baseline = Array.from({ length: 201 }, (_, i) => ({
  id: `test_${i}`, name: i === 199 ? 'Legendary Fruit Chest' : i === 200 ? 'SP Reset Essence' : `Item ${i}`,
  value: 202 - i, category: 'misc', tier: 'Tier A', rankInTier: i + 1,
}));

async function sync(text) {
  const files = new Map([['/repo/data/catalog.json', JSON.stringify({ source: { revision: 'fixture' }, items: baseline })]]);
  const disk = {
    existsSync: p => files.has(p) || p === '/repo' || p === '/repo/data',
    mkdirSync() {},
    readFileSync: p => { if (!files.has(p)) throw new Error(`Missing fixture: ${p}`); return files.get(p); },
    writeFileSync: (p, text) => files.set(p, text),
    renameSync: (from, to) => { files.set(to, files.get(from)); files.delete(from); },
  };
  const context = {
    require: name => name === 'fs' || name === 'node:fs' ? disk : require(name),
    module: { exports: {} }, __dirname: '/repo',
    console: { log() {}, warn() {}, error() {} },
  };
  vm.runInNewContext(fs.readFileSync(path.join(__dirname, '../sync_tierlist.js'), 'utf8'), context);
  context.fetchUrl = async () => `{"ty":"is","ibi":0,"s":${JSON.stringify(text)}}`;
  await context.module.exports.syncTierList();
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
