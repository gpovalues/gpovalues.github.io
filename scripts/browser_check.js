/** Real Chrome checks for the trade flow, keyboard access and mobile layout. */
const assert = require('node:assert/strict');
const path = require('node:path');
const fs = require('node:fs');
const { chromium } = require('playwright-core');
const { createServer } = require('../server');

async function checkLayout(page, label) {
  const problems = await page.evaluate(() => {
    const issues = [];
    if (document.documentElement.scrollWidth > innerWidth + 1) issues.push('page overflows horizontally');
    document.querySelectorAll('button').forEach(button => {
      if (button.getClientRects().length && button.scrollWidth > button.clientWidth + 1) {
        issues.push(`button content overflows: ${button.id || button.dataset.action}`);
      }
    });
    document.querySelectorAll('.trade-slot-card, .item-comic-card').forEach(card => {
      if (!card.getClientRects().length) return;
      const bounds = card.getBoundingClientRect();
      card.querySelectorAll('button, input').forEach(control => {
        const rect = control.getBoundingClientRect();
        if (rect.left < bounds.left - 1 || rect.right > bounds.right + 1) issues.push('item controls escape their card');
      });
    });
    return issues;
  });
  assert.deepEqual(problems, [], label);
}

async function main() {
  const siteRoot = path.resolve(__dirname, '../dist');
  assert.ok(fs.existsSync(path.join(siteRoot, 'index.html')), 'Run npm run build before the browser checks');
  const output = process.env.GPO_SCREENSHOT_DIR || path.resolve(__dirname, '../test-results');
  fs.mkdirSync(output, { recursive: true });
  const server = createServer(siteRoot);
  await new Promise(resolve => server.listen(0, '127.0.0.1', resolve));
  const base = `http://127.0.0.1:${server.address().port}`;
  let browser;
  try {
    browser = await chromium.launch({ channel: 'chrome', headless: true, args: ['--no-sandbox'] });
    const context = await browser.newContext({ viewport: { width: 1440, height: 1080 }, locale: 'en-US', reducedMotion: 'reduce' });
    const page = await context.newPage();
    const errors = [];
    const requests = [];
    const failedRequests = [];
    page.on('pageerror', error => errors.push(error.message));
    page.on('request', request => requests.push(request.url()));
    page.on('response', response => { if (response.status() >= 400) failedRequests.push(`${response.status()} ${response.url()}`); });
    await context.grantPermissions(['clipboard-read', 'clipboard-write'], { origin: base });
    await page.goto(base, { waitUntil: 'networkidle' });
    await page.evaluate(() => document.fonts.ready);
    await page.waitForFunction(() => document.querySelector('main').getAttribute('aria-busy') === 'false');
    assert.equal(await page.locator('#loadError').isVisible(), false);
    assert.equal(await page.locator('#quickItemsCardsGrid .item-comic-card').count(), 24);
    assert.equal(await page.locator('#itemsCardsGrid .item-comic-card').count(), 0);
    const initialNodes = await page.locator('*').count();
    assert.ok(initialNodes < 5000, `Initial DOM is too large: ${initialNodes}`);
    assert.ok(requests.every(url => url.startsWith(base)), 'Disabled ads or assets made an external request');
    assert.equal(requests.filter(url => url.includes('/audio/')).length, 0, 'Muted audio was fetched eagerly');
    assert.ok(requests.filter(url => url.includes('/fonts/') && url.endsWith('.woff2')).every(url => url.endsWith('/finger-paint.woff2')), 'A second web font was loaded');
    assert.match(await page.evaluate(() => getComputedStyle(document.body).fontFamily), /Finger Paint/);
    assert.equal(await page.locator('.rarity-label').first().evaluate(node => getComputedStyle(node).animationName), 'none', 'Reduced motion was ignored');
    assert.equal(requests.filter(url => url.includes('/data/history.json')).length, 0, 'History was fetched before opening an item');
    await checkLayout(page, 'Desktop calculator');
    await page.screenshot({ path: path.join(output, 'gpo-desktop.png') });

    await page.locator('[data-action="picker"][data-side="you"]').click();
    await page.locator('#pickerSearchInput').fill('legendary fruit chest');
    await page.locator('#pickerItemsGrid [data-id="item_102"]').click();
    await page.locator('#youSlotsGrid .qty-num').fill('10');
    await page.locator('#youSlotsGrid .qty-num').press('Tab');
    assert.equal(await page.locator('#youTotalLc').textContent(), '10 LC');
    await page.locator('[data-action="picker"][data-side="they"]').click();
    await page.locator('#pickerSearchInput').fill('mythical fruit chest');
    await page.locator('#pickerItemsGrid [data-id="item_58"]').click();
    const before = await page.locator('#youTotalPts').textContent();
    const theirs = await page.locator('#theyTotalPts').textContent();
    await page.locator('#btnSwapSides').click();
    assert.equal(await page.locator('#youTotalPts').textContent(), theirs);
    assert.equal(await page.locator('#theyTotalPts').textContent(), before);
    await page.reload({ waitUntil: 'networkidle' });
    assert.equal(await page.locator('#youTotalPts').textContent(), theirs, 'Shared URL lost its trade');
    await page.locator('#btnClearTrade').click();
    await page.locator('[data-action="undo"]').click();
    assert.equal(await page.locator('#youTotalPts').textContent(), theirs, 'Undo lost the offer');
    await page.locator('#btnShareTrade').click();
    const shareUrl = await page.evaluate(() => navigator.clipboard.readText());
    assert.ok(shareUrl.startsWith(base) && shareUrl.includes('#trade='), 'Share did not copy the trade URL');
    const shared = await context.newPage();
    await shared.goto(shareUrl, { waitUntil: 'networkidle' });
    assert.equal(await shared.locator('#youTotalPts').textContent(), theirs);
    assert.equal(await shared.locator('#theyTotalPts').textContent(), before);
    await shared.close();
    await page.locator('#btnDiscordExport').click();
    const exported = await page.evaluate(() => navigator.clipboard.readText());
    assert.match(exported, /Legendary Fruit Chest ×10/);
    assert.match(exported, /Mythical Fruit Chest ×1/);
    await page.locator('.gpo-toast [data-action="dismiss-toast"]').evaluateAll(buttons => buttons.forEach(button => button.click()));
    await page.screenshot({ path: path.join(output, 'gpo-trade.png') });

    await page.locator('.main-nav [data-tab="tierlist"]').click();
    await page.locator('#searchInput').fill('Mochi');
    await page.locator('#itemsCardsGrid [data-action="detail"][data-id="item_72"]').click();
    assert.equal(await page.locator('#itemDetailModal').isVisible(), true);
    assert.equal(await page.locator('#detailBody .rarity-label').textContent(), 'Mythical');
    assert.match(await page.locator('#detailBody .rarity-source').getAttribute('href'), /Mochi_Mochi_no_Mi/);
    await page.locator('#detailHistory .history-empty, #detailHistory .history-chart').waitFor();
    await page.screenshot({ path: path.join(output, 'gpo-item-detail.png') });
    await page.keyboard.press('Escape');
    assert.equal(await page.locator('#itemDetailModal').isVisible(), false);
    assert.equal(await page.evaluate(() => document.activeElement?.dataset.id), 'item_72', 'Dialog lost keyboard focus');
    await page.locator('[data-action="clear-search"][data-scope="catalog"]').click();
    assert.equal(await page.locator('#searchInput').inputValue(), '');
    assert.equal(await page.locator('#itemsCardsGrid .item-comic-card').count(), 24);
    const fruitCategory = page.locator('[data-scope="catalog"][data-category="fruits"]');
    await fruitCategory.focus();
    await page.keyboard.press('Enter');
    assert.equal(await page.evaluate(() => document.activeElement?.dataset.category), 'fruits');
    assert.equal(await fruitCategory.getAttribute('aria-pressed'), 'true');
    await page.locator('[data-scope="catalog"][data-category="all"]').click();
    await page.locator('#tierSelect').selectOption('Tier F');
    await page.locator('#searchInput').fill('SP Reset');
    await page.locator('#itemsCardsGrid [data-action="detail"][data-id="item_194"]').click();
    assert.match(await page.locator('.detail-price').textContent(), /^1 pts/);
    await page.keyboard.press('Escape');
    await page.reload({ waitUntil: 'networkidle' });
    assert.equal(await page.locator('#tierSelect').inputValue(), 'Tier F', 'Tier filter did not survive reload');
    assert.equal(await page.locator('#searchInput').inputValue(), 'SP Reset', 'Search did not survive reload');
    await page.locator('[data-action="clear-search"][data-scope="catalog"]').click();
    await page.locator('#tierSelect').selectOption('all');
    await page.locator('#raritySelect').selectOption('Mythical');
    await page.reload({ waitUntil: 'networkidle' });
    assert.equal(await page.locator('#raritySelect').inputValue(), 'Mythical');
    assert.ok(await page.locator('#itemsCardsGrid article').count() > 0);
    assert.equal(await page.locator('#itemsCardsGrid article:not([data-rarity="mythical"])').count(), 0);
    await page.screenshot({ path: path.join(output, 'gpo-mythical-values.png') });
    await page.emulateMedia({ reducedMotion: 'no-preference' });
    await page.locator('#effectsToggleBtn').click();
    assert.equal(await page.locator('#itemsCardsGrid .rarity-label').first().evaluate(node => getComputedStyle(node).animationPlayState), 'running');
    await page.locator('#effectsToggleBtn').click();
    assert.equal(await page.locator('#itemsCardsGrid .rarity-label').first().evaluate(node => getComputedStyle(node).animationPlayState), 'paused');
    await page.emulateMedia({ reducedMotion: 'reduce' });
    await page.locator('#raritySelect').selectOption('all');
    await page.locator('#langToggleBtn').click();
    assert.equal(await page.locator('html').getAttribute('lang'), 'ru');
    await page.screenshot({ path: path.join(output, 'gpo-values-ru.png') });
    const more = page.locator('[data-action="more"][data-scope="catalog"]');
    while (await more.isVisible()) await more.click();
    const catalogueSize = await page.evaluate(() => window.GPO_ITEMS.length);
    assert.equal(await page.locator('#itemsCardsGrid .item-comic-card').count(), catalogueSize);
    await page.waitForLoadState('networkidle');
    await checkLayout(page, 'Expanded catalogue');

    await page.locator('.main-nav [data-tab="forecasts"]').click();
    await page.locator('[data-scope="market"][data-category="fruits"]').click();
    await page.locator('#forecastSearchInput').fill('Mochi');
    await page.waitForFunction(() => document.querySelectorAll('#forecastTableBody tr').length === 1);
    assert.equal(await page.locator('#forecastTableBody [data-id="item_72"]').count(), 1);
    await page.locator('[data-action="timeframe"][data-tf="7d"]').click();
    assert.equal(await page.locator('[data-tf="7d"]').getAttribute('aria-pressed'), 'true');
    await page.screenshot({ path: path.join(output, 'gpo-market.png') });
    await page.locator('.main-nav [data-tab="hourly-changes"]').click();
    await page.locator('#hourlySearchInput').fill('no-item-matches-this-search');
    await page.locator('#hourlyEmptyState').waitFor({ state: 'visible' });
    await page.locator('#hourlySearchClearBtn').click();
    assert.equal(await page.locator('#hourlySearchInput').inputValue(), '');
    await page.locator('#hourlySubTabRead').click();
    assert.equal(await page.locator('#readTradesPanel').isVisible(), true);
    assert.equal(await page.locator('#changesTablePanel').isVisible(), false);
    const readCount = await page.evaluate(async () => (await (await fetch('data/values.json')).json()).read_trades?.length || 0);
    assert.equal(await page.locator('#readTradesList .read-trade-row').count(), Math.min(readCount, 24));
    assert.equal(await page.locator('#readTradesEmpty').isVisible(), readCount === 0);
    await page.reload({ waitUntil: 'networkidle' });
    assert.equal(await page.locator('#hourlySubTabRead').getAttribute('aria-pressed'), 'true');
    await checkLayout(page, 'Read trades');
    await page.screenshot({ path: path.join(output, 'gpo-read-trades.png') });
    await page.locator('.main-nav [data-tab="guide"]').click();
    assert.equal(await page.locator('#sectionGuide article').count(), 6);
    await page.screenshot({ path: path.join(output, 'gpo-guide.png') });
    await page.locator('.main-nav [data-tab="community"]').click();
    assert.equal(await page.locator('#sectionCommunity a[href="https://t.me/GPOcHa"]').count(), 1);
    assert.equal(await page.locator('#sectionCommunity a[href="https://discord.gg/AxkxVfSnY"]').count(), 1);
    await page.waitForLoadState('networkidle');
    await page.screenshot({ path: path.join(output, 'gpo-community.png') });

    const manual = await context.newPage();
    await manual.addInitScript(() => Object.defineProperty(navigator, 'clipboard', {
      value: { writeText: async () => { throw new DOMException('Clipboard denied', 'NotAllowedError'); } },
    }));
    await manual.goto(shareUrl, { waitUntil: 'networkidle' });
    await manual.locator('#btnShareTrade').click();
    assert.equal(await manual.locator('#shareModal').isVisible(), true);
    assert.equal(await manual.locator('#shareText').inputValue(), shareUrl);
    await manual.keyboard.press('Escape');
    assert.equal(await manual.evaluate(() => document.activeElement?.id), 'btnShareTrade');
    await manual.close();

    const attack = Buffer.from(encodeURIComponent(JSON.stringify({ y: [['item_102', '<img id=unsafe onerror=window.injected=true>']], t: [] }))).toString('base64');
    await page.goto(`${base}/#trade=${attack}`, { waitUntil: 'networkidle' });
    assert.equal(await page.locator('#unsafe').count(), 0);
    assert.equal(await page.locator('#youSlotsGrid .trade-slot-card').count(), 0);
    assert.deepEqual(errors, []);
    assert.deepEqual(failedRequests, [], 'Public assets failed to load');
    assert.ok(requests.every(url => url.startsWith(base)), 'A screen made an unexpected external request');

    const mobile = await browser.newContext({ viewport: { width: 390, height: 844 }, deviceScaleFactor: 1, isMobile: true, hasTouch: true, locale: 'ru-RU', reducedMotion: 'reduce' });
    const phone = await mobile.newPage();
    phone.on('pageerror', error => errors.push(error.message));
    const cdp = await mobile.newCDPSession(phone);
    await cdp.send('Emulation.setCPUThrottlingRate', { rate: 6 });
    await phone.goto(base, { waitUntil: 'networkidle' });
    await phone.evaluate(() => document.fonts.ready);
    await checkLayout(phone, 'Mobile calculator');
    await phone.screenshot({ path: path.join(output, 'gpo-mobile.png') });
    const updateTime = await phone.evaluate(async () => {
      const start = performance.now();
      window.GPO_APP.quickAdd('you', 'item_102');
      await new Promise(requestAnimationFrame);
      return performance.now() - start;
    });
    await phone.locator('.gpo-toast [data-action="dismiss-toast"]').click();
    await phone.locator('#youSlotsGrid .qty-num').fill('100000');
    await phone.locator('#youSlotsGrid .qty-num').press('Tab');
    await checkLayout(phone, 'Mobile quantity controls');
    await phone.locator('[data-action="picker"][data-side="they"]').click();
    await phone.locator('#pickerSearchInput').fill('Mochi');
    await phone.locator('#pickerItemsGrid [data-id="item_72"]').click();
    await phone.locator('.gpo-toast [data-action="dismiss-toast"]').click();
    await phone.screenshot({ path: path.join(output, 'gpo-mobile-trade.png') });
    await phone.locator('.main-nav [data-tab="tierlist"]').click();
    await phone.screenshot({ path: path.join(output, 'gpo-mobile-values.png'), fullPage: false });
    const viewports = [320, 390, 768, 1024];
    for (const width of viewports) {
      await phone.setViewportSize({ width, height: 844 });
      for (const name of ['calculator', 'tierlist', 'forecasts', 'hourly-changes', 'guide', 'community']) {
        await phone.locator(`.main-nav [data-tab="${name}"]`).click();
        await checkLayout(phone, `${name} at ${width}px`);
        if (name === 'hourly-changes') {
          await phone.locator('#hourlySubTabRead').click();
          await checkLayout(phone, `Read trades at ${width}px`);
        }
      }
      await phone.locator('.main-nav [data-tab="calculator"]').click();
      await phone.locator('[data-action="picker"][data-side="you"]').click();
      await checkLayout(phone, `Picker at ${width}px`);
      await phone.keyboard.press('Escape');
    }
    await phone.setViewportSize({ width: 390, height: 844 });
    await phone.emulateMedia({ reducedMotion: 'no-preference' });
    await phone.locator('#effectsToggleBtn').click();
    await phone.locator('.main-nav [data-tab="tierlist"]').click();
    await phone.locator('#raritySelect').selectOption('Legendary');
    await phone.locator('#itemsCardsGrid article').first().scrollIntoViewIfNeeded();
    assert.equal(await phone.locator('#itemsCardsGrid .rarity-label').first().evaluate(node => getComputedStyle(node).animationPlayState), 'running');
    const animatedUpdateTime = await phone.evaluate(async () => {
      const start = performance.now();
      window.GPO_APP.quickAdd('you', 'item_86');
      await new Promise(requestAnimationFrame);
      return performance.now() - start;
    });
    assert.equal(await phone.locator('#youSlotsGrid .trade-slot-card').count(), 2);
    await phone.locator('.gpo-toast [data-action="dismiss-toast"]').evaluateAll(buttons => buttons.forEach(button => button.click()));
    await checkLayout(phone, 'Animated legendary catalogue at 390px');
    await phone.screenshot({ path: path.join(output, 'gpo-legendary-effects.png') });
    assert.deepEqual(errors, []);
    console.log(JSON.stringify({ initial_dom_elements: initialNodes, mobile_update_ms_at_6x_cpu: Math.round(updateTime), animated_mobile_update_ms_at_6x_cpu: Math.round(animatedUpdateTime), checked_widths: [1440, ...viewports], screenshots: output }, null, 2));
  } finally {
    if (browser) await browser.close();
    await new Promise(resolve => server.close(resolve));
  }
}

main().catch(error => { console.error(error); process.exitCode = 1; });
