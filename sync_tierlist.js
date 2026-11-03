/** Import the official order. This script never invents market prices. */
const fs = require('fs');
const path = require('path');
const crypto = require('crypto');

const DOC_URL = 'https://docs.google.com/document/d/1pmF1jHksUPuQ95OMWnf7doaq8566Sba1VbhPWQtpiY4/preview';
const TIERS = ['Exclusive', 'Tier SS', 'Tier S', 'Tier A+', 'Tier A', 'Tier A-',
  'Tier B+', 'Tier B', 'Tier B-', 'Tier C', 'Tier F', 'Very Unstable', 'New Items'];
const FLEXIBLE = new Set(['Very Unstable', 'New Items']);
const RARITIES = new Set(['Common', 'Uncommon', 'Rare', 'Epic', 'Legendary', 'Mythical', 'Collectable', 'Rare Chroma', 'Legendary Chroma']);
const WIKI_BASE = 'https://grand-piece-online.fandom.com/wiki/';

function wikiLink(title) {
  const url = new URL(title, WIKI_BASE);
  if (url.origin !== 'https://grand-piece-online.fandom.com' || !url.pathname.startsWith('/wiki/')) {
    throw new Error(`Invalid wiki source: ${title}`);
  }
  return url.href;
}

function withRarity(item, rarities) {
  const verified = rarities[item.id];
  const rarity = verified ? verified.rarity : item.rarity ?? null;
  if (rarity !== null && !RARITIES.has(rarity)) throw new Error(`Invalid game rarity: ${item.name}`);
  const wikiUrl = verified?.wiki ? wikiLink(verified.wiki) : item.wikiUrl;
  const rarity_source = verified?.source ? wikiLink(verified.source) : verified?.wiki ? wikiUrl : item.rarity_source || null;
  return { ...item, rarity, wikiUrl, rarity_source };
}

async function fetchUrl(url) {
  const response = await fetch(url, { signal: AbortSignal.timeout(30000) });
  if (!response.ok) throw new Error(`Official document: HTTP ${response.status}`);
  return response.text();
}

function documentText(html) {
  const parts = new Map();
  for (const match of html.matchAll(/"ty":"is","ibi":(\d+),"s":"((?:[^"\\]|\\.)*)"/g)) {
    const position = Number(match[1]);
    if (!parts.has(position)) parts.set(position, JSON.parse(`"${match[2]}"`));
  }
  return [...parts].sort((a, b) => a[0] - b[0]).map(entry => entry[1]).join('\n');
}

function normalizeName(name) {
  return name.replace(/✦.*$/u, '').normalize('NFKC').toLowerCase()
    .replace(/[’‘`']/g, '').replace(/[^\p{L}\p{N}]+/gu, ' ').trim();
}

function parseTierDoc(text) {
  const items = [];
  let tier = null;
  let subTier = 'Standard';
  let rank = 0;
  for (const line of text.replace(/[\v\f]/g, '\n').split('\n')) {
    const raw = line.trim();
    if (raw.startsWith('⚜')) {
      tier = raw.replace(/⚜/g, '').trim();
      if (!TIERS.includes(tier)) throw new Error(`Unknown official tier: ${tier}`);
      subTier = 'Standard';
      rank = 0;
    } else if (/^◈\s*(High|Mid|Low)/.test(raw)) {
      subTier = raw.match(/^◈\s*(High|Mid|Low)/)[1];
    } else if (tier && raw.startsWith('*')) {
      for (const part of raw.split('*')) {
        const name = part.replace(/✦.*$/u, '').trim();
        if (!name) continue;
        items.push({ name, tier, subTier, rankInTier: ++rank, official_rank: items.length + 1 });
      }
    }
  }
  return items;
}

const NEW_METADATA = {
  'Verity': ['weapons', 'Верити'],
  'Traveling Merchant Snail Phone': ['misc', 'Улиткофон странствующего торговца'],
  'Moonreaver': ['weapons', 'Лунный Жнец'],
  'Blood Chains (Left Arm)': ['accessories', 'Кровавые цепи (левая рука)'],
  'Blood Chains (Right Arm)': ['accessories', 'Кровавые цепи (правая рука)'],
  'Blood Chains (Neck)': ['accessories', 'Кровавые цепи (шея)'],
  "Resurrected Ba'al's Outfit 3.0": ['outfits', 'Костюм возрождённого Баала 3.0'],
  "Resurrected Ba'al's Head 3.0": ['accessories', 'Голова возрождённого Баала 3.0'],
  'Horns of Salvation': ['accessories', 'Рога спасения'],
  'All Seeing Nightfall': ['misc', 'Всевидящая Ночь'],
  'Prestige Eclipse Moonreaver': ['weapons', 'Престижный Лунный Жнец Затмения'],
};

function buildCatalog(text, previous, rarities = {}) {
  const parsed = parseTierDoc(text);
  const oldItems = Array.isArray(previous) ? previous : previous.items;
  const retired = Array.isArray(previous.retired_items) ? previous.retired_items : [];
  const oldByName = new Map([...retired, ...oldItems].map(item => [normalizeName(item.name), item]));
  const names = new Set(parsed.map(item => normalizeName(item.name)));
  if (names.size !== parsed.length) throw new Error('Duplicate names in official document');
  if (!names.has('sp reset essence') || !names.has('legendary fruit chest')) {
    throw new Error('Incomplete official document: missing currency anchors');
  }
  // A truncated Google response must not retire most of the known catalogue.
  const coverage = oldItems.filter(item => names.has(normalizeName(item.name))).length;
  if (parsed.length < 150 || (oldItems.length && coverage / oldItems.length < 0.85)) {
    throw new Error(`Incomplete official document: coverage ${coverage}/${oldItems.length}`);
  }
  const ids = new Set();
  const items = parsed.map(record => {
    const old = oldByName.get(normalizeName(record.name)) || {};
    const id = old.id || `item_${normalizeName(record.name).replace(/ /g, '_')}`;
    if (ids.has(id)) throw new Error(`Ambiguous official item: ${record.name}`);
    ids.add(id);
    const metadata = NEW_METADATA[record.name] || ['misc', record.name];
    const seed = old.seed_value ?? old.value;
    return withRarity({
      id, ...record,
      nameRu: old.nameRu || metadata[1],
      abbreviation: old.abbreviation || '',
      category: old.category || metadata[0],
      image: fs.existsSync(path.join(__dirname, 'images/items', `${id}.webp`)) ? `images/items/${id}.webp` :
        old.image && fs.existsSync(path.join(__dirname, old.image)) ? old.image : 'images/placeholder.svg',
      wikiUrl: old.wikiUrl || `${WIKI_BASE}${encodeURIComponent(record.name.replace(/ /g, '_'))}`,
      rarity: old.rarity,
      rarity_source: old.rarity_source,
      rank_locked: !FLEXIBLE.has(record.tier),
      seed_value: Number.isFinite(seed) && seed > 0 ? seed : null,
      unit_id: id,
      unit_quantity: 1,
    }, rarities);
  });
  const byName = new Map(items.map(item => [normalizeName(item.name), item]));
  for (const item of items) {
    const pack = item.name.match(/^(\d+)x\s+(.+)$/i);
    if (pack) {
      const single = byName.get(normalizeName(pack[2]));
      item.unit_id = single ? single.id : item.id;
      item.unit_quantity = Number(pack[1]);
      // The old database gave single chests and packs identical Russian names.
      if (single) item.nameRu = `${item.unit_quantity} × ${single.nameRu}`;
    }
    if (item.name === 'SP Reset Essence') item.seed_value = 1;
    if (item.name === 'Anomalized Mega-Pow') {
      item.wikiUrl = 'https://grand-piece-online.fandom.com/wiki/Anomalized_Mega-Pow';
    }
  }
  const revision = crypto.createHash('sha256').update(JSON.stringify(parsed)).digest('hex').slice(0, 16);
  return {
    schema_version: 1,
    source: {
      url: DOC_URL, revision,
      updated_label: text.match(/Last Time Update:\s*(\d{1,2}\/\d{1,2}\/\d{4})/i)?.[1] || null,
      checked_at: new Date().toISOString(),
    },
    items,
    retired_items: [...oldByName.values()].filter(item => !ids.has(item.id)),
  };
}

async function syncTierList() {
  const catalogPath = path.join(__dirname, 'data', 'catalog.json');
  const checkpointPath = path.join(__dirname, '.state', 'catalog.json');
  const previousPath = fs.existsSync(checkpointPath) ? checkpointPath : catalogPath;
  const previous = JSON.parse(fs.readFileSync(previousPath, 'utf8'));
  const rarityPath = path.join(__dirname, 'data', 'rarities.json');
  const rarities = fs.existsSync(rarityPath) ? JSON.parse(fs.readFileSync(rarityPath, 'utf8')).items : {};
  // Reviewed Wiki metadata stays available even when Google cannot refresh the order.
  previous.items = previous.items.map(item => withRarity(item, rarities));
  fs.writeFileSync(`${catalogPath}.tmp`, JSON.stringify(previous) + '\n', 'utf8');
  fs.renameSync(`${catalogPath}.tmp`, catalogPath);
  const html = await fetchUrl(DOC_URL);
  const text = documentText(html);
  const catalog = buildCatalog(text, previous, rarities);
  fs.mkdirSync(path.dirname(catalogPath), { recursive: true });
  fs.writeFileSync(`${catalogPath}.tmp`, JSON.stringify(catalog, null, 2) + '\n', 'utf8');
  fs.renameSync(`${catalogPath}.tmp`, catalogPath);
  console.log(`Official catalogue: ${catalog.items.length} items, revision ${catalog.source.revision}`);
  return { hasChanges: catalog.source.revision !== previous.source?.revision, count: catalog.items.length };
}

if (require.main === module) {
  syncTierList().catch(error => { console.error(error.message); process.exitCode = 1; });
}

module.exports = { syncTierList, buildCatalog, parseTierDoc, normalizeName, documentText };
