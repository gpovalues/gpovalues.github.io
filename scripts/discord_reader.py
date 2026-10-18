"""
Discord Trade Reader for Grand Piece Online (GPO) Trading Hub.
Architecture: STRICTLY READ-ONLY HTTP CLIENT.
Uses only standard HTTP GET requests via `requests`. All mutating methods (POST, PUT, DELETE, PATCH)
are completely disabled at the class/architecture level.
"""

import os
import re
import sys
import json
import time
import random
import datetime
import logging
from typing import List, Dict, Any, Optional

try:
    import requests
except ImportError as exc:
    raise ImportError("Библиотека 'requests' обязательна. Установите её: pip install requests") from exc

# Настройка кодировки консоли для корректного вывода эмодзи и кириллицы
if hasattr(sys.stdout, "reconfigure"):
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S"
)
logger = logging.getLogger("DiscordReader")

# Регулярные выражения для предварительной очистки текста трейдов
ZERO_WIDTH_RE = re.compile(r"[\ufeff\u200b\u200c\u200d\u2060]")
MULTI_SPACE_RE = re.compile(r"[ \t]{2,}")
# Находит спам-повторы одной и той же сделки в одной строке (только если внутри есть FOR / 👉 / LF)
SPAM_REPEAT_RE = re.compile(
    r"^(.+?(?:<:FOR:\d+>|👉\S*|<:LF:\d+>).*?)\s+\1(?:\s+\1)*$",
    re.IGNORECASE
)


class ReadOnlyDiscordSession:
    """
    Строгое архитектурное ограничение: разрешен ТОЛЬКО метод HTTP GET.
    Любая попытка вызвать POST, PUT, DELETE или PATCH немедленно выбросит RuntimeError.
    Это гарантирует, что аккаунт или бот никогда не отправит сообщение или реакцию.
    """

    def __init__(self, token: str):
        if not token or not token.strip():
            raise ValueError("Не передан DISCORD_TOKEN для инициализации сессии.")

        self._session = requests.Session()
        self._token = token.strip()

        self._headers = {
            "User-Agent": (
                "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                "AppleWebKit/537.36 (KHTML, like Gecko) "
                "Chrome/130.0.0.0 Safari/537.36"
            ),
            "Accept": "*/*",
            "Accept-Language": "en-US,en;q=0.9,ru;q=0.8",
            "Sec-Ch-Ua": '"Chromium";v="130", "Google Chrome";v="130", "Not?A_Brand";v="99"',
            "Sec-Ch-Ua-Mobile": "?0",
            "Sec-Ch-Ua-Platform": '"Windows"',
            "Sec-Fetch-Dest": "empty",
            "Sec-Fetch-Mode": "cors",
            "Sec-Fetch-Site": "same-origin",
            "X-Debug-Options": "bugReporter-enabled",
            "X-Discord-Locale": "en-US",
            "Authorization": self._token,
        }
        self._session.headers.update(self._headers)

    def get(self, url: str, **kwargs) -> requests.Response:
        """Единственный разрешенный HTTP-метод: GET."""
        resp = self._session.get(url, **kwargs)
        # Автоматический фоллбэк: если передан токен бота без префикса "Bot "
        if resp.status_code == 401 and not self._session.headers["Authorization"].startswith("Bot "):
            self._session.headers["Authorization"] = f"Bot {self._token}"
            resp = self._session.get(url, **kwargs)
        return resp

    def close(self):
        self._session.close()

    def post(self, *args, **kwargs):
        raise RuntimeError("ARCHITECTURE VIOLATION: POST method is strictly disabled.")

    def put(self, *args, **kwargs):
        raise RuntimeError("ARCHITECTURE VIOLATION: PUT method is strictly disabled.")

    def delete(self, *args, **kwargs):
        raise RuntimeError("ARCHITECTURE VIOLATION: DELETE method is strictly disabled.")

    def patch(self, *args, **kwargs):
        raise RuntimeError("ARCHITECTURE VIOLATION: PATCH method is strictly disabled.")


class DiscordTradeReader:
    """
    Читает реальные сообщения о трейдах из указанных каналов Discord.
    - Пагинация вперед (?after={id}) для догрузки новых сообщений без дублей.
    - Пагинация назад (?before={id}) для первичного сбора истории.
    - Обработка лимитов 429 Too Many Requests и временных ошибок сервера (5xx).
    - Атомарное сохранение буфера на диск.
    """

    DISCORD_API_BASE = "https://discord.com/api/v9"
    DEFAULT_CHANNEL_ID = "966859339816124438"

    def __init__(
        self,
        token: Optional[str] = None,
        channel_ids: Optional[List[str]] = None,
        buffer_path: Optional[str] = None
    ):
        base_dir = os.path.dirname(os.path.abspath(__file__))
        self.token = self._resolve_token(token, base_dir)
        self.buffer_path = buffer_path or os.path.join(base_dir, "..", "data", "trades_buffer.json")

        # Если список каналов не передан явно, используем дефолтный канал GPO
        self.channel_ids = channel_ids if channel_ids else [self.DEFAULT_CHANNEL_ID]
        self.session = ReadOnlyDiscordSession(self.token) if self.token else None
        self.latest_read_messages: List[Dict[str, Any]] = []

    @staticmethod
    def _resolve_token(explicit_token: Optional[str], base_dir: str) -> str:
        """Ищет токен в аргументах, переменных окружения или в файле .env."""
        if explicit_token and explicit_token.strip():
            return explicit_token.strip()

        env_token = os.environ.get("DISCORD_TOKEN", "").strip()
        if env_token:
            return env_token

        env_paths = [
            os.path.join(base_dir, ".env"),
            os.path.join(base_dir, "..", ".env")
        ]
        for env_file in env_paths:
            if os.path.exists(env_file):
                try:
                    with open(env_file, "r", encoding="utf-8") as f:
                        for line in f:
                            clean_line = line.strip()
                            if clean_line.startswith("DISCORD_TOKEN="):
                                return clean_line.split("=", 1)[1].strip().strip('"').strip("'")
                except Exception as e:
                    logger.warning(f"Ошибка чтения {env_file}: {e}")
        return ""

    @staticmethod
    def is_valid_snowflake(mid: Any) -> bool:
        """Проверяет, является ли ID настоящим Discord Snowflake (число от 17 цифр)."""
        if not mid:
            return False
        s = str(mid).strip()
        return s.isdigit() and len(s) >= 17

    @staticmethod
    def _parse_timestamp(ts_str: str) -> datetime.datetime:
        """Безопасно парсит ISO-время из Discord в UTC datetime."""
        try:
            dt = datetime.datetime.fromisoformat(ts_str.replace("Z", "+00:00"))
            if dt.tzinfo is None:
                dt = dt.replace(tzinfo=datetime.timezone.utc)
            return dt
        except Exception:
            return datetime.datetime.now(datetime.timezone.utc)

    @staticmethod
    def clean_trade_content(raw_content: str) -> str:
        """
        Очищает текст сообщения от невидимых символов Unicode (BOM / Zero-Width Space)
        и убирает спам-дублирование одного и того же трейда, СОХРАНЯЯ переносы строк \n.
        """
        if not raw_content:
            return ""

        # 1. Удаляем невидимые символы (\ufeff и др.), ломающие парсинг чисел
        text = ZERO_WIDTH_RE.sub("", raw_content).strip()

        # 2. Очищаем каждую строку отдельно и убираем дублирующиеся строки
        lines = [MULTI_SPACE_RE.sub(" ", line.strip()) for line in text.splitlines() if line.strip()]
        deduped_lines: List[str] = []
        for line in lines:
            cleaned_line = SPAM_REPEAT_RE.sub(r"\1", line).strip()
            if cleaned_line and cleaned_line not in deduped_lines:
                deduped_lines.append(cleaned_line)

        # ВАЖНО: склеиваем через "\n", а НЕ через пробелы, чтобы парсер видел границы строк!
        return "\n".join(deduped_lines)

    def load_buffer(self) -> Dict[str, Any]:
        """Загружает буфер сообщений с диска."""
        if os.path.exists(self.buffer_path):
            try:
                with open(self.buffer_path, "r", encoding="utf-8") as f:
                    data = json.load(f)
                    if isinstance(data, dict) and isinstance(data.get("messages"), list):
                        data.setdefault("last_message_ids", {})
                        return data
            except Exception as e:
                logger.warning(f"Не удалось прочитать буфер {self.buffer_path}: {e}")

        return {
            "last_updated": None,
            "last_price_update": None,
            "last_message_ids": {},
            "messages": []
        }

    def save_buffer(self, buffer_data: Dict[str, Any]):
        """Атомарно сохраняет буфер на диск (защита от повреждения файла при сбое)."""
        try:
            target_dir = os.path.dirname(os.path.abspath(self.buffer_path))
            os.makedirs(target_dir, exist_ok=True)
            temp_path = f"{self.buffer_path}.tmp"

            with open(temp_path, "w", encoding="utf-8") as f:
                json.dump(buffer_data, f, separators=(",", ":"), ensure_ascii=False)

            os.replace(temp_path, self.buffer_path)
        except Exception as e:
            logger.error(f"Ошибка сохранения буфера в {self.buffer_path}: {e}")

    def prune_buffer(self, buffer_data: Dict[str, Any], max_age_hours: float = 180.0):
        """
        Удаляет дубликаты, старые сообщения (старше max_age_hours), очищает текст
        от копипаст-спама и сортирует сообщения строго по возрастанию ID.
        """
        cutoff = datetime.datetime.now(datetime.timezone.utc) - datetime.timedelta(hours=max_age_hours)
        valid_msgs = []
        seen_ids = set()

        for m in buffer_data.get("messages", []):
            mid = str(m.get("id", "")).strip()
            if not self.is_valid_snowflake(mid) or mid in seen_ids:
                continue

            m_dt = self._parse_timestamp(m.get("timestamp", ""))
            if m_dt >= cutoff:
                m["content"] = self.clean_trade_content(m.get("content", ""))
                if m["content"]:
                    seen_ids.add(mid)
                    valid_msgs.append(m)

        # Сортируем по числовому значению Snowflake ID (гарантирует хронологический порядок)
        valid_msgs.sort(key=lambda x: int(x["id"]))
        buffer_data["messages"] = valid_msgs

    def _request_batch(self, url: str, params: Dict[str, Any], channel_id: str) -> Optional[List[Dict[str, Any]]]:
        """Выполняет запрос к Discord API с обработкой Rate Limit (429) и ошибок сервера (5xx)."""
        if not self.session:
            return None

        max_retries = 4
        for attempt in range(max_retries):
            try:
                resp = self.session.get(url, params=params, timeout=15)
            except requests.RequestException as e:
                logger.error(f"[Канал {channel_id}] Ошибка сети (попытка {attempt + 1}/{max_retries}): {e}")
                time.sleep(3.0)
                continue

            if resp.status_code == 200:
                try:
                    data = resp.json()
                    return data if isinstance(data, list) else []
                except ValueError:
                    logger.error(f"[Канал {channel_id}] Некорректный JSON в ответе.")
                    return None

            if resp.status_code == 429:
                try:
                    retry_after = float(resp.json().get("retry_after", 3.0))
                except Exception:
                    retry_after = 3.0
                sleep_time = retry_after + random.uniform(0.4, 1.0)
                logger.warning(f"[Канал {channel_id}] Rate Limit (429). Ожидание {sleep_time:.2f} сек...")
                time.sleep(sleep_time)
                continue

            if resp.status_code in (500, 502, 503, 504):
                wait = 4.0 * (attempt + 1)
                logger.warning(f"[Канал {channel_id}] Сервер Discord вернул {resp.status_code}. Повтор через {wait} сек...")
                time.sleep(wait)
                continue

            if resp.status_code in (401, 403):
                logger.error(
                    f"[Канал {channel_id}] Ошибка доступа (HTTP {resp.status_code}). "
                    f"Проверьте валидность DISCORD_TOKEN и наличие доступа к каналу."
                )
                return None

            logger.warning(f"[Канал {channel_id}] Неожиданный статус HTTP {resp.status_code}: {resp.text[:200]}")
            return None

        logger.error(f"[Канал {channel_id}] Превышено количество попыток запроса.")
        return None

    def fetch_channel_messages_after(
        self, channel_id: str, after_id: str, max_messages: int = 2000
    ) -> List[Dict[str, Any]]:
        """Догружает новые сообщения, появившиеся после `after_id` (?after={id}&limit=100)."""
        if not self.session:
            return []

        new_messages: List[Dict[str, Any]] = []
        current_after = after_id
        url = f"{self.DISCORD_API_BASE}/channels/{channel_id}/messages"

        logger.info(f"[Канал {channel_id}] Проверка новых сообщений после ID {after_id}...")

        while len(new_messages) < max_messages:
            params = {"limit": 100, "after": current_after}
            batch = self._request_batch(url, params, channel_id)

            if not batch:
                break

            # При запросе с `after` Discord возвращает сообщения от более старых к более новым,
            # но для полной надежности сортируем пакет по возрастанию ID.
            batch.sort(key=lambda m: int(m.get("id", 0)))

            for msg in batch:
                content = self.clean_trade_content(msg.get("content", ""))
                author = msg.get("author", {})
                if content and not author.get("bot", False):
                    msg_dt = self._parse_timestamp(msg.get("timestamp", ""))
                    new_messages.append({
                        "id": str(msg["id"]),
                        "author_id": str(author.get("id", "anonymous")),
                        "content": content,
                        "timestamp": msg_dt.isoformat()
                    })

            current_after = str(batch[-1]["id"])
            logger.info(f"[Канал {channel_id}] Загружен пакет: +{len(batch)} (Всего новых: {len(new_messages)})")

            if len(batch) < 100 or len(new_messages) >= max_messages:
                break

            time.sleep(random.uniform(1.3, 2.3))

        return new_messages

    def fetch_channel_messages(
        self, channel_id: str, max_messages: int = 1500, hours_back: float = 24.0
    ) -> List[Dict[str, Any]]:
        """Первичный сбор истории вглубь (?before={id}&limit=100) за последние `hours_back` часов."""
        if not self.session:
            logger.warning(f"[Канал {channel_id}] Сессия не активна (нет токена). Пропуск.")
            return []

        messages: List[Dict[str, Any]] = []
        last_id: Optional[str] = None
        cutoff_dt = datetime.datetime.now(datetime.timezone.utc) - datetime.timedelta(hours=hours_back)
        url = f"{self.DISCORD_API_BASE}/channels/{channel_id}/messages"

        logger.info(
            f"[Канал {channel_id}] Сбор истории до {cutoff_dt.strftime('%Y-%m-%d %H:%M:%S UTC')} "
            f"(лимит: {max_messages})..."
        )

        while len(messages) < max_messages:
            params: Dict[str, Any] = {"limit": 100}
            if last_id:
                params["before"] = last_id

            batch = self._request_batch(url, params, channel_id)
            if not batch:
                break

            reached_cutoff = False
            for msg in batch:
                msg_dt = self._parse_timestamp(msg.get("timestamp", ""))
                if msg_dt < cutoff_dt:
                    reached_cutoff = True
                    break

                content = self.clean_trade_content(msg.get("content", ""))
                author = msg.get("author", {})
                if content and not author.get("bot", False):
                    messages.append({
                        "id": str(msg["id"]),
                        "author_id": str(author.get("id", "anonymous")),
                        "content": content,
                        "timestamp": msg_dt.isoformat()
                    })

                last_id = str(msg["id"])
                if len(messages) >= max_messages:
                    break

            logger.info(f"[Канал {channel_id}] Загружен пакет: {len(batch)} шт. (Собрано подходящих: {len(messages)})")

            if reached_cutoff or len(batch) < 100 or len(messages) >= max_messages:
                if reached_cutoff:
                    logger.info(f"[Канал {channel_id}] Достигнута временная отсечка истории.")
                break

            time.sleep(random.uniform(1.6, 2.8))

        # Сортируем в хронологическом порядке (от старых к новым)
        messages.sort(key=lambda x: int(x["id"]))
        logger.info(f"[Канал {channel_id}] Итого скачано сообщений: {len(messages)}")
        return messages

    def fetch_all_trades(self, max_per_channel: int = 10000, backfill_hours: float = 2.0) -> List[Dict[str, Any]]:
        """
        Синхронизирует поток трейдов из всех отслеживаемых каналов.
        - Если в буфере есть валидный `last_message_id`, догружает только новые сообщения (?after=).
        - Если запуск первый, собирает историю за `backfill_hours` часов (?before=).
        - Очищает дубликаты и сообщения старше 7.5 дней (180 часов).
        """
        buffer_data = self.load_buffer()
        self.latest_read_messages = []

        if not self.session:
            logger.warning(
                "DISCORD_TOKEN не найден! Укажите его в переменных окружения или в файле .env. "
                "Возвращаются только ранее сохраненные сообщения из буфера."
            )
            self.prune_buffer(buffer_data, max_age_hours=180.0)
            self.save_buffer(buffer_data)
            return buffer_data["messages"]

        for cid in self.channel_ids:
            last_id = buffer_data["last_message_ids"].get(cid)

            if last_id and self.is_valid_snowflake(last_id):
                new_msgs = self.fetch_channel_messages_after(
                    cid, after_id=str(last_id), max_messages=max_per_channel
                )
                if new_msgs:
                    buffer_data["messages"].extend(new_msgs)
                    self.latest_read_messages.extend(new_msgs)
                    buffer_data["last_message_ids"][cid] = new_msgs[-1]["id"]
            else:
                backfill_msgs = self.fetch_channel_messages(
                    cid, max_messages=max_per_channel, hours_back=backfill_hours
                )
                if backfill_msgs:
                    buffer_data["messages"].extend(backfill_msgs)
                    self.latest_read_messages.extend(backfill_msgs)
                    buffer_data["last_message_ids"][cid] = backfill_msgs[-1]["id"]

        # Дедупликация, очистка спама и удаление сообщений старше 7.5 суток (180 часов)
        self.prune_buffer(buffer_data, max_age_hours=180.0)

        buffer_data["last_updated"] = datetime.datetime.now(datetime.timezone.utc).isoformat()
        self.save_buffer(buffer_data)

        logger.info(f"Синхронизация завершена. В активном буфере {len(buffer_data['messages'])} реальных сообщений.")
        return buffer_data["messages"]


if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser(description="GPO Discord Trade Reader & Realtime Audit Pipeline")
    parser.add_argument("--limit", "-n", type=int, default=100, help="Количество трейдов для чтения/анализа (по умолчанию: 100)")
    parser.add_argument("--all", "-a", action="store_true", help="Прочитать и показать абсолютно ВСЕ трейды из буфера")
    parser.add_argument("--channel-id", type=str, default=DiscordTradeReader.DEFAULT_CHANNEL_ID, help="ID канала Discord")
    parser.add_argument("--update-prices", action="store_true", help="Синхронизировать новые цены в gpo_items.json и items_data.js")
    args = parser.parse_args()

    # 1. Читаем сообщения через DiscordTradeReader
    reader = DiscordTradeReader(channel_ids=[args.channel_id])
    fetch_limit = 10000 if args.all else max(100, args.limit)
    all_buffer_msgs = reader.fetch_all_trades(max_per_channel=fetch_limit)

    # Определяем сообщения, которые нужно вывести в отчете
    if reader.latest_read_messages:
        messages_to_process = reader.latest_read_messages
        print(f"\n[+] С сервера Discord напрямую получено {len(messages_to_process)} новых сообщений.")
    else:
        target_count = len(all_buffer_msgs) if args.all else min(args.limit, len(all_buffer_msgs))
        messages_to_process = all_buffer_msgs[-target_count:]
        print(f"\n[i] Прочитано {len(messages_to_process)} сообщений из локального буфера трейдов.")

    # 2. Парсим сообщения в реальные сделки GPO
    from trade_parser import GPOTradeParser
    trade_parser = GPOTradeParser()
    parsed_trades = trade_parser.parse_all(messages_to_process)

    # 3. Загружаем текущую базу предметов до расчетов
    root_dir = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
    items_path = os.path.join(root_dir, "gpo_items.json")
    with open(items_path, "r", encoding="utf-8") as f:
        old_items = json.load(f)

    # 4. Рассчитываем цены и состояние тир-листа на полном буфере истории,
    # чтобы окна 1h / 24h / 7d считались корректно
    from price_engine import GPOPriceEngine
    engine = GPOPriceEngine(items_path=items_path)
    full_parsed_buffer = (
        parsed_trades
        if len(messages_to_process) == len(all_buffer_msgs)
        else trade_parser.parse_all(all_buffer_msgs)
    )
    calc_dataset = full_parsed_buffer if full_parsed_buffer else parsed_trades
    engine_output = engine.run_pipeline(calc_dataset)
    new_items = engine_output["items"]

    if args.update_prices:
        with open(items_path, "w", encoding="utf-8") as f:
            json.dump(new_items, f, indent=2, ensure_ascii=False)
        items_js_path = os.path.join(root_dir, "items_data.js")
        with open(items_js_path, "w", encoding="utf-8") as f:
            f.write("// Official Grand Piece Online Trading Database (Live Synchronized)\n")
            f.write("window.GPO_ITEMS = " + json.dumps(new_items, indent=2, ensure_ascii=False) + ";\n")
        print("[✓] Файлы gpo_items.json и items_data.js успешно обновлены новыми ценами!")

    # 5. Запускаем полный отчет
    from trade_reporter import run_full_trade_audit
    run_full_trade_audit(
        trades=parsed_trades,
        old_items=old_items,
        new_items=new_items,
        items_dict=trade_parser.items_dict
    )