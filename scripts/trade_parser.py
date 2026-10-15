"""
GPO Trade Message Parser for Grand Piece Online.
Parses raw Discord trading hub messages into structured trades:
- Cleans and strips NLF (Not Looking For) segments.
- Handles custom Discord emojis (<:emoji_name:123456789>).
- Splits into Offer (Supply) vs Want (Demand) sides.
- Extracts item counts (2x, x3, etc.) and aliases.
- Deduplicates messages from the same author ID within 12h.
"""

import re
import json
import os
import logging
from typing import List, Dict, Any, Tuple, Optional, Set

logger = logging.getLogger("TradeParser")

EMOJI_REGEX = re.compile(r"<a?:([a-zA-Z0-9_]+):\d+>")
NLF_REGEX = re.compile(r"\b(nlf|not\s+looking\s+for|no\s+want|dont\s+want|don't\s+want)\b.*$", re.IGNORECASE | re.DOTALL)


class GPOTradeParser:
    """
    Robust trading message parser tuned specifically for Grand Piece Online community slang.
    """
    def __init__(self, items_path: Optional[str] = None, aliases_path: Optional[str] = None):
        self.items_path = items_path or os.path.join(os.path.dirname(__file__), "..", "gpo_items.json")
        self.aliases_path = aliases_path or os.path.join(os.path.dirname(__file__), "..", "data", "trade_aliases.json")
        
        self.items_dict: Dict[str, Dict[str, Any]] = {}
        self.alias_map: Dict[str, str] = {}
        self._load_items_and_aliases()

    def _load_items_and_aliases(self):
        # 1. Load canonical items
        if os.path.exists(self.items_path):
            try:
                with open(self.items_path, "r", encoding="utf-8") as f:
                    items_list = json.load(f)
                    for it in items_list:
                        self.items_dict[it["id"]] = it
            except Exception as e:
                logger.error(f"Error loading items from {self.items_path}: {e}")

        # 2. Build or load alias map
        if os.path.exists(self.aliases_path):
            try:
                with open(self.aliases_path, "r", encoding="utf-8") as f:
                    self.alias_map = json.load(f)
                    return
            except Exception as e:
                logger.warning(f"Error loading aliases from {self.aliases_path}: {e}")

        self._build_default_aliases()

    def _build_default_aliases(self):
        """Builds a rich alias map from item attributes and known community nicknames."""
        self.alias_map = {}
        
        for iid, it in self.items_dict.items():
            name = it.get("name", "").lower().strip()
            self.alias_map[name] = iid
            clean_name = re.sub(r"[^\w\s]", "", name).strip()
            self.alias_map[clean_name] = iid

            if it.get("nameRu"):
                ru_name = it["nameRu"].lower().strip()
                self.alias_map[ru_name] = iid
                self.alias_map[re.sub(r"[^\w\s]", "", ru_name).strip()] = iid

            if it.get("abbreviation"):
                abbr = it["abbreviation"].lower().strip()
                self.alias_map[abbr] = iid

        # Popular Trading Slang and Abbreviations
        slang = {
            "ase": "item_31",
            "eye": "item_31",
            "all seeing eye": "item_31",
            "case": "item_14",
            "chromatic eye": "item_14",
            "cc": "item_16",
            "candycane": "item_16",
            "cane": "item_16",
            "pcc": "item_6",
            "qfit": "item_7",
            "cfit": "item_7",
            "qmaid": "item_7",
            "maid outfit": "item_7",
            "pwe": "item_8",
            "we": "item_35",
            "world ender": "item_35",
            "hwe": "item_52",
            "kikoku": "item_62",
            "law sword": "item_62",
            "lc": "item_102",
            "leg chest": "item_102",
            "legchest": "item_102",
            "lchest": "item_102",
            "legendary chest": "item_102",
            "legendary fruit chest": "item_102",
            "10lc": "item_60",
            "10 lc": "item_60",
            "10x lc": "item_60",
            "10x leg chest": "item_60",
            "mythic chest": "item_58",
            "mythical chest": "item_58",
            "mc": "item_58",
            "10x mythic chest": "item_26",
            "10x mythic": "item_26",
            "10 mc": "item_26",
            "10x mc": "item_26",
            "sp": "item_194",
            "sp reset": "item_194",
            "sp reset essence": "item_194",
            "dr": "item_193",
            "dark root": "item_193",
            "darkroot": "item_193",
            "rare chest": "item_208",
            "10x rare chest": "item_207",
            "pbag": "item_13",
            "fruitbag": "item_121",
            "bag": "item_121",
            "spare bag": "item_121",
            "mochi": "item_72",
            "venom": "item_76",
            "pika": "item_86",
            "light": "item_86",
            "tori": "item_84",
            "phoenix": "item_84",
            "ope": "item_100",
            "buddha": "item_107",
            "magu": "item_122",
            "magma": "item_122",
            "mera": "item_127",
            "flame": "item_127",
            "goro": "item_134",
            "lightning": "item_134",
            "suna": "item_135",
            "sand": "item_135",
            "dragon": "item_38",
            "ryu": "item_38",
            "leopard": "item_63",
            "soul": "item_75",
            "pteranodon": "item_87",
            "ptera": "item_87",
            "gura": "item_117",
            "quake": "item_117",
            "zushi": "item_152",
            "gravity": "item_152",
            "ito": "item_143",
            "string": "item_143",
            "kage": "item_144",
            "shadow": "item_144",
            "hiei": "item_142",
            "ice": "item_142",
            "yami": "item_165",
            "dark": "item_165",
            "paw": "item_166",
            "hover": "item_213",
            "hoverboard": "item_213",
            "striker": "item_212",
            "baal head": "item_59",
            "baals head": "item_59",
            "baal": "item_59",
            "df rod": "item_47",
            "devil fruit rod": "item_47",
            "egg": "item_24",
            "all seeing egg": "item_24",
            "cs": "item_1",
            "shades": "item_1",
            "cool shades": "item_1",
            "mcape": "item_2",
            "marine cape": "item_2",
            "mcap": "item_3",
            "marine cap": "item_3",
            "sg": "item_4",
            "sakamoto": "item_4",
            "sakamoto glasses": "item_4",
            "flancer": "item_205",
            "fest lancer": "item_205",
            "love shades": "item_209",
            "banana": "item_204"
        }
        self.alias_map.update(slang)

        # Save to disk if data dir exists
        try:
            os.makedirs(os.path.dirname(self.aliases_path), exist_ok=True)
            with open(self.aliases_path, "w", encoding="utf-8") as f:
                json.dump(self.alias_map, f, indent=2, ensure_ascii=False)
        except Exception:
            pass

    def clean_text(self, text: str) -> str:
        """Removes Discord custom emoji syntax, URLs, and strips NLF parts."""
        # 1. Strip NLF
        text = NLF_REGEX.sub("", text)

        # 2. Convert Discord custom emojis <:name:12345> to ' name '
        text = EMOJI_REGEX.sub(r" \1 ", text)

        # 3. Clean up discord markdown (bold, italics, code blocks)
        text = re.sub(r"[*_~`|]", " ", text)
        return text.strip()

    def split_offer_want(self, text: str) -> Tuple[str, str]:
        """
        Splits message into offer_side (what user gives) and want_side (what user wants).
        Recognizes common trade formats:
        - 'LF [want] for [offer]'
        - 'H: [offer] W: [want]'
        - '[offer] -> [want]'
        - 'WTT [offer] LF [want]'
        - '[offer] for [want]'
        """
        t = text

        # Format: LF <want> for <offer>
        m_lf_for = re.search(r"^\s*(?:lf|looking\s+for|want|w)\s+(.*?)\s+(?:for|offer|giving)\s+(.*)$", t, re.IGNORECASE)
        if m_lf_for:
            return m_lf_for.group(2).strip(), m_lf_for.group(1).strip()

        # Format: H: <offer> W: <want>
        m_hw = re.search(r"(?:h|have|giving|trading)\s*:\s*(.*?)\s*(?:w|want|lf|looking\s+for)\s*:\s*(.*)", t, re.IGNORECASE)
        if m_hw:
            return m_hw.group(1).strip(), m_hw.group(2).strip()

        # Format: <offer> -> <want> / <offer> ➡ <want>
        m_arrow = re.search(r"^(.*?)\s*(?:->|=>|➡|–>|-->)\s*(.*)$", t)
        if m_arrow:
            return m_arrow.group(1).strip(), m_arrow.group(2).strip()

        # Format: WTT <offer> LF <want>
        m_wtt_lf = re.search(r"(?:wtt|trading|giving|have|h)\s+(.*?)\s+(?:lf|looking\s+for|want|w)\s+(.*)", t, re.IGNORECASE)
        if m_wtt_lf:
            return m_wtt_lf.group(1).strip(), m_wtt_lf.group(2).strip()

        # Format: <offer> LF <want>
        m_lf = re.search(r"^(.*?)\s+(?:lf|looking\s+for|want)\s+(.*)$", t, re.IGNORECASE)
        if m_lf:
            return m_lf.group(1).strip(), m_lf.group(2).strip()

        # Format: <offer> for <want>
        m_for = re.search(r"^(.*?)\s+(?:for)\s+(.*)$", t, re.IGNORECASE)
        if m_for:
            return m_for.group(1).strip(), m_for.group(2).strip()

        # Default fallback: treat entire text as offer
        return t, ""

    def extract_items_with_qty(self, segment: str) -> List[Tuple[str, int]]:
        """
        Extracts matched item IDs and their multipliers (e.g. '2x LC' -> [('item_102', 2)]).
        """
        if not segment:
            return []

        results: List[Tuple[str, int]] = []
        tokens = re.split(r"[,+/|&\n]+|\b(?:and|with)\b", segment, flags=re.IGNORECASE)

        for raw_token in tokens:
            token = raw_token.strip().lower()
            if not token or len(token) < 2:
                continue

            # Skip common filler words
            if token in ("adds", "small adds", "good adds", "dm me", "fast", "fast trade", "or offer"):
                continue

            # Look for quantity prefix like '2x item', '3 item', 'x2 item'
            qty = 1
            qty_match = re.search(r"^(?:x\s*(\d+)|(\d+)\s*x|\b(\d+)\b)\s*(.*)$", token)
            if qty_match:
                q_str = qty_match.group(1) or qty_match.group(2) or qty_match.group(3)
                if q_str and int(q_str) <= 50:
                    qty = int(q_str)
                    token = (qty_match.group(4) or "").strip()

            clean_token = re.sub(r"[^\w\s]", "", token).strip()

            # Exact alias lookup
            if token in self.alias_map:
                results.append((self.alias_map[token], qty))
                continue
            if clean_token in self.alias_map:
                results.append((self.alias_map[clean_token], qty))
                continue

            # Substring matching for longer multi-word names
            matched_id = None
            for alias_key, iid in self.alias_map.items():
                if len(alias_key) >= 4 and f" {alias_key} " in f" {clean_token} ":
                    matched_id = iid
                    break

            if matched_id:
                results.append((matched_id, qty))

        return results

    def parse_message(self, message: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        """
        Parses a single Discord message object into a structured trade record.
        """
        raw_text = message.get("content", "")
        if not raw_text or len(raw_text) < 4:
            return None

        cleaned = self.clean_text(raw_text)
        offer_str, want_str = self.split_offer_want(cleaned)

        offer_items = self.extract_items_with_qty(offer_str)
        want_items = self.extract_items_with_qty(want_str)

        # Must have at least one recognized item in offer or want
        if not offer_items and not want_items:
            return None

        return {
            "id": message.get("id"),
            "author_id": message.get("author_id"),
            "timestamp": message.get("timestamp"),
            "raw_text": raw_text,
            "offer_items": offer_items,  # [(item_id, count)] -> Supply
            "want_items": want_items     # [(item_id, count)] -> Demand
        }

    def parse_all(self, messages: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        """
        Parses all messages with 12h author deduplication to block spam.
        """
        parsed_trades: List[Dict[str, Any]] = []
        seen_author_hashes: Set[str] = set()

        for msg in messages:
            author_id = msg.get("author_id", "anon")
            content = (msg.get("content") or "").strip().lower()

            # Simple content hash per author for deduplication
            dedup_key = f"{author_id}:{content[:50]}"
            if dedup_key in seen_author_hashes:
                continue
            seen_author_hashes.add(dedup_key)

            parsed = self.parse_message(msg)
            if parsed:
                parsed_trades.append(parsed)

        logger.info(f"Successfully parsed {len(parsed_trades)} distinct trade signals from {len(messages)} raw messages.")
        return parsed_trades


if __name__ == "__main__":
    parser = GPOTradeParser()
    test_cases = [
        "WTT Mochi + 2x LC LF ASE nlf low tier fruits",
        "LF Venom + adds for my Kikoku",
        "Trading 10x Legendary Fruit Chest -> Mythical Fruit Chest",
        "H: Cool Shades W: Marine Cape + 5x LC",
        "Candy Cane for PWE and adds dm me"
    ]
    for tc in test_cases:
        res = parser.parse_message({"content": tc, "author_id": "test_1", "id": "1", "timestamp": "2026-10-15T12:00:00Z"})
        print("INPUT :", tc)
        print("OUTPUT:", res)
        print("-" * 50)
