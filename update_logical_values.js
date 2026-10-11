const fs = require('fs');

const itemsPath = 'gpo_items.json';
const items = JSON.parse(fs.readFileSync(itemsPath, 'utf8'));

// 1. Precise, logical adjustments for Chests and Stackable items
items.forEach(it => {
  // Legendary Chests (Standard GPO baseline: 1 LC = 2,800 pts)
  if (it.id === 'item_102' || it.name === 'Legendary Fruit Chest') {
    it.value = 2800;
    it.lcValue = 1.00;
  }
  if (it.id === 'item_60' || it.name === '10x Legendary Fruit Chest') {
    it.value = 28000;
    it.lcValue = 10.00;
  }

  // Rare Chests (Logical 10x ratio and realistic GPO valuation: ~0.085 LC / 240 pts)
  if (it.id === 'item_208' || it.name === 'Rare Fruit Chest') {
    it.value = 240;
    it.lcValue = 0.09;
    it.demand = 'Low';
  }
  if (it.id === 'item_207' || it.name === '10x Rare Fruit Chest') {
    it.value = 2400;
    it.lcValue = 0.86;
    it.demand = 'Medium';
  }

  // Mythical Chests (1 MC = ~12 LC, 10 MC = ~120 LC)
  if (it.id === 'item_58' || it.name === 'Mythical Fruit Chest') {
    it.value = 34000;
    it.lcValue = 12.14;
  }
  if (it.id === 'item_26' || it.name.includes('10x') && it.name.includes('Mythical Fruit Chest')) {
    it.value = 340000;
    it.lcValue = 121.43;
  }

  // New Items & Event items with realistic GPO trade values
  if (it.id === 'item_205' || it.name === 'Festival Lancer') {
    it.value = 7000;
    it.lcValue = 2.50;
    it.category = 'weapons';
  }
  if (it.id === 'item_206' || it.name === 'Hunter’s Journal') {
    it.value = 4200;
    it.lcValue = 1.50;
    it.category = 'misc';
  }
  if (it.id === 'item_209' || it.name === 'Love Shades') {
    it.value = 840;
    it.lcValue = 0.30;
    it.category = 'accessories';
  }
  if (it.id === 'item_210' || it.name === 'Love Boppers Headband') {
    it.value = 700;
    it.lcValue = 0.25;
    it.category = 'accessories';
  }
  if (it.id === 'item_211' || it.name === 'Coffin Boat') {
    it.value = 2800;
    it.lcValue = 1.00;
    it.category = 'boats';
  }
  if (it.id === 'item_212' || it.name === 'Striker') {
    it.value = 2240;
    it.lcValue = 0.80;
    it.category = 'boats';
  }
  if (it.id === 'item_213' || it.name === 'Hoverboard') {
    it.value = 1960;
    it.lcValue = 0.70;
    it.category = 'boats';
  }

  // Fix misassigned categories
  if (it.name === "Leo's Inferno Hagoromo") it.category = 'accessories';
  if (it.name === 'Yukio The Bunny') it.category = 'accessories';
  if (it.name === 'Festival Shield') it.category = 'accessories';
  if (it.name === 'Mochi Trident') it.category = 'weapons';
  if (it.name === 'Mochi Emperor’s Scarf') it.category = 'accessories';
  if (it.name === 'Emerald Valkyrie') it.category = 'accessories';

  // Ensure lcValue is always rounded to 2 decimal places
  it.lcValue = +(it.value / 2800).toFixed(2);
});

// Save updated gpo_items.json
fs.writeFileSync(itemsPath, JSON.stringify(items, null, 2));

// Update items_data.js
const jsContent = `// Official Grand Piece Online Trading Database
// Synchronized with Official GPO Tier List & In-Game Economy
window.GPO_ITEMS = ${JSON.stringify(items, null, 2)};
`;
fs.writeFileSync('items_data.js', jsContent);

console.log('Successfully updated gpo_items.json and items_data.js with logical values and categories!');
