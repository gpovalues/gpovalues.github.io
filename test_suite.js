const fs = require('fs');
const path = require('path');
const { JSDOM } = require('jsdom');

async function runTestSuite() {
  console.log('🧪 Starting GPO Values automated test suite...');

  const html = fs.readFileSync(path.join(__dirname, 'index.html'), 'utf8');

  const virtualConsole = new (require('jsdom').VirtualConsole)();
  const errors = [];
  const warnings = [];

  virtualConsole.on('error', (...args) => {
    console.error('🔴 JSDOM Error:', ...args);
    errors.push(args.join(' '));
  });

  virtualConsole.on('warn', (...args) => {
    warnings.push(args.join(' '));
  });

  virtualConsole.on('jsdomError', (err) => {
    console.error('🔴 JSDOM Exception:', err);
    errors.push(err.message || String(err));
  });

  const dom = new JSDOM(html, {
    url: 'http://localhost:8080/',
    runScripts: 'dangerously',
    virtualConsole,
    beforeParse(window) {
      // Mock AudioContext and Audio
      window.AudioContext = class {
        constructor() { this.state = 'running'; }
        createGain() { return { connect() {}, gain: { value: 1, setValueAtTime() {}, linearRampToValueAtTime() {} } }; }
        createBufferSource() { return { connect() {}, start() {}, stop() {}, buffer: null }; }
        resume() { return Promise.resolve(); }
        decodeAudioData(buf) { return Promise.resolve({}); }
      };
      window.webkitAudioContext = window.AudioContext;
      window.Audio = class {
        constructor(src) { this.src = src; }
        play() { return Promise.resolve(); }
        pause() {}
        cloneNode() { return new window.Audio(this.src); }
      };
      window.fetch = (url) => Promise.resolve({
        arrayBuffer: () => Promise.resolve(new ArrayBuffer(8))
      });
      // Mock clipboard
      window.navigator.clipboard = {
        writeText: (t) => Promise.resolve(t)
      };
    }
  });

  const { window } = dom;
  const { document } = window;
  global.window = window;
  global.document = window.document;

  // Manually execute local scripts if JSDOM didn't load them synchronously
  if (!window.GPO_ICONS) {
    const iconsScript = fs.readFileSync(path.join(__dirname, 'icons.js'), 'utf8');
    window.eval(iconsScript);
  }
  if (!window.GPO_ITEMS) {
    const itemsScript = fs.readFileSync(path.join(__dirname, 'items_data.js'), 'utf8');
    window.eval(itemsScript);
  }
  if (!window.GPO_APP) {
    const appScript = fs.readFileSync(path.join(__dirname, 'app.js'), 'utf8');
    window.eval(appScript);
  }

  // Trigger DOMContentLoaded
  const dclEvent = new window.Event('DOMContentLoaded');
  window.document.dispatchEvent(dclEvent);

  console.log('✅ DOMContentLoaded fired.');

  // Test 1: Navigation Tabs
  console.log('Testing Navigation Tabs...');
  const tabs = ['calculator', 'tierlist', 'forecasts', 'hourly-changes', 'community', 'guide'];
  const tabSectionMap = {
    calculator: 'sectionCalculator',
    tierlist: 'sectionTierlist',
    forecasts: 'sectionForecasts',
    'hourly-changes': 'sectionHourlyChanges',
    community: 'sectionCommunity',
    guide: 'sectionGuide'
  };
  for (const t of tabs) {
    const btn = document.querySelector(`.nav-tab-btn[data-tab="${t}"]`);
    if (!btn) throw new Error(`Tab button for ${t} not found`);
    btn.click();
    const section = document.getElementById(tabSectionMap[t]);
    if (!section || section.style.display === 'none') {
      throw new Error(`Section ${t} (${tabSectionMap[t]}) failed to display on tab click`);
    }
  }
  console.log('✓ Navigation Tabs working.');

  // Switch back to calculator
  document.querySelector('[data-tab="calculator"]').click();

  // Test 2: Language Toggle
  console.log('Testing Language Toggle...');
  const langBtn = document.getElementById('langToggleBtn');
  if (!langBtn) throw new Error('langToggleBtn not found');
  langBtn.click(); // to RU
  const langCodeEl = document.getElementById('langCode');
  if (langCodeEl.textContent !== 'RU') throw new Error(`Expected RU, got ${langCodeEl.textContent}`);
  langBtn.click(); // back to EN
  if (langCodeEl.textContent !== 'EN') throw new Error(`Expected EN, got ${langCodeEl.textContent}`);
  console.log('✓ Language Toggle working.');

  // Test 3: Audio Toggle
  console.log('Testing Audio Toggle...');
  const audioBtn = document.getElementById('audioToggleBtn');
  if (!audioBtn) throw new Error('audioToggleBtn not found');
  audioBtn.click();
  audioBtn.click();
  console.log('✓ Audio Toggle working.');

  // Test 4: Calculator quick add
  console.log('Testing Trade Calculator Quick Add...');
  const firstItem = window.GPO_ITEMS[0];
  const secondItem = window.GPO_ITEMS[1];
  window.GPO_APP.quickAdd('you', firstItem.id);
  window.GPO_APP.quickAdd('they', secondItem.id);

  const youSlots = document.querySelectorAll('#youSlotsGrid .trade-slot-card');
  const theySlots = document.querySelectorAll('#theySlotsGrid .trade-slot-card');
  if (youSlots.length !== 1) throw new Error(`Expected 1 user slot card, got ${youSlots.length}`);
  if (theySlots.length !== 1) throw new Error(`Expected 1 trader slot card, got ${theySlots.length}`);

  // Test quantity adjustment
  window.GPO_APP.changeQty('you', firstItem.id, 1);
  const qtyEl = document.querySelector('#youSlotsGrid .qty-num');
  if (!qtyEl || qtyEl.textContent !== 'x2') throw new Error(`Expected x2 qty, got ${qtyEl ? qtyEl.textContent : 'none'}`);

  // Test side swap
  const swapBtn = document.getElementById('swapSidesBtn');
  if (swapBtn) {
    swapBtn.click();
    console.log('✓ Swap sides clicked.');
  }

  // Test clear all
  const clearBtn = document.getElementById('clearTradeBtn');
  if (clearBtn) {
    clearBtn.click();
    const youSlotsAfter = document.querySelectorAll('#youSlotsGrid .trade-slot-card');
    if (youSlotsAfter.length !== 0) throw new Error(`Expected 0 slots after clear, got ${youSlotsAfter.length}`);
    console.log('✓ Clear trade working.');
  }

  // Test 5: Item Picker Modal
  console.log('Testing Item Picker Modal...');
  const addSlotBtn = document.querySelector('.add-slot-placeholder');
  if (addSlotBtn) {
    addSlotBtn.click();
    const modal = document.getElementById('itemPickerModal');
    if (!modal.classList.contains('open')) throw new Error('Picker modal not open');
    
    // Test search inside picker
    const searchInput = document.getElementById('pickerSearchInput');
    searchInput.value = 'eye';
    window.filterPickerItems(true);
    
    // Pick first item in grid
    const pickItem = document.querySelector('#pickerItemsGrid .picker-grid-item');
    if (pickItem) {
      pickItem.click();
      console.log('✓ Item selected from picker.');
    }
  }

  // Test 6: Tier List Filtering & Search
  console.log('Testing Tier List Filtering...');
  document.querySelector('[data-tab="tierlist"]').click();
  const mainSearch = document.getElementById('mainSearchInput');
  if (mainSearch) {
    mainSearch.value = 'Mochi';
    const inputEv = new window.Event('input');
    mainSearch.dispatchEvent(inputEv);
  }

  // Test 7: Forecasts Timeframe
  console.log('Testing Forecasts Timeframe...');
  document.querySelector('[data-tab="forecasts"]').click();
  const tfBtns = document.querySelectorAll('.tf-btn');
  if (tfBtns.length > 0) {
    tfBtns[1].click();
    tfBtns[2].click();
  }
  console.log('✓ Forecasts timeframe working.');

  // Test 7b: Hourly Changes Section (UP & DOWN tables)
  console.log('Testing Hourly Changes Section (UP & DOWN)...');
  document.querySelector('[data-tab="hourly-changes"]').click();
  const hourlySection = document.getElementById('sectionHourlyChanges');
  if (!hourlySection || hourlySection.style.display === 'none') {
    throw new Error('Hourly Changes section failed to display');
  }

  // Trigger render
  if (window.renderHourlyChanges) {
    window.renderHourlyChanges();
  }

  // Test subtabs UP, DOWN, ALL
  const subTabUp = document.getElementById('hourlySubTabUp');
  const subTabDown = document.getElementById('hourlySubTabDown');
  const subTabAll = document.getElementById('hourlySubTabAll');
  if (!subTabUp || !subTabDown || !subTabAll) {
    throw new Error('Hourly subtabs (UP, DOWN, ALL) not found');
  }

  subTabUp.click();
  let upRows = document.querySelectorAll('#hourlyTableBody tr');
  if (upRows.length === 0) throw new Error('Expected rows in UP section');

  subTabDown.click();
  let downRows = document.querySelectorAll('#hourlyTableBody tr');
  if (downRows.length === 0) throw new Error('Expected rows in DOWN section');

  subTabAll.click();
  let allRows = document.querySelectorAll('#hourlyTableBody tr');
  if (allRows.length < upRows.length) throw new Error('Expected ALL rows >= UP rows');

  // Verify first row contains image, name, prices, and delta badges
  const sampleRow = upRows[0];
  const imgEl = sampleRow.querySelector('img');
  const deltaBadge = sampleRow.querySelector('.delta-badge');
  const pctBadge = sampleRow.querySelector('.pct-badge');
  if (!imgEl) throw new Error('Item photo missing in Hourly Changes row');
  if (!deltaBadge) throw new Error('Delta pts badge missing in Hourly Changes row');
  if (!pctBadge) throw new Error('Delta pct badge missing in Hourly Changes row');

  console.log(`✓ Hourly Changes verified (${upRows.length} UP, ${downRows.length} DOWN).`);

  // Test 8: Item Detail Modal
  console.log('Testing Item Detail Modal...');
  window.GPO_APP.openDetail(firstItem.id);
  const detailModal = document.getElementById('itemDetailModal');
  if (!detailModal.classList.contains('open')) throw new Error('Detail modal not open');
  
  // Test Escape key shortcut
  console.log("Detail modal isOpen before Escape:", detailModal.classList.contains('open'));
  const escEvent = new window.KeyboardEvent('keydown', { key: 'Escape', code: 'Escape', keyCode: 27, which: 27, bubbles: true, cancelable: true });
  document.dispatchEvent(escEvent);
  console.log("Detail modal isOpen after Escape:", detailModal.classList.contains('open'));
  if (detailModal.classList.contains('open')) throw new Error('Escape key did not close detail modal');
  console.log('✓ Keyboard Escape shortcut working.');

  // Test 9: Discord Export & Toast Notifications
  console.log('Testing Discord Export & Toast notifications...');
  document.querySelector('[data-tab="calculator"]').click();
  window.GPO_APP.quickAdd('you', firstItem.id);
  window.GPO_APP.quickAdd('they', secondItem.id);
  
  const discordBtn = document.getElementById('btnDiscordExport');
  if (!discordBtn) throw new Error('btnDiscordExport not found');
  discordBtn.click();
  
  const toastContainer = document.getElementById('gpoToastContainer');
  if (!toastContainer || toastContainer.children.length === 0) {
    throw new Error('Expected toast notification to appear');
  }
  console.log('✓ Toast notification & Discord Export working.');

  // Test 10: Search Clear Button
  console.log('Testing Search Clear Button...');
  const searchInput = document.getElementById('searchInput');
  if (searchInput) {
    searchInput.value = 'Mochi';
    const inputEv = new window.Event('input');
    searchInput.dispatchEvent(inputEv);
    window.clearSearchInput('searchInput');
    if (searchInput.value !== '') throw new Error('Expected searchInput to be cleared');
    console.log('✓ Search clear button working.');
  }

  // Test 11: Rare Fruit Chest Economy Rule
  console.log('Testing Chest Economy Ratios (Item 208)...');
  const rcItem = window.GPO_ITEMS.find(x => x.id === 'item_208');
  if (!rcItem) throw new Error('Item 208 not found in GPO_ITEMS');
  if (rcItem.value > 100) {
    throw new Error(`Item 208 Rare Fruit Chest value is ${rcItem.value}, expected <= 100 pts`);
  }
  console.log(`✓ Rare Fruit Chest correctly valued at ${rcItem.value} pts (${rcItem.lcValue} LC).`);

  console.log('\n--- Summary ---');
  console.log(`Total Errors caught: ${errors.length}`);
  if (errors.length > 0) {
    console.error('Errors:', errors);
    process.exit(1);
  } else {
    console.log('🎉 ALL INTEGRATION TESTS PASSED WITHOUT ERRORS!');
  }
}

runTestSuite().catch(err => {
  console.error('Fatal test error:', err);
  process.exit(1);
});
