/**
 * Local Daily Runner for GPO Tier List Sync Bot
 * 
 * Usage:
 *   node run_bot.js
 * 
 * Runs a sync immediately upon start, and then repeats automatically
 * every 24 hours (86,400,000 ms).
 */

const { syncTierList } = require('./sync_tierlist.js');

const CHECK_INTERVAL_MS = 24 * 60 * 60 * 1000; // 24 hours

console.log('🤖 GPO Tier List Sync Bot started!');
console.log(`⏰ Check interval set to 24 hours (${CHECK_INTERVAL_MS} ms).`);

async function runCycle() {
  const timestamp = new Date().toLocaleString();
  console.log(`\n======================================================`);
  console.log(`[${timestamp}] 🔄 Starting scheduled tier list check...`);
  try {
    const result = await syncTierList();
    console.log(`[${timestamp}] ✅ Check finished successfully. Status:`, result);
  } catch (err) {
    console.error(`[${timestamp}] ❌ Error during sync:`, err.message);
  }
  console.log(`======================================================\n`);
}

// Run immediately on start
runCycle();

// Repeat every 24 hours
setInterval(runCycle, CHECK_INTERVAL_MS);
