/**
 * GPO VALUES - OFFICIAL TIER LIST AUTO-SYNC ENGINE & BOT
 * 
 * Fetches the official Grand Piece Online trading tier list Google Doc,
 * compares for changes, and automatically updates the database, values,
 * and date badges while preserving 100% accurate economy rules:
 * - SP Reset Essence = 1 point
 * - 1 LC = 233 points
 * - Candy Cane + top items boost = +15,000 points
 * - Demand score & metadata preservation
 */

const fs = require('fs');
const https = require('https');
const path = require('path');

const DOC_URL = 'https://docs.google.com/document/d/1pmF1jHksUPuQ95OMWnf7doaq8566Sba1VbhPWQtpiY4/preview';

// Helper to download URL content using native HTTPS
function fetchUrl(url) {
  return new Promise((resolve, reject) => {
    https.get(url, { headers: { 'User-Agent': 'Mozilla/5.0' } }, (res) => {
      if (res.statusCode >= 300 && res.statusCode < 400 && res.headers.location) {
        return resolve(fetchUrl(res.headers.location));
      }
      if (res.statusCode !== 200) {
        return reject(new Error(`HTTP ${res.statusCode}: ${res.statusMessage}`));
      }
      let data = '';
      res.on('data', chunk => { data += chunk; });
      res.on('end', () => resolve(data));
    }).on('error', reject);
  });
}

// Base value ranges for tiers matching GPO market economy (where 1 LC ≈ 2,800 pts unscaled)
const tierBaseValues = {
  "Exclusive": {
    "default": { base: 30000000, step: 6000000 },
    "Standard": { base: 30000000, step: 6000000 }
  },
  "Tier SS": {
    "High": { base: 8500000, step: 900000 },
    "Mid": { base: 4500000, step: 600000 },
    "Low": { base: 2500000, step: 300000 },
    "default": { base: 5000000, step: 600000 },
    "Standard": { base: 5000000, step: 600000 }
  },
  "Tier S": {
    "High": { base: 1600000, step: 140000 },
    "Mid": { base: 750000, step: 50000 },
    "Low": { base: 450000, step: 25000 },
    "default": { base: 600000, step: 40000 },
    "Standard": { base: 600000, step: 40000 }
  },
  "Tier A+": {
    "High": { base: 260000, step: 18000 },
    "Mid": { base: 160000, step: 8000 },
    "Low": { base: 75000, step: 4000 },
    "default": { base: 140000, step: 7000 },
    "Standard": { base: 140000, step: 7000 }
  },
  "Tier A": {
    "High": { base: 56000, step: 2200 },
    "Mid": { base: 24000, step: 1800 },
    "Low": { base: 16000, step: 1000 },
    "default": { base: 32000, step: 1800 },
    "Standard": { base: 32000, step: 1800 }
  },
  "Tier A-": {
    "High": { base: 14000, step: 700 },
    "Mid": { base: 10500, step: 450 },
    "Low": { base: 7800, step: 180 },
    "default": { base: 9000, step: 250 },
    "Standard": { base: 9000, step: 250 }
  },
  "Tier B+": {
    "High": { base: 4600, step: 110 },
    "Mid": { base: 2000, step: 50 },
    "Low": { base: 1650, step: 40 },
    "default": { base: 2800, step: 70 },
    "Standard": { base: 2800, step: 70 }
  },
  "Tier B": {
    "High": { base: 750, step: 30 },
    "Mid": { base: 530, step: 25 },
    "Low": { base: 410, step: 15 },
    "default": { base: 550, step: 20 },
    "Standard": { base: 550, step: 20 }
  },
  "Tier B-": {
    "High": { base: 300, step: 10 },
    "Mid": { base: 240, step: 8 },
    "Low": { base: 160, step: 5 },
    "default": { base: 210, step: 6 },
    "Standard": { base: 210, step: 6 }
  },
  "Tier C": {
    "High": { base: 110, step: 5 },
    "Mid": { base: 80, step: 4 },
    "Low": { base: 50, step: 3 },
    "default": { base: 75, step: 4 },
    "Standard": { base: 75, step: 4 }
  },
  "Tier F": {
    "default": { base: 15, step: 3 },
    "Standard": { base: 15, step: 3 }
  },
  "Very Unstable": {
    "default": { base: 1500000, step: 140000 },
    "Standard": { base: 1500000, step: 140000 }
  },
  "New Items": {
    "default": { base: 25000, step: 2500 },
    "Standard": { base: 25000, step: 2500 }
  }
};

function normalizeName(str) {
  let s = (str || '')
    .replace(/✦[^\s]+/g, '')
    .replace(/✦/g, '')
    .replace(/\([^\)]*(?:permanent|notifier|rates)[^\)]*\)/gi, '')
    .replace(/['']/g, "'");

  return s
    .toLowerCase()
    .replace(/[^a-z0-9]/g, ' ')
    .trim()
    .replace(/\s+/g, ' ');
}

function parseTierDoc(fullText) {
  const lines = fullText.split('\n');
  const tiers = [];
  let currentTier = null;
  let currentSubtier = null;
  let items = [];

  for (let i = 0; i < lines.length; i++) {
    const rawLine = lines[i].trim();
    if (!rawLine || rawLine === '-' || rawLine === '*' || rawLine === '**') continue;

    if (rawLine.startsWith('⚜') || rawLine.includes('⚜ Tier') || rawLine.includes('⚜ Exclusive') || rawLine.includes('⚜ Very Unstable') || rawLine.includes('⚜ Unobtainable')) {
      if (currentTier) {
        tiers.push({
          tierName: currentTier,
          items: [...items]
        });
        items = [];
      }
      currentTier = rawLine.replace(/⚜/g, '').trim();
      currentSubtier = 'Standard';
      continue;
    }

    if (rawLine.includes('◈ High Tier ◈') || rawLine.startsWith('◈ High')) {
      currentSubtier = 'High';
      continue;
    } else if (rawLine.includes('◈ Mid Tier ◈') || rawLine.startsWith('◈ Mid')) {
      currentSubtier = 'Mid';
      continue;
    } else if (rawLine.includes('◈ Low Tier ◈') || rawLine.startsWith('◈ Low')) {
      currentSubtier = 'Low';
      continue;
    }

    if (rawLine.includes('*') || rawLine.includes('✦')) {
      const parts = rawLine.split('*').map(p => p.trim()).filter(Boolean);
      parts.forEach(part => {
        if (!part || part === 'High' || part === 'Mid' || part === 'Low') return;
        items.push({
          tier: currentTier || 'Unknown',
          subTier: currentSubtier || 'Standard',
          rawName: part
        });
      });
    }
  }

  if (currentTier && items.length > 0) {
    tiers.push({
      tierName: currentTier,
      items: [...items]
    });
  }

  return tiers;
}

async function syncTierList() {
  console.log(`[${new Date().toISOString()}] 🔍 Fetching official GPO tier list from Google Docs...`);
  
  const html = await fetchUrl(DOC_URL);
  
  // Extract "Last Time Update" date
  const dateMatch = html.match(/Last Time Update:\s*(\d{1,2}\/\d{1,2}\/\d{4})/i);
  const docDate = dateMatch ? dateMatch[1] : null;
  console.log(`📅 Official Doc Update Date: ${docDate || 'Unknown'}`);

  // Extract model chunk texts
  const textParts = [];
  const regex = /"ty":"is","ibi":(\d+),"s":"((?:[^"\\]|\\.)*)"/g;
  let m;
  while ((m = regex.exec(html)) !== null) {
    const ibi = parseInt(m[1], 10);
    let str = m[2];
    try {
      str = JSON.parse('"' + str + '"');
    } catch (e) {
      str = str.replace(/\\n/g, '\n').replace(/\\"/g, '"');
    }
    textParts.push({ ibi, text: str });
  }

  textParts.sort((a, b) => a.ibi - b.ibi);
  const fullDocText = textParts.map(p => p.text).join('\n');

  if (fullDocText.length < 1000) {
    throw new Error('Fetched document text is too short or empty!');
  }

  const structure = parseTierDoc(fullDocText);
  let totalDocItems = 0;
  structure.forEach(t => { totalDocItems += t.items.length; });
  console.log(`✅ Parsed ${structure.length} tiers and ${totalDocItems} items from doc.`);

  // Load existing items
  const localDbPath = path.join(__dirname, 'gpo_items.json');
  if (!fs.existsSync(localDbPath)) {
    throw new Error(`gpo_items.json not found at ${localDbPath}`);
  }
  const existingItems = JSON.parse(fs.readFileSync(localDbPath, 'utf8'));

  // Flatten new structure
  const newItemsList = [];
  structure.forEach(t => {
    const subtierCounts = {};
    t.items.forEach((it, idx) => {
      const subtier = it.subTier || 'Standard';
      if (!subtierCounts[subtier]) subtierCounts[subtier] = 0;
      const subIdx = subtierCounts[subtier];
      subtierCounts[subtier]++;

      newItemsList.push({
        tier: t.tierName,
        subTier: subtier,
        rankInTier: idx + 1,
        rankInSubTier: subIdx,
        rawName: it.rawName,
        normName: normalizeName(it.rawName)
      });
    });
  });

  // Calculate unscaled base values
  newItemsList.forEach(item => {
    const tierConfig = tierBaseValues[item.tier];
    const subConfig = tierConfig ? (tierConfig[item.subTier] || tierConfig["default"] || tierConfig["Standard"]) : { base: 100, step: 5 };
    item.unscaledVal = Math.max(1, subConfig.base - (item.rankInSubTier * subConfig.step));
  });

  // Match items with existing database
  const usedExistingIds = new Set();
  const matches = [];

  // Pass 1: exact normalized match
  newItemsList.forEach((newItem, newIdx) => {
    const exactMatch = existingItems.find(ex => !usedExistingIds.has(ex.id) && normalizeName(ex.name) === newItem.normName);
    if (exactMatch) {
      usedExistingIds.add(exactMatch.id);
      matches[newIdx] = { newItem, existing: exactMatch };
    }
  });

  // Pass 2: fuzzy containment match
  newItemsList.forEach((newItem, newIdx) => {
    if (matches[newIdx]) return;
    const fuzzyMatch = existingItems.find(ex => {
      if (usedExistingIds.has(ex.id)) return false;
      const exNorm = normalizeName(ex.name);
      return exNorm.includes(newItem.normName) || newItem.normName.includes(exNorm);
    });
    if (fuzzyMatch) {
      usedExistingIds.add(fuzzyMatch.id);
      matches[newIdx] = { newItem, existing: fuzzyMatch };
    }
  });

  const matchedCount = matches.filter(Boolean).length;
  console.log(`🔗 Matched items: ${matchedCount} / ${newItemsList.length}`);

  if (matchedCount < existingItems.length * 0.9) {
    console.warn(`⚠️ Warning: Only matched ${matchedCount} items. Skipping write to prevent corrupt data.`);
    return false;
  }

  // Find Candy Cane index
  const ccIdx = matches.findIndex(m => m && m.existing && m.existing.name === 'Candy Cane');

  // Build final updated items
  const finalItems = matches.map((m, idx) => {
    const orig = m.existing;
    const nw = m.newItem;

    let val;
    if (orig.name === 'SP Reset Essence') {
      val = 1;
    } else {
      const base = nw.unscaledVal >= 120 ? Math.round(nw.unscaledVal / 12) : +(nw.unscaledVal / 12).toFixed(1);
      if (ccIdx !== -1 && idx <= ccIdx) {
        val = base + 15000;
      } else {
        val = base;
      }
    }

    let lcVal = +(val / 233.33).toFixed(2);
    if (val === 1) lcVal = 0.00;

    let demandText = orig.demand;
    if (nw.tier === 'Very Unstable') {
      demandText = 'Unstable';
    } else if (orig.demandScore >= 9.2) {
      demandText = 'Extremely High';
    } else if (orig.demandScore >= 7.5) {
      demandText = 'High';
    } else if (orig.demandScore >= 5.5) {
      demandText = 'Medium';
    } else {
      demandText = 'Low';
    }

    return {
      id: orig.id,
      name: orig.name,
      nameRu: orig.nameRu,
      abbreviation: orig.abbreviation,
      tier: nw.tier,
      subTier: nw.subTier,
      rankInTier: nw.rankInTier,
      value: val,
      lcValue: lcVal,
      demand: demandText,
      trend: orig.trend || 'Stable',
      category: orig.category,
      image: orig.image,
      wikiUrl: orig.wikiUrl,
      demandScore: orig.demandScore !== undefined ? orig.demandScore : 7.0
    };
  });

  // Check if anything actually changed compared to current JSON
  const currentJson = JSON.stringify(existingItems);
  const updatedJson = JSON.stringify(finalItems);
  const hasDataChanges = currentJson !== updatedJson;

  // Paths to update
  const targetDirs = [
    __dirname,
    'D:/gag/gpovalues'
  ].filter(d => fs.existsSync(d));

  targetDirs.forEach(dir => {
    fs.writeFileSync(path.join(dir, 'gpo_items.json'), JSON.stringify(finalItems, null, 2) + '\n', 'utf8');
    fs.writeFileSync(path.join(dir, 'items_data.js'), `window.GPO_ITEMS = ${JSON.stringify(finalItems, null, 2)};\n`, 'utf8');

    // Update date badges in index.html & app.js if docDate is known
    if (docDate) {
      const indexHtmlPath = path.join(dir, 'index.html');
      if (fs.existsSync(indexHtmlPath)) {
        let idxHtml = fs.readFileSync(indexHtmlPath, 'utf8');
        idxHtml = idxHtml.replace(/📅 Updated:\s*\d{1,2}\/\d{1,2}\/\d{4}/g, `📅 Updated: ${docDate}`);
        fs.writeFileSync(indexHtmlPath, idxHtml, 'utf8');
      }

      const appJsPath = path.join(dir, 'app.js');
      if (fs.existsSync(appJsPath)) {
        let appContent = fs.readFileSync(appJsPath, 'utf8');
        appContent = appContent.replace(/badge_updated:\s*"📅 Updated:\s*[^"]+"/g, `badge_updated: "📅 Updated: ${docDate}"`);
        appContent = appContent.replace(/badge_updated:\s*"📅 Обновление:\s*[^"]+"/g, `badge_updated: "📅 Обновление: ${docDate}"`);
        fs.writeFileSync(appJsPath, appContent, 'utf8');
      }
    }
  });

  console.log(`🎉 Sync completed! Data changes detected: ${hasDataChanges ? 'YES' : 'NO'}`);
  return { hasChanges: hasDataChanges, docDate };
}

if (require.main === module) {
  syncTierList()
    .then(res => {
      console.log('Result:', res);
      process.exit(0);
    })
    .catch(err => {
      console.error('Sync failed:', err);
      process.exit(1);
    });
}

module.exports = { syncTierList };
