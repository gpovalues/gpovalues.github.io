const { test, before, after } = require('node:test');
const assert = require('node:assert/strict');
const net = require('node:net');
const { spawn } = require('node:child_process');
const path = require('node:path');

let child;
let base;
before(async () => {
  const probe = net.createServer();
  await new Promise(resolve => probe.listen(0, '127.0.0.1', resolve));
  const port = probe.address().port;
  await new Promise(resolve => probe.close(resolve));
  base = `http://127.0.0.1:${port}`;
  child = spawn(process.execPath, ['server.js'], {
    cwd: path.resolve(__dirname, '..'), env: { ...process.env, PORT: String(port), HOST: '127.0.0.1' }, stdio: 'ignore',
  });
  for (let i = 0; i < 50; i++) {
    try { await fetch(base); return; } catch { await new Promise(resolve => setTimeout(resolve, 30)); }
  }
  throw new Error('Static server did not start');
});
after(async () => { if (child && child.exitCode === null) { child.kill(); await new Promise(resolve => child.once('exit', resolve)); } });

test('private repository and collector state are not served', async () => {
  for (const file of ['.git/config', '.state/market.sqlite3', 'scripts/update_values.py', 'package.json', 'data/trades_buffer.json']) {
    assert.equal((await fetch(`${base}/${file}`)).status, 404, file);
  }
});

test('public snapshots support conditional requests', async () => {
  const response = await fetch(`${base}/data/values.json`);
  assert.equal(response.status, 200);
  const etag = response.headers.get('etag');
  assert.ok(etag);
  assert.equal((await fetch(`${base}/data/values.json`, { headers: { 'If-None-Match': etag } })).status, 304);
});

test('static server rejects writes', async () => {
  assert.equal((await fetch(`${base}/index.html`, { method: 'POST', body: 'unwanted data' })).status, 405);
});
