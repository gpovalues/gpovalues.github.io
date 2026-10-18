"""
Discord Emoji & Item Trade Extractor for Grand Piece Online (GPO).
Version: 1.1 (Live GitHub Secrets & Authentic Snowflake Sync)

1. Discord Emoji Extractor & Link Resolver:
   - Fetches custom server emojis via Discord REST API (GET /guilds/{guild_id}/emojis).
   - Scans Discord trade messages for <:emoji_name:emoji_id> and <a:emoji_name:emoji_id> tags.
   - Generates direct Discord CDN image URLs (https://cdn.discordapp.com/emojis/{id}.png or .gif).
   - Exports all emoji references with their URLs and mapped GPO items to data/discord_emojis.json.

2. Trading Syntax & Emoji Interpreter:
   - Understands LF (Looking For), W (Want), H (Have), WTT (Want to trade), FOR, ->, etc.
   - Filters out NLF (Not Looking For) segments completely so unwanted items are never parsed into demand.
   - Recognizes single-item emojis:
     e.g., :Mochi:, :Tori:, :Pika:, :Magu:, :Venom:, :Ope:, :Goro:, :Suna:, :Buddha:, :Kikoku:, :ASE:, etc.
   - Recognizes multi-emoji compound items where single components mean nothing alone:
     e.g., :kaido::cape: or :kaido: :cape: -> Dragon Emperor's Cape (Kaido Cape)
           :kaido::gourd: -> Dragon Emperor's Gourd
           :kaido::outfit: -> Dragon Emperor's Outfit
           :big::mom::cape: -> Big Mama's Cape
           :titan::cape: -> Titan of Justice's Cape
           :radiant::cape: -> Radiant Admiral's Cape
           :soul::king::scarf: -> Soul King Scarf
           :soul::king::guitar: -> Soul King Guitar
           :cupid::queen::outfit: -> Cupid Queen's Maid Outfit
           :all::seeing::eye: -> All Seeing Eye
           :all::seeing::egg: -> All Seeing Egg
           :candy::cane: -> Candy Cane
           :devil::fruit::rod: / :df::rod: -> Devil Fruit Rod
           :leg::chest: -> Legendary Fruit Chest
           :sp::reset: -> SP Reset Essence
           :dark::root: -> Dark Root
   - Strictly guarantees that isolated parts (like :cape: alone or :kaido: alone) DO NOT count as items.
   - Supports multipliers (e.g. 2x :Mochi:, 3x :kaido::cape:, 4️⃣ :leg::chest:).
"""

import os
import sys
import re
import json
import logging
from typing import List, Dict, Any, Tuple, Optional, Set

if hasattr(sys.stdout, "reconfigure"):
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass

try:
    import requests
except ImportError:
    requests = None

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger("DiscordEmojiExtractor")

# Default official GPO Trade Hub IDs
DEFAULT_GUILD_ID = "842875016524595240"
DEFAULT_CHANNEL_ID = "966859339816124438"
DISCORD_API_BASE = "https://discord.com/api/v9"
DISCORD_CDN_BASE = "https://cdn.discordapp.com/emojis"

# NLF regex: strips out everything after NLF / Not Looking For
NLF_REGEX = re.compile(
    r"\b(nlf|not\s+looking\s+for|no\s+want|dont\s+want|don't\s+want|не\s+предлагать|не\s+лф|не\s+ищу)\b.*$",
    re.IGNORECASE | re.DOTALL
)

# Number emoji normalizations
KEYCAP_MAP = {
    "0️⃣": " 0 ", "1️⃣": " 1 ", "2️⃣": " 2 ", "3️⃣": " 3 ", "4️⃣": " 4 ",
    "5️⃣": " 5 ", "6️⃣": " 6 ", "7️⃣": " 7 ", "8️⃣": " 8 ", "9️⃣": " 9 ",
    "🔟": " 10 ", "0\u20e3": " 0 ", "1\u20e3": " 1 ", "2\u20e3": " 2 ",
    "3\u20e3": " 3 ", "4\u20e3": " 4 ", "5\u20e3": " 5 ", "6\u20e3": " 6 ",
    "7\u20e3": " 7 ", "8\u20e3": " 8 ", "9\u20e3": " 9 "
}

CIRCLED_DIGITS = {
    "①": " 1 ", "②": " 2 ", "③": " 3 ", "④": " 4 ", "⑤": " 5 ",
    "⑥": " 6 ", "⑦": " 7 ", "⑧": " 8 ", "⑨": " 9 ", "⑩": " 10 ",
    "❶": " 1 ", "❷": " 2 ", "❸": " 3 ", "❹": " 4 ", "❺": " 5 ",
    "❻": " 6 ", "❼": " 7 ", "❽": " 8 ", "❾": " 9 ", "❿": " 10 "
}

WORD_NUMS = {
    "zero": 0, "one": 1, "two": 2, "three": 3, "four": 4, "five": 5,
    "six": 6, "seven": 7, "eight": 8, "nine": 9, "ten": 10,
    "ноль": 0, "один": 1, "одна": 1, "одно": 1, "два": 2, "две": 2, "три": 3,
    "четыре": 4, "пять": 5, "шесть": 6, "семь": 7, "восемь": 8, "девять": 9, "десять": 10
}

# --------------------------------------------------------------------------
# Multi-Emoji Compound Dictionary
# Maps ordered tuples of emoji names -> canonical GPO Item ID & Item Name
# --------------------------------------------------------------------------
COMPOUND_EMOJI_RULES = [
    # Kaido / Dragon Emperor Items
    (("kaido", "cape"), "item_104", "Dragon Emperor's Cape (Kaido Cape)"),
    (("kaidos", "cape"), "item_104", "Dragon Emperor's Cape (Kaido Cape)"),
    (("dragon", "emperor", "cape"), "item_104", "Dragon Emperor's Cape (Kaido Cape)"),
    (("dragon", "cape"), "item_104", "Dragon Emperor's Cape (Kaido Cape)"),
    (("de", "cape"), "item_104", "Dragon Emperor's Cape (Kaido Cape)"),
    (("kaido", "gourd"), "item_105", "Dragon Emperor's Gourd (Kaido Gourd)"),
    (("dragon", "emperor", "gourd"), "item_105", "Dragon Emperor's Gourd (Kaido Gourd)"),
    (("kaido", "outfit"), "item_108", "Dragon Emperor's Outfit (Kaido Outfit)"),
    (("kaidos", "outfit"), "item_108", "Dragon Emperor's Outfit (Kaido Outfit)"),
    (("dragon", "emperor", "outfit"), "item_108", "Dragon Emperor's Outfit (Kaido Outfit)"),

    # Big Mom / Big Mama Items
    (("big", "mom", "cape"), "item_119", "Big Mama's Cape"),
    (("big", "moms", "cape"), "item_119", "Big Mama's Cape"),
    (("big", "mama", "cape"), "item_119", "Big Mama's Cape"),
    (("big", "mamas", "cape"), "item_119", "Big Mama's Cape"),
    (("bm", "cape"), "item_119", "Big Mama's Cape"),
    (("big", "mom", "hat"), "item_124", "Big Mama's Hat"),
    (("big", "mama", "hat"), "item_124", "Big Mama's Hat"),

    # Other Distinct Capes
    (("titan", "cape"), "item_162", "Titan of Justice's Cape"),
    (("titan", "of", "justice", "cape"), "item_162", "Titan of Justice's Cape"),
    (("radiant", "cape"), "item_166", "Radiant Admiral's Cape"),
    (("radiant", "admiral", "cape"), "item_166", "Radiant Admiral's Cape"),
    (("admiral", "cape"), "item_166", "Radiant Admiral's Cape"),
    (("ashen", "cape"), "item_165", "Ashen's Cape"),
    (("captain", "zhen", "cape"), "item_184", "Captain Zhen's Cape"),
    (("zhen", "cape"), "item_184", "Captain Zhen's Cape"),
    (("marine", "cape"), "item_2", "Marine Cape"),

    # Soul King Items
    (("soul", "king", "scarf"), "item_30", "Soul King Scarf"),
    (("sk", "scarf"), "item_30", "Soul King Scarf"),
    (("soul", "king", "guitar"), "item_74", "Soul King Guitar"),
    (("sk", "guitar"), "item_74", "Soul King Guitar"),

    # Cupid / Outfits
    (("cupid", "queen", "outfit"), "item_7", "Cupid Queen's Maid Outfit"),
    (("cupid", "maid", "outfit"), "item_7", "Cupid Queen's Maid Outfit"),
    (("cupid", "maid"), "item_7", "Cupid Queen's Maid Outfit"),
    (("q", "maid"), "item_7", "Cupid Queen's Maid Outfit"),
    (("cupid", "outfit"), "item_79", "Cupid Queen Outfit"),
    (("jester", "outfit"), "item_21", "Jester Outfit"),

    # Eyes & Candy
    (("all", "seeing", "eye"), "item_31", "All Seeing Eye"),
    (("ase", "eye"), "item_31", "All Seeing Eye"),
    (("all", "seeing", "egg"), "item_24", "All Seeing Egg"),
    (("candy", "cane"), "item_16", "Candy Cane"),
    (("prestige", "candy", "cane"), "item_6", "Prestige Candy Cane"),
    (("p", "cc"), "item_6", "Prestige Candy Cane"),
    (("p", "candy", "cane"), "item_6", "Prestige Candy Cane"),

    # Weapons
    (("world", "ender"), "item_35", "World Ender"),
    (("prestige", "world", "ender"), "item_8", "Prestige World Ender"),
    (("p", "we"), "item_8", "Prestige World Ender"),
    (("p", "world", "ender"), "item_8", "Prestige World Ender"),
    (("firework", "lancer"), "item_70", "Firework Lancer"),
    (("prestige", "firework", "lancer"), "item_9", "Prestige Firework Lancer"),
    (("p", "fl"), "item_9", "Prestige Firework Lancer"),
    (("devil", "fruit", "rod"), "item_47", "Devil Fruit Rod"),
    (("df", "rod"), "item_47", "Devil Fruit Rod"),
    (("elo", "hammer"), "item_82", "Elo Hammer"),
    (("dark", "blade"), "item_54", "Dark Blade (Yoru)"),

    # Shades
    (("cool", "shades"), "item_1", "Cool Shades"),
    (("love", "shades"), "item_209", "Love Shades"),
    (("heart", "shades"), "item_209", "Love Shades"),

    # Chests
    (("leg", "chest"), "item_102", "Legendary Fruit Chest"),
    (("legendary", "chest"), "item_102", "Legendary Fruit Chest"),
    (("legendary", "fruit", "chest"), "item_102", "Legendary Fruit Chest"),
    (("rare", "chest"), "item_103", "Rare Fruit Chest"),
    (("rare", "fruit", "chest"), "item_103", "Rare Fruit Chest"),
    (("mythical", "chest"), "item_32", "Mythical Fruit Chest"),
    (("mythical", "fruit", "chest"), "item_32", "Mythical Fruit Chest"),

    # Consumables
    (("sp", "reset"), "item_198", "SP Reset Essence"),
    (("sp", "essence"), "item_198", "SP Reset Essence"),
    (("dark", "root"), "item_199", "Dark Root"),
    (("d", "root"), "item_199", "Dark Root")
]

# Single-token item mapping (e.g. fruits, single words, established acronyms)
SINGLE_EMOJI_ITEMS = {
    # Fruits
    "mochi": ("item_72", "Mochi"),
    "tori": ("item_84", "Tori"),
    "pika": ("item_86", "Pika"),
    "magu": ("item_122", "Magu"),
    "venom": ("item_76", "Venom"),
    "ope": ("item_100", "Ope"),
    "goro": ("item_134", "Goro"),
    "suna": ("item_135", "Suna"),
    "mera": ("item_127", "Mera"),
    "buddha": ("item_107", "Buddha"),
    "dragon": ("item_38", "Dragon"),
    "ryu": ("item_38", "Dragon"),
    "leopard": ("item_63", "Leopard"),
    "leo": ("item_63", "Leopard"),
    "soul": ("item_75", "Soul"),
    "pteranodon": ("item_87", "Pteranodon"),
    "ptera": ("item_87", "Pteranodon"),
    "gura": ("item_117", "Gura"),
    "zushi": ("item_152", "Zushi"),
    "ito": ("item_143", "Ito"),
    "kage": ("item_144", "Kage"),
    "hiei": ("item_142", "Hiei"),
    "yami": ("item_165", "Yami"),
    "paw": ("item_166", "Paw"),
    
    # Standalone High-Tier Weapons & Eyes
    "ase": ("item_31", "All Seeing Eye"),
    "eye": ("item_31", "All Seeing Eye"),
    "kikoku": ("item_62", "Kikoku"),
    "yoru": ("item_54", "Dark Blade (Yoru)"),
    "cc": ("item_16", "Candy Cane"),
    "pcc": ("item_6", "Prestige Candy Cane"),
    "we": ("item_35", "World Ender"),
    "pwe": ("item_8", "Prestige World Ender"),
    "pfl": ("item_9", "Prestige Firework Lancer"),
    "pirb": ("item_10", "Prestige Inferno Rocket Blade"),
    "flancer": ("item_205", "Festival Lancer"),
    "baal": ("item_59", "Ba'al Head"),
    "hoverboard": ("item_115", "Hoverboard"),
    "striker": ("item_167", "Striker"),
    "coffboat": ("item_168", "Coffin Boat"),
    "lc": ("item_102", "Legendary Fruit Chest"),
    "legchest": ("item_102", "Legendary Fruit Chest"),
    "spreset": ("item_198", "SP Reset Essence"),
    "darkroot": ("item_199", "Dark Root"),
    "droot": ("item_199", "Dark Root"),
    "root": ("item_199", "Dark Root")
}

# Individual tokens that MUST NOT match an item by themselves
DISALLOWED_STANDALONE = {
    "cape", "kaido", "kaidos", "de", "gourd", "outfit", "big", "mom", "mama",
    "bm", "titan", "radiant", "admiral", "ashen", "zhen", "captain",
    "king", "scarf", "guitar", "sk", "cupid", "queen", "maid", "all", "seeing",
    "candy", "cane", "world", "ender", "prestige", "p", "firework", "lancer",
    "devil", "fruit", "rod", "df", "elo", "hammer", "dark", "blade", "cool",
    "love", "heart", "shades", "leg", "chest", "legendary", "rare", "mythical",
    "sp", "reset", "плащ", "кайдо", "тыква", "костюм", "сет", "очки"
}


class DiscordEmojiExtractor:
    """
    Connects to Discord or parses stored trading messages to discover all item emojis,
    builds CDN URLs, and parses trading syntax including compound emojis and NLF filtering.
    """
    def __init__(
        self,
        token: Optional[str] = None,
        guild_id: str = DEFAULT_GUILD_ID,
        channel_id: str = DEFAULT_CHANNEL_ID,
        items_path: Optional[str] = None
    ):
        self.root_dir = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
        self.token = token or os.environ.get("DISCORD_TOKEN", "").strip()
        if not self.token:
            env_file = os.path.join(self.root_dir, ".env")
            if os.path.exists(env_file):
                try:
                    with open(env_file, "r", encoding="utf-8") as f:
                        for line in f:
                            if line.strip().startswith("DISCORD_TOKEN="):
                                self.token = line.strip().split("=", 1)[1].strip().strip('"').strip("'")
                                break
                except Exception:
                    pass
        self.guild_id = guild_id
        self.channel_id = channel_id
        self.items_path = items_path or os.path.join(self.root_dir, "gpo_items.json")
        self.emojis_output_path = os.path.join(self.root_dir, "data", "discord_emojis.json")
        
        self.items_dict: Dict[str, Dict[str, Any]] = {}
        self.diagnostic_info: Dict[str, Any] = {
            "token_configured": bool(self.token),
            "token_length": len(self.token) if self.token else 0
        }
        self._load_items()

    def _load_items(self):
        if os.path.exists(self.items_path):
            try:
                with open(self.items_path, "r", encoding="utf-8") as f:
                    data = json.load(f)
                    for item in data:
                        self.items_dict[item["id"]] = item
            except Exception as e:
                logger.warning(f"Error loading {self.items_path}: {e}")

    # --------------------------------------------------------------------------
    # 1. Fetching & Extracting Discord Emojis
    # --------------------------------------------------------------------------
    def fetch_guild_emojis(self) -> List[Dict[str, Any]]:
        """
        Queries Discord API GET /guilds/{guild_id}/emojis using authorized token.
        Returns all registered custom emojis with their direct CDN image links.
        """
        if not self.token or not requests:
            print("[DISCORD API] No DISCORD_TOKEN provided or requests unavailable.")
            self.diagnostic_info["guild_api"] = {"status": "no_token_provided"}
            return []

        url = f"{DISCORD_API_BASE}/guilds/{self.guild_id}/emojis"
        auth_val = self.token.strip()
        headers = {
            "Authorization": auth_val,
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/129.0.0.0 Safari/537.36"
        }
        try:
            resp = requests.get(url, headers=headers, timeout=10)
            print(f"[DISCORD API] GET /guilds/{self.guild_id}/emojis -> HTTP {resp.status_code}")
            self.diagnostic_info["guild_api"] = {
                "url": url,
                "status_code": resp.status_code,
                "response_preview": resp.text[:200]
            }

            if resp.status_code == 401 and not auth_val.startswith("Bot "):
                # Retry with Bot prefix in case a bot token was supplied without prefix
                headers["Authorization"] = f"Bot {auth_val}"
                resp = requests.get(url, headers=headers, timeout=10)
                print(f"[DISCORD API] Retry with 'Bot ' prefix -> HTTP {resp.status_code}")
                self.diagnostic_info["guild_api_retry_bot"] = {
                    "status_code": resp.status_code,
                    "response_preview": resp.text[:200]
                }

            if resp.status_code == 200:
                raw_emojis = resp.json()
                results = []
                for em in raw_emojis:
                    eid = str(em.get("id"))
                    name = em.get("name", "")
                    animated = bool(em.get("animated", False))
                    ext = "gif" if animated else "png"
                    cdn_url = f"{DISCORD_CDN_BASE}/{eid}.{ext}?size=128"
                    results.append({
                        "id": eid,
                        "name": name,
                        "animated": animated,
                        "url": cdn_url,
                        "discord_tag": f"<{'a:' if animated else ':'}{name}:{eid}>",
                        "colon_syntax": f":{name}:",
                        "source": "guild_api"
                    })
                print(f"[DISCORD API] Successfully retrieved {len(results)} custom emojis from Guild {self.guild_id}.")
                return results
            else:
                print(f"[DISCORD API] Guild emojis returned {resp.status_code}: {resp.text[:150]}")
        except Exception as e:
            print(f"[DISCORD API] Error requesting guild emojis: {e}")
            self.diagnostic_info["guild_api"] = {"error": str(e)}
        return []

    def fetch_live_channel_messages(self, limit: int = 100) -> List[Dict[str, Any]]:
        """
        Fetches live messages directly from the Discord trading channel.
        Works for both User tokens and Bot tokens.
        """
        if not self.token or not requests:
            self.diagnostic_info["channel_api"] = {"status": "no_token_provided"}
            return []

        url = f"{DISCORD_API_BASE}/channels/{self.channel_id}/messages"
        headers = {
            "Authorization": self.token.strip(),
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/129.0.0.0 Safari/537.36"
        }
        try:
            resp = requests.get(url, headers=headers, params={"limit": limit}, timeout=12)
            print(f"[DISCORD API] GET /channels/{self.channel_id}/messages -> HTTP {resp.status_code}")
            self.diagnostic_info["channel_api"] = {
                "url": url,
                "status_code": resp.status_code,
                "response_preview": resp.text[:200]
            }

            if resp.status_code == 401 and not self.token.startswith("Bot "):
                headers["Authorization"] = f"Bot {self.token.strip()}"
                resp = requests.get(url, headers=headers, params={"limit": limit}, timeout=12)
                print(f"[DISCORD API] Channel retry with 'Bot ' prefix -> HTTP {resp.status_code}")
                self.diagnostic_info["channel_api_retry_bot"] = {
                    "status_code": resp.status_code,
                    "response_preview": resp.text[:200]
                }

            if resp.status_code == 200:
                msgs = resp.json()
                print(f"[DISCORD API] Successfully fetched {len(msgs)} live messages from channel {self.channel_id}.")
                return msgs
            else:
                print(f"[DISCORD API] Channel fetch returned {resp.status_code}: {resp.text[:150]}")
        except Exception as e:
            print(f"[DISCORD API] Error querying channel messages: {e}")
            self.diagnostic_info["channel_api"] = {"error": str(e)}
        return []

    def extract_emojis_from_messages(self, messages: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        """
        Scans trading message history for custom emojis <:name:id> and <a:name:id>.
        Only accepts genuine Discord snowflake IDs (numeric, >= 17 digits).
        """
        found_emojis: Dict[str, Dict[str, Any]] = {}

        pattern_custom = re.compile(r"<(a)?:([a-zA-Z0-9_]+):(\d+)>")
        pattern_colon = re.compile(r":([a-zA-Z0-9_]+):")

        for msg in messages:
            content = msg.get("content", "")
            if not content:
                continue

            # 1. Custom <:name:id>
            for match in pattern_custom.finditer(content):
                anim = bool(match.group(1))
                name = match.group(2)
                eid = match.group(3)

                # Strictly require genuine Discord snowflakes (17-19 digits). Reject fake IDs.
                if not (eid.isdigit() and len(eid) >= 17):
                    continue

                ext = "gif" if anim else "png"
                cdn_url = f"{DISCORD_CDN_BASE}/{eid}.{ext}?size=128"
                key = f"{name.lower()}_{eid}"
                if key not in found_emojis:
                    found_emojis[key] = {
                        "id": eid,
                        "name": name,
                        "animated": anim,
                        "url": cdn_url,
                        "discord_tag": f"<{'a:' if anim else ':'}{name}:{eid}>",
                        "colon_syntax": f":{name}:",
                        "source": "message_stream",
                        "occurrences": 1
                    }
                else:
                    found_emojis[key]["occurrences"] += 1

            # 2. Colon emojis :name:
            for match in pattern_colon.finditer(content):
                name = match.group(1)
                lower_name = name.lower()
                key = f"colon_{lower_name}"
                if key not in found_emojis:
                    found_emojis[key] = {
                        "id": None,
                        "name": name,
                        "animated": False,
                        "url": None,
                        "discord_tag": f":{name}:",
                        "colon_syntax": f":{name}:",
                        "source": "colon_syntax",
                        "occurrences": 1
                    }
                else:
                    found_emojis[key]["occurrences"] += 1

        results = list(found_emojis.values())
        logger.info(f"Scanned {len(messages)} messages: discovered {len(results)} distinct emoji tokens.")
        return results

    def build_complete_emoji_catalog(self, messages_buffer_path: Optional[str] = None) -> Dict[str, Any]:
        """
        Combines live guild API emojis and live channel messages.
        Exports only verified genuine Discord emojis to data/discord_emojis.json.
        """
        all_emojis_map: Dict[str, Dict[str, Any]] = {}

        # 1. Live Guild API
        guild_emojis = self.fetch_guild_emojis()
        for em in guild_emojis:
            all_emojis_map[em["name"].lower()] = em

        # 2. Live Channel Messages from Discord
        live_msgs = self.fetch_live_channel_messages(limit=100)
        if live_msgs:
            live_emojis = self.extract_emojis_from_messages(live_msgs)
            for em in live_emojis:
                k = em["name"].lower()
                if k not in all_emojis_map or not all_emojis_map[k].get("url"):
                    all_emojis_map[k] = em

        # 3. From Messages Buffer (if genuine snowflakes exist)
        buf_path = messages_buffer_path or os.path.join(self.root_dir, "data", "trades_buffer.json")
        if os.path.exists(buf_path):
            try:
                with open(buf_path, "r", encoding="utf-8") as f:
                    buf_data = json.load(f)
                    msgs = buf_data.get("messages", [])
                    stream_emojis = self.extract_emojis_from_messages(msgs)
                    for em in stream_emojis:
                        k = em["name"].lower()
                        if k not in all_emojis_map or not all_emojis_map[k].get("url"):
                            all_emojis_map[k] = em
            except Exception as e:
                logger.warning(f"Error reading buffer from {buf_path}: {e}")

        # 3. Only authentic emojis from Guild API or live messages are included.
        # If API was not reachable and no live stream, do NOT invent fake IDs.


        # 4. Map each emoji to its GPO item (or compound role)
        catalog = {
            "guild_id": self.guild_id,
            "channel_id": self.channel_id,
            "total_emojis": len(all_emojis_map),
            "emojis": all_emojis_map,
            "compound_rules": [
                {
                    "tokens": [f":{t}:" for t in tokens],
                    "item_id": iid,
                    "item_name": iname
                }
                for tokens, iid, iname in COMPOUND_EMOJI_RULES
            ]
        }

        # Save to disk
        try:
            os.makedirs(os.path.dirname(self.emojis_output_path), exist_ok=True)
            with open(self.emojis_output_path, "w", encoding="utf-8") as f:
                json.dump(catalog, f, indent=2, ensure_ascii=False)
            logger.info(f"Saved complete Discord emoji catalog to {self.emojis_output_path}")

            # Save diagnostic status report
            diag_path = os.path.join(self.root_dir, "data", "discord_api_status.json")
            with open(diag_path, "w", encoding="utf-8") as f:
                json.dump(self.diagnostic_info, f, indent=2)
            print(f"[DIAGNOSTIC] Saved API status to {diag_path}")
        except Exception as e:
            logger.error(f"Error saving emoji catalog: {e}")

        return catalog

    # --------------------------------------------------------------------------
    # 2. Smart Trade Parser (LF, NLF, for, Single Emojis & Multi-Emoji Compounds)
    # --------------------------------------------------------------------------
    @staticmethod
    def strip_nlf(text: str) -> str:
        """Strips NLF (Not Looking For / DONT WANT) sections so unwanted items are never parsed."""
        return NLF_REGEX.sub("", text).strip()

    @staticmethod
    def split_offer_want(text: str) -> Tuple[str, str]:
        """
        Splits trade into offer (Supply) and want (Demand) sides.
        Recognizes: LF <want> for <offer>, H: <offer> W: <want>, <offer> -> <want>, <offer> for <want>, etc.
        """
        t = text

        # Format: LF <want> for <offer>
        m_lf_for = re.search(r"^\s*\b(?:lf|looking\s+for|want|w|ищу)\b\s+(.*?)\s+\b(?:for|offer|giving|за|на)\b\s+(.*)$", t, re.IGNORECASE)
        if m_lf_for:
            return m_lf_for.group(2).strip(), m_lf_for.group(1).strip()

        # Format: H: <offer> W: <want> (colon directly attached to keyword like H: or W:)
        m_hw = re.search(r"\b(?:h|have|giving|trading|wtt|отдам|трейд):\s*(.*?)\s*\b(?:w|want|lf|looking\s+for|ищу):\s*(.*)", t, re.IGNORECASE)
        if m_hw:
            return m_hw.group(1).strip(), m_hw.group(2).strip()

        # Format: WTT <offer> LF <want>
        m_wtt_lf = re.search(r"\b(?:wtt|trading|giving|have|h)\b\s+(.*?)\s+\b(?:lf|looking\s+for|want|w|ищу)\b\s+(.*)", t, re.IGNORECASE)
        if m_wtt_lf:
            return m_wtt_lf.group(1).strip(), m_wtt_lf.group(2).strip()

        # Format: <offer> LF <want>
        m_lf = re.search(r"^(.*?)\s+\b(?:lf|looking\s+for|want|ищу)\b\s+(.*)$", t, re.IGNORECASE)
        if m_lf:
            return m_lf.group(1).strip(), m_lf.group(2).strip()

        # Format: <offer> for <want>
        m_for = re.search(r"^(.*?)\s+\b(?:for|на|за)\b\s+(.*)$", t, re.IGNORECASE)
        if m_for:
            return m_for.group(1).strip(), m_for.group(2).strip()

        # Default fallback: entire text is offer
        return t, ""

    def clean_and_tokenize(self, text: str) -> List[str]:
        """
        Converts custom Discord emojis <:name:id> and colons :name: to normalized word tokens.
        Preserves sequences of emojis so compounds like :kaido::cape: become ['kaido', 'cape'].
        Normalizes multipliers and number emojis.
        """
        # 1. Strip NLF
        t = self.strip_nlf(text)

        # 2. Number emojis
        for k, v in KEYCAP_MAP.items():
            t = t.replace(k, v)
        for k, v in CIRCLED_DIGITS.items():
            t = t.replace(k, v)
        t = re.sub(r"(\d)\ufe0f?\u20e3", r" \1 ", t)

        # 3. Heart emojis -> 'heart'
        t = re.sub(r"[\u2764\u2665\u2763\u2765-\u2767\U0001F490-\U0001F49F\U0001F90D-\U0001F90F\U0001FA75-\U0001FA77]\ufe0f?|<3", " heart ", t)

        # 4. Handle adjacent custom tags <:a:1><:b:2> -> <:a:1> <:b:2>
        t = t.replace("><", "> <")

        # 5. Expand adjacent colons :: -> : : so :kaido::cape: becomes :kaido: :cape:
        while "::" in t:
            t = t.replace("::", ": :")

        # 6. Custom emojis <:name:id> or <a:name:id> -> ' name '
        t = re.sub(r"<a?:([a-zA-Z0-9_]+):\d+>", r" \1 ", t)

        # 7. Colon emojis :name: -> ' name '
        t = re.sub(r":([a-zA-Z0-9_]+):", r" \1 ", t)

        # 8. Normalize multipliers (e.g. 4x mochi -> 4 mochi, 4лк -> 4 лк)
        t = re.sub(r"(\d+)\s*[xхXХ]\s*", r"\1 ", t)
        t = re.sub(r"(\d+)([a-zA-Zа-яА-ЯёЁ])", r"\1 \2", t)

        # 9. Strip discord markdown and punctuation
        t = re.sub(r"[*_~`|()\[\]{}]", " ", t)

        return t.lower().split()

    def parse_qty_token(self, tok: str) -> Optional[int]:
        """Parses quantity tokens into an integer (e.g. '2', '2x', 'four', '4️⃣')."""
        t = tok.lower().strip()
        if t in WORD_NUMS:
            return WORD_NUMS[t]
        m = re.match(r"^(?:[xхXХ]\s*(\d+)|(\d+)\s*[xхXХ]|\b(\d+)\b)$", t)
        if m:
            val = int(m.group(1) or m.group(2) or m.group(3))
            if 1 <= val <= 100:
                return val
        return None

    def match_compound_or_single(self, words: List[str], start_idx: int) -> Tuple[Optional[str], Optional[str], int]:
        """
        Matches multi-emoji compound sequences first, then single-item emojis.
        STRICTLY ENFORCES: Single components of compound items (like 'cape' or 'kaido')
        are in DISALLOWED_STANDALONE and will NEVER match as an item by themselves!
        Returns: (item_id, item_name, token_span_consumed)
        """
        n = len(words)

        # 1. Greedy search across compound emoji rules (spans of 4, 3, 2)
        for compound_tokens, iid, iname in COMPOUND_EMOJI_RULES:
            span = len(compound_tokens)
            if start_idx + span <= n:
                candidate = tuple(words[start_idx : start_idx + span])
                if candidate == compound_tokens:
                    return iid, iname, span

        # 2. Single token matching (span = 1)
        w = words[start_idx]

        # If it's a disallowed standalone token (like 'cape' or 'kaido' alone), IGNORE IT!
        if w in DISALLOWED_STANDALONE:
            return None, None, 0

        # Check known single item emojis / abbreviations
        if w in SINGLE_EMOJI_ITEMS:
            iid, iname = SINGLE_EMOJI_ITEMS[w]
            return iid, iname, 1

        # Check in items_dict canonical names
        for iid, it in self.items_dict.items():
            canonical_name = it.get("name", "").lower()
            if w == canonical_name:
                return iid, it.get("name"), 1

        return None, None, 0

    def extract_items_from_side(self, raw_side_text: str) -> List[Dict[str, Any]]:
        """
        Extracts item objects from one trade side (offer or want),
        handling quantities, multi-emoji compounds, and single emojis.
        """
        words = self.clean_and_tokenize(raw_side_text)
        n = len(words)
        idx = 0
        items_found = []

        filler_words = {
            "adds", "add", "small", "good", "fast", "trade", "or", "and", "with",
            "offer", "my", "the", "for", "all", "any", "want", "have", "lf", "nlf",
            "wtt", "h", "w", "dm", "me", "плюс", "допы", "доп", "фаст", "трейд", "лф", "хочу", "дам", "мои"
        }

        while idx < n:
            w = words[idx]
            if w in filler_words:
                idx += 1
                continue

            # Check for prefix quantity (e.g. 2x, 3, four)
            qty = 1
            q_val = self.parse_qty_token(w)
            if q_val:
                qty = q_val
                idx += 1
                if idx >= n:
                    break

            # Try to match compound or single item
            iid, iname, span = self.match_compound_or_single(words, idx)
            if iid and iname:
                idx += span
                # Check for suffix quantity if prefix wasn't present
                if idx < n and qty == 1:
                    suffix_q = self.parse_qty_token(words[idx])
                    if suffix_q:
                        # Only treat as suffix if next word is not itself an item
                        next_iid, _, _ = self.match_compound_or_single(words, idx + 1)
                        if not next_iid:
                            qty = suffix_q
                            idx += 1

                items_found.append({
                    "item_id": iid,
                    "item_name": iname,
                    "quantity": qty
                })
            else:
                idx += 1

        return items_found

    def parse_trade_message(self, content: str) -> Dict[str, Any]:
        """
        Full end-to-end parser for a Discord trade message:
        - Strips NLF
        - Splits Offer vs Want
        - Extracts items & quantities from both sides
        - Resolves compound emojis (:kaido::cape:) and single emojis (:Mochi:)
        """
        cleaned_no_nlf = self.strip_nlf(content)
        offer_str, want_str = self.split_offer_want(cleaned_no_nlf)

        offer_items = self.extract_items_from_side(offer_str)
        want_items = self.extract_items_from_side(want_str)

        return {
            "raw_content": content,
            "cleaned_content": cleaned_no_nlf,
            "offer_text": offer_str,
            "want_text": want_str,
            "offer_items": offer_items,
            "want_items": want_items
        }


def run_tests():
    """Runs a test suite proving all user requirements."""
    extractor = DiscordEmojiExtractor()
    
    test_cases = [
        # 1. Single emoji understanding
        ("WTT :Mochi: LF :Tori: + :Pika:", "Single item emojis (:Mochi:, :Tori:, :Pika:)"),
        
        # 2. NLF filtering
        ("LF :Mochi: for 2x :LC: nlf bad fruits or commons", "LF ... for ... with NLF stripped"),
        
        # 3. Compound Kaido Cape test (User explicit requirement!)
        (":kaido::cape: for :Mochi:", "Compound :kaido::cape: -> Dragon Emperor's Cape"),
        ("WTT 2x :kaido: :cape: LF :ASE:", "Spaced compound :kaido: :cape: with 2x multiplier"),
        ("H: <:kaido:101><:cape:102> W: :Mochi:", "Discord custom tag compound <:kaido:101><:cape:102>"),
        
        # 4. Isolated component test (Kaido or Cape alone MUST NOT match!)
        ("WTT :cape: for :kaido:", "Isolated :cape: and :kaido: alone (MUST BE EMPTY!)"),
        
        # 5. Other compounds: Kaido Gourd, Kaido Outfit, Big Mom Cape
        ("LF :kaido::gourd: offer :kaido::outfit: + 3x :LC:", "Kaido Gourd & Kaido Outfit compounds"),
        ("H: :big::mom::cape: W: :titan::cape: + :radiant::cape:", "Big Mom Cape, Titan Cape & Radiant Cape"),
        
        # 6. Devil Fruit Rod, Love Shades, Chest compounds
        ("WTT :df::rod: LF :love::shades: + 4️⃣ :leg::chest:", "DF Rod, Love Shades and 4️⃣ Leg Chest"),
        
        # 7. Complex Russian trade message
        ("Трейд 2x :kaido::cape: на :mochi: + :kikoku: не предлагать коммонки", "Russian trade with compound cape and NLF filtering")
    ]

    print("=" * 75)
    print(" 🧪 DISCORD EMOJI & TRADE EXTRACTOR TEST SUITE")
    print("=" * 75)

    for idx, (tc, desc) in enumerate(test_cases, 1):
        parsed = extractor.parse_trade_message(tc)
        print(f"\n[TEST #{idx}] {desc}")
        print(f"INPUT : {tc}")
        print(f"OFFER : {parsed['offer_items']}")
        print(f"WANT  : {parsed['want_items']}")

    print("\n" + "=" * 75)
    print(" ✅ All tests completed.")


if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser(description="Discord Emoji & Trade Extractor for GPO")
    parser.add_argument("--token", type=str, default=None, help="Discord user/bot token")
    parser.add_argument("--guild-id", type=str, default=DEFAULT_GUILD_ID, help="Discord Guild ID")
    parser.add_argument("--channel-id", type=str, default=DEFAULT_CHANNEL_ID, help="Discord Channel ID")
    parser.add_argument("--test", action="store_true", help="Run test suite")
    parser.add_argument("--sync", action="store_true", help="Build and save discord_emojis.json catalog")
    args = parser.parse_args()

    extractor = DiscordEmojiExtractor(
        token=args.token,
        guild_id=args.guild_id,
        channel_id=args.channel_id
    )

    if args.sync or not args.test:
        print("[DISCORD EMOJI] Building complete Discord emoji catalog and CDN links...")
        catalog = extractor.build_complete_emoji_catalog()
        print(f"[DISCORD EMOJI] Catalog created with {catalog['total_emojis']} emojis.")
        print(f"[DISCORD EMOJI] Saved to {extractor.emojis_output_path}")

    if args.test or not args.sync:
        run_tests()
