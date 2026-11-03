import json
import os
import tempfile
import unittest
from pathlib import Path

from scripts.build_site import build_site


class BuildTests(unittest.TestCase):
    def test_only_public_assets_are_packaged(self):
        with tempfile.TemporaryDirectory(prefix="gpo-build-test-", dir=os.environ.get("GPO_TEST_TMP")) as folder:
            target = Path(folder) / "site"
            build_site(target)
            self.assertTrue((target / "index.html").exists())
            snapshot = json.loads((target / "data/values.json").read_text(encoding="utf-8"))
            self.assertEqual(snapshot["schema_version"], 2)
            for private in (".state", ".git", "scripts", "tests", "node_modules", "data/trades_buffer.json", "data/catalog.json"):
                self.assertFalse((target / private).exists(), private)
            for item in snapshot["items"]:
                self.assertTrue((target / item["image"]).is_file(), item["image"])
            build_site(target)
            self.assertTrue((target / "app.js").is_file())

    def test_build_will_not_delete_an_unrelated_directory(self):
        with tempfile.TemporaryDirectory(prefix="gpo-build-test-", dir=os.environ.get("GPO_TEST_TMP")) as folder:
            target = Path(folder)
            (target / "keep.txt").write_text("user work", encoding="utf-8")
            with self.assertRaises(ValueError):
                build_site(target)
            self.assertEqual((target / "keep.txt").read_text(encoding="utf-8"), "user work")
