(function () {
  'use strict';

  const $ = id => document.getElementById(id);
  const tabs = ['calculator', 'tierlist', 'forecasts', 'hourly-changes', 'guide', 'community'];
  const categories = ['all', 'fruits', 'weapons', 'chests', 'accessories', 'outfits', 'boats', 'misc'];
  const rarities = ['Common', 'Uncommon', 'Rare', 'Epic', 'Legendary', 'Mythical', 'Collectable', 'Rare Chroma', 'Legendary Chroma'];
  const rarityKey = item => rarities.includes(item.rarity) ? item.rarity.toLowerCase().replace(/ /g, '-') : 'unknown';
  const categoryIcons = { all: 'boxes', fruits: 'apple', weapons: 'swords', chests: 'package', accessories: 'crown', outfits: 'shirt', boats: 'ship', misc: 'sparkles' };
  const inputs = { quick: 'quickSearchInput', catalog: 'searchInput', market: 'forecastSearchInput', changes: 'hourlySearchInput', picker: 'pickerSearchInput' };
  const scopes = { calculator: 'quick', tierlist: 'catalog', forecasts: 'market', 'hourly-changes': 'changes' };
  const tierColors = { Exclusive: '#e9ad97', 'Tier SS': '#ecb857', 'Tier S': '#d6b46f', 'Tier A+': '#c9abdb', 'Tier A': '#8cb8d2', 'Tier A-': '#83bea8', 'Tier B+': '#afd394', 'Tier B': '#82afb6', 'Tier B-': '#9faebd', 'Tier C': '#a2a3b8', 'Tier F': '#8b939e', 'Very Unstable': '#edb0ce', 'New Items': '#afd6e9' };
  const batchSize = 24;
  const filters = Object.fromEntries(Object.keys(inputs).map(scope => [scope, { query: '', category: 'all', limit: batchSize }]));
  let data = null;
  let byId = new Map();
  let searchKeys = new Map();
  let trade = { you: [], they: [] };
  let tab = 'calculator';
  let tier = 'all';
  let rarity = 'all';
  let timeframe = '1h';
  let direction = 'all';
  let pickerSide = 'you';
  let detailId = null;
  let pendingData = null;
  let loading = false;
  let lastCheck = 0;
  let undoTrade = null;
  let returnFocus = null;
  let historyPromise = null;
  const searchTimers = new Map();
  const sounds = new Map();

  function stored(key, fallback = null) {
    try { return localStorage.getItem(key) ?? fallback; } catch { return fallback; }
  }
  function store(key, value) {
    try { localStorage.setItem(key, value); } catch { /* Storage is optional. */ }
  }
  const initialLang = new URLSearchParams(location.search).get('lang') || stored('gpo_lang') || ((navigator.language || '').startsWith('ru') ? 'ru' : 'en');
  let lang = initialLang === 'ru' ? 'ru' : 'en';
  let audioEnabled = stored('gpo_audio') === 'true';
  let effectsEnabled = stored('gpo_effects') !== 'false' && !window.matchMedia?.('(prefers-reduced-motion: reduce)')?.matches;
  const t = (key, values = {}) => (window.GPO_TRANSLATIONS[lang][key] || key).replace(/\{(\w+)\}/g, (_, name) => String(values[name] ?? ''));
  const nameOf = item => lang === 'ru' ? item.nameRu || item.name : item.name;
  const number = (value, digits = 2) => value === null || !Number.isFinite(value) ? '—' : new Intl.NumberFormat(lang, { maximumFractionDigits: digits }).format(value);
  const points = value => value === null || !Number.isFinite(value) ? '—' : `${number(value)} pts`;
  const dateText = value => !value || !Number.isFinite(Date.parse(value)) ? '—' : new Intl.DateTimeFormat(lang, { dateStyle: 'medium', timeStyle: 'short' }).format(new Date(value));
  const normalize = value => String(value || '').normalize('NFKC').toLowerCase().replace(/['’`"()\-–—]/g, '').replace(/\s+/g, ' ').trim();

  function element(tag, className = '', text) {
    const node = document.createElement(tag);
    if (className) node.className = className;
    if (text !== undefined) node.textContent = text;
    return node;
  }
  function icon(name) {
    const node = element('span', 'icon');
    node.setAttribute('aria-hidden', 'true');
    node.innerHTML = window.getIcon ? window.getIcon(name) : '';
    return node;
  }
  function decorateIcons(container = document) {
    container.querySelectorAll('[data-icon]').forEach(node => {
      node.innerHTML = window.getIcon ? window.getIcon(node.dataset.icon) : '';
      node.setAttribute('aria-hidden', 'true');
    });
  }
  function button(text, action, className = 'game-button', attributes = {}) {
    const node = element('button', className, text);
    node.type = 'button';
    node.dataset.action = action;
    Object.assign(node.dataset, attributes);
    return node;
  }
  function image(item, size, className = '') {
    const node = element('img', className);
    node.src = /^images\/[\w/.-]+\.(?:webp|png|jpg|jpeg|svg)$/.test(item.image || '') ? item.image : 'images/placeholder.svg';
    node.alt = nameOf(item);
    node.width = node.height = size;
    node.loading = 'lazy';
    node.decoding = 'async';
    node.addEventListener('error', () => { node.src = 'images/placeholder.svg'; }, { once: true });
    return node;
  }
  function toast(message, undo = false) {
    const container = $('gpoToastContainer');
    const node = element('div', 'gpo-toast');
    node.append(element('span', '', message));
    if (undo) node.append(button(t('undo'), 'undo', ''));
    const close = button('×', 'dismiss-toast', '');
    close.setAttribute('aria-label', t('close'));
    node.append(close);
    while (container.children.length >= 3) container.firstElementChild.remove();
    container.append(node);
    setTimeout(() => node.remove(), undo ? 6500 : 3500);
  }
  function sound(kind = 'add') {
    if (!audioEnabled) return;
    try {
      const files = { add: 'item_add.wav', remove: 'item_remove.wav', click: 'click.wav' };
      if (!sounds.has(kind)) sounds.set(kind, new Audio(`audio/${files[kind] || files.click}`));
      const audio = sounds.get(kind);
      audio.volume = 0.2;
      audio.currentTime = 0;
      audio.play().catch(() => {});
    } catch { /* Sound must never block a trade action. */ }
  }

  function validateSnapshot(snapshot) {
    if (snapshot?.schema_version !== 2 || !Array.isArray(snapshot.items) || !snapshot.items.length || snapshot.items.length > 5000) throw new Error('Invalid snapshot');
    const ids = new Set();
    let lastRank = 0;
    let lastValue = null;
    for (const item of snapshot.items) {
      if (!/^[a-zA-Z0-9_]+$/.test(item.id || '') || ids.has(item.id) || typeof item.name !== 'string' || item.name.length > 250) throw new Error('Invalid item');
      ids.add(item.id);
      if (item.value !== null && (!Number.isFinite(item.value) || item.value <= 0)) throw new Error('Invalid price');
      if (!Number.isInteger(item.official_rank) || item.official_rank < 1) throw new Error('Invalid official rank');
      if (item.rank_locked) {
        if (item.official_rank <= lastRank) throw new Error('Official order mismatch');
        lastRank = item.official_rank;
        if (item.value !== null) {
          if (lastValue !== null && lastValue <= item.value) throw new Error('Price order mismatch');
          lastValue = item.value;
        }
      }
    }
    const anchor = snapshot.items.find(item => item.id === snapshot.currency?.anchor_id);
    if (!anchor || anchor.value !== 1) throw new Error('Invalid point anchor');
    return snapshot;
  }

  async function loadSnapshot(explicit = true) {
    if (loading) return;
    loading = true;
    lastCheck = Date.now();
    $('refreshDataBtn').disabled = true;
    const controller = new AbortController();
    const timeout = setTimeout(() => controller.abort(), 15000);
    try {
      const response = await fetch('data/values.json', { cache: 'no-cache', signal: controller.signal });
      if (!response.ok) throw new Error(`HTTP ${response.status}`);
      const incoming = validateSnapshot(await response.json());
      $('loadError').hidden = true;
      if (data && incoming.revision !== data.revision && !explicit && (trade.you.length || trade.they.length)) {
        pendingData = incoming;
        $('newDataNotice').hidden = false;
      } else if (!data || data.revision !== incoming.revision || explicit) {
        applySnapshot(incoming);
      }
    } catch {
      $('loadError').hidden = false;
      $('loadErrorText').textContent = t('load_error') + (data ? ` ${t('source_cached')}` : '');
      if (!data) {
        $('sourceStatus').textContent = t('source_unavailable');
        $('sourceIndicator').className = 'source-indicator error';
      }
    } finally {
      clearTimeout(timeout);
      loading = false;
      $('refreshDataBtn').disabled = false;
      $('main').setAttribute('aria-busy', 'false');
    }
  }

  function applySnapshot(snapshot) {
    const firstLoad = !data;
    data = snapshot;
    byId = new Map(data.items.map(item => [item.id, item]));
    searchKeys = new Map(data.items.map(item => [item.id, normalize(`${item.name} ${item.nameRu || ''} ${item.abbreviation || ''}`)]));
    window.GPO_ITEMS = data.items;
    pendingData = null;
    historyPromise = null;
    $('newDataNotice').hidden = true;
    document.querySelectorAll('[data-requires-data]').forEach(node => { node.disabled = false; });
    if (firstLoad) restoreTrade();
    fillTierSelect();
    renderCategories();
    renderSource();
    renderTrade();
    renderCurrent();
    if (detailId && $('itemDetailModal').open) renderDetail(detailId);
  }

  function renderSource() {
    if (!data) return;
    const source = data.discord_source || {};
    const age = Date.now() - Date.parse(data.meta.updated_at_iso);
    const failed = source.channels?.some(channel => channel.status === 'error');
    let key = 'source_waiting';
    let status = 'waiting';
    if (source.mode !== 'offline' && source.complete) {
      key = age > 2 * 3600000 ? 'source_stale' : 'source_live';
      status = age > 2 * 3600000 ? 'waiting' : 'live';
    } else if (failed) { key = 'source_error'; status = 'error'; }
    else if (source.mode === 'scheduled') key = 'source_partial';
    $('sourceStatus').textContent = t(key);
    $('sourceIndicator').className = `source-indicator ${status}`;
    $('sourceDescription').textContent = t('snapshot_at', { count: number(data.items.length), time: dateText(data.meta.updated_at_iso) });
    $('heroLcValue').textContent = points(byId.get(data.currency.lc_id)?.value);
  }

  function restoreTrade() {
    if (!data) return;
    const hash = location.hash;
    if (hash && !hash.startsWith('#trade=')) return;
    const restored = { you: [], they: [] };
    let invalid = false;
    if (hash.startsWith('#trade=')) {
      try {
        if (hash.length > 32000) throw new Error('Trade link is too long');
        const decoded = atob(hash.slice(7).split('&')[0]);
        const parsed = JSON.parse(decoded.startsWith('%') ? decodeURIComponent(decoded) : decoded);
        if (!parsed || typeof parsed !== 'object') throw new Error('Invalid trade');
        for (const [key, side] of [['y', 'you'], ['t', 'they']]) {
          const entries = parsed[key] ?? [];
          if (!Array.isArray(entries) || entries.length > 60) throw new Error('Invalid trade side');
          const grouped = new Map();
          for (const entry of entries) {
            if (!Array.isArray(entry) || entry.length !== 2) { invalid = true; continue; }
            const [id, qty] = entry;
            if (!byId.has(id) || !Number.isSafeInteger(qty) || qty < 1 || qty > 100000) { invalid = true; continue; }
            const total = (grouped.get(id) || 0) + qty;
            if (total > 100000) { invalid = true; continue; }
            grouped.set(id, total);
          }
          restored[side] = [...grouped].map(([id, qty]) => ({ id, qty }));
        }
      } catch { invalid = true; }
    }
    trade = restored;
    if (invalid) toast(t('invalid_trade'));
    renderTrade();
  }

  function saveTrade() {
    const url = new URL(location.href);
    const payload = { y: trade.you.map(entry => [entry.id, entry.qty]), t: trade.they.map(entry => [entry.id, entry.qty]) };
    url.hash = trade.you.length || trade.they.length ? `trade=${btoa(encodeURIComponent(JSON.stringify(payload)))}` : '';
    history.replaceState(null, '', url);
  }

  function sideTotal(side) {
    let cents = 0;
    let known = true;
    let weight = 0;
    for (const entry of trade[side]) {
      const item = byId.get(entry.id);
      if (!item || item.value === null) { known = false; continue; }
      const subtotal = Math.round(item.value * 100) * entry.qty;
      if (!Number.isSafeInteger(subtotal) || !Number.isSafeInteger(cents + subtotal)) { known = false; continue; }
      cents += subtotal;
      weight += subtotal * (item.confidence || 0);
    }
    const lc = byId.get(data?.currency?.lc_id)?.value;
    return { cents: known ? cents : null, value: known ? cents / 100 : null, lc: known && lc ? cents / 100 / lc : null, confidence: cents ? weight / cents : 0, count: trade[side].length };
  }

  function renderTrade() {
    const focus = document.activeElement;
    const focusedQuantity = focus?.closest('.trade-slot-card') ? { ...focus.dataset, input: focus.classList.contains('qty-num') } : null;
    for (const side of ['you', 'they']) {
      const fragment = document.createDocumentFragment();
      for (const entry of trade[side]) {
        const item = byId.get(entry.id) || { id: entry.id, name: t('unavailable_item'), image: 'images/placeholder.svg', value: null };
        const card = element('div', 'trade-slot-card');
        card.dataset.rarity = rarityKey(item);
        const remove = button('', 'remove', 'slot-remove-btn', { side, id: item.id });
        remove.append(icon('x'));
        remove.setAttribute('aria-label', t('remove', { name: nameOf(item) }));
        const title = element('div', 'slot-item-name', nameOf(item));
        title.title = `${nameOf(item)} · ${item.rarity || t('rarity_unknown')}`;
        const controls = element('div', 'slot-qty-controls');
        const minus = button('−', 'quantity-step', 'qty-btn', { side, id: item.id, delta: '-1' });
        minus.setAttribute('aria-label', t('decrease', { name: nameOf(item) }));
        const input = element('input', 'qty-num');
        Object.assign(input, { type: 'number', name: `quantity-${side}-${item.id}`, autocomplete: 'off', min: '1', max: '100000', step: '1', value: entry.qty, inputMode: 'numeric' });
        input.dataset.side = side;
        input.dataset.id = item.id;
        input.setAttribute('aria-label', t('quantity', { name: nameOf(item) }));
        const plus = button('+', 'quantity-step', 'qty-btn', { side, id: item.id, delta: '1' });
        plus.setAttribute('aria-label', t('increase', { name: nameOf(item) }));
        controls.append(minus, input, plus);
        card.append(remove, image(item, 45, 'slot-item-img'), title, element('div', 'slot-item-val', points(item.value === null ? null : item.value * entry.qty)), controls);
        fragment.append(card);
      }
      if (!trade[side].length) {
        const empty = element('div', 'empty-offer');
        empty.append(icon(side === 'you' ? 'package' : 'gift'), element('p', '', t('empty_offer')));
        fragment.append(empty);
      }
      $(`${side}SlotsGrid`).replaceChildren(fragment);
      const total = sideTotal(side);
      $(`${side}TotalPts`).textContent = points(total.value);
      $(`${side}TotalLc`).textContent = `${number(total.lc)} LC`;
      $(`${side}Count`).textContent = number(trade[side].length);
    }
    $('btnClearTrade').disabled = !trade.you.length && !trade.they.length;
    const you = sideTotal('you');
    const they = sideTotal('they');
    let verdict = 'empty';
    let label = 'verdict_empty';
    let advice = 'verdict_hint';
    let difference = '—';
    if (you.count && they.count) {
      if (you.value === null || they.value === null) {
        verdict = 'unknown'; label = 'verdict_unknown'; advice = 'verdict_unknown_hint';
      } else {
        const diff = (they.cents - you.cents) / 100;
        const pct = (they.cents - you.cents) / you.cents * 100;
        verdict = pct >= 5 ? 'win' : pct <= -5 ? 'lose' : 'fair';
        label = `verdict_${verdict}`;
        difference = `${diff >= 0 ? '+' : '−'}${points(Math.abs(diff))} (${pct >= 0 ? '+' : '−'}${number(Math.abs(pct), 1)}%)`;
        advice = Math.min(you.confidence, they.confidence) < 0.35 ? 'weak_evidence' : 'good_evidence';
      }
    }
    $('verdictStamp').className = `verdict-stamp ${verdict}`;
    $('verdictStamp').dataset.state = verdict;
    $('verdictText').textContent = t(label);
    $('verdictDiffText').textContent = difference;
    $('verdictAdvice').textContent = t(advice);
    if (focusedQuantity) {
      const selector = focusedQuantity.input ? '.qty-num' : `[data-action="${focusedQuantity.action}"]${focusedQuantity.delta ? `[data-delta="${focusedQuantity.delta}"]` : ''}`;
      const target = document.querySelector(`${selector}[data-id="${focusedQuantity.id}"][data-side="${focusedQuantity.side}"]`) ||
        document.querySelector(`[data-action="picker"][data-side="${focusedQuantity.side}"]`);
      target?.focus({ preventScroll: true });
    }
  }

  function addItem(side, id) {
    if (!['you', 'they'].includes(side) || !byId.has(id)) return;
    const current = trade[side].find(entry => entry.id === id);
    if (current?.qty >= 100000) return toast(t('quantity_error'));
    if (!current && trade[side].length >= 60) return toast(t('limit_error'));
    if (current) current.qty += 1;
    else trade[side].push({ id, qty: 1 });
    renderTrade(); saveTrade(); sound();
    toast(t('added', { name: nameOf(byId.get(id)) }));
  }
  function removeItem(side, id) {
    if (!['you', 'they'].includes(side)) return;
    trade[side] = trade[side].filter(entry => entry.id !== id);
    renderTrade(); saveTrade(); sound('remove');
  }
  function setQuantity(side, id, value) {
    const entry = trade[side]?.find(entry => entry.id === id);
    if (!entry) return;
    if (!Number.isSafeInteger(value) || value < 1 || value > 100000) { toast(t('quantity_error')); renderTrade(); return; }
    entry.qty = value;
    renderTrade(); saveTrade();
  }
  function changeQuantity(side, id, delta) {
    const entry = trade[side]?.find(entry => entry.id === id);
    if (!entry || !Number.isSafeInteger(delta)) return;
    if (entry.qty + delta <= 0) removeItem(side, id);
    else setQuantity(side, id, entry.qty + delta);
  }

  function evidence(item) {
    if (item.value === null) return t('price_unknown');
    if (item.price_status === 'baseline') return t('price_baseline');
    if (item.price_status === 'carried') return t('price_carried');
    return t(item.confidence >= 0.7 ? 'evidence_high' : item.confidence >= 0.35 ? 'evidence_medium' : 'evidence_low');
  }
  function evidenceTag(item) {
    const tag = element('span', `evidence-tag${item.confidence >= 0.7 ? ' strong' : ''}`);
    tag.append(element('span', 'evidence-dot'), document.createTextNode(evidence(item)));
    return tag;
  }
  function tierTag(item) {
    const tag = element('span', 'tier-tag', item.tier.replace(/^Tier /, ''));
    tag.title = t('trade_tier');
    tag.style.setProperty('--tier-color', tierColors[item.tier] || '#91a8b4');
    return tag;
  }
  function rarityTag(item) {
    const tag = element('span', 'rarity-label rarity-text', item.rarity || t('rarity_unknown'));
    tag.title = t('game_rarity');
    return tag;
  }
  function card(item) {
    const node = element('article', 'item-comic-card');
    node.dataset.rarity = rarityKey(item);
    node.style.setProperty('--tier-color', tierColors[item.tier] || '#91a8b4');
    const top = element('div', 'item-card-top');
    const rank = element('span', `rank-indicator${item.rank_locked ? '' : ' flexible'}`, `#${item.display_rank}`);
    rank.prepend(icon(item.rank_locked ? 'shield-check' : 'trending-up'));
    rank.title = t(item.rank_locked ? 'locked_order' : 'flexible_order');
    top.append(tierTag(item), rank);
    const open = button('', 'detail', 'item-open-button', { id: item.id });
    const art = element('span', 'item-art');
    art.append(image(item, 112));
    open.append(art, element('span', 'item-name', nameOf(item)));
    open.title = nameOf(item);
    const values = element('div', 'card-values-row');
    values.append(element('span', 'item-price', points(item.value)), element('span', 'item-lc', `${number(item.lcValue)} LC`));
    const actions = element('div', 'card-actions-row');
    actions.append(button(t('add_you'), 'add', 'quick-add-btn add-you', { id: item.id, side: 'you' }), button(t('add_they'), 'add', 'quick-add-btn add-them', { id: item.id, side: 'they' }));
    node.append(top, open, rarityTag(item), element('div', 'item-abbr', item.abbreviation || (lang === 'ru' ? item.name : t(`cat_${item.category}`))), values, evidenceTag(item), actions);
    return node;
  }
  function filtered(scope) {
    const filter = filters[scope];
    const words = normalize(filter.query).split(' ').filter(Boolean);
    return (data?.items || []).filter(item => (filter.category === 'all' || item.category === filter.category) &&
      (scope !== 'catalog' || tier === 'all' || item.tier === tier) &&
      (scope !== 'catalog' || rarity === 'all' || (rarity === 'unknown' ? !item.rarity : item.rarity === rarity)) &&
      words.every(word => searchKeys.get(item.id)?.includes(word)));
  }
  function emptyResults() {
    const node = element('div', 'empty-state');
    node.append(icon('search'), element('h3', '', t('no_results')), element('p', '', t('no_results_hint')));
    return node;
  }
  function moreState(scope, total) {
    document.querySelector(`[data-action="more"][data-scope="${scope}"]`).hidden = total <= filters[scope].limit;
  }
  function renderCatalog(scope, start = 0) {
    if (!data) return;
    const list = filtered(scope);
    const grid = $(scope === 'quick' ? 'quickItemsCardsGrid' : 'itemsCardsGrid');
    const fragment = document.createDocumentFragment();
    list.slice(start, filters[scope].limit).forEach(item => fragment.append(card(item)));
    if (!list.length) fragment.append(emptyResults());
    if (start) grid.append(fragment); else grid.replaceChildren(fragment);
    $(`${scope === 'quick' ? 'quick' : 'catalog'}ResultCount`).textContent = t('results', { shown: Math.min(list.length, filters[scope].limit), total: list.length });
    moreState(scope, list.length);
  }
  function renderCategories() {
    if (!data) return;
    const focused = document.activeElement?.closest('[data-action="category"]')?.dataset;
    const counts = categoryCounts();
    document.querySelectorAll('[data-categories]').forEach(container => {
      const scope = container.dataset.categories;
      const fragment = document.createDocumentFragment();
      for (const category of categories) {
        const active = filters[scope].category === category;
        const node = button('', 'category', `filter-pill-btn${active ? ' active' : ''}`, { scope, category });
        node.setAttribute('aria-pressed', String(active));
        node.append(icon(categoryIcons[category]), element('span', '', t(`cat_${category}`)), element('span', 'category-count', number(counts[category] || 0)));
        fragment.append(node);
      }
      container.replaceChildren(fragment);
    });
    if (focused) document.querySelector(`[data-categories="${focused.scope}"] [data-category="${focused.category}"]`)?.focus({ preventScroll: true });
  }
  function categoryCounts() {
    const counts = { all: data.items.length };
    data.items.forEach(item => { counts[item.category] = (counts[item.category] || 0) + 1; });
    return counts;
  }
  function fillTierSelect() {
    const select = $('tierSelect');
    select.replaceChildren(new Option(t('all_tiers'), 'all'));
    [...new Set(data.items.slice().sort((a, b) => a.official_rank - b.official_rank).map(item => item.tier))].forEach(value => select.add(new Option(value, value)));
    if (![...select.options].some(option => option.value === tier)) tier = 'all';
    select.value = tier;
  }
  function tableItem(item) {
    const open = button('', 'detail', 'table-item-button', { id: item.id });
    open.dataset.rarity = rarityKey(item);
    const text = element('span');
    text.append(element('strong', '', nameOf(item)), rarityTag(item), element('small', '', `${item.tier}${item.abbreviation ? ` · ${item.abbreviation}` : ''}`));
    open.append(image(item, 44), text);
    return open;
  }
  function cell(content, className = '') {
    const node = element('td', className);
    if (content instanceof Node) node.append(content); else node.textContent = content;
    return node;
  }
  function renderMarket(start = 0) {
    if (!data) return;
    const offers = data.meta[`total_trades_${timeframe}`] ?? 0;
    $('marketOffersCount').textContent = number(offers);
    $('marketSupportedCount').textContent = number(data.meta.supported_observations ?? 0);
    const source = data.discord_source;
    $('marketCoverage').textContent = t(source?.mode === 'offline' ? 'history_waiting' : source?.history_complete ? 'history_complete' : 'history_partial');
    $('marketPeriodNote').textContent = t('period_note', { count: number(offers), period: t(`period_${timeframe}`) });
    const list = filtered('market');
    const fragment = document.createDocumentFragment();
    for (const item of list.slice(start, filters.market.limit)) {
      const row = element('tr');
      const value = element('span', 'table-number', points(item.value));
      value.append(element('span', 'secondary-number', `${number(item.lcValue)} LC`));
      const metrics = item.timeframes?.[timeframe];
      row.append(cell(tableItem(item)), cell(value), cell(number(metrics?.demand_count ?? 0)), cell(number(metrics?.supply_count ?? 0)), cell(evidenceTag(item)));
      fragment.append(row);
    }
    if (!list.length) { const row = element('tr'); const td = cell(emptyResults()); td.colSpan = 5; row.append(td); fragment.append(row); }
    if (start) $('forecastTableBody').append(fragment); else $('forecastTableBody').replaceChildren(fragment);
    moreState('market', list.length);
  }
  function renderChanges(start = 0) {
    if (!data) return;
    const allowed = new Set(filtered('changes').map(item => item.id));
    const changes = (data.changes || []).filter(change => allowed.has(change.id) &&
      (direction === 'all' || (direction === 'up' ? change.delta_pts > 0 : change.delta_pts < 0)));
    $('changesTime').textContent = dateText(data.meta.updated_at_iso);
    $('changesTablePanel').hidden = !changes.length;
    $('hourlyEmptyState').hidden = Boolean(changes.length);
    const fragment = document.createDocumentFragment();
    for (const change of changes.slice(start, filters.changes.limit)) {
      const item = byId.get(change.id);
      const row = element('tr');
      const delta = element('span', change.delta_pts > 0 ? 'delta-positive' : 'delta-negative', `${change.delta_pts > 0 ? '+' : '−'}${points(Math.abs(change.delta_pts))}`);
      delta.append(element('span', 'secondary-number', `${change.delta_pct > 0 ? '+' : '−'}${number(Math.abs(change.delta_pct), 1)}%`));
      row.append(cell(tableItem(item)), cell(points(change.old_value)), cell(points(change.new_value), 'table-number'), cell(delta), cell(t(change.reason === 'official_order' ? 'reason_official' : 'reason_market'), 'reason-label'));
      fragment.append(row);
    }
    if (start) $('hourlyTableBody').append(fragment); else $('hourlyTableBody').replaceChildren(fragment);
    moreState('changes', changes.length);
  }
  function renderPicker(start = 0) {
    if (!data) return;
    const list = filtered('picker');
    const fragment = document.createDocumentFragment();
    for (const item of list.slice(start, filters.picker.limit)) {
      const node = button('', 'pick', 'picker-item-btn', { id: item.id });
      node.dataset.rarity = rarityKey(item);
      const art = element('span', 'item-art picker-art');
      art.append(image(item, 88));
      node.append(art, element('span', 'item-name', nameOf(item)), rarityTag(item), element('span', 'item-price', points(item.value)));
      fragment.append(node);
    }
    if (!list.length) fragment.append(emptyResults());
    if (start) $('pickerItemsGrid').append(fragment); else $('pickerItemsGrid').replaceChildren(fragment);
    moreState('picker', list.length);
  }
  function renderScope(scope, start = 0) {
    if (scope === 'quick' || scope === 'catalog') renderCatalog(scope, start);
    else if (scope === 'market') renderMarket(start);
    else if (scope === 'changes') renderChanges(start);
    else if (scope === 'picker') renderPicker(start);
  }
  function renderCurrent() { if (scopes[tab]) renderScope(scopes[tab]); }

  function openDialog(id) {
    returnFocus = document.activeElement;
    document.querySelectorAll('dialog[open]').forEach(dialog => closeDialog(dialog));
    const dialog = $(id);
    document.body.classList.add('modal-open');
    if (typeof dialog.showModal === 'function') dialog.showModal(); else dialog.setAttribute('open', '');
  }
  function closeDialog(dialog) {
    if (!dialog) return;
    if (typeof dialog.close === 'function') dialog.close(); else dialog.removeAttribute('open');
    if (!document.querySelector('dialog[open]')) document.body.classList.remove('modal-open');
    if (dialog.id === 'itemDetailModal') detailId = null;
    if (returnFocus?.isConnected && !returnFocus.closest('[hidden]')) returnFocus.focus({ preventScroll: true });
  }
  function openPicker(side) {
    if (!data || !['you', 'they'].includes(side)) return;
    pickerSide = side;
    filters.picker = { query: '', category: 'all', limit: batchSize };
    $('pickerSearchInput').value = '';
    $('pickerModalTitle').textContent = t(side === 'you' ? 'picker_you' : 'picker_they');
    updateSearchClear('picker'); renderCategories(); renderPicker();
    openDialog('itemPickerModal');
    if (window.matchMedia?.('(pointer: fine)').matches) $('pickerSearchInput').focus();
  }
  function openDetail(id) {
    if (!byId.has(id)) return;
    renderDetail(id);
    openDialog('itemDetailModal');
    detailId = id;
  }
  function renderDetail(id) {
    const item = byId.get(id);
    if (!item) return;
    const body = $('detailBody');
    body.dataset.rarity = rarityKey(item);
    const top = element('div', 'detail-top');
    const text = element('div');
    const title = element('h2', '', nameOf(item));
    title.id = 'detailName';
    const price = element('div', 'detail-price', points(item.value));
    price.append(element('span', 'detail-lc', `${number(item.lcValue)} LC`));
    const badges = element('div', 'detail-badges');
    badges.append(rarityTag(item), tierTag(item), element('span', '', t(item.rank_locked ? 'locked_order' : 'flexible_order')));
    text.append(badges, title, price, evidenceTag(item));
    const art = element('span', 'item-art detail-art');
    art.append(image(item, 135, 'detail-image'));
    top.append(art, text);
    const facts = element('dl', 'detail-facts');
    const entries = [
      ['independent_traders', number(item.observation_authors ?? 0)],
      ['quote_range', Array.isArray(item.quote_range) ? `${number(item.quote_range[0])}–${points(item.quote_range[1])}` : '—'],
      ['last_observed', item.last_observed_at ? dateText(item.last_observed_at) : t('no_observations')],
      ['price_updated', item.price_updated_at ? dateText(item.price_updated_at) : t('no_price_update')],
      ['point_reference', item.id === data.currency.anchor_id ? t('currency_note') : t(`reference_${item.reference_basis || (item.value === null ? 'unknown' : 'historical')}`)],
      ['weekly_demand', item.demandScore === null || item.demandScore === undefined ? '—' : `${number(item.demandScore, 1)} / 10`],
      ['source_position', `#${item.official_rank} · ${item.tier}`],
    ];
    for (const [key, value] of entries) { const fact = element('div', 'detail-fact'); fact.append(element('dt', '', t(key)), element('dd', '', value)); facts.append(fact); }
    const chart = element('div', 'history-block');
    chart.id = 'detailHistory';
    chart.append(element('h3', '', t('history_title')), element('p', 'history-empty', t('history_loading')));
    const actions = element('div', 'detail-actions');
    actions.append(button(t('picker_you'), 'detail-add', 'game-button', { id, side: 'you' }), button(t('picker_they'), 'detail-add', 'game-button gold-button', { id, side: 'they' }));
    if (/^https:\/\/grand-piece-online\.fandom\.com\/wiki\//.test(item.wikiUrl || '')) {
      const link = element('a', 'text-link', t('wiki_item'));
      Object.assign(link, { href: item.wikiUrl, target: '_blank', rel: 'noopener noreferrer' });
      actions.append(link);
    }
    body.replaceChildren(top, facts);
    if (/^https:\/\/grand-piece-online\.fandom\.com\/wiki\//.test(item.rarity_source || '')) {
      const source = element('a', 'rarity-source', t('rarity_source'));
      Object.assign(source, { href: item.rarity_source, target: '_blank', rel: 'noopener noreferrer' });
      body.append(source);
    }
    if (item.value === null) body.append(element('p', 'detail-note', t('unknown_note')));
    else if ((item.observation_authors || 0) < 5) body.append(element('p', 'detail-note', t('preliminary_note')));
    else if (item.constraint_applied) body.append(element('p', 'detail-note', t('rank_constraint')));
    if (!item.rank_locked) body.append(element('p', 'fine-print', t('flexible_note')));
    body.append(chart, actions);
    loadHistory(item, chart);
  }
  async function loadHistory(item, container) {
    try {
      if (!historyPromise) historyPromise = fetch('data/history.json', { cache: 'no-cache' }).then(response => { if (!response.ok) throw new Error(); return response.json(); });
      const historyData = await historyPromise;
      if (!container.isConnected) return;
      const limit = Date.parse(data.meta.updated_at_iso);
      const samples = (historyData.items?.[item.id] || []).filter(sample => Array.isArray(sample) && Number.isFinite(Date.parse(sample[0])) && Date.parse(sample[0]) <= limit && Number.isFinite(sample[1]) && sample[1] > 0).slice(-43);
      const title = element('h3', '', t('history_title'));
      container.replaceChildren(title);
      if (samples.length < 2) { container.append(element('p', 'history-empty', t('history_empty'))); return; }
      const min = Math.min(...samples.map(sample => sample[1]));
      const max = Math.max(...samples.map(sample => sample[1]));
      const svg = document.createElementNS('http://www.w3.org/2000/svg', 'svg');
      svg.setAttribute('viewBox', '0 0 600 120'); svg.classList.add('history-chart'); svg.setAttribute('role', 'img'); svg.setAttribute('aria-label', t('history_description', { name: nameOf(item) }));
      const line = document.createElementNS(svg.namespaceURI, 'polyline');
      line.setAttribute('points', samples.map((sample, i) => `${5 + i / (samples.length - 1) * 590},${max === min ? 60 : 110 - (sample[1] - min) / (max - min) * 100}`).join(' '));
      line.setAttribute('fill', 'none'); line.setAttribute('stroke', '#ffc764'); line.setAttribute('stroke-width', '2.5'); line.setAttribute('vector-effect', 'non-scaling-stroke'); svg.append(line);
      const caption = element('div', 'history-caption');
      caption.append(element('span', '', `${dateText(samples[0][0])} · ${points(min)}`), element('span', '', `${dateText(samples.at(-1)[0])} · ${points(max)}`));
      container.append(svg, caption);
    } catch {
      historyPromise = null;
      if (container.isConnected) container.replaceChildren(element('h3', '', t('history_title')), element('p', 'history-empty', t('history_error')));
    }
  }

  function updateSearchClear(scope) {
    const clear = document.querySelector(`[data-action="clear-search"][data-scope="${scope}"]`);
    if (clear) { clear.hidden = !filters[scope].query.trim(); clear.setAttribute('aria-label', t('clear_search')); }
  }
  function clearSearch(scope) {
    if (!filters[scope]) return;
    clearTimeout(searchTimers.get(scope));
    filters[scope].query = '';
    filters[scope].limit = batchSize;
    $(inputs[scope]).value = '';
    updateSearchClear(scope); renderScope(scope); writeFilters();
    $(inputs[scope]).focus();
  }
  function writeFilters(push = false) {
    const url = new URL(location.href);
    url.searchParams.set('tab', tab);
    const filter = filters[scopes[tab]];
    for (const [key, value] of Object.entries({ q: filter?.query || '', category: filter?.category === 'all' ? '' : filter?.category || '', tier: tab === 'tierlist' && tier !== 'all' ? tier : '', rarity: tab === 'tierlist' && rarity !== 'all' ? rarity : '', direction: tab === 'hourly-changes' && direction !== 'all' ? direction : '' })) {
      if (value) url.searchParams.set(key, value); else url.searchParams.delete(key);
    }
    history[push ? 'pushState' : 'replaceState'](null, '', url);
  }
  function readRoute() {
    const params = new URLSearchParams(location.search);
    tab = tabs.includes(params.get('tab')) ? params.get('tab') : 'calculator';
    if (scopes[tab]) {
      const filter = filters[scopes[tab]];
      filter.query = (params.get('q') || '').slice(0, 200);
      filter.category = categories.includes(params.get('category')) ? params.get('category') : 'all';
      filter.limit = batchSize;
      $(inputs[scopes[tab]]).value = filter.query;
      updateSearchClear(scopes[tab]);
    }
    tier = params.get('tier') || 'all';
    rarity = [...rarities, 'unknown'].includes(params.get('rarity')) ? params.get('rarity') : 'all';
    direction = ['up', 'down'].includes(params.get('direction')) ? params.get('direction') : 'all';
    showTab();
  }
  function showTab() {
    $('raritySelect').value = rarity;
    document.querySelectorAll('[data-section]').forEach(section => { section.hidden = section.dataset.section !== tab; });
    document.querySelectorAll('.main-nav [data-tab]').forEach(link => {
      const active = link.dataset.tab === tab;
      link.classList.toggle('active', active);
      if (active) link.setAttribute('aria-current', 'page'); else link.removeAttribute('aria-current');
    });
    document.querySelectorAll('[data-action="change-filter"]').forEach(node => { const active = node.dataset.direction === direction; node.classList.toggle('active', active); node.setAttribute('aria-pressed', String(active)); });
    if (data) { fillTierSelect(); renderCategories(); renderCurrent(); }
  }
  function switchTab(next, push = true) {
    if (!tabs.includes(next)) return;
    tab = next;
    writeFilters(push);
    showTab();
  }
  function translate() {
    document.documentElement.lang = lang;
    document.querySelectorAll('[data-i18n]').forEach(node => { node.textContent = t(node.dataset.i18n); });
    document.querySelectorAll('[data-placeholder]').forEach(node => { node.placeholder = t(node.dataset.placeholder); });
    $('langCode').textContent = lang.toUpperCase();
    $('audioToggleBtn').setAttribute('aria-label', t(audioEnabled ? 'sound_on' : 'sound_off'));
    $('audioToggleBtn').setAttribute('aria-pressed', String(audioEnabled));
    $('audioToggleBtn').replaceChildren(icon(audioEnabled ? 'volume-2' : 'volume-x'));
    document.documentElement.dataset.effects = effectsEnabled ? 'on' : 'off';
    $('effectsToggleBtn').setAttribute('aria-pressed', String(effectsEnabled));
    $('effectsToggleBtn').setAttribute('aria-label', t(effectsEnabled ? 'effects_pause' : 'effects_resume'));
    $('effectsToggleBtn').title = t(effectsEnabled ? 'effects_pause' : 'effects_resume');
    document.querySelectorAll('[data-action="close-dialog"]').forEach(node => node.setAttribute('aria-label', t('close')));
    $('hourlySubTabUp').setAttribute('aria-label', t('increases'));
    $('hourlySubTabDown').setAttribute('aria-label', t('decreases'));
    Object.keys(inputs).forEach(updateSearchClear);
    if (data) { renderSource(); renderCategories(); fillTierSelect(); renderTrade(); renderCurrent(); }
    if (detailId && $('itemDetailModal').open) renderDetail(detailId);
  }
  async function share(discord = false) {
    saveTrade();
    let text = location.href;
    if (discord) {
      const describe = side => trade[side].map(entry => `${nameOf(byId.get(entry.id) || { name: t('unavailable_item') })} ×${entry.qty}`).join(', ') || '—';
      text = `GPO Values\n${t('export_you')}: ${describe('you')} — ${points(sideTotal('you').value)}\n${t('export_they')}: ${describe('they')} — ${points(sideTotal('they').value)}\n${t('export_note', { time: dateText(data.meta.updated_at_iso) })}\n${location.href}`;
    }
    try { await navigator.clipboard.writeText(text); toast(t('copied')); }
    catch { $('shareText').value = text; openDialog('shareModal'); $('shareText').focus(); $('shareText').select(); }
  }

  function bindEvents() {
    document.addEventListener('click', event => {
      const link = event.target.closest('a[data-tab]');
      if (link && !event.ctrlKey && !event.metaKey && !event.shiftKey && event.button === 0) { event.preventDefault(); switchTab(link.dataset.tab); return; }
      const node = event.target.closest('[data-action]');
      if (!node || node.disabled) return;
      const { action, side, id, scope } = node.dataset;
      if (action === 'add') addItem(side, id);
      else if (action === 'remove') removeItem(side, id);
      else if (action === 'quantity-step') changeQuantity(side, id, Number(node.dataset.delta));
      else if (action === 'picker') openPicker(side);
      else if (action === 'detail') openDetail(id);
      else if (action === 'pick') { addItem(pickerSide, id); closeDialog($('itemPickerModal')); }
      else if (action === 'detail-add') { addItem(side, id); closeDialog($('itemDetailModal')); switchTab('calculator'); }
      else if (action === 'close-dialog') closeDialog(node.closest('dialog'));
      else if (action === 'swap') { [trade.you, trade.they] = [trade.they, trade.you]; renderTrade(); saveTrade(); toast(t('swapped')); }
      else if (action === 'clear') { undoTrade = structuredClone(trade); trade = { you: [], they: [] }; renderTrade(); saveTrade(); toast(t('cleared'), true); sound('remove'); }
      else if (action === 'undo' && undoTrade) { trade = undoTrade; undoTrade = null; renderTrade(); saveTrade(); node.closest('.gpo-toast')?.remove(); }
      else if (action === 'dismiss-toast') node.closest('.gpo-toast')?.remove();
      else if (action === 'share') share();
      else if (action === 'export') share(true);
      else if (action === 'refresh') loadSnapshot();
      else if (action === 'apply-update' && pendingData) applySnapshot(pendingData);
      else if (action === 'language') { lang = lang === 'en' ? 'ru' : 'en'; store('gpo_lang', lang); const url = new URL(location.href); url.searchParams.set('lang', lang); history.replaceState(null, '', url); translate(); }
      else if (action === 'audio') { audioEnabled = !audioEnabled; store('gpo_audio', String(audioEnabled)); translate(); if (audioEnabled) sound('click'); }
      else if (action === 'effects') { effectsEnabled = !effectsEnabled; store('gpo_effects', String(effectsEnabled)); translate(); }
      else if (action === 'clear-search') clearSearch(scope);
      else if (action === 'category') { filters[scope].category = node.dataset.category; filters[scope].limit = batchSize; renderCategories(); renderScope(scope); if (scope !== 'picker') writeFilters(); }
      else if (action === 'more') { const start = filters[scope].limit; filters[scope].limit += batchSize; renderScope(scope, start); }
      else if (action === 'timeframe') { timeframe = node.dataset.tf; filters.market.limit = batchSize; document.querySelectorAll('[data-action="timeframe"]').forEach(button => { const active = button.dataset.tf === timeframe; button.classList.toggle('active', active); button.setAttribute('aria-pressed', String(active)); }); renderMarket(); }
      else if (action === 'change-filter') { direction = node.dataset.direction; filters.changes.limit = batchSize; writeFilters(); showTab(); }
    });
    document.addEventListener('input', event => {
      const scope = event.target.dataset.search;
      if (!filters[scope]) return;
      filters[scope].query = event.target.value.slice(0, 200);
      filters[scope].limit = batchSize;
      updateSearchClear(scope);
      if (scope !== 'picker') writeFilters();
      clearTimeout(searchTimers.get(scope));
      searchTimers.set(scope, setTimeout(() => renderScope(scope), 90));
    });
    document.addEventListener('change', event => {
      if (event.target.classList.contains('qty-num')) setQuantity(event.target.dataset.side, event.target.dataset.id, Number(event.target.value));
      if (event.target.id === 'tierSelect') { tier = event.target.value; filters.catalog.limit = batchSize; renderCatalog('catalog'); writeFilters(); }
      if (event.target.id === 'raritySelect') { rarity = event.target.value; filters.catalog.limit = batchSize; renderCatalog('catalog'); writeFilters(); }
    });
    document.querySelectorAll('dialog').forEach(dialog => {
      dialog.addEventListener('click', event => { if (event.target === dialog) closeDialog(dialog); });
      dialog.addEventListener('close', () => { if (!document.querySelector('dialog[open]')) document.body.classList.remove('modal-open'); });
    });
    document.addEventListener('keydown', event => {
      const dialog = document.querySelector('dialog[open]');
      if (event.key === 'Escape' && dialog) { event.preventDefault(); closeDialog(dialog); }
      if (event.key === 'Tab' && dialog) {
        const focusable = [...dialog.querySelectorAll('button:not(:disabled):not([hidden]), input, textarea, a[href]')].filter(node => !node.closest('[hidden]'));
        const first = focusable[0], last = focusable.at(-1);
        if (event.shiftKey && document.activeElement === first) { event.preventDefault(); last?.focus(); }
        else if (!event.shiftKey && document.activeElement === last) { event.preventDefault(); first?.focus(); }
      }
      if (event.key === '/' && !dialog && !event.target.matches('input,textarea,select,[contenteditable]') && scopes[tab]) { event.preventDefault(); $(inputs[scopes[tab]]).focus(); }
    });
    window.addEventListener('popstate', () => { readRoute(); restoreTrade(); });
    window.addEventListener('hashchange', restoreTrade);
    document.addEventListener('visibilitychange', () => { if (document.visibilityState === 'visible' && Date.now() - lastCheck > 60000) loadSnapshot(false); });
  }

  function init() {
    decorateIcons();
    translate();
    bindEvents();
    readRoute();
    loadSnapshot();
  }
  window.GPO_APP = {
    quickAdd: addItem, removeItem, changeQty: changeQuantity, openDetail, openPicker,
    renderHourlyChanges: renderChanges,
  };
  window.clearSearchInput = inputId => { const scope = Object.keys(inputs).find(key => inputs[key] === inputId); if (scope) clearSearch(scope); };
  if (document.readyState === 'loading') document.addEventListener('DOMContentLoaded', init, { once: true });
  else init();
})();
