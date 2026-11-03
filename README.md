# GPO Values & Trade Calculator

A community trading companion for [Grand Piece Online](https://www.roblox.com/games/1730877806/Grand-Piece-Online): compare offers, browse the official item order, and see the evidence behind estimated values.

## Features
- GPO-inspired artwork, hand-drawn headings, English/Russian localization, and responsive layouts down to 320px.
- Two-sided calculator with quantities, point/LC totals, swap, undo, shareable URLs, and Discord text export.
- Search by name or abbreviation, category/tier filters, item details, and recorded price history.
- Market activity over 1 hour, 24 hours, and 7 days; recorded changes are separate from estimates.
- Local WebP images and fonts, lazy item rendering, keyboard-accessible dialogs, and optional sound. Ads are disabled in `site_config.js` by default.

## How Values Work

The [official document](https://docs.google.com/document/d/1pmF1jHksUPuQ95OMWnf7doaq8566Sba1VbhPWQtpiY4/preview) supplies item order, not verified sale prices. Regular tiers retain that order; **New Items** and **Very Unstable** have free market positions.

- **SP Reset = 1 point.** LC equivalents use the current estimated value of one Legendary Fruit Chest.
- Chest packs share a physical unit: ten chests always equal ten singles.
- Complete barter offers are fitted together. A relationship needs at least five independent authors before it affects prices; repeated posts do not add influence.
- Confidence reflects recent evidence and the strength of the connection to SP. An unanchored market remains on a historical point scale with limited confidence.
- Initial references and retained prices are marked explicitly. Unpriced items stay unpriced. These are estimates from offers, not proof of completed trades or guaranteed profit.

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

The visual direction draws on the original GPO Values site and [GPO Wiki](https://grand-piece-online.fandom.com/wiki/Grand_Piece_Online_Wiki). Game artwork belongs to its respective creators. Finger Paint, PT Sans, and the Cyrillic Neucha font are self-hosted with their SIL Open Font License files under `fonts/`. `scripts/prepare_assets.py` is a one-time asset utility and additionally requires Pillow.
