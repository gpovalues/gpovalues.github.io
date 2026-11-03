"""Deterministic offer parser. Ambiguous text never becomes a price equation."""
import hashlib
import itertools
import json
import re
import unicodedata
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
ZERO_WIDTH = re.compile(r"[\ufeff\u200b\u200c\u200d\u2060]")
WORDS = re.compile(r"\d+(?:\.\d+)?|[^\W\d_]+|[+\n|;/=-]", re.UNICODE)
FOR = {"for", "за", "на", "to"}
LF = {"lf", "want", "ищу", "lookingfor", "w"}
NLF = {"nlf", "dontwant", "notlookingfor"}
FILLER = {"wtt", "trading", "trade", "have", "h", "my", "отдам", "трейд", "меняю",
          "and", "plus", "with", "и", "плюс", "the", "dm", "me", "pm", "fast", "only"}
UNCERTAIN = {"adds", "add", "small", "big", "strong", "good", "max", "offer", "offers",
             "any", "anything", "upgrade", "downgrade", "bounty", "peli", "доп", "допы"}
ADDS = {"adds", "add", "доп", "допы"}
ADD_SIZES = {"small": "small_adds", "little": "small_adds", "big": "big_adds",
             "large": "big_adds", "strong": "big_adds"}
VARIANT_WORDS = {"prestige", "nightfall", "blessed", "exalted", "virtuous", "chromatic",
                 "chroma", "iceborn", "hollow", "hollows", "azure", "blue", "red", "green",
                 "violet", "black", "og", "vflag", "eflag", "qflag", "bflag", "oflag", "gflag"}
UNICODE_WORDS = {"🍶": "gourd", "🪽": "wings", "💂": "guard", "✨": "sparkle",
                 "🐌": "snail", "🐒": "monkey", "🐵": "monkey", "🛡": "shield",
                 "🏹": "bow",
                 "🇻": "vflag", "🇪": "eflag", "🇶": "qflag", "🇧": "bflag",
                 "🇴": "oflag", "🇬": "gflag", "🫴": "offers", "❓": "offers", "❔": "offers"}
NUMBER_WORDS = dict(zip(["zero", "one", "two", "three", "four", "five", "six", "seven", "eight", "nine", "ten"], range(11)))


def normalize(text):
    text = re.sub(r"([a-z])([A-Z])", r"\1 \2", str(text))
    return unicodedata.normalize("NFKC", text).casefold().replace("_", " ").translate(
        str.maketrans({"’": "", "‘": "", "'": "", "`": ""}))


class GPOTradeParser:
    def __init__(self, items_path=None):
        self.items_path = Path(items_path) if items_path else ROOT / "data/catalog.json"
        payload = json.loads(self.items_path.read_text(encoding="utf-8"))
        items = payload if isinstance(payload, list) else payload["items"]
        self.items_dict = {item["id"]: item for item in items}
        self.aliases = {}
        aliases = json.loads((ROOT / "data/trade_aliases.json").read_text(encoding="utf-8"))
        for alias, iid in aliases.items():
            self._register(alias, iid)
        for item in items:
            self._register(item["name"], item["id"])
            self._register(item.get("nameRu", ""), item["id"])
            self._register(item.get("abbreviation", ""), item["id"])
        self.max_span = max(map(len, self.aliases), default=1)
        self.stats = {}

    def _register(self, alias, iid):
        item = self.items_dict.get(iid)
        if not item or not alias:
            return
        # A pack is expressed as N units in the grammar, not as another currency.
        if item.get("unit_id", iid) != iid:
            return
        alias = re.sub(r"^\d+x\s*", "", alias, flags=re.I)
        tokens = tuple(WORDS.findall(normalize(alias).replace("-", " ")))
        if tokens and not tokens[0].isdigit():
            self.aliases[tokens] = iid
            if len(tokens) > 1:
                self.aliases[("".join(tokens),)] = iid

    def tokenize(self, content):
        text = ZERO_WIDTH.sub("", content)
        text = re.sub(r"(?m)^[ \t]*[-•][ \t]+", "", text)

        def emoji(match):
            name = match.group(1)
            return f" {NUMBER_WORDS.get(name.casefold(), name)} "

        text = re.sub(r"<a?:([\w]+):\d+>", emoji, text)
        text = re.sub(r":([\w]+):", emoji, text)
        text = re.sub(r"(?:\d\ufe0f?\u20e3\s*)+", lambda m: " " + "".join(re.findall(r"\d", m[0])) + " ", text)
        text = text.replace("🔟", " 10 ")
        for chars in ("①②③④⑤⑥⑦⑧⑨⑩", "❶❷❸❹❺❻❼❽❾❿", "➀➁➂➃➄➅➆➇➈➉"):
            for number, char in enumerate(chars, 1):
                text = text.replace(char, f" {number} ")
        text = re.sub(r"(\d+)\s*🇰", lambda m: str(int(m[1]) * 1000), text)
        text = re.sub(r"(\d+)\s*🇲", lambda m: str(int(m[1]) * 1000000), text)
        for char, word in UNICODE_WORDS.items():
            text = text.replace(char, f" {word} ")
        text = re.sub(r"[♥❤💖💗💘💙💚💛💜🖤🤍]", " heart ", text)
        text = re.sub(r"(?:<[-=]+>|[-=]+>|👉|➡|▶)", " for ", text).replace("➕", "+")
        text = re.sub(r"[\U0001f3fb-\U0001f3ff]", "", text)
        text = re.sub(r"[\U0001f000-\U0001faff]", " unknownemoji ", text)
        text = normalize(text)
        text = re.sub(r"\b(?:not\s+looking\s+for|dont\s+want|не\s+предлагать|не\s+ищу)\b", "nlf", text)
        text = re.sub(r"\b(?:looking\s+for)\b", "lf", text)
        text = re.sub(r"(?<=[^\W\d_])-(?=[^\W\d_])", " ", text)
        return WORDS.findall(text)

    def _match(self, tokens, start):
        for size in range(min(self.max_span, len(tokens) - start), 0, -1):
            span = tuple(tokens[start:start + size])
            iid = self.aliases.get(span) or self.aliases.get(("".join(span),))
            if iid:
                return iid, size
        return None, 0

    @staticmethod
    def _quantity(tokens, i):
        start = i
        if i < len(tokens) and tokens[i] in ("x", "х", "-"):
            i += 1
        if i >= len(tokens) or not re.fullmatch(r"\d+(?:\.\d+)?", tokens[i]):
            return None, 0
        value = float(tokens[i])
        if tokens[start] == "-":
            value = -value
        i += 1
        if i < len(tokens) and tokens[i] in ("x", "х"):
            i += 1
        return value, i - start

    def _side(self, tokens):
        found = {}
        issues = []
        markers = []
        i = 0
        while i < len(tokens):
            qty, consumed = self._quantity(tokens, i)
            prefix = consumed > 0
            if prefix:
                i += consumed
            iid, span = self._match(tokens, i)
            if not iid:
                if i >= len(tokens):
                    issues.append("quantity_without_item")
                    markers.append("unknown")
                    break
                token = tokens[i]
                if not prefix and (token in FILLER or token in ("+", "=", ",", "-")):
                    i += 1
                    continue
                if token in ADD_SIZES and i + 1 < len(tokens) and tokens[i + 1] in ADDS:
                    marker = ADD_SIZES[token]
                    issues.append(f"unspecified:{marker}")
                    markers.append(marker)
                    i += 2
                    continue
                if token in ADDS or token in ("offer", "offers"):
                    marker = "adds" if token in ADDS else "offers"
                    issues.append(f"unspecified:{marker}")
                    markers.append(marker)
                    i += 1
                    continue
                end = i + 1
                if token in VARIANT_WORDS:
                    while end < len(tokens) and tokens[end] in VARIANT_WORDS:
                        end += 1
                    nested, nested_span = self._match(tokens, end)
                    if nested:
                        end += nested_span
                issues.append(f"{'unspecified' if token in UNCERTAIN else 'unknown'}:{' '.join(tokens[i:end])}")
                markers.append("unknown")
                i = end
                continue
            i += span
            qty = qty if prefix else 1
            suffix, consumed = self._quantity(tokens, i)
            if consumed and not prefix:
                # A number before an unread item/currency must not multiply the previous item.
                after = i + consumed
                if after == len(tokens) or tokens[after] in {"+", "="} | ADDS | ADD_SIZES.keys() | {"offer", "offers"}:
                    qty = suffix
                    i += consumed
            if not 1 <= qty <= 100000 or qty != int(qty):
                issues.append("invalid_quantity")
                markers.append("unknown")
                continue
            found[iid] = found.get(iid, 0) + int(qty)
        return list(found.items()), issues, list(dict.fromkeys(markers))

    @staticmethod
    def _alternatives(tokens):
        branches = [[]]
        for token in tokens:
            if token in ("or", "или", "/"):
                branches.append([])
            else:
                branches[-1].append(token)
        return branches

    def parse_message(self, message):
        content = message.get("content", "")
        if not isinstance(content, str) or (not content.strip() and not message.get("has_attachments")):
            return []
        tokens = self.tokenize(content) if content.strip() else ["unreadattachment", "for", "unreadattachment"]
        lines = [[]]
        for index, token in enumerate(tokens):
            if token in ("\n", "|", ";"):
                lines.append([])
            elif (token in LF | {"wtt", "trading", "отдам"} and any(word in FOR for word in lines[-1])
                  and not self._match(tokens, index)[0]):
                lines.append([token])
            else:
                lines[-1].append(token)
        clauses = []
        for line in filter(None, lines):
            previous = clauses[-1] if clauses else []
            separate = any(word in FOR for word in line) or line[0] in LF | {"wtt", "trading", "отдам"}
            if previous and ((line[0] in FOR and not any(word in FOR for word in previous)) or
                             (not separate and (previous[-1] in FOR | {"+"} or line[0] == "+"))):
                previous.extend(line)
            else:
                clauses.append(line)
        records = []
        for line_number, line in enumerate(clauses):
            nlf = next((i for i, word in enumerate(line) if word in NLF), len(line))
            line = line[:nlf]
            if not line:
                continue
            separators = [i for i, word in enumerate(line) if word in FOR]
            issues = []
            if len(separators) > 1:
                # Never infer clause boundaries by comparing current prices.
                offer, want = [], []
                issues = ["ambiguous_clauses", f"unknown:{' '.join(line)}"]
            elif separators:
                split = separators[0]
                left, right = line[:split], line[split + 1:]
                if left and left[0] in LF:
                    offer, want = right, left[1:]
                else:
                    offer, want = left, right
            else:
                split = next((i for i, word in enumerate(line) if word in LF), None)
                offer, want = (line[:split], line[split + 1:]) if split is not None else (line, [])
            offers = self._alternatives(offer)
            wants = self._alternatives(want)
            if len(offers) * len(wants) > 16:
                continue
            for variant, (off, wanted) in enumerate(itertools.product(offers, wants)):
                off_items, off_issues, off_markers = self._side(off)
                want_items, want_issues, want_markers = self._side(wanted)
                if len(separators) > 1:
                    off_markers = want_markers = ["unknown"]
                explicit = separators or any(token in LF | {"wtt", "trading", "отдам"} for token in line)
                if not off_items and not want_items and not (explicit and (off_markers or want_markers)):
                    continue
                problems = issues + off_issues + want_issues
                if message.get("has_attachments"):
                    problems.append("attachment_not_parsed")
                    off_markers = list(dict.fromkeys(off_markers + ["unknown"]))
                    want_markers = list(dict.fromkeys(want_markers + ["unknown"]))
                signature = json.dumps([sorted(off_items), sorted(want_items), sorted(set(problems)), off_markers, want_markers], ensure_ascii=False)
                records.append({
                    "id": f"{message.get('id', '')}:{line_number}:{variant}",
                    "message_id": message.get("id"),
                    "author_id": str(message.get("author_id") or ""),
                    "channel_id": str(message.get("channel_id") or ""),
                    "timestamp": message.get("edited_at") or message.get("timestamp"),
                    "offer_items": off_items, "want_items": want_items,
                    "offer_markers": off_markers, "want_markers": want_markers,
                    "kind": "offer", "pricing_eligible": bool(off_items and want_items and not problems),
                    "counts_eligible": "unknown" not in off_markers + want_markers,
                    "issues": sorted(set(problems)),
                    "variant_count": len(offers) * len(wants),
                    "signature": hashlib.sha256(signature.encode()).hexdigest(),
                })
        return records

    def parse_all(self, messages):
        latest = {}
        recognized = 0
        for message in messages:
            records = self.parse_message(message)
            recognized += any(record["offer_items"] or record["want_items"] for record in records)
            for record in records:
                author = record["author_id"] or record["message_id"]
                key = (author, record["signature"])
                if key not in latest or (record["timestamp"] or "") > (latest[key]["timestamp"] or ""):
                    latest[key] = record
        result = sorted(latest.values(), key=lambda record: (record["timestamp"] or "", record["id"]))
        self.stats = {
            "messages_seen": len(messages), "messages_recognized": recognized,
            "messages_unrecognized": len(messages) - recognized,
            "unique_offers": len(result), "price_observations": sum(t["pricing_eligible"] for t in result),
        }
        return result

    def get_item_name(self, item_id):
        return self.items_dict.get(item_id, {}).get("name", item_id)
