"""
GPO Strictly Emoji-Only Trade Parser for Grand Piece Online.
Игнорирует обычный текст и рекламу кланов. Работает исключительно как лексер
Discord-эмодзи (<:name:id>) и системных Unicode-символов трейдинга.
"""

import os
import re
import sys
import json
import logging
from typing import List, Dict, Any, Tuple, Optional, Set

if hasattr(sys.stdout, "reconfigure"):
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger("TradeParser")

# Регулярное выражение, которое извлекает эмодзи, спецсимволы, множители (X10, 🇰) и шорткоды (:Name:)
TOKEN_PATTERN = re.compile(
    r"<a?:([a-zA-Z0-9_]+):\d+>"                                        # 1. Кастомные Discord эмодзи <:name:id>
    r"|:([a-zA-Z0-9_]{2,32}):"                                         # 2. Текстовые шорткоды эмодзи :SoulKingGuitar:
    r"|(\d\ufe0f?\u20e3|🔟|[①-⑩❶-❿➀-➉➊-➓])"                          # 3. Цифровые эмодзи (2️⃣, 🔟, ④)
    r"|(?:(?<=\s)|(?<=>))([xX]\d{1,4})(?=\s|<|$)"                      # 4. Явные множители после эмодзи (X10, x5)
    r"|(\d{1,4}[kKmM])\b"                                              # 5. Текстовые числа с k/m (800k, 2m)
    r"|(🍶|🇻|🇪|🇶|🇧|🇴|🇬|🇰|🇲|🪽|🫴|🛡️|🛡|❓|❔|➡️|➡|👉|▶️|✨|💂|🐌|🐒|🐵|➕)" # 6. Структурные и предметные Unicode эмодзи
    r"|([\u2764\u2665\u2763\U0001F490-\U0001F49F\U0001F90D-\U0001F90F\U0001FA75-\U0001FA77]\ufe0f?)" # 7. Сердца
    r"|(\n|\|)"                                                        # 8. Перенос строки или вертикальный разделитель |
)

UNICODE_DIGITS: Dict[str, int] = {
    "0️⃣": 0, "1️⃣": 1, "2️⃣": 2, "3️⃣": 3, "4️⃣": 4,
    "5️⃣": 5, "6️⃣": 6, "7️⃣": 7, "8️⃣": 8, "9️⃣": 9, "🔟": 10,
    "0\u20e3": 0, "1\u20e3": 1, "2\u20e3": 2, "3\u20e3": 3, "4\u20e3": 4,
    "5\u20e3": 5, "6\u20e3": 6, "7\u20e3": 7, "8\u20e3": 8, "9\u20e3": 9,
    "①": 1, "②": 2, "③": 3, "④": 4, "⑤": 5, "⑥": 6, "⑦": 7, "⑧": 8, "⑨": 9, "⑩": 10,
    "❶": 1, "❷": 2, "❸": 3, "❹": 4, "❺": 5, "❻": 6, "❼": 7, "❽": 8, "❾": 9, "❿": 10,
    "➀": 1, "➁": 2, "➂": 3, "➃": 4, "➄": 5, "➅": 6, "➆": 7, "➇": 8, "➈": 9, "➉": 10,
    "➊": 1, "➋": 2, "➌": 3, "➍": 4, "➎": 5, "➏": 6, "➐": 7, "➑": 8, "➒": 9, "➓": 10,
}

WORD_NUM_TOKENS: Dict[str, int] = {
    "zero": 0, "one": 1, "two": 2, "three": 3, "four": 4,
    "five": 5, "six": 6, "seven": 7, "eight": 8, "nine": 9, "ten": 10,
}

# Операторы и модификаторы внутри эмодзи-сообщений
FOR_TOKENS = {"for", "arrow", "to", "right_arrow", "rightarrow"}
LF_TOKENS = {"lf", "looking_for", "lookingfor", "want"}
OFFER_PLACEHOLDERS = {
    "offer", "offers", "any", "anything", "question", "question_mark",
    "give_offer", "trade", "fair_trade", "upgrade", "downgrade"
}
NLF_TOKENS = {"nlf", "not_looking_for", "no_want", "dont_want"}
OR_TOKENS = {"or", "slash"}
CURRENCY_TOKENS = {"peli", "bounty", "2mi", "1mi", "500k"}

IGNORE_MODIFIERS = {
    "adds", "add", "small_adds", "smalladds", "strong_adds", "strongadds",
    "good_adds", "big_adds", "max", "wtt", "trading", "have", "h", "fast",
    "dm", "pm", "plus", "and", "with", "unobs", "how_many", "weapon", "random"
}


class GPOTradeParser:
    """
    Строгий парсер эмодзи-трейдов GPO.
    Связывает названия и комбинации эмодзи с предметами из gpo_items.json.
    """

    def __init__(self, items_path: Optional[str] = None):
        base_dir = os.path.dirname(os.path.abspath(__file__))
        self.items_path = items_path or os.path.join(base_dir, "..", "gpo_items.json")

        self.items_dict: Dict[str, Dict[str, Any]] = {}
        self.seq_map: Dict[Tuple[str, ...], str] = {}
        self.name_to_id: Dict[str, str] = {}
        self.abbr_to_id: Dict[str, str] = {}

        self._load_items_and_build_rules()

    @staticmethod
    def _norm(s: str) -> str:
        """Нормализует строку в нижний регистр с одиночными подчеркиваниями."""
        return re.sub(r"[^a-z0-9]+", "_", s.lower()).strip("_")

    @staticmethod
    def _split_camel_and_norm(s: str) -> Tuple[str, ...]:
        """Разбивает CamelCase и подчеркивания на отдельные слова: 'BatSwarm' -> ('bat', 'swarm')."""
        s_spaced = re.sub(r"([a-z0-9])([A-Z])", r"\1_\2", s)
        normed = re.sub(r"[^a-z0-9]+", "_", s_spaced.lower()).strip("_")
        return tuple(p for p in normed.split("_") if p)

    def _find_id_by_keywords(self, *keywords: str, fallback: str) -> str:
        """
        Безопасный поиск ID предмета в gpo_items.json:
        1. Точное совпадение нормализованного имени.
        2. Точное совпадение аббревиатуры.
        3. Пословное вхождение (без ложных срабатываний вроде 'mera' внутри 'emerald').
        """
        for kw in keywords:
            kw_norm = self._norm(kw)
            if kw_norm in self.name_to_id:
                return self.name_to_id[kw_norm]
            if kw_norm in self.abbr_to_id:
                return self.abbr_to_id[kw_norm]

        for kw in keywords:
            kw_words = set(self._norm(kw).split("_"))
            if not kw_words:
                continue
            for name_norm, iid in self.name_to_id.items():
                name_words = set(name_norm.split("_"))
                if kw_words.issubset(name_words):
                    return iid

        return fallback

    def _register_pattern(self, item_id: str, *token_sequences: Tuple[str, ...]):
        if not item_id:
            return
        for seq in token_sequences:
            norm_seq = tuple(t.lower().strip("_") for t in seq if t.strip("_"))
            if norm_seq:
                self.seq_map[norm_seq] = item_id
                # Также регистрируем склеенный вариант без подчеркиваний (например, ('batswarm',))
                compact = "".join(t.replace("_", "") for t in norm_seq)
                if len(norm_seq) == 1 and compact != norm_seq[0]:
                    self.seq_map[(compact,)] = item_id
                # И развернутый по словам вариант
                flat = tuple(part for t in norm_seq for part in t.split("_") if part)
                if flat != norm_seq:
                    self.seq_map[flat] = item_id

    def _ensure_virtual_item(self, item_id: str, name: str, category: str = "misc", value: float = 0.0) -> str:
        """
        Регистрирует предмет в памяти парсера, если его еще нет в gpo_items.json,
        чтобы он никогда не подменялся чужим ID (как было с Race Reroll -> Dominus Empyreus).
        """
        if item_id not in self.items_dict:
            self.items_dict[item_id] = {
                "id": item_id,
                "name": name,
                "nameRu": name,
                "abbreviation": name,
                "category": category,
                "value": value,
            }
        return item_id

    def _load_items_and_build_rules(self):
        # 1. Загружаем gpo_items.json
        if os.path.exists(self.items_path):
            try:
                with open(self.items_path, "r", encoding="utf-8") as f:
                    items_list = json.load(f)
                    for it in items_list:
                        iid = it["id"]
                        self.items_dict[iid] = it
                        name_norm = self._norm(it.get("name", ""))
                        if name_norm:
                            self.name_to_id[name_norm] = iid
                            self.seq_map[(name_norm,)] = iid
                            self.seq_map[tuple(name_norm.split("_"))] = iid

                        abbr = self._norm(it.get("abbreviation", ""))
                        if abbr and len(abbr) >= 2:
                            self.abbr_to_id[abbr] = iid
                            self.seq_map[(abbr,)] = iid
            except Exception as e:
                logger.error(f"Ошибка чтения {self.items_path}: {e}")

        # 2. Привязка точных ID из gpo_items.json
        # --- Все виды All Seeing Eye ---
        id_ase          = self._find_id_by_keywords("All Seeing Eye", fallback="item_31")
        id_case         = self._find_id_by_keywords("Chromatic All Seeing Eye", fallback="item_14")
        id_sase         = self._find_id_by_keywords("All Seeing Shamrock", fallback="item_18")
        id_egg_ase      = self._find_id_by_keywords("All Seeing Egg", fallback="item_24")
        id_blossom_ase  = self._find_id_by_keywords("All Seeing Blossom", fallback="item_25")
        id_baal_ase     = self._find_id_by_keywords("All Seeing Ba’al", "All Seeing Ba'al", fallback="item_27")
        id_holly_ase    = self._find_id_by_keywords("All Seeing Holly", fallback="item_28")
        id_cupid_ase    = self._find_id_by_keywords("Cupid’s All Seeing Eye", "Cupid's All Seeing Eye", fallback="item_29")

        # --- Kaido & Big Mama & Marine ---
        id_kaido_cape   = self._find_id_by_keywords("Dragon Emperor’s Cape", "Dragon Emperor's Cape", fallback="item_104")
        id_kaido_gourd  = self._find_id_by_keywords("Dragon Emperor’s Gourd", "Dragon Emperor's Gourd", fallback="item_105")
        id_kaido_outfit = self._find_id_by_keywords("Dragon Emperor’s Outfit", "Dragon Emperor's Outfit", fallback="item_108")
        id_bm_cape      = self._find_id_by_keywords("Big Mama’s Cape", "Big Mama's Cape", fallback="item_119")
        id_bm_fit       = self._find_id_by_keywords("Big Mama’s Outfit (Male)", "Big Mama's Outfit", fallback="item_120")
        id_bm_hat       = self._find_id_by_keywords("Big Mama’s Hat", "Big Mama's Hat", fallback="item_124")
        id_marine_cape  = self._find_id_by_keywords("Marine Cape", fallback="item_2")
        id_marine_cap   = self._find_id_by_keywords("Marine Cap", fallback="item_3")

        # --- Оружие ---
        id_cc           = self._find_id_by_keywords("Candy Cane", fallback="item_16")
        id_pcc          = self._find_id_by_keywords("Prestige Candy Cane", fallback="item_6")
        id_icc          = self._find_id_by_keywords("Iceborn Candy Cane", fallback="item_11")
        id_we           = self._find_id_by_keywords("World Ender", fallback="item_35")
        id_pwe          = self._find_id_by_keywords("Prestige World Ender", fallback="item_8")
        id_hwe          = self._find_id_by_keywords("Hollow’s World Ender", "Hollow's World Ender", fallback="item_52")
        id_yoru         = self._find_id_by_keywords("Dark Blade ✦YORU", "Dark Blade", fallback="item_54")
        id_kikoku       = self._find_id_by_keywords("Kikoku", fallback="item_62")
        id_sos          = self._find_id_by_keywords("Sickle of Sorrow", fallback="item_56")
        id_flower_sword = self._find_id_by_keywords("Flower Sword", fallback="item_64")
        id_fbouquet     = self._find_id_by_keywords("Flower Bouquet", fallback="item_36")
        id_fest_lancer  = self._find_id_by_keywords("Festival Lancer", fallback="item_205")
        id_fest_shield  = self._find_id_by_keywords("Festival Shield", fallback="item_81")
        id_fl           = self._find_id_by_keywords("Firework Lancer", fallback="item_70")
        id_fd           = self._find_id_by_keywords("Firework Daggers", fallback="item_111")
        id_irb          = self._find_id_by_keywords("Inferno Rocket Blade", fallback="item_69")
        id_pirb         = self._find_id_by_keywords("Prestige Inferno Rocket Blade", fallback="item_10")
        id_thunder_club = self._find_id_by_keywords("Thunder Club", fallback="item_45")
        id_tttc         = self._find_id_by_keywords("Tung Tung Thunder Club", fallback="item_44")
        id_df_rod       = self._find_id_by_keywords("Devil Fruit Rod", fallback="item_47")
        id_odm_rod      = self._find_id_by_keywords("ODM Rod", fallback="item_80")
        id_ls_rod       = self._find_id_by_keywords("Lovestruck Rod", fallback="item_116")
        id_isoh         = self._find_id_by_keywords("Inverted Spear Of Heaven", fallback="item_46")
        id_sguns        = self._find_id_by_keywords("Stark Guns", fallback="item_61")
        id_cbow         = self._find_id_by_keywords("Cupid’s Bow", "Cupid's Bow", fallback="item_140")
        id_bbow         = self._find_id_by_keywords("Blessed Cupid’s Bow", "Blessed Cupid's Bow", fallback="item_48")
        id_chakram      = self._find_id_by_keywords("Cupid’s Chakram", "Cupid's Chakram", fallback="item_103")
        id_pcchakram    = self._find_id_by_keywords("Prestige Cupid's Chakram", fallback="item_5")
        id_cwand        = self._find_id_by_keywords("Cupid’s Wand", "Cupid's Wand", fallback="item_129")
        id_cbattleaxe   = self._find_id_by_keywords("Cupid’s Battleaxe", "Cupid's Battleaxe", fallback="item_172")
        id_mtrident     = self._find_id_by_keywords("Mochi Trident", fallback="item_113")
        id_ntrident     = self._find_id_by_keywords("Neptune's Trident", fallback="item_164")
        id_sscepter     = self._find_id_by_keywords("Snowcap Scepter", fallback="item_42")
        id_jscythe      = self._find_id_by_keywords("Demon Jester's Scythe", fallback="item_97")
        id_elo          = self._find_id_by_keywords("Elo’s Sledgehammer", "Elo's Sledgehammer", fallback="item_82")
        id_bcs          = self._find_id_by_keywords("Blo’s Crimson Sledgehammer", fallback="item_90")
        id_bsledge      = self._find_id_by_keywords("Blo’s Sledgehammer", fallback="item_96")
        id_boneshiver   = self._find_id_by_keywords("Boneshiver", fallback="item_152")
        id_shusui       = self._find_id_by_keywords("Shusui", fallback="item_179")
        id_napoleon     = self._find_id_by_keywords("Soul Cleaver", fallback="item_41")
        id_race         = self._find_id_by_keywords("Roger’s Ace", "Roger's Ace", fallback="item_106")
        id_ibk          = self._find_id_by_keywords("Iceborn Katana", fallback="item_149")
        id_irapier      = self._find_id_by_keywords("Iceborn Rapier", fallback="item_142")
        id_iblade       = self._find_id_by_keywords("Iceborn Blade", fallback="item_169")
        id_igunblade    = self._find_id_by_keywords("Iceborn Gunblade", fallback="item_170")
        id_idaggers     = self._find_id_by_keywords("Iceborn Daggers", fallback="item_171")
        id_srapier      = self._find_id_by_keywords("Swordfish Rapier", fallback="item_143")
        id_sanchor      = self._find_id_by_keywords("Sunken Anchor", fallback="item_147")
        id_scane        = self._find_id_by_keywords("Soul Cane", fallback="item_138")
        id_hskewer      = self._find_id_by_keywords("Helix Skewer", fallback="item_137")
        id_gpumbrella   = self._find_id_by_keywords("Ghost Princess’s Umbrella", fallback="item_176")
        id_vpipe        = self._find_id_by_keywords("Vrael’s Pipe", fallback="item_181")
        id_verity       = self._find_id_by_keywords("Verity", fallback="item_verity")

        # --- Prestige оружие и мешки ---
        id_pfl          = self._find_id_by_keywords("Prestige Firework Lancer", fallback="item_9")
        id_pfd          = self._find_id_by_keywords("Prestige Firework Daggers", fallback="item_15")
        id_pfrl         = self._find_id_by_keywords("Prestige Firework Rocket Launcher", fallback="item_20")
        id_pbag         = self._find_id_by_keywords("Prestige Fruitbag", fallback="item_13")
        id_sfbag        = self._find_id_by_keywords("Spare Fruit Bag", fallback="item_121")

        # --- Аксессуары, ауры и костюмы ---
        id_tsa          = self._find_id_by_keywords("Titan Shifter’s Aura", "Titan Shifter's Aura", fallback="item_22")
        id_hagoromo     = self._find_id_by_keywords("Leo's Inferno Hagoromo", fallback="item_17")
        id_mpow         = self._find_id_by_keywords("Mega-Pow", fallback="item_37")
        id_amp          = self._find_id_by_keywords("Anomalized Mega-Pow", fallback="item_12")
        id_bos          = self._find_id_by_keywords("Brand of Sacrifice", fallback="item_39")
        id_nfa          = self._find_id_by_keywords("Nightfall Aura", fallback="item_40")
        id_nfs          = self._find_id_by_keywords("Nightfall Shroud", fallback="item_51")
        id_nfhs         = self._find_id_by_keywords("Nightfall Half Shroud", fallback="item_77")
        id_sks          = self._find_id_by_keywords("Soul King’s Scarf", "Soul King's Scarf", fallback="item_30")
        id_skg          = self._find_id_by_keywords("Soul King's Guitar", fallback="item_74")
        id_skhat        = self._find_id_by_keywords("Soul King’s Tophat", fallback="item_191")
        id_tbg          = self._find_id_by_keywords("True Ba'al's Guard", fallback="item_99")
        id_res_head     = self._find_id_by_keywords("Resurrected Ba'al's Head", fallback="item_59")
        id_hob          = self._find_id_by_keywords("Head of Ba'al", fallback="item_71")
        id_skeletal     = self._find_id_by_keywords("Dark Skeletal Shark Mask", fallback="item_91")
        id_hfang        = self._find_id_by_keywords("Hollow’s Fang", "Hollow's Fang", fallback="item_95")
        id_neko         = self._find_id_by_keywords("Snoozy Neko", fallback="item_85")
        id_coyote       = self._find_id_by_keywords("Coyote Outfit", fallback="item_50")
        id_toj_fit      = self._find_id_by_keywords("Titan of Justice’s Outfit", fallback="item_163")
        id_toj_cape     = self._find_id_by_keywords("Titan of Justice’s Cape", fallback="item_162")
        id_hfit         = self._find_id_by_keywords("Hawk Eye’s Outfit", "Hawk Eye's Outfit", fallback="item_182")
        id_hhat         = self._find_id_by_keywords("Hawkeye's Hat", fallback="item_150")
        id_rfit         = self._find_id_by_keywords("Roger’s Outfit", "Roger's Outfit", fallback="item_125")
        id_rhat         = self._find_id_by_keywords("Roger’s Hat", "Roger's Hat", fallback="item_151")
        id_jfit         = self._find_id_by_keywords("Jester’s Outfit", "Jester's Outfit", fallback="item_21")
        id_jhat         = self._find_id_by_keywords("Jester’s Hat", "Jester's Hat", fallback="item_115")
        id_jbox         = self._find_id_by_keywords("Jester Box", fallback="item_131")
        id_mescarf      = self._find_id_by_keywords("Mochi Emperor’s Scarf", fallback="item_114")
        id_tdrums       = self._find_id_by_keywords("Tomoe Drums", fallback="item_180")
        id_kcore        = self._find_id_by_keywords("Sea Serpent's Core & Kraken Core", fallback="item_136")
        id_bswarm       = self._find_id_by_keywords("Bat Swarm", fallback="item_101")
        id_tsss         = self._find_id_by_keywords("Triple Strongest Slash Scroll", fallback="item_175")
        id_trc          = self._find_id_by_keywords("Time-Rift Capsule", fallback="item_55")
        id_tailor       = self._find_id_by_keywords("Special Tailor Token", fallback="item_168")
        id_tsc          = self._find_id_by_keywords("Tung Sahur Costume", fallback="item_112")
        id_sgc          = self._find_id_by_keywords("Supreme Giftbox Crown", fallback="item_88")
        id_de           = self._find_id_by_keywords("Dominus Empyreus", fallback="item_195")
        id_du           = self._find_id_by_keywords("Dominus Ultimus", fallback="item_19")
        id_banana       = self._find_id_by_keywords("Epic Banana", fallback="item_204")
        id_lbh          = self._find_id_by_keywords("Love Boppers Headband", fallback="item_210")
        id_cheadband    = self._find_id_by_keywords("Cupid’s Headband", "Cupid's Headband", fallback="item_141")
        id_cmask        = self._find_id_by_keywords("Cupid Mask", fallback="item_173")
        id_shat         = self._find_id_by_keywords("Santa’s Hat", fallback="item_66")
        id_sbells       = self._find_id_by_keywords("Santa’s Bells", fallback="item_148")
        id_shelm        = self._find_id_by_keywords("Sunken Helmet", fallback="item_132")
        id_sarmor       = self._find_id_by_keywords("Sunken Armor", fallback="item_174")
        id_eba          = self._find_id_by_keywords("Endbringer Armor", fallback="item_110")
        id_azure_armor  = self._find_id_by_keywords("Kraken Armor Set (Azure)", fallback="item_92")
        id_azure_blade  = self._find_id_by_keywords("Kraken Blade (Azure)", fallback="item_93")

        # --- Крылья ---
        id_vqw          = self._find_id_by_keywords("Virtuous Cupid Queen's Wings", fallback="item_57")
        id_beqw         = self._find_id_by_keywords("Blessed Exalted Cupid Queen’s Wings", fallback="item_23")
        id_ewings       = self._find_id_by_keywords("Exalted Cupid Queen’s Wings", fallback="item_67")
        id_qwings       = self._find_id_by_keywords("Cupid Queen’s Wings", fallback="item_78")
        id_ebw          = self._find_id_by_keywords("Endbringer Wings", fallback="item_83")

        # --- Валькирии ---
        id_ev           = self._find_id_by_keywords("Emerald Valkyrie", fallback="item_197")
        id_stv          = self._find_id_by_keywords("Sparkle Time Valkyrie", fallback="item_196")
        id_iv           = self._find_id_by_keywords("Ice Valkyrie", fallback="item_198")
        id_vv           = self._find_id_by_keywords("Violet Valkyrie", fallback="item_199")
        id_bv           = self._find_id_by_keywords("Blackvalk", fallback="item_200")
        id_vh           = self._find_id_by_keywords("Valkyrie Helm", fallback="item_201")

        # --- Cupid предметы ---
        id_cupid_scarf  = self._find_id_by_keywords("Cupid Queen’s Scarf", "Cupid's Scarf", fallback="item_94")
        id_cupid_outfit = self._find_id_by_keywords("Cupid Queen’s Outfit", "Cupid's Outfit", fallback="item_79")
        id_cqmaid       = self._find_id_by_keywords("Cupid Queen's Maid Outfit", fallback="item_7")
        id_maid_fit     = self._find_id_by_keywords("Maid Outfit", fallback="item_109")
        id_bscarf       = self._find_id_by_keywords("Blessed Cupid Queen’s Scarf", fallback="item_43")
        id_bqfit        = self._find_id_by_keywords("Blessed Exalted Cupid Queen Outfit", fallback="item_49")
        id_eqfit        = self._find_id_by_keywords("Exalted Cupid Queen Outfit", fallback="item_98")

        # --- Транспорт ---
        id_cboat        = self._find_id_by_keywords("Coffin Boat", fallback="item_211")
        id_hpod         = self._find_id_by_keywords("Hover Pod", fallback="item_65")
        id_hb           = self._find_id_by_keywords("Hoverboard", fallback="item_213")
        id_striker      = self._find_id_by_keywords("Striker", fallback="item_212")
        id_fboat        = self._find_id_by_keywords("Flamingo Boat", fallback="item_68")

        # --- Очки и кролики ---
        id_cool_shades  = self._find_id_by_keywords("Cool Shades", fallback="item_1")
        id_love_shades  = self._find_id_by_keywords("Love Shades", fallback="item_209")
        id_rad_shades   = self._find_id_by_keywords("Radiant Shades", fallback="item_118")
        id_don_shades   = self._find_id_by_keywords("Donmingo’s Shades", fallback="item_183")
        id_sakamoto     = self._find_id_by_keywords("Sakamoto Glasses", fallback="item_4")
        id_bunyo        = self._find_id_by_keywords("Bunyo The Bunny", fallback="item_34")
        id_hopiyo       = self._find_id_by_keywords("Hopiyo The Bunny", fallback="item_53")
        id_yukio        = self._find_id_by_keywords("Yukio The Bunny", fallback="item_32")

        # --- Сундуки и расходники ---
        id_lc           = self._find_id_by_keywords("Legendary Fruit Chest", fallback="item_102")
        id_mc           = self._find_id_by_keywords("Mythical Fruit Chest", fallback="item_58")
        id_rc           = self._find_id_by_keywords("Rare Fruit Chest", fallback="item_208")
        id_10mc         = self._find_id_by_keywords("10x  Mythical Fruit Chest", "10x Mythical Fruit Chest", fallback="item_26")
        id_10lc         = self._find_id_by_keywords("10x Legendary Fruit Chest", fallback="item_60")
        id_10rc         = self._find_id_by_keywords("10x Rare Fruit Chest", fallback="item_207")
        id_fish_bait    = self._find_id_by_keywords("300x  Legendary Fish Bait", "Legendary Fish Bait", fallback="item_73")
        id_sp           = self._find_id_by_keywords("SP Reset Essence", fallback="item_194")
        id_droot        = self._find_id_by_keywords("Dark Root", fallback="item_193")

        # --- Виртуальные предметы (которых нет в gpo_items.json, чтобы они не затирали чужие ID) ---
        id_race_reroll  = self._ensure_virtual_item("item_race_reroll", "Race Reroll", "misc", 10.0)
        id_verity       = self._ensure_virtual_item("item_verity", "Verity", "weapons", 5000.0)
        id_lc_bp        = self._ensure_virtual_item("item_lc_blueprint", "Legendary Chest Blueprint", "misc", 262.0)
        id_coyote_set   = self._ensure_virtual_item("item_coyote_set", "Coyote Set", "outfits", 6400.0)
        id_kaido_set    = self._ensure_virtual_item("item_kaido_set", "Dragon Emperor's Set", "outfits", 700.0)
        id_sea_mask     = self._ensure_virtual_item("item_sea_mask", "Sea Serpent's Mask", "accessories", 100.0)
        id_snail        = self._ensure_virtual_item("item_merchant_snail", "Merchant Transponder Snail", "misc", 300.0)

        # 3. Регистрация строгих паттернов и комбинаций токенов
        # --- Все виды All Seeing Eye ---
        self._register_pattern(id_ase, ("ase",), ("all_seeing_eye",))
        self._register_pattern(id_case, ("case",), ("chromatic_ase",), ("chromatic", "ase"))
        self._register_pattern(id_sase, ("sase",), ("shamrock_ase",), ("shamrock", "ase"))
        # ВАЖНО: <:blo_ase:...> — это All Seeing Egg (item_24), а <:Blossom_ASE:...> — All Seeing Blossom (item_25)!
        self._register_pattern(id_egg_ase, ("blo_ase",), ("egg_ase",), ("all_seeing_egg",), ("egg", "ase"))
        self._register_pattern(id_blossom_ase, ("blossom_ase",), ("blase",), ("blossom", "ase"))
        self._register_pattern(id_baal_ase, ("baal_ase",), ("base",), ("baal", "ase"))
        self._register_pattern(id_holly_ase, ("hollyase",), ("holly_ase",), ("hase",), ("holly", "ase"))
        self._register_pattern(id_cupid_ase, ("cqase",), ("cupid_ase",), ("case_cupid",), ("cupid", "ase"))

        # --- Kaido & Big Mama & Marine & Stark Sets ---
        self._register_pattern(id_kaido_gourd, ("kaido", "gourd"), ("kaido_gourd",), ("gourd",), ("de_gourd",))
        self._register_pattern(id_kaido_cape, ("kaido", "cape"), ("kaido_cape",), ("de_cape",), ("dec",))
        self._register_pattern(id_kaido_outfit, ("kaido", "outfit"), ("kaido_outfit",), ("de_outfit",))
        self._register_pattern(id_kaido_set, ("kaido", "set"), ("kaido_set",))
        self._register_pattern(id_coyote_set, ("stark", "set"), ("coyote", "set"))
        self._register_pattern(id_bm_cape, ("big", "mom", "cape"), ("big_mom", "cape"), ("bm_cape",), ("bmc",), ("bigmom", "cape"))
        self._register_pattern(id_bm_fit, ("big", "mom", "outfit"), ("big_mom", "outfit"), ("bm_fit",), ("bmfit",), ("bigmom", "outfit"))
        self._register_pattern(id_bm_hat, ("big", "mom", "hat"), ("big_mom", "hat"), ("bm_hat",), ("bmhat",), ("bigmom", "hat"))
        self._register_pattern(id_marine_cape, ("marine", "cape"), ("marine_cape",), ("mcape",))
        self._register_pattern(id_marine_cap, ("marine", "cap"), ("marine_cap",), ("mcap",))

        # --- Оружие и комбо ---
        self._register_pattern(id_cc, ("cc",), ("candy_cane",), ("candycane",))
        self._register_pattern(id_pcc, ("pcc",), ("prestige_cc",), ("prestige", "cc"))
        self._register_pattern(id_icc, ("icc",), ("iceborn_cc",), ("iceborn", "cc"))
        self._register_pattern(id_we, ("we",), ("world_ender",))
        self._register_pattern(id_pwe, ("pwe",), ("prestige_we",), ("prestige", "we"))
        self._register_pattern(id_hwe, ("hwe",), ("hollow_we",), ("hollows_world_ender",))
        self._register_pattern(id_yoru, ("yoru",), ("db",), ("dark_blade",))
        self._register_pattern(id_kikoku, ("kikoku",))
        self._register_pattern(id_sos, ("sos",), ("sickle_of_sorrow",))
        self._register_pattern(id_flower_sword, ("flowers",), ("flower", "sword"), ("flower_sword",), ("flowers", "sword"))
        self._register_pattern(id_fbouquet, ("flower", "bouquet"), ("flower_bouquet",), ("fbouquet",))
        self._register_pattern(id_fest_shield, ("festival_lancer", "shield"), ("festival", "shield"), ("festival_shield",), ("fshield",))
        self._register_pattern(id_fest_lancer, ("festival_lancer",), ("festival", "lancer"), ("flancer",))
        self._register_pattern(id_fl, ("firework_lancer",), ("firework", "lancer"), ("fl",))
        self._register_pattern(id_fd, ("firework_daggers",), ("firework", "daggers"), ("fd",))
        self._register_pattern(id_irb, ("inferno_blade",), ("inferno_rocket_blade",), ("inferno", "blade"), ("irb",))
        self._register_pattern(id_pirb, ("pirb",), ("prestige_inferno_rocket_blade",))
        self._register_pattern(id_thunder_club, ("thunder_club",), ("thunder", "club"), ("tc",))
        self._register_pattern(id_tttc, ("tttc",), ("tung_club",), ("tung_thunder_club",), ("tung", "club"))
        self._register_pattern(id_df_rod, ("df_rod",), ("df", "rod"), ("devil_fruit_rod",), ("rumbling",), ("rumbling_rod",), ("rumbling", "rod"))
        self._register_pattern(id_odm_rod, ("odm_rod",), ("odm", "rod"), ("odm",))
        self._register_pattern(id_ls_rod, ("lsrod",), ("lovestruck_rod",), ("lovestruck", "rod"))
        self._register_pattern(id_isoh, ("isoh",), ("toji",), ("toji", "spear"), ("toji", "weapon"), ("toji", "sword"), ("inverted_spear",))
        self._register_pattern(id_sguns, ("sguns",), ("stark_guns",), ("stark_gun",), ("stark", "gun"), ("stark", "guns"))
        self._register_pattern(id_cbow, ("cbow",), ("cupid_bow",), ("cupid", "bow"))
        self._register_pattern(id_bbow, ("bbow",), ("blessed_bow",), ("blessed", "bow"), ("blessed", "cupid", "bow"))
        self._register_pattern(id_chakram, ("cupidschakram",), ("cupids_chakram",), ("cupid_chakram",), ("cupid", "chakram"), ("chakram",))
        self._register_pattern(id_pcchakram, ("pcchakram",), ("prestige", "chakram"), ("prestige", "cupid", "chakram"))
        self._register_pattern(id_cwand, ("cwand",), ("cupid", "wand"), ("cupid_wand",))
        self._register_pattern(id_cbattleaxe, ("cbattleaxe",), ("cupid", "battleaxe"), ("cupid", "axe"))
        self._register_pattern(id_mtrident, ("mtrident",), ("mochi_trident",), ("mochi", "trident"), ("katakuri", "trident"), ("katakuri", "weapon"))
        self._register_pattern(id_ntrident, ("ntrident",), ("neptune_trident",), ("neptune", "trident"))
        self._register_pattern(id_sscepter, ("sscepter",), ("snowcap_scepter",), ("snowcap", "scepter"), ("snowcap",))
        self._register_pattern(id_jscythe, ("jscythe",), ("jester_scythe",), ("jester", "scythe"), ("scythe",))
        self._register_pattern(id_elo, ("elo",), ("elohammer",), ("elo_hammer",), ("elo_sledgehammer",), ("elo", "hammer"))
        self._register_pattern(id_bcs, ("bcs",), ("blo_crimson_hammer",), ("blo", "crimson", "hammer"))
        self._register_pattern(id_bsledge, ("bsledge",), ("blo_hammer",), ("blo_sledge",), ("blo", "hammer"), ("blo", "sledge"))
        self._register_pattern(id_boneshiver, ("boneshiver",))
        self._register_pattern(id_shusui, ("shusui",))
        self._register_pattern(id_napoleon, ("soul_cleaver",), ("napoleon",))
        self._register_pattern(id_race, ("ace",), ("race",), ("roger_ace",), ("roger", "ace"))
        self._register_pattern(id_ibk, ("ibk",), ("iceborn", "katana"), ("iceborn_katana",))
        self._register_pattern(id_irapier, ("irapier",), ("iceborn", "rapier"), ("iceborn_rapier",))
        self._register_pattern(id_iblade, ("iblade",), ("iceborn", "blade"), ("iceborn_blade",))
        self._register_pattern(id_igunblade, ("igunblade",), ("iceborn", "gunblade"), ("iceborn_gunblade",))
        self._register_pattern(id_idaggers, ("idaggers",), ("iceborn", "daggers"), ("iceborn_daggers",))
        self._register_pattern(id_srapier, ("srapier",), ("swordfish", "rapier"), ("swordfish_rapier",))
        self._register_pattern(id_sanchor, ("sanchor",), ("sunken", "anchor"), ("sunken_anchor",))
        self._register_pattern(id_scane, ("scane",), ("soul", "cane"), ("soul_cane",))
        self._register_pattern(id_hskewer, ("hskewer",), ("helix", "skewer"), ("helix_skewer",))
        self._register_pattern(id_gpumbrella, ("gpumbrella",), ("perona", "umbrella"), ("ghost", "umbrella"))
        self._register_pattern(id_vpipe, ("vpipe",), ("vrael", "pipe"))
        self._register_pattern(id_verity, ("verity",))

        # --- Prestige экипировка ---
        self._register_pattern(id_pfl, ("pfl",), ("pflancer",), ("prestige_lancer",), ("prestige", "lancer"))
        self._register_pattern(id_pfd, ("pfd",), ("pfdaggers",), ("prestige_daggers",), ("prestige", "daggers"))
        self._register_pattern(id_pfrl, ("pfrl",), ("prestige_rocket_launcher",), ("prestige", "rocket_launcher"))
        self._register_pattern(id_pbag, ("pbag",), ("prestige_bag",), ("prestige_fruitbag",), ("prestige", "bag"))
        self._register_pattern(id_sfbag, ("sfbag",), ("spare_bag",), ("spare_fruit_bag",), ("spare", "bag"))

        # --- Аксессуары, ауры и костюмы ---
        self._register_pattern(id_tsa, ("aura",), ("tsa",), ("titan_shifters_aura",), ("titan", "aura"))
        self._register_pattern(id_hagoromo, ("hagoromo",), ("leos_inferno_hagoromo",), ("lih",))
        self._register_pattern(id_mpow, ("mpow",), ("mega_pow",), ("megapow",), ("mp",))
        self._register_pattern(id_amp, ("amp",), ("ampow",), ("anomalized_megapow",), ("anomalized_mega_pow",), ("anomalized", "mpow"), ("anomalized", "mega_pow"))
        self._register_pattern(id_bos, ("bos",), ("brand_of_sacrifice",))
        self._register_pattern(id_nfa, ("nfa",), ("nightfall_aura",), ("nightfall",))
        self._register_pattern(id_nfs, ("nfs",), ("nightfall_shroud",), ("nightfall", "shroud"))
        self._register_pattern(id_nfhs, ("nfhs",), ("half_nfs",), ("half", "nfs"), ("nightfall_half_shroud",), ("nightfall", "half", "shroud"))
        self._register_pattern(id_sks, ("sks",), ("soul_king_scarf",))
        self._register_pattern(id_skg, ("skg",), ("soulkingguitar",), ("soul_king_guitar",))
        self._register_pattern(id_skhat, ("skhat",), ("soul_king_tophat",), ("soul_king", "hat"))
        self._register_pattern(id_tbg, ("truebaalsguard",), ("true_baals_guard",), ("tbg",))
        self._register_pattern(id_res_head, ("res_head",), ("reshead",), ("resurrected_baals_head",), ("resurrected_baal_head",), ("resurrected", "head"), ("res", "head"), ("truebaalssnakehead",), ("true_baals_snake_head",))
        self._register_pattern(id_hob, ("hob",), ("head_of_baal",), ("baal_head",), ("baal", "head"))
        self._register_pattern(id_skeletal, ("darkskeletalmask",), ("dark_skeletal_mask",), ("skeletal_mask",), ("dssm",))
        self._register_pattern(id_hfang, ("hfang",), ("hollowfang",), ("hollow_fang",), ("hollows_fang",), ("hollow", "fang"))
        self._register_pattern(id_neko, ("neko",), ("snoozyneko",), ("snoozy_neko",), ("snoozy", "neko"))
        self._register_pattern(id_coyote, ("coyote",), ("coyote_outfit",), ("stark_outfit",), ("stark", "outfit"))
        self._register_pattern(id_toj_fit, ("tojfit",), ("toj_fit",), ("toji", "outfit"), ("titan_of_justice_outfit",), ("titan", "outfit"), ("titan", "justice", "outfit"))
        self._register_pattern(id_toj_cape, ("tojcape",), ("toj_cape",), ("toji", "cape"), ("titan_of_justice_cape",), ("titan", "cape"), ("titan", "justice", "cape"))
        self._register_pattern(id_hfit, ("hfit",), ("hawkeye_outfit",), ("hawkeye", "outfit"), ("hawk_eye", "outfit"), ("hawk", "eye", "outfit"), ("hawk", "outfit"))
        self._register_pattern(id_hhat, ("hhat",), ("hawkeye_hat",), ("hawkeye", "hat"), ("hawk_eye", "hat"), ("hawk", "eye", "hat"), ("hawk", "hat"))
        self._register_pattern(id_rfit, ("rfit",), ("roger_outfit",), ("roger", "outfit"))
        self._register_pattern(id_rhat, ("rhat",), ("roger_hat",), ("roger", "hat"))
        self._register_pattern(id_jfit, ("jfit",), ("jester_outfit",), ("jester", "outfit"))
        self._register_pattern(id_jhat, ("jhat",), ("jester_hat",), ("jester", "hat"))
        self._register_pattern(id_jbox, ("jbox",), ("jester_box",), ("jester", "box"))
        self._register_pattern(id_mescarf, ("mescarf",), ("mochi_scarf",), ("katakuri", "scarf"))
        self._register_pattern(id_tdrums, ("tdrums",), ("tomoe_drums",), ("drums",), ("susanoo",))
        self._register_pattern(id_kcore, ("kcore",), ("kraken_core",), ("sea_serpent_core",), ("kraken", "core"), ("core",))
        self._register_pattern(id_bswarm, ("bswarm",), ("batswarm",), ("bat_swarm",), ("bats",))
        self._register_pattern(id_tsss, ("tsss",), ("scroll",), ("slash_scroll",))
        self._register_pattern(id_trc, ("trc",), ("capsule",), ("timerift_capsule",))
        self._register_pattern(id_tailor, ("sttoken",), ("tailortoken",), ("tailor_token",), ("tailor", "token"), ("tailor",))
        self._register_pattern(id_tsc, ("tungcostume",), ("tung_costume",), ("tung", "costume"), ("tung_sahur_costume",), ("tsc",))
        self._register_pattern(id_sgc, ("gift", "crown"), ("giftbox", "crown"), ("supreme", "crown"), ("sgc",))
        self._register_pattern(id_de, ("dominus_empyreus",), ("dominus", "empyreus"), ("de",))
        self._register_pattern(id_du, ("dominus_ultimus",), ("dominus", "ultimus"), ("du",))
        self._register_pattern(id_banana, ("epicbanana",), ("epic_banana",), ("banana",))
        self._register_pattern(id_lbh, ("heart", "headband"), ("love", "headband"), ("love_headband",), ("lbh",))
        self._register_pattern(id_cheadband, ("cupid", "headband"), ("cupid_headband",), ("cheadband",), ("headband",))
        self._register_pattern(id_cmask, ("cupid", "mask"), ("cupid_mask",), ("cmask",))
        self._register_pattern(id_sea_mask, ("sea", "mask"), ("sea_mask",), ("kraken", "mask"))
        self._register_pattern(id_shat, ("santa", "hat"), ("santa_hat",), ("shat",))
        self._register_pattern(id_sbells, ("santa", "bells"), ("santa_bells",), ("sbells",))
        self._register_pattern(id_shelm, ("sunken", "helmet"), ("sunken_helmet",), ("shelm",))
        self._register_pattern(id_sarmor, ("sunken", "armor"), ("sunken_armor",), ("sarmor",))
        self._register_pattern(id_eba, ("endbringer", "armor"), ("endbringer_armor",), ("eba",))
        self._register_pattern(id_azure_armor, ("azure", "armor"), ("azure", "set"), ("azure_armor",), ("azure_set",), ("kraken", "azure", "armor"), ("kraken", "azure", "set"))
        self._register_pattern(id_azure_blade, ("azure", "blade"), ("azure_blade",), ("kraken", "azure", "blade"), ("azure", "sword"))
        self._register_pattern(id_snail, ("snail", "monkey"), ("monkey", "snail"), ("merchant", "snail"), ("snail",))

        # --- Крылья ---
        self._register_pattern(
            id_vqw,
            ("vqw",), ("virtuous_wings",), ("virtuous", "wings"),
            ("v_flag", "wings"), ("v_flag", "q_flag", "wings"),
            ("v_flag", "cupid", "wings"), ("v_flag", "cupid", "q_flag", "wings")
        )
        self._register_pattern(
            id_beqw,
            ("beqw",), ("blessed_wings",), ("blessed", "wings"),
            ("blessed", "exalted", "wings"), ("b_flag", "e_flag", "q_flag", "wings"),
            ("b_flag", "wings"), ("blessed", "cupid", "wings")
        )
        self._register_pattern(
            id_ewings,
            ("ewings",), ("exalted_wings",), ("exalted", "wings"),
            ("exalted", "cupid", "wings"), ("e_flag", "q_flag", "wings"), ("e_flag", "wings")
        )
        self._register_pattern(
            id_qwings,
            ("qwings",), ("cupid_wings",), ("queen_wings",), ("cupid", "wings"),
            ("og", "wings"), ("o_flag", "g_flag", "wings"), ("q_flag", "wings"), ("wings",)
        )
        self._register_pattern(id_ebw, ("ebw",), ("endbringer_wings",), ("endbringer", "wings"))

        # --- Валькирии ---
        self._register_pattern(id_ev, ("ev",), ("emerald_valk",), ("emerald", "valk"), ("emerald", "valkyrie"), ("green", "valk"), ("green", "valkyrie"))
        self._register_pattern(id_stv, ("stv",), ("sparkle_time_valk",), ("sparkle", "valk"), ("sparkle", "valkyrie"))
        self._register_pattern(id_iv, ("iv",), ("ice_valk",), ("ice", "valk"), ("ice", "valkyrie"))
        self._register_pattern(id_vv, ("vv",), ("violet_valk",), ("violet", "valk"), ("purple", "valk"))
        self._register_pattern(id_bv, ("bv",), ("blackvalk",), ("black_valk",), ("black", "valk"))
        self._register_pattern(id_vh, ("vh",), ("valkyrie_helm",), ("valk_helm",), ("valk",))

        # --- Cupid предметы ---
        self._register_pattern(id_cupid_scarf, ("cupid", "scarf"), ("cupid_scarf",), ("qscarf",))
        self._register_pattern(id_cupid_outfit, ("outfit", "cupid"), ("cupid", "outfit"), ("cupid_outfit",), ("qfit",), ("og", "outfit"), ("og", "cupid", "outfit"))
        self._register_pattern(id_cqmaid, ("cqmaid",), ("pmaidfit",), ("cupid_maid",), ("cupid", "maid"), ("cupid", "maid", "outfit"))
        self._register_pattern(id_maid_fit, ("maid_fit",), ("maid", "outfit"), ("maid", "fit"))
        self._register_pattern(id_bscarf, ("bscarf",), ("blessed_cupid_scarf",), ("blessed", "scarf"), ("blessed", "cupid", "scarf"))
        self._register_pattern(
            id_bqfit,
            ("bqfit",), ("blessed_cupid_outfit",), ("blessed", "outfit"),
            ("blessed", "cupid", "outfit"), ("blessed", "cupid", "guard", "outfit"),
            ("blessed", "guard", "outfit"), ("blessed", "exalted", "outfit"),
            ("blessed", "exalted", "cupid", "outfit")
        )
        self._register_pattern(id_eqfit, ("eqfit",), ("exalted", "outfit"), ("exalted", "cupid", "outfit"), ("guard", "outfit"), ("cupid", "guard", "outfit"))

        # --- Транспорт ---
        self._register_pattern(id_cboat, ("cboat",), ("coffinboat",), ("coffin_boat",), ("coffin", "boat"))
        self._register_pattern(id_hpod, ("hpod",), ("hover_pod",), ("hoverpod",), ("hover", "pod"))
        self._register_pattern(id_hb, ("hb",), ("hoverboard",))
        self._register_pattern(id_striker, ("striker",))
        self._register_pattern(id_fboat, ("fboat",), ("flamingo_boat",), ("flamingo", "boat"))

        # --- Очки и кролики ---
        self._register_pattern(id_love_shades, ("heart", "shades"), ("cupid", "shades"), ("love_shades",), ("heart_shades",), ("lshades",))
        self._register_pattern(id_rad_shades, ("kizaru", "shades"), ("radiant", "shades"), ("radiant_shades",), ("rshades",))
        self._register_pattern(id_don_shades, ("doflamingo", "shades"), ("donmingo", "shades"), ("dshades",))
        self._register_pattern(id_sakamoto, ("sakamoto", "glasses"), ("sakamoto", "shades"), ("sg",))
        self._register_pattern(id_cool_shades, ("shades",), ("cool_shades",), ("cs",))
        self._register_pattern(id_bunyo, ("bunyo",))
        self._register_pattern(id_hopiyo, ("hopiyo",))
        self._register_pattern(id_yukio, ("yukio",))

        # --- Сундуки, чертежи и расходники ---
        self._register_pattern(id_lc_bp, ("lc", "blueprint"), ("blueprint", "lc"), ("legendary", "chest", "blueprint"))
        self._register_pattern(id_lc, ("lc",), ("leg", "chest"), ("legendary", "chest"), ("leg_chest",))
        self._register_pattern(id_mc, ("mc",), ("mythic", "chest"), ("mythical", "chest"), ("mythic_chest",))
        self._register_pattern(id_rc, ("rc",), ("rare", "chest"), ("rare_chest",))
        self._register_pattern(id_10lc, ("10x_lc",), ("10xlc",))
        self._register_pattern(id_10mc, ("10x_mc",), ("10xmc",))
        self._register_pattern(id_10rc, ("10x_rc",), ("10xrc",))
        self._register_pattern(
            id_fish_bait,
            ("legendary", "fish_bait"), ("legendary", "fish", "bait"),
            ("leg_fish", "fish_bait"), ("leg", "fish", "fish", "bait"),
            ("fish_bait", "leg_fish"), ("fish_bait",), ("fish", "bait"), ("leg_fish",)
        )
        self._register_pattern(id_race_reroll, ("racereroll",), ("race_reroll",), ("race", "reroll"), ("rr",))
        self._register_pattern(id_sp, ("sp",), ("sp_reset",))
        self._register_pattern(id_droot, ("dr",), ("dark_root",), ("droot",))

        # --- Фрукты (точное сопоставление с gpo_items.json) ---
        fruits = [
            ("mochi", "Mochi", "item_72"),
            ("venom", "Venom", "item_76"),
            ("pika", "Pika", "item_86"),
            ("tori", "Tori", "item_84"),
            ("ope", "Ope", "item_100"),
            ("buddha", "Buddha", "item_107"),
            ("magu", "Magu", "item_122"),
            ("mera", "Mera Mera", "item_127"),
            ("goro", "Goro", "item_134"),
            ("suna", "Suna", "item_135"),
            ("dragon", "Dragon", "item_38"),
            ("ryu", "Dragon", "item_38"),
            ("leopard", "Leopard", "item_63"),
            ("leo", "Leopard", "item_63"),
            ("soul", "Soul", "item_75"),
            ("ptera", "Pteranodon", "item_87"),
            ("pteranodon", "Pteranodon", "item_87"),
            ("gura", "Gura", "item_117"),
            ("zushi", "Zushi", "item_145"),
            ("ito", "Ito", "item_128"),
            ("kage", "Kage", "item_159"),
            ("yami", "Yami", "item_157"),
            ("paw", "Paw", "item_156"),
            ("smoke", "Smoke", "item_155"),
            ("yuki", "Yuki", "item_158"),
            ("biscuit", "Biscuit", "item_123"),
            ("hie", "Hie", "item_144"),
            ("hiei", "Hie", "item_144"),
            ("goru", "Goru", "item_146"),
        ]
        for token_name, canonical, fb_id in fruits:
            fid = self._find_id_by_keywords(canonical, fallback=fb_id)
            if fid:
                self._register_pattern(fid, (token_name,))

    def _classify_custom_name(self, raw_name: str) -> Tuple[str, Any]:
        """Классифицирует имя кастомного эмодзи или шорткода."""
        name_low = raw_name.lower()
        if name_low.isdigit():
            return ("DIGIT", int(name_low))
        if name_low in WORD_NUM_TOKENS:
            return ("DIGIT", WORD_NUM_TOKENS[name_low])
        m_num = re.match(r"^(?:num_|n)?(\d+)$", name_low)
        if m_num:
            return ("DIGIT", int(m_num.group(1)))
        if name_low in FOR_TOKENS:
            return ("FOR", "for")
        if name_low in LF_TOKENS:
            return ("LF", "lf")
        if name_low in OFFER_PLACEHOLDERS:
            return ("OFFER_PH", "offer")
        if name_low in NLF_TOKENS:
            return ("NLF", "nlf")
        if name_low in OR_TOKENS:
            return ("OR", "or")
        if name_low in CURRENCY_TOKENS:
            return ("CURRENCY", name_low)
        if name_low in IGNORE_MODIFIERS:
            return ("MOD", name_low)
        if "heart" in name_low or name_low == "love":
            return ("SYM", "heart")
        return ("SYM", name_low)

    def tokenize_emoji_stream(self, raw_text: str) -> List[Tuple[str, Any]]:
        """
        Извлекает из сообщения ТОЛЬКО эмодзи-токены и системные множители.
        """
        raw_tokens: List[Tuple[str, Any]] = []

        for match in TOKEN_PATTERN.finditer(raw_text):
            custom_name, shortcode, uni_digit, mult_x, num_km, uni_sym, uni_heart, newline = match.groups()

            if custom_name or shortcode:
                raw_tokens.append(self._classify_custom_name(custom_name or shortcode))

            elif uni_digit:
                val = UNICODE_DIGITS.get(uni_digit, 1)
                raw_tokens.append(("DIGIT", val))

            elif mult_x:
                val = int(mult_x[1:])
                if 1 <= val <= 2000:
                    raw_tokens.append(("MULT_X", val))

            elif num_km:
                raw_tokens.append(("CURRENCY", num_km.lower()))

            elif uni_sym:
                if uni_sym == "🍶":
                    raw_tokens.append(("SYM", "gourd"))
                elif uni_sym == "🇻":
                    raw_tokens.append(("SYM", "v_flag"))
                elif uni_sym == "🇪":
                    raw_tokens.append(("SYM", "e_flag"))
                elif uni_sym == "🇶":
                    raw_tokens.append(("SYM", "q_flag"))
                elif uni_sym == "🇧":
                    raw_tokens.append(("SYM", "b_flag"))
                elif uni_sym == "🇴":
                    raw_tokens.append(("SYM", "o_flag"))
                elif uni_sym == "🇬":
                    raw_tokens.append(("SYM", "g_flag"))
                elif uni_sym in ("🇰", "🇲"):
                    raw_tokens.append(("KM_MULT", 1000 if uni_sym == "🇰" else 1000000))
                elif uni_sym == "🪽":
                    raw_tokens.append(("SYM", "wings"))
                elif uni_sym == "✨":
                    raw_tokens.append(("SYM", "sparkle"))
                elif uni_sym == "💂":
                    raw_tokens.append(("SYM", "guard"))
                elif uni_sym == "🐌":
                    raw_tokens.append(("SYM", "snail"))
                elif uni_sym in ("🐒", "🐵"):
                    raw_tokens.append(("SYM", "monkey"))
                elif uni_sym == "➕":
                    raw_tokens.append(("MOD", "plus"))
                elif uni_sym == "🫴":
                    raw_tokens.append(("OFFER_PH", "offer"))
                elif uni_sym in ("🛡️", "🛡"):
                    raw_tokens.append(("SYM", "shield"))
                elif uni_sym in ("❓", "❔"):
                    raw_tokens.append(("OFFER_PH", "question"))
                elif uni_sym in ("➡️", "➡", "👉", "▶️"):
                    raw_tokens.append(("FOR", "for"))

            elif uni_heart:
                raw_tokens.append(("SYM", "heart"))

            elif newline:
                raw_tokens.append(("NL", "\n"))

        # 1. Склеиваем соседние одиночные цифры: 2️⃣ 0️⃣ -> 20, 1️⃣ 5️⃣ 🇰 -> 15000
        merged_tokens: List[Tuple[str, Any]] = []
        i = 0
        n = len(raw_tokens)
        while i < n:
            ttype, tval = raw_tokens[i]
            if ttype == "DIGIT" and 0 <= tval <= 9:
                num_str = str(tval)
                while i + 1 < n and raw_tokens[i + 1][0] == "DIGIT" and 0 <= raw_tokens[i + 1][1] <= 9:
                    i += 1
                    num_str += str(raw_tokens[i][1])
                final_num = int(num_str)
                # Если сразу после числа идет 🇰 / 🇲
                if i + 1 < n and raw_tokens[i + 1][0] == "KM_MULT":
                    i += 1
                    # Если после 15k идет Bounty или Peli — это валюта, а не количество предметов!
                    if i + 1 < n and raw_tokens[i + 1][0] == "CURRENCY":
                        i += 1
                        merged_tokens.append(("CURRENCY", f"{final_num}k"))
                        i += 1
                        continue
                    final_num *= raw_tokens[i][1]
                # Если сразу после числа идет Bounty или Peli — поглощаем число как валюту
                if i + 1 < n and raw_tokens[i + 1][0] == "CURRENCY":
                    i += 1
                    merged_tokens.append(("CURRENCY", str(final_num)))
                    i += 1
                    continue
                if 1 <= final_num <= 100000:
                    merged_tokens.append(("QTY", final_num))
            elif ttype == "DIGIT" and tval >= 10:
                merged_tokens.append(("QTY", tval))
            elif ttype == "KM_MULT":
                # Одиночный 🇰 без цифр пропускаем
                pass
            else:
                merged_tokens.append((ttype, tval))
            i += 1

        return merged_tokens

    def _match_symbol_sequence(self, symbols: List[str], idx: int) -> Tuple[Optional[str], int]:
        """Жадный поиск самой длинной комбинации символов (от 4 до 1 токена)."""
        n = len(symbols)
        for span in (4, 3, 2, 1):
            if idx + span <= n:
                seq = tuple(symbols[idx : idx + span])
                if seq in self.seq_map:
                    return self.seq_map[seq], span
                flat_seq = tuple(part for s in seq for part in self._split_camel_and_norm(s) if part)
                if flat_seq in self.seq_map:
                    return self.seq_map[flat_seq], span
        return None, 0

    def _parse_single_or_branch(self, tokens: List[Tuple[str, Any]], fallback_item_id: Optional[str] = None) -> List[Tuple[str, int]]:
        """Парсит одну ветку без OR, суммируя одинаковые предметы внутри этой ветки."""
        items: List[Tuple[str, int]] = []
        i = 0
        n = len(tokens)
        pending_qty: Optional[int] = None

        while i < n:
            ttype, tval = tokens[i]

            if ttype in ("MOD", "OFFER_PH", "NL", "CURRENCY"):
                if ttype == "CURRENCY":
                    pending_qty = None
                i += 1
                continue

            if ttype == "MULT_X":
                # Явный суффиксный множитель (например: <:mc:...> X10)
                if items and items[-1][1] == 1:
                    prev_id, _ = items[-1]
                    items[-1] = (prev_id, tval)
                else:
                    pending_qty = tval
                i += 1
                continue

            if ttype == "QTY":
                next_is_sym = (i + 1 < n and tokens[i + 1][0] == "SYM")
                # Прикрепляем число как суффикс к предыдущему предмету ТОЛЬКО если дальше нет SYM и число <= 20
                if not next_is_sym and items and items[-1][1] == 1 and pending_qty is None and tval <= 20:
                    prev_id, _ = items[-1]
                    items[-1] = (prev_id, tval)
                else:
                    pending_qty = tval
                i += 1
                continue

            if ttype == "SYM":
                sym_chain: List[str] = []
                j = i
                while j < n and tokens[j][0] == "SYM":
                    sym_chain.append(tokens[j][1])
                    j += 1

                matched_id, span = self._match_symbol_sequence(sym_chain, 0)
                if matched_id:
                    qty = pending_qty if pending_qty is not None else 1
                    pending_qty = None

                    if items and items[-1][0] == matched_id:
                        items[-1] = (matched_id, items[-1][1] + qty)
                    else:
                        items.append((matched_id, qty))
                    i += span
                else:
                    pending_qty = None
                    i += 1
                continue

            i += 1

        if not items and pending_qty is not None and fallback_item_id:
            items.append((fallback_item_id, pending_qty))

        return items

    def _parse_item_group(self, tokens: List[Tuple[str, Any]], fallback_item_id: Optional[str] = None) -> List[Tuple[str, int]]:
        """
        Разбивает сегмент по OR на альтернативные ветки.
        Внутри одной ветки одинаковые предметы суммируются (<:mc:> <:mc:> -> x2),
        а между альтернативными ветками через OR берется max(), чтобы 3 Blossom OR 2 Blossom не давало x5 или x4.
        """
        branches: List[List[Tuple[str, Any]]] = [[]]
        for tok in tokens:
            if tok[0] == "OR":
                branches.append([])
            else:
                branches[-1].append(tok)

        merged_order: List[str] = []
        merged_qty: Dict[str, int] = {}

        for idx, branch in enumerate(branches):
            fb = fallback_item_id if idx == 0 else None
            branch_items = self._parse_single_or_branch(branch, fallback_item_id=fb)
            # Суммируем одинаковые предметы внутри одной ветки
            branch_dict: Dict[str, int] = {}
            for iid, q in branch_items:
                branch_dict[iid] = branch_dict.get(iid, 0) + q
                if iid not in merged_order:
                    merged_order.append(iid)
            # Между ветками OR берем максимум, а не сумму
            for iid, q in branch_dict.items():
                merged_qty[iid] = max(merged_qty.get(iid, 0), q)

        return [(iid, merged_qty[iid]) for iid in merged_order]

    def _get_item_value(self, item_id: str) -> float:
        if item_id in self.items_dict:
            return float(self.items_dict[item_id].get("value", 0.0) or 0.0)
        return 0.0

    def _extract_distinct_item_spans(self, mid_tokens: List[Tuple[str, Any]]) -> List[Tuple[int, int, str, int]]:
        """
        Находит все распознанные группы предметов (включая их префиксные QTY и повторы подряд)
        внутри сегмента между двумя FOR: возвращает список (start_idx, end_idx, item_id, total_qty).
        """
        spans: List[Tuple[int, int, str, int]] = []
        i = 0
        n = len(mid_tokens)

        while i < n:
            start_i = i
            qty = 1
            if mid_tokens[i][0] == "QTY":
                qty = mid_tokens[i][1]
                i += 1
            while i < n and mid_tokens[i][0] in ("MOD", "CURRENCY"):
                i += 1

            if i < n and mid_tokens[i][0] == "SYM":
                sym_chain = []
                j = i
                while j < n and mid_tokens[j][0] == "SYM":
                    sym_chain.append(mid_tokens[j][1])
                    j += 1
                matched_id, span = self._match_symbol_sequence(sym_chain, 0)
                if matched_id and span > 0:
                    end_i = i + span
                    # Если дальше идут точно такие же предметы подряд (например <:mc:> <:mc:>),
                    # объединяем их в один неделимый спан!
                    while end_i < n and mid_tokens[end_i][0] == "SYM":
                        sub_chain = []
                        k = end_i
                        while k < n and mid_tokens[k][0] == "SYM":
                            sub_chain.append(mid_tokens[k][1])
                            k += 1
                        next_id, next_span = self._match_symbol_sequence(sub_chain, 0)
                        if next_id == matched_id and next_span > 0:
                            qty += 1
                            end_i += next_span
                        else:
                            break
                    # Поглощаем суффиксные модификаторы (кроме max, который относится к следующему предмету)
                    while end_i < n and mid_tokens[end_i][0] in ("MOD", "MULT_X"):
                        if mid_tokens[end_i][0] == "MOD" and mid_tokens[end_i][1] == "max":
                            break
                        if mid_tokens[end_i][0] == "MULT_X":
                            qty = mid_tokens[end_i][1]
                        end_i += 1

                    spans.append((start_i, end_i, matched_id, qty))
                    i = end_i
                    continue
            i += 1

        return spans

    def _find_split_between_wants_and_next_offer(
        self,
        mid_tokens: List[Tuple[str, Any]],
        left_offer_tokens: Optional[List[Tuple[str, Any]]] = None,
        right_want_tokens: Optional[List[Tuple[str, Any]]] = None
    ) -> int:
        """
        Умный поиск границы между концом первой сделки (WANT_1) и началом второй сделки (OFFER_2)
        в конструкциях вида: `OFFER_1 FOR [mid_tokens] FOR WANT_2`.
        """
        # 1. Если есть перенос строки \n (или |), делим строго по нему
        for idx, (ttype, _) in enumerate(mid_tokens):
            if ttype == "NL":
                return idx

        # 2. Если внутри есть OFFER_PH (Offer / ❓ / 🫴), он завершает первую сделку
        # (включая возможные альтернативы через OR сразу после него)
        for idx, (ttype, _) in enumerate(mid_tokens):
            if ttype == "OFFER_PH":
                end_ph = idx + 1
                while end_ph < len(mid_tokens) and mid_tokens[end_ph][0] == "OR":
                    end_ph += 1
                    while end_ph < len(mid_tokens) and mid_tokens[end_ph][0] in ("MOD", "QTY", "OFFER_PH"):
                        end_ph += 1
                    if end_ph < len(mid_tokens) and mid_tokens[end_ph][0] == "SYM":
                        sym_chain = []
                        j = end_ph
                        while j < len(mid_tokens) and mid_tokens[j][0] == "SYM":
                            sym_chain.append(mid_tokens[j][1])
                            j += 1
                        _, sp = self._match_symbol_sequence(sym_chain, 0)
                        end_ph += max(1, sp)
                return end_ph

        # 3. Если в mid_tokens есть OR, все альтернативы OR относятся к одной части
        spans = self._extract_distinct_item_spans(mid_tokens)
        if len(spans) <= 1:
            return len(mid_tokens)

        # Если между первым и вторым спаном стоит OR, двигаемся дальше, пока не закончатся OR-связки
        min_split_span_idx = 1
        while min_split_span_idx < len(spans):
            prev_end = spans[min_split_span_idx - 1][1]
            curr_start = spans[min_split_span_idx][0]
            has_or = any(mid_tokens[p][0] == "OR" for p in range(prev_end, curr_start))
            if has_or:
                min_split_span_idx += 1
            else:
                break

        if min_split_span_idx >= len(spans):
            return spans[-1][0]

        # 4. Если между сделками ровно 2 группы предметов — первая группа в WANT_1, вторая в OFFER_2
        if len(spans) == 2:
            return spans[1][0]

        # 5. Если групп предметов >= 3 (например: Aura FOR CQASE + ASE   JFit FOR Blossom + CQASE),
        # выбираем точку разреза по балансу стоимости сделок из gpo_items.json!
        lhs_val = 0.0
        if left_offer_tokens:
            lhs_parsed = self._parse_item_group(left_offer_tokens)
            lhs_val = sum(self._get_item_value(iid) * q for iid, q in lhs_parsed)

        rhs_val = 0.0
        if right_want_tokens:
            rhs_parsed = self._parse_item_group(right_want_tokens)
            rhs_val = sum(self._get_item_value(iid) * q for iid, q in rhs_parsed)

        if lhs_val > 0:
            best_k = min_split_span_idx
            best_score = float("inf")
            for k in range(min_split_span_idx, len(spans)):
                want1_val = sum(self._get_item_value(spans[m][2]) * spans[m][3] for m in range(0, k))
                offer2_val = sum(self._get_item_value(spans[m][2]) * spans[m][3] for m in range(k, len(spans)))
                if want1_val <= 0 or offer2_val <= 0:
                    continue
                err1 = abs(want1_val - lhs_val) / max(want1_val, lhs_val)
                err2 = (abs(offer2_val - rhs_val) / max(offer2_val, rhs_val)) if rhs_val > 0 else 0.0
                score = err1 + err2
                if score < best_score:
                    best_score = score
                    best_k = k
            return spans[best_k][0]

        return spans[min_split_span_idx][0]

    def parse_message(self, message: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        """
        Разбирает сообщение Discord на чистые пары OFFER и WANT.
        """
        raw_text = message.get("content", "")
        if not raw_text:
            return None

        if "<" not in raw_text and ":" not in raw_text and not any(
            sym in raw_text for sym in ("🍶", "🇻", "🇪", "🇶", "🇧", "🪽", "🫴", "🐌")
        ):
            return None

        tokens = self.tokenize_emoji_stream(raw_text)
        if not tokens:
            return None

        # 1. Отрезаем всё после NLF (<:NLF:...>) до конца строки
        filtered_tokens: List[Tuple[str, Any]] = []
        skip_until_nl = False
        for ttype, tval in tokens:
            if ttype == "NLF":
                skip_until_nl = True
                continue
            if ttype == "NL":
                skip_until_nl = False
                filtered_tokens.append((ttype, tval))
                continue
            if not skip_until_nl:
                filtered_tokens.append((ttype, tval))

        # 2. Если в сообщении есть и LF, и FOR подряд (например: <:LF:> <:hopiyo:> <:FOR:> <:NFA:>),
        # убираем LF-маркер перед предложением, чтобы предмет слева от FOR не попадал в WANT
        cleaned_ops: List[Tuple[str, Any]] = []
        for idx, (ttype, tval) in enumerate(filtered_tokens):
            if ttype == "LF":
                # Проверяем, есть ли впереди FOR до следующего LF или NL
                has_for_ahead = False
                for j in range(idx + 1, len(filtered_tokens)):
                    if filtered_tokens[j][0] == "FOR":
                        has_for_ahead = True
                        break
                    if filtered_tokens[j][0] in ("LF", "NL"):
                        break
                if has_for_ahead:
                    cleaned_ops.append(("NL", "\n"))
                    continue
            cleaned_ops.append((ttype, tval))
        filtered_tokens = cleaned_ops

        # 3. Разбиваем поток токенов вокруг операторов FOR и LF
        clause_offers: List[List[Tuple[str, int]]] = []
        clause_wants: List[List[Tuple[str, int]]] = []

        op_indices = [idx for idx, (ttype, _) in enumerate(filtered_tokens) if ttype in ("FOR", "LF")]

        if not op_indices:
            clause_offers.append(self._parse_item_group(filtered_tokens))
        else:
            last_primary_offer_item: Optional[str] = None

            segments: List[Any] = []
            start = 0
            for op_idx in op_indices:
                segments.append(filtered_tokens[start:op_idx])
                start = op_idx + 1
            segments.append(filtered_tokens[start:])

            for k in range(len(op_indices) - 1):
                op_curr = filtered_tokens[op_indices[k]][0]
                op_next = filtered_tokens[op_indices[k + 1]][0]
                mid_seg = segments[k + 1]

                if op_curr == "FOR" and op_next == "FOR" and isinstance(mid_seg, list) and mid_seg:
                    left_ref = segments[k][1] if isinstance(segments[k], tuple) else segments[k]
                    right_ref = segments[k + 2] if isinstance(segments[k + 2], list) else []
                    split_pos = self._find_split_between_wants_and_next_offer(mid_seg, left_ref, right_ref)
                    want_part = mid_seg[:split_pos]
                    next_offer_part = mid_seg[split_pos:]
                    segments[k + 1] = (want_part, next_offer_part)

            carry_left: List[Tuple[str, Any]] = segments[0]
            for k, op_idx in enumerate(op_indices):
                op_type = filtered_tokens[op_idx][0]
                right_raw = segments[k + 1]

                if isinstance(right_raw, tuple):
                    right_seg, next_carry = right_raw
                else:
                    right_seg, next_carry = right_raw, []

                if op_type == "FOR":
                    lhs_items = self._parse_item_group(carry_left, fallback_item_id=last_primary_offer_item)
                    rhs_items = self._parse_item_group(right_seg)
                    if lhs_items:
                        last_primary_offer_item = lhs_items[0][0]
                    clause_offers.append(lhs_items)
                    clause_wants.append(rhs_items)
                elif op_type == "LF":
                    if k == 0 and carry_left:
                        lhs_items = self._parse_item_group(carry_left)
                        clause_offers.append(lhs_items)
                    rhs_items = self._parse_item_group(right_seg)
                    clause_wants.append(rhs_items)

                carry_left = next_carry

        # 4. Консолидация между отдельными сделками одного сообщения:
        # Внутри одной сделки одинаковые предметы уже просуммированы, а между разными сделками
        # в одном сообщении берем max(qty), чтобы альтернативные трейды (Dragon FOR 4 MC OR Dragon FOR 3 MC)
        # не удваивали предметы игрока.
        offer_dict: Dict[str, int] = {}
        for c_off in clause_offers:
            for iid, q in c_off:
                offer_dict[iid] = max(offer_dict.get(iid, 0), q)

        want_dict: Dict[str, int] = {}
        for c_wnt in clause_wants:
            for iid, q in c_wnt:
                want_dict[iid] = max(want_dict.get(iid, 0), q)

        offer_items = list(offer_dict.items())
        want_items = list(want_dict.items())

        if not offer_items and not want_items:
            return None

        return {
            "id": message.get("id"),
            "author_id": message.get("author_id"),
            "timestamp": message.get("timestamp"),
            "raw_text": raw_text,
            "offer_items": offer_items,
            "want_items": want_items
        }

    def get_item_name(self, item_id: str) -> str:
        """Возвращает читаемое название предмета для логов."""
        if item_id in self.items_dict:
            return self.items_dict[item_id].get("name", item_id)
        return item_id

    def parse_all(self, messages: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        """Парсит массив сообщений с защитой от спама одного и того же автора."""
        parsed_trades: List[Dict[str, Any]] = []
        seen_author_hashes: Set[str] = set()

        for msg in messages:
            author_id = msg.get("author_id", "anon")
            content = (msg.get("content") or "").strip()

            dedup_key = f"{author_id}:{content[:80]}"
            if dedup_key in seen_author_hashes:
                continue
            seen_author_hashes.add(dedup_key)

            parsed = self.parse_message(msg)
            if parsed:
                parsed_trades.append(parsed)

        logger.info(f"Распознано {len(parsed_trades)} реальных эмодзи-трейдов из {len(messages)} сообщений.")
        return parsed_trades


if __name__ == "__main__":
    parser = GPOTradeParser()

    if len(sys.argv) > 1:
        trade_str = " ".join(sys.argv[1:])
        res = parser.parse_message({"id": "cli", "author_id": "test_user", "content": trade_str})
        print(f"RAW    : {trade_str}")
        if not res:
            print("PARSED : [IGNORED - NO EMOJI TRADE]")
        else:
            off_str = ", ".join(f"{parser.get_item_name(i)} (x{q})" for i, q in res["offer_items"]) or "None"
            wnt_str = ", ".join(f"{parser.get_item_name(i)} (x{q})" for i, q in res["want_items"]) or "None"
            print(f"PARSED : OFFER: [{off_str}]  ==>  WANT: [{wnt_str}]")
    else:
        print("--- GPO Trade Parser Verification Suite (All Problematic Cases) ---")
        test_cases = [
            ('<:Mera:1523917154657898576> <:FOR:1433910700975067146> <:lc:1038468258975719444>', "Mera Mera (NOT Emerald Valkyrie)"),
            ('1️⃣ 5️⃣ 🇰 <:RaceReroll:1523925540392927293> <:FOR:1433910700975067146> <:Offer:1433929248669958276>', "15,000x Race Reroll (NOT Dominus Empyreus)"),
            ('<:blo_ase:1519457155537961133> <:FOR:1433910700975067146> <:Blossom_ASE:1543808857892192257>', "All Seeing Egg (blo_ase) FOR All Seeing Blossom"),
            ('<:yoru:1519457861342593318> <:SOS:1523896968592490506> 2️⃣ 9️⃣ 0️⃣ 🇰 <:Bounty:1433910205124579439> <:FOR:1433910700975067146> <:mpow:1523898619789443113>', "Bounty 290k does NOT attach to SOS"),
            ('<:Aura:1442679962850300066> <:FOR:1433910700975067146> <:cqase:1519457222890094812> <:ase:1519457110465839155> <:jfit:1519457440909889768> <:FOR:1433910700975067146> <:Blossom_ASE:1543808857892192257> <:cqase:1519457222890094812>', "Value-balanced multi-trade [100]"),
            ('<:Thunder_Club:1543808596595441664> <:FOR:1433910700975067146> <:mc:1519457464091803668> <:mc:1519457464091803668> <:venom:1519457841138761909> <:mochi:1519457484874448966> <:FOR:1433910700975067146> <:mc:1519457464091803668>', "Repeated MC in multi-trade [319]"),
            ('<:buddha:1519457180921757746> <:FOR:1433910700975067146> <:ope:1519470446280446053> <:Kizaru:1433928877931102441> <:Shades:1433929602169966642>', "Kizaru Shades = Radiant Shades (NOT Cool Shades)"),
            ('2️⃣ <:lc:1038468258975719444> <:FOR:1433910700975067146> <:BatSwarm:1523915861142798496> <:Cupid:1433910376847904830> <:Shades:1433929602169966642>', "Bat Swarm + Cupid Shades = Love Shades [262]"),
            ('<:pfd:1519457631557910682> <:FOR:1433910700975067146> 3️⃣ <:Blossom_ASE:1543808857892192257> <:Adds:1433909995426152519> <:OR:1433929275144142879> <:Blossom_ASE:1543808857892192257> <:Blossom_ASE:1543808857892192257> <:jfit:1519457440909889768>', "OR branch max consolidation [3474]"),
            ('5️⃣ <:lc:1038468258975719444> <:Blueprint:1433910159197081652> <:FOR:1433910700975067146> <:lc:1038468258975719444>', "Legendary Chest Blueprint [076]"),
        ]

        for raw, desc in test_cases:
            res = parser.parse_message({"id": "t", "author_id": "u", "content": raw})
            off_str = ", ".join(f"{parser.get_item_name(i)} (x{q})" for i, q in res["offer_items"]) if res else "None"
            wnt_str = ", ".join(f"{parser.get_item_name(i)} (x{q})" for i, q in res["want_items"]) if res else "None"
            print(f"[{desc}]\n  OFFER: [{off_str}]  ==>  WANT: [{wnt_str}]")