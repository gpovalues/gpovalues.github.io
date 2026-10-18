"""
Audit and Reporting Engine for GPO Discord Trades.
Provides detailed analytics:
1. Full trade stream logger (displays 100% of read trades, removing any arbitrary limits).
2. Tier list change tracker (item-by-item delta: old value -> new value, % change, demand score delta, tier shifts).
3. Popularity leaderboard (top items by trade volume, split into offers and wants).
4. Zero-volume audit (complete breakdown of items that had 0 mentions in trades, grouped by category).
"""

import sys
from typing import List, Dict, Any, Optional


def print_all_trades_log(trades: List[Dict[str, Any]], items_dict: Dict[str, Dict[str, Any]]):
    """Выводит абсолютно ВСЕ прочитанные и распознанные трейды без искусственных ограничений."""
    total = len(trades)
    print("\n" + "=" * 90)
    print(f" 📜 ПОЛНЫЙ ЛОГ ВСЕХ ПРОЧИТАННЫХ ТРЕЙДОВ ДИСКОРДА (ВСЕГО: {total} шт.)")
    print("=" * 90)

    if not trades:
        print(" [!] В текущей сессии не найдено подходящих трейдов.")
        print("-" * 90)
        return

    for idx, tr in enumerate(trades, start=1):
        mid = tr.get("id", "N/A")
        ts = tr.get("timestamp", "")
        author = tr.get("author_id", "anon")
        raw = tr.get("raw_text", "").replace("\n", " ").strip()

        offer_items = tr.get("offer_items", [])
        want_items = tr.get("want_items", [])

        offer_desc = [
            f"{items_dict.get(iid, {}).get('name', iid)} (x{cnt})"
            for iid, cnt in offer_items
        ]
        want_desc = [
            f"{items_dict.get(iid, {}).get('name', iid)} (x{cnt})"
            for iid, cnt in want_items
        ]

        offer_str = ", ".join(offer_desc) if offer_desc else "Ничего / Offers"
        want_str = ", ".join(want_desc) if want_desc else "Любые предложения / Offers"

        print(f"[{idx:03d}/{total:03d}] ID: {mid} | Время: {ts or 'N/A'} | Автор: {author}")
        print(f"      [ТЕКСТ]      : {raw}")
        print(f"      [ПРЕДЛАГАЕТ] : [ {offer_str} ]")
        print(f"      [ХОЧЕТ]      : [ {want_str} ]")
        print("-" * 90)

    print(f" >>> Успешно выведены ВСЕ {total} прочитанных трейдов. <<<\n")


def safe_float(val: Any, default: float = 0.0) -> float:
    """Безопасно переводит значение в float (если там строка вроде 'Medium' или None)."""
    try:
        return float(val)
    except (ValueError, TypeError):
        return default


def format_demand(val: Any) -> str:
    """Форматирует значение спроса (число 0-10 или строковый статус)."""
    if val is None or val == "":
        return "N/A"
    try:
        f = float(val)
        return f"{f:.1f}/10"
    except (ValueError, TypeError):
        return str(val)


def print_tierlist_changes(old_items: List[Dict[str, Any]], new_items: List[Dict[str, Any]]):
    """Сравнивает тир-лист до и после чтения трейдов и выводит все изменения."""
    old_map = {it["id"]: it for it in old_items}
    new_map = {it["id"]: it for it in new_items}

    value_changes = []
    demand_changes = []
    tier_changes = []

    for iid, new_it in new_map.items():
        old_it = old_map.get(iid)
        if not old_it:
            continue

        old_val = safe_float(old_it.get("value", 0.0))
        new_val = safe_float(new_it.get("value", 0.0))
        diff_val = new_val - old_val

        old_dem = old_it.get("demand", 0.0)
        new_dem = new_it.get("demand", 0.0)

        old_dem_f = safe_float(old_dem)
        new_dem_f = safe_float(new_dem)
        diff_dem = new_dem_f - old_dem_f

        old_tier = str(old_it.get("tier", ""))
        new_tier = str(new_it.get("tier", ""))

        if abs(diff_val) >= 0.5:
            pct = (diff_val / old_val * 100.0) if old_val > 0 else 0.0
            value_changes.append({
                "item": new_it,
                "old_val": old_val,
                "new_val": new_val,
                "diff": diff_val,
                "pct": pct,
                "old_dem": old_dem,
                "new_dem": new_dem
            })

        if old_tier and new_tier and old_tier != new_tier:
            tier_changes.append({
                "item": new_it,
                "old_tier": old_tier,
                "new_tier": new_tier
            })

        if abs(diff_dem) >= 0.2:
            demand_changes.append({
                "item": new_it,
                "old_dem": old_dem,
                "new_dem": new_dem,
                "diff": diff_dem
            })

    print("=" * 90)
    print(" 📈 ИЗМЕНЕНИЯ В ТИР-ЛИСТЕ ПО РЕЗУЛЬТАТАМ СДЕЛОК")
    print("=" * 90)

    if tier_changes:
        print(f" ⭐ СМЕНА ТИРОВ ({len(tier_changes)} предметов):")
        for tc in tier_changes:
            it = tc["item"]
            print(f"   • {it['name']} ({it.get('category', 'misc')}): Тир {tc['old_tier']} ➔ Тир {tc['new_tier']}")
        print()

    if value_changes:
        # Сортируем по абсолютному проценту изменения
        value_changes.sort(key=lambda x: abs(x["pct"]), reverse=True)
        risers = [c for c in value_changes if c["diff"] > 0]
        fallers = [c for c in value_changes if c["diff"] < 0]

        print(f" 📊 ИЗМЕНЕНИЯ СТОИМОСТИ (Всего изменилось: {len(value_changes)} предметов):")
        if risers:
            print(f"\n   [↑ ВЫРОСЛИ В ЦЕНЕ] ({len(risers)} предметов):")
            for c in risers[:15]:
                it = c["item"]
                sign = "+"
                print(
                    f"   • {it['name']} (#{it.get('official_rank', '?')}, {it.get('category', 'misc')}): "
                    f"{c['old_val']:,.1f} pts ➔ {c['new_val']:,.1f} pts "
                    f"({sign}{c['diff']:,.1f} pts, {sign}{c['pct']:.2f}%) "
                    f"[Спрос: {format_demand(c['old_dem'])} ➔ {format_demand(c['new_dem'])}]"
                )
            if len(risers) > 15:
                print(f"     ... и еще {len(risers) - 15} выросших предметов.")

        if fallers:
            print(f"\n   [↓ УПАЛИ В ЦЕНЕ] ({len(fallers)} предметов):")
            for c in fallers[:15]:
                it = c["item"]
                print(
                    f"   • {it['name']} (#{it.get('official_rank', '?')}, {it.get('category', 'misc')}): "
                    f"{c['old_val']:,.1f} pts ➔ {c['new_val']:,.1f} pts "
                    f"({c['diff']:,.1f} pts, {c['pct']:.2f}%) "
                    f"[Спрос: {format_demand(c['old_dem'])} ➔ {format_demand(c['new_dem'])}]"
                )
            if len(fallers) > 15:
                print(f"     ... и еще {len(fallers) - 15} упавших предметов.")
    else:
        print(" • Изменений в стоимости нет: все цены стабильны и находятся в равновесии с рынком.")

    print("-" * 90)


def print_popular_items_leaderboard(
    trades: List[Dict[str, Any]],
    items_dict: Dict[str, Dict[str, Any]],
    top_n: int = 15
):
    """Выводит топ самых популярных предметов на рынке (по предложениям и запросам)."""
    offer_counts = {}
    want_counts = {}
    total_counts = {}

    for tr in trades:
        for iid, cnt in tr.get("offer_items", []):
            offer_counts[iid] = offer_counts.get(iid, 0) + cnt
            total_counts[iid] = total_counts.get(iid, 0) + cnt
        for iid, cnt in tr.get("want_items", []):
            want_counts[iid] = want_counts.get(iid, 0) + cnt
            total_counts[iid] = total_counts.get(iid, 0) + cnt

    sorted_popular = sorted(total_counts.items(), key=lambda x: x[1], reverse=True)

    print("=" * 90)
    print(f" 🏆 ТОП-{top_n} САМЫХ ПОПУЛЯРНЫХ ПРЕДМЕТОВ НА РЫНКЕ")
    print("=" * 90)

    if not sorted_popular:
        print(" [!] Нет данных по популярности предметов.")
        print("-" * 90)
        return

    for rank, (iid, total) in enumerate(sorted_popular[:top_n], start=1):
        it = items_dict.get(iid, {})
        name = it.get("name", iid)
        cat = it.get("category", "misc")
        val = safe_float(it.get("value", 0.0))
        demand_str = format_demand(it.get("demand"))

        offered = offer_counts.get(iid, 0)
        wanted = want_counts.get(iid, 0)

        # Вычисляем баланс спроса/предложения
        ratio_str = f"WTT (предлагают): {offered:3d} | LF (ищут): {wanted:3d}"
        print(
            f" {rank:02d}. {name:<28} | Всего: {total:4d} сдел. "
            f"({ratio_str}) | Спрос: {demand_str} | Цена: {val:,.0f} pts | [{cat}]"
        )

    print("-" * 90)


def print_unread_items_report(
    trades: List[Dict[str, Any]],
    all_items: List[Dict[str, Any]]
):
    """Выводит полный список предметов из базы, которые ВООБЩЕ НЕ прочитались/не встретились в трейдах."""
    seen_ids = set()
    for tr in trades:
        for iid, _ in tr.get("offer_items", []):
            seen_ids.add(iid)
        for iid, _ in tr.get("want_items", []):
            seen_ids.add(iid)

    unread_items = [it for it in all_items if it["id"] not in seen_ids]
    total_db = len(all_items)
    unread_count = len(unread_items)
    active_count = total_db - unread_count

    print("=" * 90)
    print(f" ⚠️ ПРЕДМЕТЫ, КОТОРЫЕ ВООБЩЕ НЕ ВСТРЕТИЛИСЬ В ТРЕЙДАХ (0 УПОМИНАНИЙ)")
    print("=" * 90)
    print(f" • Активных предметов на рынке : {active_count} из {total_db} ({active_count / total_db * 100:.1f}%)")
    print(f" • Предметов без сделок (0 упоминаний): {unread_count} из {total_db} ({unread_count / total_db * 100:.1f}%)")
    print("-" * 90)

    if not unread_items:
        print(" 🎉 ПОТРЯСАЮЩЕ: Абсолютно все предметы из базы хотя бы раз встретились в сделках!")
        print("=" * 90 + "\n")
        return

    # Группируем по категориям
    by_category = {}
    for it in unread_items:
        cat = it.get("category", "misc")
        by_category.setdefault(cat, []).append(it)

    category_order = ["fruits", "weapons", "accessories", "outfits", "chests", "boats", "misc"]
    existing_cats = [c for c in category_order if c in by_category] + [c for c in by_category if c not in category_order]

    for cat in existing_cats:
        cat_items = by_category[cat]
        cat_names = [it["name"] for it in cat_items]
        print(f"\n 📁 {cat.upper()} ({len(cat_items)} предметов без сделок):")
        # Выводим по строкам по 4-5 штук для максимальной читаемости
        chunk_size = 4
        for i in range(0, len(cat_names), chunk_size):
            chunk = cat_names[i:i + chunk_size]
            print(f"    • {', '.join(chunk)}")

    print("\n" + "=" * 90 + "\n")


def run_full_trade_audit(
    trades: List[Dict[str, Any]],
    old_items: List[Dict[str, Any]],
    new_items: List[Dict[str, Any]],
    items_dict: Dict[str, Dict[str, Any]]
):
    """Запускает полную цепочку итоговых отчетов после чтения трейдов."""
    # 1. Показываем ВСЕ прочитанные трейды
    print_all_trades_log(trades, items_dict)

    # 2. Показываем изменения в тир листе
    print_tierlist_changes(old_items, new_items)

    # 3. Показываем самые популярные предметы
    print_popular_items_leaderboard(trades, items_dict, top_n=15)

    # 4. Показываем предметы, которые вообще не прочитались
    print_unread_items_report(trades, list(items_dict.values()))
