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

# Регулярное выражение, которое извлекает ТОЛЬКО эмодзи и спецсимволы (весь обычный текст отбрасывается)
TOKEN_PATTERN = re.compile(
    r"<a?:([a-zA-Z0-9_]+):\d+>"                        # 1. Кастомные Discord эмодзи <:name:id>
    r"|(\d\ufe0f?\u20e3|🔟|[①-⑩❶-❿➀-➉➊-➓])"          # 2. Цифровые эмодзи (2️⃣, 🔟, ④)
    r"|(🍶|🇻|🛡️|🛡|❓|❔|➡️|➡|👉|▶️)"                 # 3. Предметные и структурные Unicode эмодзи
    r"|([\u2764\u2665\u2763\U0001F490-\U0001F49F\U0001F90D-\U0001F90F\U0001FA75-\U0001FA77]\ufe0f?)" # 4. Сердца
    r"|(\n)"                                           # 5. Перенос строки
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
LF_TOKENS = {"lf", "looking_for", "lookingfor", "want", "w"}
OFFER_PLACEHOLDERS = {"offer", "offers", "any", "anything", "question"}
NLF_TOKENS = {"nlf", "not_looking_for", "no_want", "dont_want"}
OR_TOKENS = {"or", "slash"}
IGNORE_MODIFIERS = {
    "adds", "add", "small_adds", "smalladds", "strong_adds", "strongadds",
    "good_adds", "big_adds", "max", "wtt", "trading", "have", "h", "fast",
    "dm", "pm", "plus", "and", "with"
}


class GPOTradeParser:
    """
    Строгий парсер эмодзи-трейдов GPO.
    Автоматически связывает названия эмодзи с предметами из gpo_items.json.
    """

    def __init__(self, items_path: Optional[str] = None):
        base_dir = os.path.dirname(os.path.abspath(__file__))
        self.items_path = items_path or os.path.join(base_dir, "..", "gpo_items.json")

        self.items_dict: Dict[str, Dict[str, Any]] = {}
        # Карта последовательностей токенов -> item_id: например ("kaido", "gourd") -> "item_105"
        self.seq_map: Dict[Tuple[str, ...], str] = {}
        # Быстрый поиск ID по каноническому названию предмета
        self.name_to_id: Dict[str, str] = {}

        self._load_items_and_build_rules()

    @staticmethod
    def _norm(s: str) -> str:
        """Нормализует строку в нижний регистр без спецсимволов."""
        return re.sub(r"[^a-z0-9]+", "_", s.lower()).strip("_")

    def _find_id_by_keywords(self, *keywords: str, fallback: str) -> str:
        """
        Ищет реальный ID предмета в загруженном gpo_items.json по его названию,
        чтобы никогда не путать ID (даже если gpo_items.json обновился).
        """
        for kw in keywords:
            kw_norm = self._norm(kw)
            if kw_norm in self.name_to_id:
                return self.name_to_id[kw_norm]
        for kw in keywords:
            kw_lower = kw.lower()
            for iid, item in self.items_dict.items():
                iname = item.get("name", "").lower()
                if iname == kw_lower:
                    return iid
        return fallback

    def _register_pattern(self, item_id: str, *token_sequences: Tuple[str, ...]):
        for seq in token_sequences:
            norm_seq = tuple(t.lower().strip("_") for t in seq if t.strip("_"))
            if norm_seq:
                self.seq_map[norm_seq] = item_id

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
                            # Регистрируем как цельное название с подчеркиваниями, так и разбитое по словам
                            self.seq_map[(name_norm,)] = iid
                            self.seq_map[tuple(name_norm.split("_"))] = iid

                        abbr = self._norm(it.get("abbreviation", ""))
                        if abbr and len(abbr) >= 2:
                            self.seq_map[(abbr,)] = iid
            except Exception as e:
                logger.error(f"Ошибка чтения {self.items_path}: {e}")

        # 2. Динамическая привязка точных ID из базы (с надежными fallback ID)
        id_ase          = self._find_id_by_keywords("All Seeing Eye", fallback="item_31")
        id_case         = self._find_id_by_keywords("Chromatic All Seeing Eye", fallback="item_14")
        id_sase         = self._find_id_by_keywords("All Seeing Shamrock", "Shamrock All Seeing Eye", fallback="item_18")
        id_egg_ase      = self._find_id_by_keywords("All Seeing Egg", fallback="item_24")
        id_blossom_ase  = self._find_id_by_keywords("All Seeing Blossom", "Blossom All Seeing Eye", fallback="item_25")
        id_baal_ase     = self._find_id_by_keywords("All Seeing Ba'al", "All Seeing Baal", fallback="item_27")
        id_holly_ase    = self._find_id_by_keywords("All Seeing Holly", "Holly All Seeing Eye", fallback="item_28")
        id_cupid_ase    = self._find_id_by_keywords("Cupid's All Seeing Eye", "Cupid All Seeing Eye", fallback="item_29")

        id_kaido_cape   = self._find_id_by_keywords("Dragon Emperor's Cape", "Kaido Cape", fallback="item_104")
        id_kaido_gourd  = self._find_id_by_keywords("Dragon Emperor's Gourd", "Kaido Gourd", fallback="item_105")
        id_kaido_outfit = self._find_id_by_keywords("Dragon Emperor's Outfit", "Kaido Outfit", fallback="item_108")
        id_bm_cape      = self._find_id_by_keywords("Big Mama's Cape", "Big Mom Cape", fallback="item_119")
        id_marine_cape  = self._find_id_by_keywords("Marine Cape", fallback="item_2")
        id_marine_cap   = self._find_id_by_keywords("Marine Cap", fallback="item_3")

        id_cc           = self._find_id_by_keywords("Candy Cane", fallback="item_16")
        id_pcc          = self._find_id_by_keywords("Prestige Candy Cane", fallback="item_6")
        id_icc          = self._find_id_by_keywords("Iceborn Candy Cane", fallback="item_11")
        id_we           = self._find_id_by_keywords("World Ender", fallback="item_35")
        id_pwe          = self._find_id_by_keywords("Prestige World Ender", fallback="item_8")
        id_hwe          = self._find_id_by_keywords("Hollow's World Ender", "Hollow World Ender", fallback="item_52")
        id_yoru         = self._find_id_by_keywords("Dark Blade", "Yoru", fallback="item_54")
        id_kikoku       = self._find_id_by_keywords("Kikoku", fallback="item_62")
        id_sos          = self._find_id_by_keywords("Sickle of Sorrow", fallback="item_56")
        id_flower_sword = self._find_id_by_keywords("Flower Sword", "Vista's Flower Sword", fallback="item_64")
        id_fest_lancer  = self._find_id_by_keywords("Festival Lancer", fallback="item_205")
        id_fest_shield  = self._find_id_by_keywords("Festival Shield", fallback="item_206")
        id_thunder_club = self._find_id_by_keywords("Thunder Club", fallback="item_45")
        id_df_rod       = self._find_id_by_keywords("Devil Fruit Rod", fallback="item_47")

        id_hagoromo     = self._find_id_by_keywords("Leo's Inferno Hagoromo", "Inferno Hagoromo", "Hagoromo", fallback="item_17")
        id_mpow         = self._find_id_by_keywords("Mega-Pow", "Mega Pow", fallback="item_37")
        id_bos          = self._find_id_by_keywords("Brand of Sacrifice", fallback="item_39")
        id_nfa          = self._find_id_by_keywords("Nightfall Aura", "Nightfall", fallback="item_40")
        id_sks          = self._find_id_by_keywords("Soul King's Scarf", "Soul King Scarf", fallback="item_30")
        id_skg          = self._find_id_by_keywords("Soul King's Guitar", "Soul King Guitar", fallback="item_74")
        id_tbg          = self._find_id_by_keywords("True Ba'al's Guard", "True Baal's Guard", "True Baal Guard", fallback="item_99")
        id_skeletal     = self._find_id_by_keywords("Dark Skeletal Shark Mask", "Dark Skeletal Mask", fallback="item_91")
        id_valk_wings   = self._find_id_by_keywords("Valkyrie's Wings", "Valkyrie Wings", "Wings of the Valkyrie", fallback="item_197")
        id_cupid_scarf  = self._find_id_by_keywords("Cupid's Scarf", "Cupid Queen's Scarf", "Cupid Scarf", fallback="item_78")
        id_cupid_shield = self._find_id_by_keywords("Cupid's Shield", "Cupid Queen's Shield", "Cupid Shield", fallback="item_81")
        id_cupid_outfit = self._find_id_by_keywords("Cupid Queen's Outfit", "Cupid's Outfit", "Cupid Outfit", fallback="item_79")
        id_cool_shades  = self._find_id_by_keywords("Cool Shades", fallback="item_1")
        id_love_shades  = self._find_id_by_keywords("Love Shades", "Heart Shades", fallback="item_209")
        id_bunyo        = self._find_id_by_keywords("Bunyo The Bunny", "Bunyo", fallback="item_34")
        id_hopiyo       = self._find_id_by_keywords("Hopiyo The Bunny", "Hopiyo", fallback="item_53")
        id_yukio        = self._find_id_by_keywords("Yukio The Bunny", "Yukio", fallback="item_32")

        id_lc           = self._find_id_by_keywords("Legendary Fruit Chest", fallback="item_102")
        id_mc           = self._find_id_by_keywords("Mythical Fruit Chest", fallback="item_58")
        id_rc           = self._find_id_by_keywords("Rare Fruit Chest", fallback="item_208")
        id_fish_bait    = self._find_id_by_keywords("300x Legendary Fish Bait", "Legendary Fish Bait", "Fish Bait", fallback="item_73")
        id_race_reroll  = self._find_id_by_keywords("Race Reroll", "Max Race Reroll", fallback="item_195")
        id_sp           = self._find_id_by_keywords("SP Reset Essence", fallback="item_194")
        id_droot        = self._find_id_by_keywords("Dark Root", fallback="item_193")

        # 3. Явные правила для эмодзи и их комбинаций
        # --- Все виды All Seeing Eye (строго разделены!) ---
        self._register_pattern(id_ase, ("ase",), ("all_seeing_eye",))
        self._register_pattern(id_case, ("case",), ("chromatic_ase",), ("chromatic", "ase"))
        self._register_pattern(id_sase, ("sase",), ("shamrock_ase",), ("shamrock", "ase"))
        self._register_pattern(id_egg_ase, ("egg_ase",), ("all_seeing_egg",), ("egg",))
        self._register_pattern(id_blossom_ase, ("blossom_ase",), ("blo_ase",), ("blase",), ("blossom", "ase"))
        self._register_pattern(id_baal_ase, ("baal_ase",), ("base",), ("baal", "ase"))
        self._register_pattern(id_holly_ase, ("hollyase",), ("holly_ase",), ("hase",), ("holly", "ase"))
        self._register_pattern(id_cupid_ase, ("cqase",), ("cupid_ase",), ("case_cupid",), ("cupid", "ase"))

        # --- Kaido & Capes (строго отличаем Gourd от Cape!) ---
        self._register_pattern(id_kaido_gourd, ("kaido", "gourd"), ("kaido_gourd",), ("gourd",), ("de_gourd",))
        self._register_pattern(id_kaido_cape, ("kaido", "cape"), ("kaido_cape",), ("de_cape",), ("dec",))
        self._register_pattern(id_kaido_outfit, ("kaido", "outfit"), ("kaido_outfit",), ("de_outfit",))
        self._register_pattern(id_bm_cape, ("big", "mom", "cape"), ("big_mom", "cape"), ("bm_cape",), ("bmc",))
        self._register_pattern(id_marine_cape, ("marine", "cape"), ("marine_cape",), ("mcape",))
        self._register_pattern(id_marine_cap, ("marine", "cap"), ("marine_cap",), ("mcap",))

        # --- Оружие и комбо-эмодзи ---
        self._register_pattern(id_cc, ("cc",), ("candy_cane",), ("candycane",))
        self._register_pattern(id_pcc, ("pcc",), ("prestige_cc",), ("prestige", "cc"))
        self._register_pattern(id_icc, ("icc",), ("iceborn_cc",), ("iceborn", "cc"))
        self._register_pattern(id_we, ("we",), ("world_ender",))
        self._register_pattern(id_pwe, ("pwe",), ("prestige_we",), ("prestige", "we"))
        self._register_pattern(id_hwe, ("hwe",), ("hollow_we",), ("hollows_world_ender",))
        self._register_pattern(id_yoru, ("yoru",), ("db",), ("dark_blade",))
        self._register_pattern(id_kikoku, ("kikoku",))
        self._register_pattern(id_sos, ("sos",), ("sickle_of_sorrow",))
        self._register_pattern(id_flower_sword, ("flower", "sword"), ("flower_sword",))
        self._register_pattern(id_fest_shield, ("festival_lancer", "shield"), ("festival", "shield"), ("festival_shield",))
        self._register_pattern(id_fest_lancer, ("festival_lancer",), ("festival", "lancer"), ("flancer",))
        self._register_pattern(id_thunder_club, ("thunder_club",), ("thunder", "club"), ("tc",))
        self._register_pattern(id_df_rod, ("df_rod",), ("df", "rod"), ("devil_fruit_rod",))

        # --- Аксессуары и комбо-эмодзи ---
        self._register_pattern(id_hagoromo, ("hagoromo",), ("leos_inferno_hagoromo",))
        self._register_pattern(id_mpow, ("mpow",), ("mega_pow",), ("megapow",))
        self._register_pattern(id_bos, ("bos",), ("brand_of_sacrifice",))
        self._register_pattern(id_nfa, ("nfa",), ("nightfall_aura",), ("nightfall",))
        self._register_pattern(id_sks, ("sks",), ("soul_king_scarf",))
        self._register_pattern(id_skg, ("skg",), ("soul_king_guitar",))
        self._register_pattern(id_tbg, ("truebaalsguard",), ("true_baals_guard",), ("tbg",))
        self._register_pattern(id_skeletal, ("darkskeletalmask",), ("dark_skeletal_mask",), ("skeletal_mask",))
        self._register_pattern(id_valk_wings, ("v_flag", "wings"), ("valk", "wings"), ("valkyrie", "wings"), ("valkyrie_wings",), ("wings",))
        self._register_pattern(id_cupid_shield, ("cupid", "scarf", "shield"), ("cupid", "shield"), ("cupid_shield",))
        self._register_pattern(id_cupid_scarf, ("cupid", "scarf"), ("cupid_scarf",))
        self._register_pattern(id_cupid_outfit, ("outfit", "cupid"), ("cupid", "outfit"), ("cupid_outfit",))
        self._register_pattern(id_love_shades, ("heart", "shades"), ("love_shades",), ("heart_shades",))
        self._register_pattern(id_cool_shades, ("shades",), ("cool_shades",), ("cs",))
        self._register_pattern(id_bunyo, ("bunyo",))
        self._register_pattern(id_hopiyo, ("hopiyo",))
        self._register_pattern(id_yukio, ("yukio",))

        # --- Сундуки и расходники ---
        self._register_pattern(id_lc, ("lc",), ("leg", "chest"), ("legendary", "chest"), ("leg_chest",))
        self._register_pattern(id_mc, ("mc",), ("mythic", "chest"), ("mythical", "chest"), ("mythic_chest",))
        self._register_pattern(id_rc, ("rc",), ("rare", "chest"), ("rare_chest",))
        self._register_pattern(id_fish_bait, ("legendary", "fish_bait"), ("legendary", "fish", "bait"), ("fish_bait",), ("fish", "bait"))
        self._register_pattern(id_race_reroll, ("racereroll",), ("race_reroll",), ("race", "reroll"), ("rr",))
        self._register_pattern(id_sp, ("sp",), ("sp_reset",))
        self._register_pattern(id_droot, ("dr",), ("dark_root",), ("droot",))

        # --- Фрукты ---
        fruits = [
            ("mochi", "Mochi"), ("venom", "Venom"), ("pika", "Pika"), ("tori", "Tori"),
            ("ope", "Ope"), ("buddha", "Buddha"), ("magu", "Magu"), ("mera", "Mera"),
            ("goro", "Goro"), ("suna", "Suna"), ("dragon", "Dragon"), ("leopard", "Leopard"),
            ("soul", "Soul"), ("ptera", "Pteranodon"), ("pteranodon", "Pteranodon"),
            ("gura", "Gura"), ("zushi", "Zushi"), ("ito", "Ito"), ("kage", "Kage"),
            ("yami", "Yami"), ("paw", "Paw"), ("smoke", "Smoke")
        ]
        for token_name, canonical in fruits:
            fid = self._find_id_by_keywords(canonical, fallback="")
            if fid:
                self._register_pattern(fid, (token_name,))

    def tokenize_emoji_stream(self, raw_text: str) -> List[Tuple[str, Any]]:
        """
        Извлекает из сообщения ТОЛЬКО эмодзи-токены.
        Любой обычный текст (реклама кланов, слова, приписки) полностью игнорируется.
        """
        raw_tokens: List[Tuple[str, Any]] = []

        for match in TOKEN_PATTERN.finditer(raw_text):
            custom_name, uni_digit, uni_sym, uni_heart, newline = match.groups()

            if custom_name:
                name_low = custom_name.lower()
                # Проверка цифровых кастомных эмодзи (<:4:999>, <:two:123>, <:10:123>)
                if name_low.isdigit():
                    raw_tokens.append(("DIGIT", int(name_low)))
                elif name_low in WORD_NUM_TOKENS:
                    raw_tokens.append(("DIGIT", WORD_NUM_TOKENS[name_low]))
                elif re.match(r"^(?:num_|n)?(\d+)$", name_low):
                    val = int(re.match(r"^(?:num_|n)?(\d+)$", name_low).group(1))
                    raw_tokens.append(("DIGIT", val))
                elif name_low in FOR_TOKENS:
                    raw_tokens.append(("FOR", "for"))
                elif name_low in LF_TOKENS:
                    raw_tokens.append(("LF", "lf"))
                elif name_low in OFFER_PLACEHOLDERS:
                    raw_tokens.append(("OFFER_PH", "offer"))
                elif name_low in NLF_TOKENS:
                    raw_tokens.append(("NLF", "nlf"))
                elif name_low in OR_TOKENS:
                    raw_tokens.append(("OR", "or"))
                elif name_low in IGNORE_MODIFIERS:
                    raw_tokens.append(("MOD", name_low))
                elif "heart" in name_low or name_low == "love":
                    raw_tokens.append(("SYM", "heart"))
                else:
                    raw_tokens.append(("SYM", name_low))

            elif uni_digit:
                val = UNICODE_DIGITS.get(uni_digit, 1)
                raw_tokens.append(("DIGIT", val))

            elif uni_sym:
                if uni_sym == "🍶":
                    raw_tokens.append(("SYM", "gourd"))
                elif uni_sym == "🇻":
                    raw_tokens.append(("SYM", "v_flag"))
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

        # Склеиваем соседние одиночные цифры: 2️⃣ 0️⃣ -> 20, 1️⃣ 0️⃣ 0️⃣ -> 100
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
                if 1 <= final_num <= 1000:
                    merged_tokens.append(("QTY", final_num))
            elif ttype == "DIGIT" and tval >= 10:
                merged_tokens.append(("QTY", tval))
            else:
                merged_tokens.append((ttype, tval))
            i += 1

        return merged_tokens

    def _match_symbol_sequence(self, symbols: List[str], idx: int) -> Tuple[Optional[str], int]:
        """Жадный поиск самой длинной комбинации символов (от 3 до 1 токена)."""
        n = len(symbols)
        for span in (3, 2, 1):
            if idx + span <= n:
                seq = tuple(symbols[idx : idx + span])
                if seq in self.seq_map:
                    return self.seq_map[seq], span
                # Если внутри одного токена есть подчеркивания (например, <:Legendary:><:Fish_Bait:>),
                # разворачиваем и проверяем
                flat_seq = tuple(part for s in seq for part in s.split("_") if part)
                if flat_seq in self.seq_map:
                    return self.seq_map[flat_seq], span
        return None, 0

    def _parse_item_group(self, tokens: List[Tuple[str, Any]], fallback_item_id: Optional[str] = None) -> List[Tuple[str, int]]:
        """
        Превращает сегмент токенов (левую или правую часть от FOR/LF) в список [(item_id, qty)].
        Корректно обрабатывает:
        - Префиксное количество: 8️⃣ <:mc:> -> (mc, 8)
        - Суффиксное количество: <:mc:> 2️⃣ <:OR:> <:df_rod:> -> (mc, 2), (df_rod, 1)
        - Одинаковые предметы через <:OR:>: <:lancer:> <:OR:> <:lancer:> 🛡️ -> (lancer, 1), (shield, 1)
        - Пропущенный предмет во второй сделке: 7️⃣ <:FOR:> <:ase:> -> использует fallback_item_id (mc, 7)
        """
        items: List[Tuple[str, int]] = []
        i = 0
        n = len(tokens)
        pending_qty: Optional[int] = None
        after_or = False

        while i < n:
            ttype, tval = tokens[i]

            if ttype in ("MOD", "OFFER_PH", "NL"):
                i += 1
                continue

            if ttype == "OR":
                after_or = True
                i += 1
                continue

            if ttype == "QTY":
                # Проверяем, является ли число суффиксом к предыдущему предмету:
                # например: <:mc:> 2️⃣ <:OR:> <:df_rod:>
                next_is_sym = (i + 1 < n and tokens[i + 1][0] == "SYM")
                if not next_is_sym and items and items[-1][1] == 1 and pending_qty is None:
                    prev_id, _ = items[-1]
                    items[-1] = (prev_id, tval)
                else:
                    pending_qty = tval
                i += 1
                continue

            if ttype == "SYM":
                # Собираем непрерывную цепочку SYM для жадного матчинга комбо (<:Kaido:> 🍶, <:Flower:> <:Sword:>)
                sym_chain: List[str] = []
                j = i
                while j < n and tokens[j][0] == "SYM":
                    sym_chain.append(tokens[j][1])
                    j += 1

                matched_id, span = self._match_symbol_sequence(sym_chain, 0)
                if matched_id:
                    qty = pending_qty if pending_qty is not None else 1
                    pending_qty = None

                    # Если идет подряд тот же предмет (например <:lc:> <:lc:> без <:OR:>), суммируем
                    if items and items[-1][0] == matched_id and not after_or:
                        items[-1] = (matched_id, items[-1][1] + qty)
                    elif items and items[-1][0] == matched_id and after_or:
                        # Если через OR тот же самый предмет, не удваиваем его искусственно
                        pass
                    else:
                        items.append((matched_id, qty))

                    after_or = False
                    i += span
                else:
                    i += 1
                continue

            i += 1

        # Если в сегменте была только цифра (например: "8️⃣ <:mc:> <:FOR:> <:baal_ase:>  7️⃣ <:FOR:> <:ase:>"),
        # подставляем предмет из предыдущего оффера!
        if not items and pending_qty is not None and fallback_item_id:
            items.append((fallback_item_id, pending_qty))

        return items

    def parse_message(self, message: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        """
        Разбирает сообщение Discord на чистые пары OFFER и WANT.
        Сообщения без кастомных эмодзи (текстовый спам, реклама кланов) отбрасываются.
        """
        raw_text = message.get("content", "")
        if not raw_text or "<" not in raw_text:
            # В настоящих эмодзи-трейдах GPO всегда есть хотя бы один кастомный Discord эмодзи <:...:id>
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

        # 2. Разбиваем поток токенов на независимые клаузы вокруг операторов FOR и LF
        # Это идеально решает проблему нескольких сделок в одном сообщении ([01], [03], [05], [08], [24])
        total_offer: List[Tuple[str, int]] = []
        total_want: List[Tuple[str, int]] = []

        # Находим индексы всех операторов FOR и LF
        op_indices = [idx for idx, (ttype, _) in enumerate(filtered_tokens) if ttype in ("FOR", "LF")]

        if not op_indices:
            # Нет ни FOR, ни LF — просто перечисление предметов на обмен (считаем как Offer)
            total_offer.extend(self._parse_item_group(filtered_tokens))
        else:
            last_primary_offer_item: Optional[str] = None

            # Вычисляем границы сегментов между операторами
            # Если между двумя FOR стоит несколько предметов (как в [03], [05], [08]),
            # последний предмет/число перед вторым FOR относится к левой части второго FOR!
            segments: List[List[Tuple[str, Any]]] = []
            start = 0
            for op_idx in op_indices:
                segments.append(filtered_tokens[start:op_idx])
                start = op_idx + 1
            segments.append(filtered_tokens[start:])

            # Корректируем стыки между соседними операторами (например: A FOR B C FOR D)
            for k in range(len(op_indices) - 1):
                op_curr = filtered_tokens[op_indices[k]][0]
                op_next = filtered_tokens[op_indices[k + 1]][0]
                mid_seg = segments[k + 1]

                if op_curr == "FOR" and op_next == "FOR" and mid_seg:
                    # Ищем точку разделения между WANT первой сделки и OFFER второй сделки
                    split_pos = self._find_split_between_wants_and_next_offer(mid_seg)
                    want_part = mid_seg[:split_pos]
                    next_offer_part = mid_seg[split_pos:]
                    segments[k + 1] = want_part
                    # Сохраняем отрезанный хвост как начало следующего сегмента
                    segments[k + 1] = (want_part, next_offer_part)  # type: ignore

            # Проходим по всем операторам и собираем Offer / Want
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
                    total_offer.extend(lhs_items)
                    total_want.extend(rhs_items)
                elif op_type == "LF":
                    # Если перед LF были предметы (и это первый оператор), они идут в Offer, а после LF — в Want
                    if k == 0 and carry_left:
                        lhs_items = self._parse_item_group(carry_left)
                        total_offer.extend(lhs_items)
                    rhs_items = self._parse_item_group(right_seg)
                    total_want.extend(rhs_items)

                carry_left = next_carry

        # 3. Умная консолидация (не суммируем количество, если один и тот же предмет упомянут и до, и после LF в [01])
        offer_dict: Dict[str, int] = {}
        for iid, q in total_offer:
            offer_dict[iid] = offer_dict.get(iid, 0) + q

        want_dict: Dict[str, int] = {}
        for iid, q in total_want:
            # Если в [01] человек написал "FOR hagoromo + Blossom_ASE LF hagoromo", не делаем hagoromo x2
            if iid in want_dict and q == 1 and want_dict[iid] == 1:
                continue
            want_dict[iid] = want_dict.get(iid, 0) + q

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

    def _find_split_between_wants_and_next_offer(self, mid_tokens: List[Tuple[str, Any]]) -> int:
        """
        Находит границу между концом первой сделки (WANT) и началом второй сделки (OFFER)
        в конструкциях вида: `<:A:> <:FOR:> <:B:>  <:C:> <:FOR:> <:D:>`.
        """
        # 1. Если есть перенос строки \n, делим по нему
        for idx, (ttype, _) in enumerate(mid_tokens):
            if ttype == "NL":
                return idx

        # 2. Если внутри есть цифра (например: `<:baal_ase:> 7️⃣`), делим прямо перед цифрой
        for idx in range(1, len(mid_tokens)):
            if mid_tokens[idx][0] == "QTY":
                return idx

        # 3. Если идет два предмета подряд (например: `<:venom:> <:Max:> <:RaceReroll:>` или `<:lc:> <:SKG:>`),
        # первый распознанный предмет относится к WANT первого FOR, а всё остальное — к OFFER второго FOR.
        idx = 0
        n = len(mid_tokens)
        while idx < n and mid_tokens[idx][0] in ("MOD", "QTY"):
            idx += 1

        if idx < n and mid_tokens[idx][0] == "SYM":
            sym_chain = []
            j = idx
            while j < n and mid_tokens[j][0] == "SYM":
                sym_chain.append(mid_tokens[j][1])
                j += 1
            _, span = self._match_symbol_sequence(sym_chain, 0)
            if span > 0:
                end_of_first_item = idx + span
                # Захватываем модификаторы типа <:Small_Adds:> сразу после первого предмета, если они есть
                while end_of_first_item < n and mid_tokens[end_of_first_item][0] == "MOD":
                    if mid_tokens[end_of_first_item][1] == "max":
                        break  # <:Max:> относится к следующему предмету (например, <:Max:> <:Fish_Bait:>)
                    end_of_first_item += 1
                return end_of_first_item

        return len(mid_tokens)

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

    # Все 24 твоих реальных примера из логов
    raw_samples = [
        '<:CC:1523897313964068963> <:mc:1519457464091803668> <:FOR:1433910700975067146> <:hagoromo:1519457338124402808> <:Blossom_ASE:1543808857892192257>  <:LF:1433928971099177063> <:hagoromo:1519457338124402808>',
        '<:Leopard:1543808730485755905> <:FOR:1433910700975067146> <:Offer:1433929248669958276>',
        '<:Max:1433929025021153311> <:Legendary:1434728891926450276> <:Fish_Bait:1434690900193448059> <:FOR:1433910700975067146> <:venom:1519457841138761909>  <:Max:1433929025021153311> <:RaceReroll:1523925540392927293> <:FOR:1433910700975067146> <:Pika:1523917220944547850>',
        '<:df_rod:1519457245958508696> <:FOR:1433910700975067146> 2️⃣ <:mc:1519457464091803668> <:Small_Adds:1433929646512144454>',
        '8️⃣ <:mc:1519457464091803668> <:FOR:1433910700975067146> <:baal_ase:1519457131697541141>  7️⃣ <:FOR:1433910700975067146> <:ase:1519457110465839155> <:OR:1433929275144142879> <:sks:1519457776424845494>',
        '<:sase:1519457756740976852> <:blo_ase:1519457155537961133> <:ase:1519457110465839155> <:FOR:1433910700975067146> <:Offer:1433929248669958276>',
        '<:df_rod:1519457245958508696> <:dragon:1519457318461247618> <:FOR:1433910700975067146> ❓',
        '<:Kaido:1543801666535555133> 🍶 <:FOR:1433910700975067146> <:lc:1038468258975719444>  <:SKG:1523898730019815494> <:FOR:1433910700975067146> <:Max:1433929025021153311> <:Fish_Bait:1434690900193448059>',
        '<:HWE:1523899219830902844> <:SOS:1523896968592490506> <:Flower:1468057888248561694> <:Sword:1433929727474663494> 🇻 <:Wings:1433929830466064394> <:FOR:1433910700975067146> <:Offer:1433929248669958276>',
        '<:Pika:1523917220944547850> <:FOR:1433910700975067146> <:festival_lancer:1559587987220598985> <:OR:1433929275144142879> <:festival_lancer:1559587987220598985> 🛡️',
        '<:mochi:1519457484874448966> <:FOR:1433910700975067146> <:Offer:1433929248669958276>',
        '<:hollyase:1519457376564936804> <:sase:1519457756740976852> <:Blossom_ASE:1543808857892192257> <:FOR:1433910700975067146> <:CC:1523897313964068963> <:mpow:1523898619789443113> <:Small_Adds:1433929646512144454>',
        'Perm Invite To Crew "AFT"   #7 PRICE 2-3 MC /  Offers ﺤ═══════ι▬▬⊱🔫 ⊰▬▬ι═══════ﺤ ✦ ADVANTAGES: ⚔️  Prestige Yoru! 👑  Exclusive title (Collector) 🍀  No more Infamy farming! 🤝 We invite first! 👑 Top #7 crew ﺤ═══════ι▬▬⊱𓆩🔥 𓆪⊰▬▬ι═══════ﺤ',
        '<:NFA:1555378885401649192> <:FOR:1433910700975067146> 🇻 <:Wings:1433929830466064394> <:Adds:1433909995426152519>',
        '4️⃣  <:mc:1519457464091803668> 🇻 <:Wings:1433929830466064394> <:yoru:1519457861342593318><:SOS:1523896968592490506>  <:FOR:1433910700975067146> <:ase:1519457110465839155>',
        '<:Kikoku:1120440014883537047> <:lc:1038468258975719444> <:lc:1038468258975719444> <:FOR:1433910700975067146> <:Offer:1433929248669958276>',
        '<:BOS:1555378662608470107> <:FOR:1433910700975067146> <:hopiyo:1523896400025223168>',
        '<:Thunder_Club:1543808596595441664> <:mc:1519457464091803668> <:FOR:1433910700975067146> <:dragon:1519457318461247618>',
        '<:mpow:1523898619789443113> <:BOS:1555378662608470107> <:Cupid:1433910376847904830> <:Scarf:1433929454748565546> 🛡️ <:FOR:1433910700975067146> <:ase:1519457110465839155>',
        '<:Blossom_ASE:1543808857892192257> <:FOR:1433910700975067146> <:ase:1519457110465839155> <:Strong_Adds:1433929688207855769>',
        '<:sase:1519457756740976852><:Bunyo:1523916102147768330><:FOR:1433910700975067146><:hagoromo:1519457338124402808><:OR:1433929275144142879><:Offer:1433929248669958276>',
        '2️⃣ 0️⃣ <:Legendary:1434728891926450276> <:Fish_Bait:1434690900193448059> <:FOR:1433910700975067146> <:smoke:1523902047068356639>',
        '<:yoru:1519457861342593318> <:buddha:1519457180921757746> <:ptera:1519457706178515016> <:Outfit:1433929299475566592> <:Cupid:1433910376847904830> <:TrueBaalsGuard:1523900180175257742> <:FOR:1433910700975067146> <:mc:1519457464091803668> 2️⃣ <:OR:1433929275144142879> <:df_rod:1519457245958508696>',
        '<:DarkSkeletalMask:1523918005849817120><:FOR:1433910700975067146><:Offer:1433929248669958276> <:LF:1433928971099177063><:mochi:1519457484874448966><:OR:1433929275144142879><:ptera:1519457706178515016>',
    ]

    for idx, raw in enumerate(raw_samples, 1):
        res = parser.parse_message({"id": str(idx), "author_id": f"u_{idx}", "content": raw})
        print(f"[{idx:02d}] RAW    : {raw}")
        if not res:
            print("     PARSED : [IGNORED - SPAM / NO EMOJI TRADE]")
        else:
            off_str = ", ".join(f"{parser.get_item_name(i)} (x{q})" for i, q in res["offer_items"]) or "None"
            wnt_str = ", ".join(f"{parser.get_item_name(i)} (x{q})" for i, q in res["want_items"]) or "None"
            print(f"     PARSED : OFFER: [{off_str}]  ==>  WANT: [{wnt_str}]")