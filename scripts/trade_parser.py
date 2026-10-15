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

        # 2. Build default aliases
        self._build_default_aliases()

        # 3. Merge custom aliases from disk if present
        if os.path.exists(self.aliases_path):
            try:
                with open(self.aliases_path, "r", encoding="utf-8") as f:
                    disk_aliases = json.load(f)
                    self.alias_map.update(disk_aliases)
            except Exception as e:
                logger.warning(f"Error loading aliases from {self.aliases_path}: {e}")

        # 4. Save merged back to disk
        try:
            os.makedirs(os.path.dirname(self.aliases_path), exist_ok=True)
            with open(self.aliases_path, "w", encoding="utf-8") as f:
                json.dump(self.alias_map, f, indent=2, ensure_ascii=False)
        except Exception:
            pass

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

        # Popular Trading Slang, Split Stickers, and Community Nicknames
        slang = {
            # Kaido / Dragon Emperor Items (frequently split as :kaido: :cape: stickers)
            "kaido cape": "item_104",
            "kaidos cape": "item_104",
            "kaido's cape": "item_104",
            "kaidocape": "item_104",
            "kaido": "item_104",
            "dragon emperor cape": "item_104",
            "dragon emperors cape": "item_104",
            "dragon emperor's cape": "item_104",
            "dragon cape": "item_104",
            "decape": "item_104",
            "плащ кайдо": "item_104",
            "кайдо плащ": "item_104",
            "кайдо": "item_104",
            "kaido gourd": "item_105",
            "kaidos gourd": "item_105",
            "kaido's gourd": "item_105",
            "kaidogourd": "item_105",
            "dragon emperor gourd": "item_105",
            "degourd": "item_105",
            "тыква кайдо": "item_105",
            "kaido outfit": "item_108",
            "kaidos outfit": "item_108",
            "kaido's outfit": "item_108",
            "kaidofit": "item_108",
            "dragon emperor outfit": "item_108",
            "defit": "item_108",
            "костюм кайдо": "item_108",
            "сет кайдо": "item_108",

            # Big Mom / Big Mama
            "big mom cape": "item_119",
            "big moms cape": "item_119",
            "big mom's cape": "item_119",
            "big mama cape": "item_119",
            "big mamas cape": "item_119",
            "big mama's cape": "item_119",
            "bigmom cape": "item_119",
            "bm cape": "item_119",
            "bmcape": "item_119",
            "плащ биг мам": "item_119",
            "плащ большой мамочки": "item_119",

            # Marine Gear
            "marine cape": "item_2",
            "mcape": "item_2",
            "плащ дозора": "item_2",
            "marine cap": "item_3",
            "mcap": "item_3",
            "кепка дозора": "item_3",

            # Eyes
            "ase": "item_31",
            "eye": "item_31",
            "all seeing eye": "item_31",
            "всевидящее око": "item_31",
            "око": "item_31",
            "case": "item_14",
            "chromatic eye": "item_14",
            "chromatic all seeing eye": "item_14",
            "egg": "item_24",
            "all seeing egg": "item_24",
            "blo ase": "item_24",
            "base": "item_27",
            "all seeing baal": "item_27",
            "blase": "item_25",
            "all seeing blossom": "item_25",
            "hase": "item_28",
            "all seeing holly": "item_28",
            "cqase": "item_29",
            "cupid all seeing eye": "item_29",

            # Weapons & Tools
            "cc": "item_16",
            "candycane": "item_16",
            "candy cane": "item_16",
            "cane": "item_16",
            "леденец": "item_16",
            "pcc": "item_6",
            "prestige candy cane": "item_6",
            "icc": "item_11",
            "iceborn candy cane": "item_11",
            "we": "item_35",
            "world ender": "item_35",
            "ворлд эндер": "item_35",
            "pwe": "item_8",
            "prestige world ender": "item_8",
            "hwe": "item_52",
            "hollow world ender": "item_52",
            "hollows world ender": "item_52",
            "kikoku": "item_62",
            "law sword": "item_62",
            "кикоку": "item_62",
            "df rod": "item_47",
            "devil fruit rod": "item_47",
            "dfrod": "item_47",
            "дф удочка": "item_47",
            "удочка дф": "item_47",
            "odm rod": "item_80",
            "odm": "item_80",
            "elo": "item_82",
            "elo hammer": "item_82",
            "elo sledgehammer": "item_82",
            "db": "item_54",
            "dark blade": "item_54",
            "yoru": "item_54",
            "йору": "item_54",
            "tc": "item_45",
            "thunder club": "item_45",
            "tttc": "item_44",
            "tung tung thunder club": "item_44",
            "napoleon": "item_41",
            "soul cleaver": "item_41",
            "fl": "item_70",
            "firework lancer": "item_70",
            "pfl": "item_9",
            "prestige firework lancer": "item_9",
            "flancer": "item_205",
            "fest lancer": "item_205",
            "festival lancer": "item_205",
            "irb": "item_69",
            "inferno rocket blade": "item_69",
            "pirb": "item_10",
            "prestige inferno rocket blade": "item_10",

            # Outfits & Accessories
            "qfit": "item_7",
            "cfit": "item_7",
            "qmaid": "item_7",
            "maid outfit": "item_7",
            "cupid outfit": "item_79",
            "cupid queen outfit": "item_79",
            "jfit": "item_21",
            "jester outfit": "item_21",
            "jesters outfit": "item_21",
            "coyote outfit": "item_50",
            "coyote": "item_50",
            "baal head": "item_59",
            "baals head": "item_59",
            "baal's head": "item_59",
            "baal": "item_59",
            "res head": "item_59",
            "hob": "item_71",
            "head of baal": "item_71",
            "tbg": "item_99",
            "true baal guard": "item_99",
            "sks": "item_30",
            "soul king scarf": "item_30",
            "soul king's scarf": "item_30",
            "skg": "item_74",
            "soul king guitar": "item_74",
            "soul king's guitar": "item_74",
            "cs": "item_1",
            "cool shades": "item_1",
            "shades": "item_1",
            "sg": "item_4",
            "sakamoto": "item_4",
            "sakamoto glasses": "item_4",
            "cwig": "item_203",
            "clown wig": "item_203",
            "love shades": "item_209",
            "banana": "item_204",

            # Chests
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
            "10x legendary fruit chest": "item_60",
            "mc": "item_58",
            "mythic chest": "item_58",
            "mythical chest": "item_58",
            "mythic fruit chest": "item_58",
            "mythical fruit chest": "item_58",
            "10mc": "item_26",
            "10 mc": "item_26",
            "10x mc": "item_26",
            "10x mythic chest": "item_26",
            "10x mythical fruit chest": "item_26",
            "rare chest": "item_208",
            "rare fruit chest": "item_208",
            "rc": "item_208",
            "10rc": "item_207",
            "10 rc": "item_207",
            "10x rc": "item_207",
            "10x rare fruit chest": "item_207",

            # Essences & Bags & Vehicles
            "sp": "item_194",
            "sp reset": "item_194",
            "sp reset essence": "item_194",
            "dr": "item_193",
            "dark root": "item_193",
            "darkroot": "item_193",
            "pbag": "item_13",
            "prestige fruitbag": "item_13",
            "prestige fruit bag": "item_13",
            "fruitbag": "item_121",
            "fruit bag": "item_121",
            "bag": "item_121",
            "spare bag": "item_121",
            "hover": "item_213",
            "hoverboard": "item_213",
            "striker": "item_212",
            "cboat": "item_211",
            "coffin boat": "item_211",
            "fboat": "item_68",
            "flamingo boat": "item_68",
            "hpod": "item_65",
            "hover pod": "item_65",

            # Devil Fruits
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
            "leo": "item_63",
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
            "paw": "item_166"
        }
        self.alias_map.update(slang)

    def clean_text(self, text: str) -> str:
        """
        Removes Discord custom emoji syntax, standard colon emojis,
        replaces underscores, and strips NLF parts.
        Handles adjacent/split emojis like <:kaido:1><:cape:2> or :kaido::cape:.
        """
        # 1. Strip NLF
        text = NLF_REGEX.sub("", text)

        # 2. Convert Discord custom emojis <:name:12345> or <a:name:12345> to ' name '
        text = re.sub(r"<a?:([a-zA-Z0-9_]+):\d+>", r" \1 ", text)

        # 3. Convert standard Discord colon emojis (:name:) to ' name '
        # Repeat while pattern matches to handle adjacent or overlapped colons like :kaido::cape:
        prev = None
        while prev != text:
            prev = text
            text = re.sub(r":([a-zA-Z0-9_]+):", r" \1 ", text)

        # 4. Clean up discord markdown (bold, italics, code blocks) and replace underscores with spaces
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

    def find_item_match(self, words: List[str], start_idx: int) -> Tuple[Optional[str], int]:
        """Tries to greedily match phrases of length 4, 3, 2, 1 against alias_map."""
        n = len(words)
        for span in (4, 3, 2, 1):
            if start_idx + span <= n:
                phrase = " ".join(words[start_idx : start_idx + span]).lower().strip()
                clean_phrase = re.sub(r"[^\w\s]", "", phrase).strip()
                if phrase in self.alias_map:
                    return self.alias_map[phrase], span
                if clean_phrase in self.alias_map:
                    return self.alias_map[clean_phrase], span
        return None, 0

    def extract_items_with_qty(self, segment: str) -> List[Tuple[str, int]]:
        """
        Extracts matched item IDs and their multipliers.
        Supports:
        - Split stickers (e.g. <:kaido:1><:cape:2>, :kaido::cape:, :kaido: :cape:)
        - Undelimited item sequences (e.g. 'kaido cape mochi 2x lc')
        - Prefix and suffix quantities (e.g. '2x item', 'item 2x')
        """
        if not segment:
            return []

        results: List[Tuple[str, int]] = []
        # Split by major trade delimiters
        clauses = re.split(r"[,+/|&\n]+|\b(?:and|with)\b", segment, flags=re.IGNORECASE)

        qty_regex = re.compile(r"^(?:x(\d+)|(\d+)x|\b(\d+)\b)$", re.IGNORECASE)
        filler_words = {"adds", "add", "small", "good", "dm", "me", "fast", "trade", "or", "offer", "my", "the", "for", "all", "any", "want", "have", "lf"}

        for clause in clauses:
            clause_clean = re.sub(r"[:;]+", " ", clause)
            words = clause_clean.split()
            n = len(words)
            idx = 0

            while idx < n:
                w = words[idx].lower()
                if w in filler_words:
                    idx += 1
                    continue

                qty = 1
                m_pre = qty_regex.match(w)
                if m_pre:
                    q_val = int(m_pre.group(1) or m_pre.group(2) or m_pre.group(3))
                    if 1 <= q_val <= 100:
                        qty = q_val
                        idx += 1
                        if idx >= n:
                            break

                matched_id, span = self.find_item_match(words, idx)
                if matched_id:
                    idx += span
                    # Check for suffix quantity if prefix wasn't set
                    if idx < n and qty == 1:
                        next_w = words[idx].lower()
                        m_suf = qty_regex.match(next_w)
                        if m_suf:
                            # Only treat as suffix if what follows is NOT another item
                            next_item, _ = self.find_item_match(words, idx + 1)
                            if not next_item:
                                q_val = int(m_suf.group(1) or m_suf.group(2) or m_suf.group(3))
                                if 1 <= q_val <= 100:
                                    qty = q_val
                                    idx += 1
                    results.append((matched_id, qty))
                else:
                    idx += 1

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
        "Candy Cane for PWE and adds dm me",
        # Split stickers & Kaido tests
        "WTT <:kaido:101><:cape:102> <:mochi:103> + 2x <:leg:104><:chest:105> LF <:ase:106>",
        ":kaido::cape: :mochi: :pika:",
        "H: :kaido: :cape: W: :mochi:",
        "3x <:marine:201><:cape:202> -> :kaido::gourd:",
        "2x:kaido::cape:",
        ":kaido::cape: 2x",
        "trading devil fruit rod for kaido cape and adds",
        "h: :kaido::outfit: w: :big::mom::cape:",
        "LF 2x :kaido::cape: offer :mochi: + 10x lc",
        "kaido cape 2x leg chest mochi 3x pika"
    ]
    for tc in test_cases:
        res = parser.parse_message({"content": tc, "author_id": "test_1", "id": "1", "timestamp": "2026-10-15T12:00:00Z"})
        print("INPUT :", tc)
        print("OUTPUT:", res)
        print("-" * 50)
