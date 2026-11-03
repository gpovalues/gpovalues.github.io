"""Package a validated snapshot and public assets for GitHub Pages."""
import argparse
import hashlib
import json
import os
import re
import shutil
import tempfile
from pathlib import Path

from scripts.market_data import ROOT, load_catalog, validate_snapshot


PUBLIC_FILES = ['index.html', 'style.css', 'app.js', 'translations.js', 'icons.js',
                'site_config.js', 'ads.js', 'ads.txt', 'robots.txt', 'sitemap.xml',
                'data/values.json', 'data/history.json', 'images/placeholder.svg']


def build_site(destination=None):
    destination = Path(destination or ROOT / 'dist').resolve()
    if destination == ROOT or destination in ROOT.parents:
        raise ValueError('The output directory cannot replace the project')
    if destination.exists() and any(destination.iterdir()) and not (destination / '.gpo-build').is_file():
        raise ValueError('Refusing to replace an unrelated output directory')
    snapshot = json.loads((ROOT / 'data/values.json').read_text(encoding='utf-8'))
    validate_snapshot(snapshot, load_catalog())
    assets = set(PUBLIC_FILES)
    assets.update(item['image'] for item in snapshot['items'])
    assets.update(p.relative_to(ROOT).as_posix() for p in (ROOT / 'images/ui').iterdir() if p.suffix in ('.svg', '.webp'))
    assets.update(p.relative_to(ROOT).as_posix() for p in (ROOT / 'fonts').iterdir() if p.suffix in ('.woff2', '.txt'))
    assets.update(f'audio/{name}' for name in ('click.wav', 'item_add.wav', 'item_remove.wav'))
    destination.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix='.gpo-build-', dir=destination.parent) as temporary:
        stage = Path(temporary)
        for relative in sorted(assets):
            source = (ROOT / relative).resolve()
            if not source.is_relative_to(ROOT) or not source.is_file():
                raise ValueError(f'Missing or invalid public asset: {relative}')
            target = stage / relative
            if not target.resolve().is_relative_to(stage):
                raise ValueError('Unsafe asset path')
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(source, target)
        html = (stage / 'index.html').read_text(encoding='utf-8')
        for name in PUBLIC_FILES:
            if Path(name).suffix in ('.js', '.css'):
                version = hashlib.sha256((stage / name).read_bytes()).hexdigest()[:12]
                html = re.sub(r'((?:src|href)=")' + re.escape(name) + r'"', rf'\g<1>{name}?v={version}"', html)
        (stage / 'index.html').write_text(html, encoding='utf-8')
        (stage / '.gpo-build').write_text('Generated GPO public site\n', encoding='utf-8')
        if destination.exists():
            shutil.rmtree(destination)
        os.replace(stage, destination)
    print(f'Public site: {len(assets)} files in {destination}; snapshot {snapshot["revision"]}')
    return destination


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', type=Path, default=ROOT / 'dist')
    build_site(parser.parse_args().output)
