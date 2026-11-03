# GPO Values & Trade Calculator

A community trading companion for [Grand Piece Online](https://www.roblox.com/games/1730877806/Grand-Piece-Online): compare offers, browse the official item order, and see the evidence behind estimated values.

## Features
- GPO Wiki silhouettes, torn rarity frames, Finger Paint lettering, English/Russian localization, and layouts down to 320px.
- Two-sided calculator with quantities, point/LC totals, swap, undo, shareable URLs, and Discord text export.
- Search by name or abbreviation, category/tier/rarity filters, item details with source links, and recorded price history.
- Changes includes an icon-only **Read trades · 1h** feed with quantities, a 👉 separator, and the price engine's processing decision for each offer.
- Market activity over 1 hour, 24 hours, and 7 days; recorded changes are separate from estimates.
- Local WebP images and fonts, lazy item rendering, keyboard-accessible dialogs, and optional sound. Ads are disabled in `site_config.js` by default.
- Animated rarity gradients use the Wiki's colour stops, including Chroma variants. The sparkle control pauses effects; reduced-motion preferences are respected.

## Game Rarities

Game rarity is separate from a trading tier and never changes the official price order. `data/rarities.json` contains reviewed Wiki metadata, keyed by stable item ID, with an item page and, where different, the evidence page. Official catalogue sync reapplies these records even when restoring an older collector checkpoint.

On 3 November 2026, 219 of the 224 listed items have a supported rarity. Cupid Queen's Maid Outfit, Hunter's Journal, Tung Sahur Costume, Triple Strongest Slash Scroll, and Special Tailor Token remain explicitly **unconfirmed** because the reviewed pages do not establish a rarity. Neither their trading rank nor their drop chance is used to guess one. For variants and incomplete individual pages, sources include the Valkyries table, Fishing/Rods and Baits, Accessories, Halloween 2025, and the season-specific Battle Pass pages.

## How Values Work

The [official document](https://docs.google.com/document/d/1pmF1jHksUPuQ95OMWnf7doaq8566Sba1VbhPWQtpiY4/preview) supplies item order, not verified sale prices. Regular tiers retain that order; **New Items** and **Very Unstable** have free market positions.

- **SP Reset = 1 point.** LC equivalents use the current estimated value of one Legendary Fruit Chest.
- Chest packs share a physical unit: ten chests always equal ten singles.
- Complete barter offers are fitted together. A relationship needs at least five independent authors before it affects prices; repeated posts do not add influence.
- Confidence reflects recent evidence and the strength of the connection to SP. An unanchored market remains on a historical point scale with limited confidence.
- Initial references and retained prices are marked explicitly. Unpriced items stay unpriced. These are estimates from offers, not proof of completed trades or guaranteed profit.

### Reviewed Unstable References

On 3 November 2026, all twelve **Very Unstable** items, including all six Valkyries, were checked against [gpo.gg](https://www.gpo.gg/values), [GPO Values](https://gpovalues.com/api/v1/items.json), [VVX](https://gpo.vaultedvaluesx.com/value-list), and [GPO Tracker](https://gpotracker.com/values/). `data/price_references.json` records each selected source, its quote date where stated, and its own LC scale. Ten references were repriced; Gift of Fruit and Kraken Armor Set (Azure) have no supported numerical quote and are unpriced. Violet uses the latest found reference from 24 October; the VVX pages do not state their quote dates.

Published item-to-LC ratios are converted using the retained **151.08 points per LC**. They are labelled **Price-checked reference**, with source links and dates in the item record; they do not add Discord observations or claim a verified SP conversion. A checked reference replaces an older collector checkpoint, while newer supported market prices take precedence. References are reapplied when loading an older catalogue checkpoint.

### Read Trade Feed

`data/values.json` includes `read_trades` for the hour ending at the snapshot timestamp, newest first. The feed uses the same deduplicated, normalized offers as the price engine, including recognized parts of incomplete offers. Each report contains item IDs and quantities, a timestamp, an anonymous stable ID, the number of independent authors supporting its barter relationship, and a decision: used, already included, waiting for five authors, incomplete, unpriced, paused, or no price relationship. Unknown parts remain excluded from market counts. The feed omits raw Discord text, author IDs and channel IDs. An empty collection produces an empty feed.

## Run Locally

Use Node.js 22 and Python 3.11 or newer.

```bash
npm ci
python3 -m venv .venv
source .venv/bin/activate
python -m pip install -r requirements.txt
npm start
```

Open http://localhost:3000. The preview serves public assets only. `HOST` and `PORT` can override its address. The committed snapshot works without a Discord token.

## Run Automated Tests

```bash
npm test
npm run build
npm run test:browser
```

The browser check requires Google Chrome (`playwright-core` uses `channel: 'chrome'`) and tests **the built `dist/` site**. It checks calculator flows, sharing/export and clipboard fallback, keyboard focus, filters, all six sections, and 320/390/768/1024/1440px layouts. Screenshots go to `test-results/`; set `GPO_SCREENSHOT_DIR` to change this.

On constrained machines, run numerical tests with `OPENBLAS_NUM_THREADS=1 OMP_NUM_THREADS=1 npm test`.

## Collect and Build

```bash
npm run sync                  # Refresh official order; preserve stable item IDs
npm run prices -- --offline   # Recalculate from retained local observations
npm run build                 # Validate and package only public files in dist/
```

For live collection, provide `DISCORD_TOKEN` through the environment and optionally `DISCORD_CHANNEL_IDS` (comma- or whitespace-separated; default `966859339816124438`), then run `npm run prices`. The Discord identity needs access to the channels and message history. Collection uses GET requests only.

`npm run prices -- --max-pages 120` limits work per cycle. Forward collection and seven-day backfill resume from saved cursors; failures retain the checkpoint and pause market repricing. `npm run bot` runs the same cycle repeatedly on a machine that stays online.

| Path | Purpose |
| --- | --- |
| `data/catalog.json` | Official order, stable IDs, item metadata and unit relationships |
| `data/rarities.json` | Reviewed game rarities and correct Wiki source links |
| `data/price_references.json` | Reviewed Unstable price sources and LC-scale conversions |
| `data/values.json` | Validated, public price/activity snapshot |
| `data/history.json` | Public sampled price history |
| `.state/market.sqlite3` | Collector messages, cursors and retained snapshots |
| `.state/catalog.json` | Catalogue needed to restore the collector checkpoint |
| `dist/` | Generated public site; never includes collector state or credentials |

## GitHub Pages and Scheduled Updates

In repository **Settings → Pages**, select **GitHub Actions** as the build source. Set the Actions secret `DISCORD_TOKEN` and, if needed, repository variable `DISCORD_CHANNEL_IDS`.

`.github/workflows/update_prices.yml` runs on pushes to `main`, manual dispatch, and hourly at minute 17 (UTC):

1. Restore a checkpoint from a trusted main-branch publisher run.
2. Refresh the official catalogue and collect Discord messages.
3. Validate the new snapshot and save a restorable checkpoint, including when publication fails.
4. Run regression checks, build `dist/`, run browser checks, and deploy to Pages.

The `gpo-market-state` artifact holds both checkpoint files; the three newest backups are retained, with a 30-day expiry. Keep this checkpoint when moving the collector. The workflow publishes generated data as a Pages artifact rather than making hourly Git commits. A missing token or unavailable source is shown on the site instead of fabricated market activity.

Pull requests and pushes also run `.github/workflows/checks.yml` against the committed snapshot.

## Artwork and Fonts

The panel/title silhouettes, button shapes, torn item masks, and rarity gradients are adapted from [GPO Wiki](https://grand-piece-online.fandom.com/wiki/Grand_Piece_Online_Wiki); attribution and source links are in `images/ui/NOTICE.md`. Wiki community content is available under [CC BY-SA](https://www.fandom.com/licensing) unless otherwise noted. Game artwork belongs to its respective creators.

**Finger Paint is the only web font**, self-hosted with its SIL Open Font License under `fonts/`. It does not contain Cyrillic glyphs, so Russian characters use the browser's built-in fallback, as on the Wiki. `scripts/prepare_assets.py` is a one-time asset utility and additionally requires Pillow.
