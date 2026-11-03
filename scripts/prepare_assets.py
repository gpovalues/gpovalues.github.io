"""One-time asset preparation: compact local images and fonts, no browser CDN requests."""
import io
import json
from pathlib import Path
from urllib.parse import unquote, urlparse

import requests
from PIL import Image

from scripts.market_data import ROOT, atomic_json


FONTS = {
    "finger-paint.woff2": "https://fonts.gstatic.com/s/fingerpaint/v21/0QInMXVJ-o-oRn_7dron8YW-9JzT.woff2",
    "Finger-Paint-OFL.txt": "https://raw.githubusercontent.com/google/fonts/main/ofl/fingerpaint/OFL.txt",
}
ART = {
    "background.webp": "https://tr.rbxcdn.com/180DAY-7ea3d13248b544e712d0dbe4d1bc84e3/768/432/Image/Png/noFilter",
    "gpo-logo.webp": "https://static.wikia.nocookie.net/grand-piece-online/images/9/91/Gpo-logo-update13.png",
}


def download(url):
    response = requests.get(url, timeout=15)
    response.raise_for_status()
    return response.content


def webp(source, target, size):
    with Image.open(source) as image:
        image = image.convert("RGBA")
        image.thumbnail(size, Image.Resampling.LANCZOS if hasattr(Image, "Resampling") else Image.LANCZOS)
        image.save(target, "WEBP", quality=85, method=6)


def main():
    fonts = ROOT / "fonts"
    images = ROOT / "images/items"
    art = ROOT / "images/ui"
    for directory in (fonts, images, art):
        directory.mkdir(parents=True, exist_ok=True)
    for name, url in FONTS.items():
        target = fonts / name
        if not target.exists():
            target.write_bytes(download(url))
    for name, url in ART.items():
        target = art / name
        if not target.exists():
            webp(io.BytesIO(download(url)), target, (1280, 800) if name == "background.webp" else (480, 240))
    for original, output in (("gpocha_avatar.jpg", "gpocha.webp"), ("fruit_trilogy_avatar.png", "fruit-trilogy.webp")):
        if (ROOT / "images" / original).exists():
            webp(ROOT / "images" / original, art / output, (144, 144))
    catalog_path = ROOT / "data/catalog.json"
    catalog = json.loads(catalog_path.read_text(encoding="utf-8"))
    for item in catalog["items"]:
        target = images / f"{item['id']}.webp"
        original = ROOT / item["image"]
        if not target.exists():
            if original.exists() and original.suffix.lower() != ".svg":
                webp(original, target, (192, 192))
            else:
                try:
                    title = unquote(urlparse(item["wikiUrl"]).path.split("/wiki/")[-1])
                    response = requests.get("https://grand-piece-online.fandom.com/api.php", params={
                        "action": "query", "format": "json", "prop": "pageimages", "piprop": "thumbnail",
                        "pithumbsize": 256, "titles": title, "redirects": 1,
                    }, timeout=10)
                    response.raise_for_status()
                    page = next(iter(response.json()["query"]["pages"].values()))
                    if page.get("thumbnail"):
                        webp(io.BytesIO(download(page["thumbnail"]["source"])), target, (192, 192))
                except (requests.RequestException, KeyError, ValueError):
                    print(f"Keeping an explicit placeholder for {item['name']}")
        if target.exists():
            item["image"] = target.relative_to(ROOT).as_posix()
    atomic_json(catalog_path, catalog)
    print(f"Prepared local assets for {sum((ROOT / item['image']).suffix == '.webp' for item in catalog['items'])} items.")


if __name__ == "__main__":
    main()
