// =====================================================================
// GRAND PIECE ONLINE (GPO) TRADING VALUES & TRADE CALCULATOR
// Interactive Application Logic & Multi-language Support (EN / RU)
// =====================================================================

(function () {
  'use strict';

  // --- AUDIO SYNTHESIS ENGINE (Web Audio API) ---
  let audioCtx = null;
  let audioEnabled = true;

  function initAudio() {
    if (!audioCtx) {
      const AudioContext = window.AudioContext || window.webkitAudioContext;
      if (AudioContext) {
        audioCtx = new AudioContext();
      }
    }
    if (audioCtx && audioCtx.state === 'suspended') {
      audioCtx.resume();
    }
  }

  function playTone(freq, type = 'sine', duration = 0.1, gainVal = 0.1) {
    if (!audioEnabled) return;
    try {
      initAudio();
      if (!audioCtx) return;
      const osc = audioCtx.createOscillator();
      const gain = audioCtx.createGain();
      osc.type = type;
      osc.frequency.setValueAtTime(freq, audioCtx.currentTime);
      gain.gain.setValueAtTime(gainVal, audioCtx.currentTime);
      gain.gain.exponentialRampToValueAtTime(0.001, audioCtx.currentTime + duration);
      osc.connect(gain);
      gain.connect(audioCtx.destination);
      osc.start();
      osc.stop(audioCtx.currentTime + duration);
    } catch (e) {
      // Audio fallback silent
    }
  }

  function playCoinSound() {
    playTone(987.77, 'triangle', 0.08, 0.12);
    setTimeout(() => playTone(1318.51, 'triangle', 0.15, 0.12), 80);
  }

  function playClickSound() {
    playTone(440, 'sine', 0.04, 0.06);
  }

  function playRemoveSound() {
    playTone(260, 'sawtooth', 0.08, 0.08);
  }

  function playWinFanfare() {
    playTone(523.25, 'triangle', 0.1, 0.15);
    setTimeout(() => playTone(659.25, 'triangle', 0.1, 0.15), 100);
    setTimeout(() => playTone(783.99, 'triangle', 0.12, 0.15), 200);
    setTimeout(() => playTone(1046.50, 'triangle', 0.25, 0.2), 300);
  }

  function playLoseSound() {
    playTone(392.00, 'sawtooth', 0.12, 0.1);
    setTimeout(() => playTone(329.63, 'sawtooth', 0.18, 0.12), 120);
  }

  // --- I18N DICTIONARY (Default: English) ---
  let currentLang = localStorage.getItem('gpo_lang') || 'en';

  const translations = {
    en: {
      brand_subtext: "Community Trade Calculator",
      tab_calculator: "Trade Calculator",
      tab_tierlist: "Tier List & Values",
      tab_community: "Community & Chats",
      tab_guide: "Trading Guide",
      hero_title: "Grand Piece Online <span>Trading Hub</span>",
      hero_desc: "All item values and demand synchronized with the official GPO tier list document. Calculate your trades, verify profits, and avoid bad trades!",
      badge_updated: "📅 Updated: 10/7/2026",
      badge_items_count: "⚔️ 213 Items",
      badge_official_doc: "⭐ Official GPO Doc",
      badge_currency: "🪙 Currency: Points & LC (Leg Chests)",
      verdict_empty: "ADD ITEMS TO TRADE",
      verdict_big_win: "🔥 BIG WIN!",
      verdict_win: "✅ WIN (PROFIT)!",
      verdict_fair: "🤝 FAIR TRADE",
      verdict_lose: "❌ LOSE (LOSS)!",
      verdict_big_lose: "💀 HUGE LOSE!",
      demand_neutral_note: "Equal demand on both sides",
      demand_warning_you: "⚠️ Warning: You are giving high demand items for low liquidity items!",
      demand_bonus_them: "💎 Great deal: They are offering highly liquid high-demand items!",
      btn_swap: "Swap Sides",
      btn_clear: "Clear All",
      btn_share: "Share Trade",
      you_give_title: "YOU GIVE (YOUR OFFER)",
      they_offer_title: "THEY OFFER (THEIR OFFER)",
      total_val_label: "Total Value",
      click_to_add: "Click to add item",
      btn_add_to_you: "Add Item (You)",
      btn_add_to_them: "Add Item (Them)",
      card_btn_you: "You",
      card_btn_them: "Them",
      card_title_add_you: "Add to You",
      card_title_add_them: "Add to Them",
      slot_btn_remove: "Remove",
      search_placeholder: "Search item by name or abbreviation (BOS, ASE, CC, Mochi, Pika, Eye...)",
      sort_tier_desc: "By Tier (Top to Bottom)",
      sort_val_desc: "By Value: High → Low",
      sort_val_asc: "By Value: Low → High",
      sort_demand_desc: "By Demand (High Demand)",
      sort_name_asc: "Alphabetical (A-Z)",
      label_category: "Category:",
      label_tier: "Tier:",
      cat_all: "All (213)",
      cat_fruits: "Devil Fruits 🍎",
      cat_weapons: "Weapons ⚔️",
      cat_chests: "Chests 📦",
      cat_accessories: "Accessories 👑",
      cat_outfits: "Outfits & Armor 🥋",
      cat_boats: "Boats & Mounts ⛵",
      cat_misc: "Misc & Items 📜",
      tier_all: "All Tiers",
      catalog_title: "ITEM CATALOG FOR TRADE (213 ITEMS)",
      catalog_hint: "💡 Click [+ You] or [+ Them] on any card for instant adding!",
      no_items_found: "🔍 No items found",
      no_items_sub: "Try adjusting your search query or filters",
      community_title: "💬 Community & Trading Chats",
      community_desc: "Join our official Grand Piece Online trading channels, discuss values, find trade partners, and connect with other players!",
      community_pill_active: "⚡ Active Trading & Discussions",
      community_pill_rules: "🛡️ Safe Trades & Moderation",
      community_pill_giveaways: "🎁 Events & Giveaways",
      chat_lang_badge: "Russian (Русский) 🇷🇺",
      chat_active_badge: "Active",
      members_label: "Members",
      online_label: "Online",
      chat_desc: "Grand Piece Online chat: here you can chat, find profitable trades, check latest prices, and team up for bosses and dungeons! Respect server rules and good luck!",
      chat_spec_lang_label: "🗣️ Language:",
      chat_spec_lang_val: "🇷🇺 Russian (Русский язык)",
      chat_spec_topic_label: "🎯 Focus:",
      chat_spec_topic_val: "Trading, Values, Boss Raids & Co-op",
      chat_spec_access_label: "🔓 Access:",
      chat_spec_access_val: "Public & Free to Join",
      btn_join_tg: "Join Telegram Chat (@GPOcHa)",
      discord_lang_badge: "Russian & English 🇷🇺 🇬🇧",
      discord_card_title: "Fruit Trilogy",
      discord_card_feature: "Trading, Voice, Raids",
      discord_card_desc: "Fruit Trilogy Grand Piece Online Discord community: here you can trade items, check latest prices, hang out in voice channels, and team up for bosses and dungeons! Respect server rules and good luck!",
      discord_spec_lang_val: "🇷🇺 Russian & 🇬🇧 English",
      discord_spec_topic_val: "Trading, Values, Boss Raids & Voice",
      btn_join_discord: "Join Discord Server (Fruit Trilogy)",
      drawer_discord_label: "🎮 DISCORD SERVER",
      drawer_subtitle: "Navigation Menu",
      drawer_nav_label: "🧭 TABS & SECTIONS",
      drawer_calc_desc: "Calculate win/loss trades",
      drawer_tier_desc: "213 items with abbreviations",
      drawer_comm_desc: "Telegram @GPOcHa chat & trade",
      drawer_guide_desc: "Rules & tips from official doc",
      drawer_comm_label: "✈️ TELEGRAM CHAT",
      drawer_btn_join: "Join ➔",
      drawer_sound: "Sound",
      guide_title: "📖 GPO Trading Rules & Guide",
      guide_desc: "Official trading economy rules from the Grand Piece Online community document. How not to get scammed and what to watch out for.",
      guide_rule1_title: "1. Hierarchy & Ranking Order",
      guide_rule1_desc: "An item's position within its tier strictly determines its value! Items placed higher in a tier are always worth more than those below. Being in the same tier does NOT guarantee equal value.",
      guide_rule1_example: "💡 Example: All Seeing Eye (ASE) is ranked higher than Troll Face and World Ender in the same A+ tier.",
      guide_rule2_title: "2. The Unstable Items Trap",
      guide_rule2_desc: "Items in the Very Unstable category (e.g. Valkyrie Helmets, Gift of Fruit, Clown Wig) do not have fixed values. Their price fluctuates heavily based on hype and individual buyers.",
      guide_rule2_example: "⚠️ Be careful: Do not trade stable liquid fruits (Mochi, Venom, Pika) for unstable items!",
      guide_rule3_title: "3. Trading Currency: Chests (LC & MC)",
      guide_rule3_desc: "Legendary Fruit Chest (LC) is the universally accepted standard currency in the game. Most traders express values in number of LC chests. A Mythical Chest (MC) is usually valued at 10-12 LC.",
      guide_rule4_title: "4. Demand Over Nominal Value",
      guide_rule4_desc: "An item with High Demand can easily be traded for an overpay (+20% value). Items with Low Demand often have to be traded at a discount.",
      picker_title: "Select Item to Trade",
      picker_title_you: "Select Item: YOU GIVE",
      picker_title_they: "Select Item: THEY OFFER",
      picker_search_placeholder: "Search item by name or abbreviation...",
      detail_modal_title: "Item Details",
      detail_value: "Value in points:",
      detail_lc: "LC equivalent:",
      detail_demand: "Demand:",
      detail_trend: "Market trend:",
      detail_wiki_btn: "Open page on GPO Fandom Wiki ↗",
      add_to_you: "Add to You",
      add_to_them: "Add to Them",
      footer_title: "⚓ GRAND PIECE ONLINE TRADING VALUE HUB",
      footer_text: "Created by the Grand Piece Online community. Prices calibrated to the official Trading Tier List Google Doc. Grand Piece Online belongs to Grand Quest Games on Roblox.",
      footer_link_doc: "📄 Official Google Doc Tier List",
      footer_link_roblox: "🎮 GPO Roblox Page",
      footer_link_wiki: "📚 Grand Piece Online Wiki",
      share_copied: "Trade link copied to clipboard!",
      demand_labels: {
        "Extremely High": "Extremely High 🔥",
        "High": "High Demand ⭐",
        "Medium": "Medium Demand",
        "Low": "Low Demand 💤",
        "Unstable": "Unstable ⚡"
      },
      trend_labels: {
        "Rising": "Rising ↗",
        "Stable": "Stable →",
        "Dropping": "Dropping ↘",
        "Fluctuating": "Fluctuating ⚡"
      }
    },
    ru: {
      brand_subtext: "Калькулятор Трейдов от Игроков",
      tab_calculator: "Калькулятор Трейдов",
      tab_tierlist: "Тир Лист & Цены",
      tab_community: "Сообщество & Чаты",
      tab_guide: "Гайд по Спросу",
      hero_title: "Grand Piece Online <span>Трейдинг Хаб</span>",
      hero_desc: "Все цены и деманд вещей синхронизированы с официальным тир-листом GPO. Рассчитывайте свои трейды, проверяйте выгоду и не попадайтесь на невыгодные сделки!",
      badge_updated: "📅 Обновление: 10/7/2026",
      badge_items_count: "⚔️ 213 Предметов",
      badge_official_doc: "⭐ Официальный GPO Doc",
      badge_currency: "🪙 Валюта: Очки & LC (Leg Chests)",
      verdict_empty: "ДОБАВЬТЕ ПРЕДМЕТЫ",
      verdict_big_win: "🔥 ОГРОМНЫЙ ВИН!",
      verdict_win: "✅ ВИН (ВЫГОДНО)!",
      verdict_fair: "🤝 РАВНЫЙ ТРЕЙД",
      verdict_lose: "❌ ЛУЗ (В УБЫТОК)!",
      verdict_big_lose: "💀 ОГРОМНЫЙ СЛИВ!",
      demand_neutral_note: "Равновесный спрос по обе стороны",
      demand_warning_you: "⚠️ Предупреждение: вы отдаете предметы с очень высоким спросом за менее ликвидные вещи!",
      demand_bonus_them: "💎 Отличный трейд: вам предлагают высоколиквидные предметы с отличным спросом!",
      btn_swap: "Поменять стороны",
      btn_clear: "Очистить всё",
      btn_share: "Поделиться трейдом",
      you_give_title: "ТЫ ОТДАЕШЬ (ТВОЙ ПРЕДЛОГ)",
      they_offer_title: "ДРУГОЙ ИГРОК ПРЕДЛАГАЕТ",
      total_val_label: "Общая ценность",
      click_to_add: "Нажми, чтобы добавить",
      btn_add_to_you: "Добавить предмет (Ты)",
      btn_add_to_them: "Добавить предмет (Другой игрок)",
      card_btn_you: "Ты",
      card_btn_them: "Игрок",
      card_title_add_you: "Добавить себе",
      card_title_add_them: "Добавить другому",
      slot_btn_remove: "Удалить",
      search_placeholder: "Поиск предмета по названию или аббревиатуре (BOS, ASE, CC, Mochi, Око, Леденец...)",
      sort_tier_desc: "По тиру (Сверху вниз)",
      sort_val_desc: "По ценности: Высокая → Низкая",
      sort_val_asc: "По ценности: Низкая → Высокая",
      sort_demand_desc: "По спросу (Высокий спрос)",
      sort_name_asc: "По алфавиту (А-Я / A-Z)",
      label_category: "Категория:",
      label_tier: "Тир:",
      cat_all: "Все (213)",
      cat_fruits: "Дьявольские Фрукты 🍎",
      cat_weapons: "Оружие ⚔️",
      cat_chests: "Сундуки 📦",
      cat_accessories: "Аксессуары 👑",
      cat_outfits: "Костюмы & Броня 🥋",
      cat_boats: "Лодки & Ховеры ⛵",
      cat_misc: "Разное & Расходники 📜",
      tier_all: "Все Тиры",
      catalog_title: "КАТАЛОГ ПРЕДМЕТОВ ДЛЯ ТРЕЙДА (213 ШТ)",
      catalog_hint: "💡 Нажмите [+ Ты] или [+ Игрок] на любой карточке для мгновенного добавления!",
      no_items_found: "🔍 Предметы не найдены",
      no_items_sub: "Попробуйте изменить поисковый запрос или фильтры",
      community_title: "💬 Сообщество и Трейдинг Чаты GPO",
      community_desc: "Присоединяйтесь к нашему официальному сообществу, трейдитесь с игроками, находите пати на рейды и следите за актуальными ценами!",
      community_pill_active: "⚡ Активные трейды и общение",
      community_pill_rules: "🛡️ Безопасные сделки и правила",
      community_pill_giveaways: "🎁 Ивенты и раздачи",
      chat_lang_badge: "Русский язык 🇷🇺",
      chat_active_badge: "Активен",
      members_label: "Участников",
      online_label: "Онлайн",
      chat_desc: "Чат по Grand Piece Online: здесь можно пообщаться, найти выгодный трейд, узнать свежие цены и собрать команду на боссов и данжи! Самое главное — соблюдать правила сервера.",
      chat_spec_lang_label: "🗣️ Язык:",
      chat_spec_lang_val: "🇷🇺 Русский язык",
      chat_spec_topic_label: "🎯 Тематика:",
      chat_spec_topic_val: "Трейдинг, Цены, Рейды на боссов и общение",
      chat_spec_access_label: "🔓 Доступ:",
      chat_spec_access_val: "Открытый чат для всех",
      btn_join_tg: "Войти в Telegram Чат (@GPOcHa)",
      discord_lang_badge: "Русский & English 🇷🇺 🇬🇧",
      discord_card_title: "Fruit Trilogy",
      discord_card_feature: "Трейды, общение, рейды",
      discord_card_desc: "Discord-сервер Fruit Trilogy по Grand Piece Online: здесь можно пообщаться, найти выгодный трейд, узнать свежие цены и собрать команду на боссов и данжи! Самое главное — соблюдать правила сервера.",
      discord_spec_lang_val: "🇷🇺 Русский и 🇬🇧 Английский",
      discord_spec_topic_val: "Трейдинг, Цены, Рейды на боссов и голосовые каналы",
      btn_join_discord: "Войти в Discord (Fruit Trilogy)",
      drawer_discord_label: "🎮 НАШ DISCORD",
      drawer_subtitle: "Меню навигации",
      drawer_nav_label: "🧭 ВКЛАДКИ И РАЗДЕЛЫ",
      drawer_calc_desc: "Расчёт трейдов на выгоду",
      drawer_tier_desc: "213 предметов с аббревиатурами",
      drawer_comm_desc: "Чат и трейды @GPOcHa",
      drawer_guide_desc: "Правила и советы из тир-листа",
      drawer_comm_label: "✈️ НАШ ТЕЛЕГРАМ ЧАТ",
      drawer_btn_join: "Войти ➔",
      drawer_sound: "Звук",
      guide_title: "📖 Правила и Советы по Трейдингу GPO",
      guide_desc: "Официальные правила экономики Grand Piece Online из документа сообщества. Как не потерять ценные вещи и на что обращать внимание при обмене.",
      guide_rule1_title: "1. Иерархия и Порядковый номер",
      guide_rule1_desc: "Положение вещи в тире строго определяет её ценность! Первые предметы в тире всегда ценнее тех, что находятся ниже. Нахождение в одном тире НЕ гарантирует одинаковую цену.",
      guide_rule1_example: "💡 Пример: All Seeing Eye (ASE) стоит выше, чем Troll Face и World Ender в том же тире A+.",
      guide_rule2_title: "2. Ловушка Нестабильных предметов (Unstable)",
      guide_rule2_desc: "Предметы из категории Very Unstable (например, Valkyrie Helmets, Gift of Fruit, Clown Wig) не имеют фиксированной стоимости. Их цена колеблется в зависимости от хайпа и конкретного покупателя.",
      guide_rule2_example: "⚠️ Будьте осторожны: не отдавайте стабильные ликвидные фрукты (Mochi, Venom, Pika) за вещи с нестабильным спросом!",
      guide_rule3_title: "3. Валюта Обмена: Сундуки (LC и MC)",
      guide_rule3_desc: "Legendary Fruit Chest (LC) — общепринятая стандартная валюта в игре. Большинство трейдеров выражают стоимость предметов в количестве сундуков LC. Мифический сундук (MC) обычно приравнивается к 10-12 LC.",
      guide_rule4_title: "4. Спрос (Demand) важнее номинала",
      guide_rule4_desc: "Предмет с высоким спросом (High Demand) всегда можно легко продать с оверпеем (+20% к цене). Предметы с низким спросом (Low Demand) часто приходится отдавать со скидкой.",
      picker_title: "Выберите предмет для трейда",
      picker_title_you: "Выберите предмет: ТЫ ОТДАЕШЬ",
      picker_title_they: "Выберите предмет: ДРУГОЙ ИГРОК",
      picker_search_placeholder: "Поиск предмета по названию или аббревиатуре...",
      detail_modal_title: "Информация о предмете",
      detail_value: "Ценность в очках:",
      detail_lc: "Эквивалент в LC:",
      detail_demand: "Спрос (Demand):",
      detail_trend: "Тренд на рынке:",
      detail_wiki_btn: "Открыть страницу на GPO Fandom Wiki ↗",
      add_to_you: "Добавить Себе",
      add_to_them: "Добавить Игроку",
      footer_title: "⚓ GRAND PIECE ONLINE TRADING VALUE HUB",
      footer_text: "Создано сообществом игроков Grand Piece Online. Цены ориентированы на официальный Trading Tier List Google Doc. Игра Grand Piece Online принадлежит Grand Quest Games на платформе Roblox.",
      footer_link_doc: "📄 Официальный Google Doc Tier List",
      footer_link_roblox: "🎮 Страница GPO в Roblox",
      footer_link_wiki: "📚 Grand Piece Online Wiki",
      share_copied: "Ссылка на трейд скопирована в буфер обмена!",
      demand_labels: {
        "Extremely High": "Огромный спрос 🔥",
        "High": "Высокий спрос ⭐",
        "Medium": "Средний спрос",
        "Low": "Низкий спрос 💤",
        "Unstable": "Нестабильный ⚡"
      },
      trend_labels: {
        "Rising": "Растет ↗",
        "Stable": "Стабилен →",
        "Dropping": "Падает ↘",
        "Fluctuating": "Колеблется ⚡"
      }
    }
  };

  function t(key) {
    return translations[currentLang][key] || key;
  }

  function applyLanguage() {
    document.documentElement.lang = currentLang;

    document.querySelectorAll('[data-i18n]').forEach(el => {
      const k = el.getAttribute('data-i18n');
      if (translations[currentLang][k]) {
        el.innerHTML = translations[currentLang][k];
      }
    });

    document.querySelectorAll('[data-i18n-placeholder]').forEach(el => {
      const k = el.getAttribute('data-i18n-placeholder');
      if (translations[currentLang][k]) {
        el.placeholder = translations[currentLang][k];
      }
    });

    const flagEl = document.getElementById('langFlag');
    const codeEl = document.getElementById('langCode');
    if (flagEl && codeEl) {
      flagEl.textContent = currentLang === 'ru' ? '🇷🇺' : '🇬🇧';
      codeEl.textContent = currentLang.toUpperCase();
    }

    const drawerFlagEl = document.getElementById('drawerLangFlag');
    const drawerCodeEl = document.getElementById('drawerLangCode');
    if (drawerFlagEl && drawerCodeEl) {
      drawerFlagEl.textContent = currentLang === 'ru' ? '🇷🇺' : '🇬🇧';
      drawerCodeEl.textContent = currentLang === 'ru' ? 'Русский' : 'English';
    }

    renderItemsGrid();
    renderQuickItemsGrid();
    renderCalculatorSlots();
    updateTradeVerdict();
  }

  function toggleLanguage() {
    currentLang = currentLang === 'en' ? 'ru' : 'en';
    localStorage.setItem('gpo_lang', currentLang);
    playClickSound();
    applyLanguage();
  }

  // --- TRADE CALCULATOR STATE ---
  let tradeState = {
    you: [],   // [ { item, qty } ]
    they: []   // [ { item, qty } ]
  };

  let activePickerSide = 'you'; // 'you' or 'they'

  // Demand numerical scores for balance check
  const demandScores = {
    "Extremely High": 5,
    "High": 4,
    "Medium": 3,
    "Low": 2,
    "Unstable": 1
  };

  function calculateSideTotal(side) {
    let pts = 0;
    let totalDemandScore = 0;
    let totalItems = 0;

    tradeState[side].forEach(entry => {
      pts += entry.item.value * entry.qty;
      const score = demandScores[entry.item.demand] || 3;
      totalDemandScore += score * entry.qty;
      totalItems += entry.qty;
    });

    const avgDemand = totalItems > 0 ? (totalDemandScore / totalItems) : 3;
    const lc = (pts / 2800).toFixed(2);
    return { pts, lc, avgDemand, count: totalItems };
  }

  function updateTradeVerdict() {
    const you = calculateSideTotal('you');
    const they = calculateSideTotal('they');

    // Update UI numbers
    document.getElementById('youTotalPts').textContent = you.pts.toLocaleString() + ' pts';
    document.getElementById('youTotalLc').textContent = you.lc + ' LC';
    document.getElementById('theyTotalPts').textContent = they.pts.toLocaleString() + ' pts';
    document.getElementById('theyTotalLc').textContent = they.lc + ' LC';

    const stamp = document.getElementById('verdictStamp');
    const icon = document.getElementById('verdictIcon');
    const text = document.getElementById('verdictText');
    const diffText = document.getElementById('verdictDiffText');
    const demandNote = document.getElementById('verdictDemandNote');

    // If both sides empty
    if (you.pts === 0 && they.pts === 0) {
      stamp.className = 'verdict-stamp fair';
      icon.textContent = '🤝';
      text.textContent = t('verdict_empty');
      diffText.className = 'verdict-diff-text neutral';
      diffText.textContent = '±0 pts (0%)';
      demandNote.innerHTML = `<span>⚖️</span> <span>${t('demand_neutral_note')}</span>`;
      return;
    }

    const diffPts = they.pts - you.pts;
    let diffPct = 0;
    if (you.pts > 0) {
      diffPct = ((diffPts / you.pts) * 100);
    } else if (they.pts > 0) {
      diffPct = 100;
    }

    const sign = diffPts >= 0 ? '+' : '';
    diffText.textContent = `${sign}${diffPts.toLocaleString()} pts (${sign}${diffPct.toFixed(1)}%)`;

    // Verdict Stamp logic
    if (diffPct >= 25) {
      stamp.className = 'verdict-stamp win-huge';
      icon.textContent = '🔥';
      text.textContent = t('verdict_big_win');
      diffText.className = 'verdict-diff-text positive';
    } else if (diffPct >= 5) {
      stamp.className = 'verdict-stamp win';
      icon.textContent = '✅';
      text.textContent = t('verdict_win');
      diffText.className = 'verdict-diff-text positive';
    } else if (diffPct <= -25) {
      stamp.className = 'verdict-stamp lose-huge';
      icon.textContent = '💀';
      text.textContent = t('verdict_big_lose');
      diffText.className = 'verdict-diff-text negative';
    } else if (diffPct <= -5) {
      stamp.className = 'verdict-stamp lose';
      icon.textContent = '❌';
      text.textContent = t('verdict_lose');
      diffText.className = 'verdict-diff-text negative';
    } else {
      stamp.className = 'verdict-stamp fair';
      icon.textContent = '🤝';
      text.textContent = t('verdict_fair');
      diffText.className = 'verdict-diff-text neutral';
    }

    // Audio fanfare on completion
    if (you.count > 0 && they.count > 0) {
      if (diffPct >= 10) playWinFanfare();
      else if (diffPct <= -15) playLoseSound();
    }

    // Demand Warning analysis
    if (you.avgDemand >= 4.0 && they.avgDemand <= 2.2 && you.count > 0 && they.count > 0) {
      demandNote.innerHTML = `<span style="color: #ef4444;">⚠️</span> <span style="color: #f87171;">${t('demand_warning_you')}</span>`;
    } else if (they.avgDemand >= 4.0 && you.avgDemand <= 2.5 && you.count > 0 && they.count > 0) {
      demandNote.innerHTML = `<span style="color: #10b981;">💎</span> <span style="color: #34d399;">${t('demand_bonus_them')}</span>`;
    } else {
      demandNote.innerHTML = `<span>⚖️</span> <span>${t('demand_neutral_note')}</span>`;
    }
  }

  function addItemToTrade(side, item, qty = 1) {
    const existing = tradeState[side].find(x => x.item.id === item.id);
    if (existing) {
      existing.qty += qty;
    } else {
      tradeState[side].push({ item, qty });
    }
    playCoinSound();
    renderCalculatorSlots();
    updateTradeVerdict();
    saveTradeToUrl();
  }

  function removeItemFromTrade(side, itemId) {
    tradeState[side] = tradeState[side].filter(x => x.item.id !== itemId);
    playRemoveSound();
    renderCalculatorSlots();
    updateTradeVerdict();
    saveTradeToUrl();
  }

  function changeItemQty(side, itemId, delta) {
    const entry = tradeState[side].find(x => x.item.id === itemId);
    if (entry) {
      entry.qty += delta;
      if (entry.qty <= 0) {
        removeItemFromTrade(side, itemId);
        return;
      }
      playClickSound();
      renderCalculatorSlots();
      updateTradeVerdict();
      saveTradeToUrl();
    }
  }

  function renderCalculatorSlots() {
    ['you', 'they'].forEach(side => {
      const container = document.getElementById(`${side}SlotsGrid`);
      if (!container) return;
      container.innerHTML = '';

      tradeState[side].forEach(entry => {
        const it = entry.item;
        const name = currentLang === 'ru' ? (it.nameRu || it.name) : it.name;
        const slotEl = document.createElement('div');
        slotEl.className = 'trade-slot-card';
        slotEl.innerHTML = `
          <button class="slot-remove-btn" title="${t('slot_btn_remove')}" onclick="window.GPO_APP.removeItem('${side}', '${it.id}')">✕</button>
          <img src="${it.image}" alt="${name}" class="slot-item-img" loading="lazy">
          <div class="slot-item-name" title="${name}">${name}</div>
          <div class="slot-item-val">${(it.value * entry.qty).toLocaleString()} pts</div>
          <div class="slot-qty-controls">
            <button class="qty-btn" onclick="window.GPO_APP.changeQty('${side}', '${it.id}', -1)">-</button>
            <span class="qty-num">x${entry.qty}</span>
            <button class="qty-btn" onclick="window.GPO_APP.changeQty('${side}', '${it.id}', 1)">+</button>
          </div>
        `;
        container.appendChild(slotEl);
      });

      // Add slot placeholder button
      const addBtn = document.createElement('div');
      addBtn.className = 'add-slot-placeholder';
      addBtn.onclick = () => openPickerModal(side);
      addBtn.innerHTML = `
        <span class="add-slot-icon">➕</span>
        <span class="add-slot-text">${t('click_to_add')}</span>
      `;
      container.appendChild(addBtn);
    });
  }

  function swapTradeSides() {
    const temp = tradeState.you;
    tradeState.you = tradeState.they;
    tradeState.they = temp;
    playCoinSound();
    renderCalculatorSlots();
    updateTradeVerdict();
    saveTradeToUrl();
  }

  function clearAllTrade() {
    tradeState.you = [];
    tradeState.they = [];
    playRemoveSound();
    renderCalculatorSlots();
    updateTradeVerdict();
    saveTradeToUrl();
  }

  function saveTradeToUrl() {
    try {
      const data = {
        y: tradeState.you.map(x => [x.item.id, x.qty]),
        t: tradeState.they.map(x => [x.item.id, x.qty])
      };
      const json = JSON.stringify(data);
      const b64 = btoa(encodeURIComponent(json));
      window.location.hash = `trade=${b64}`;
    } catch (e) {
      // Hash state fallback
    }
  }

  function loadTradeFromUrl() {
    try {
      const hash = window.location.hash;
      if (!hash || !hash.includes('trade=')) return;
      const b64 = hash.split('trade=')[1];
      if (!b64) return;
      const json = decodeURIComponent(atob(b64));
      const data = JSON.parse(json);
      const all = window.GPO_ITEMS || [];

      if (data.y && Array.isArray(data.y)) {
        tradeState.you = data.y.map(([id, qty]) => {
          const it = all.find(x => x.id === id);
          return it ? { item: it, qty: qty || 1 } : null;
        }).filter(Boolean);
      }

      if (data.t && Array.isArray(data.t)) {
        tradeState.they = data.t.map(([id, qty]) => {
          const it = all.find(x => x.id === id);
          return it ? { item: it, qty: qty || 1 } : null;
        }).filter(Boolean);
      }
    } catch (e) {
      console.warn('Could not parse trade from URL', e);
    }
  }

  function copyTradeShareLink() {
    saveTradeToUrl();
    const url = window.location.href;
    navigator.clipboard.writeText(url).then(() => {
      playCoinSound();
      alert(t('share_copied'));
    }).catch(() => {
      prompt("Copy trade URL:", url);
    });
  }

  // --- SMART BILINGUAL SEARCH HELPER ---
  function normalizeSearchStr(str) {
    if (!str) return '';
    return str.toLowerCase()
      .replace(/['’"`\-–—()]/g, '')
      .replace(/\s+/g, ' ')
      .trim();
  }

  function matchItemQuery(it, rawQuery) {
    if (!rawQuery || !rawQuery.trim()) return true;
    const qRaw = rawQuery.toLowerCase().trim();
    const qNorm = normalizeSearchStr(rawQuery);

    const en = (it.name || '').toLowerCase();
    const ru = (it.nameRu || '').toLowerCase();
    const abbr = (it.abbreviation || '').toLowerCase();
    const enNorm = normalizeSearchStr(it.name);
    const ruNorm = normalizeSearchStr(it.nameRu);
    const abbrNorm = normalizeSearchStr(it.abbreviation);

    // 1. Direct matches
    if (en.includes(qRaw) || ru.includes(qRaw) || abbr.includes(qRaw)) return true;
    if (enNorm.includes(qNorm) || ruNorm.includes(qNorm) || abbrNorm.includes(qNorm)) return true;

    // 2. Exact abbreviation check
    if (abbr.toLowerCase() === qRaw || abbrNorm === qNorm) return true;

    // 3. Multi-word token match
    const tokens = qNorm.split(' ').filter(Boolean);
    if (tokens.length > 1) {
      const combined = `${enNorm} ${ruNorm} ${abbrNorm}`;
      if (tokens.every(token => combined.includes(token))) return true;
    }

    return false;
  }

  // --- ITEM BROWSER & TIER LIST LOGIC ---
  let currentCategory = 'all';
  let currentTier = 'all';
  let searchQuery = '';
  let currentSort = 'tier_desc';

  let quickCategory = 'all';
  let quickSearch = '';
  let quickSort = 'tier_desc';

  function filterItemsList(items, q, cat, tier, sort) {
    let result = items.slice();

    if (q && q.trim()) {
      result = result.filter(it => matchItemQuery(it, q));
    }

    if (cat && cat !== 'all') {
      result = result.filter(it => it.category === cat);
    }

    if (tier && tier !== 'all') {
      result = result.filter(it => it.tier === tier);
    }

    if (sort === 'val_desc') {
      result.sort((a, b) => b.value - a.value);
    } else if (sort === 'val_asc') {
      result.sort((a, b) => a.value - b.value);
    } else if (sort === 'demand_desc') {
      result.sort((a, b) => (demandScores[b.demand] || 0) - (demandScores[a.demand] || 0));
    } else if (sort === 'name_asc') {
      result.sort((a, b) => {
        const nameA = currentLang === 'ru' ? (a.nameRu || a.name) : a.name;
        const nameB = currentLang === 'ru' ? (b.nameRu || b.name) : b.name;
        return nameA.localeCompare(nameB);
      });
    }

    return result;
  }

  function createCardElement(it) {
    const name = currentLang === 'ru' ? (it.nameRu || it.name) : it.name;
    const tierClass = `tier-${it.tier.replace(/[\s+]/g, '-')}`;
    const demandClass = `demand-${it.demand.replace(/[\s+]/g, '-')}`;
    const demandLabel = translations[currentLang].demand_labels[it.demand] || it.demand;

    const card = document.createElement('div');
    card.className = 'item-comic-card';
    card.innerHTML = `
      <span class="card-tier-tag ${tierClass}">${it.tier}</span>
      <span class="card-demand-tag ${demandClass}">${demandLabel}</span>

      <div class="card-img-wrapper" onclick="window.GPO_APP.openDetail('${it.id}')">
        <img src="${it.image}" alt="${name}" loading="lazy" onerror="this.src='https://static.wikia.nocookie.net/grand-piece-online/images/b/b3/Legendary_Chest.png/revision/latest'">
      </div>

      <h4 class="card-item-title" onclick="window.GPO_APP.openDetail('${it.id}')" title="${name}">${name}</h4>
      ${it.abbreviation ? `<span class="card-abbr-badge">✦ ${it.abbreviation}</span>` : ''}

      <div class="card-values-row">
        <span class="val-pts-text">${it.value.toLocaleString()} pts</span>
        <span class="val-lc-text">~${it.lcValue} LC</span>
      </div>

      <div class="card-actions-row">
        <button class="quick-add-btn add-you" onclick="window.GPO_APP.quickAdd('you', '${it.id}')" title="${t('card_title_add_you')}">
          <span>➕</span> <span>${t('card_btn_you')}</span>
        </button>
        <button class="quick-add-btn add-them" onclick="window.GPO_APP.quickAdd('they', '${it.id}')" title="${t('card_title_add_them')}">
          <span>➕</span> <span>${t('card_btn_them')}</span>
        </button>
      </div>
    `;
    return card;
  }

  function renderItemsGrid() {
    const grid = document.getElementById('itemsCardsGrid');
    if (!grid) return;
    grid.innerHTML = '';

    const items = filterItemsList(window.GPO_ITEMS || [], searchQuery, currentCategory, currentTier, currentSort);

    if (items.length === 0) {
      grid.innerHTML = `
        <div style="grid-column: 1 / -1; text-align: center; padding: 3rem 1rem; color: var(--text-muted);">
          <h3>${t('no_items_found')}</h3>
          <p>${t('no_items_sub')}</p>
        </div>
      `;
      return;
    }

    items.forEach(it => {
      grid.appendChild(createCardElement(it));
    });
  }

  function renderQuickItemsGrid() {
    const grid = document.getElementById('quickItemsCardsGrid');
    if (!grid) return;
    grid.innerHTML = '';

    const items = filterItemsList(window.GPO_ITEMS || [], quickSearch, quickCategory, 'all', quickSort);

    if (items.length === 0) {
      grid.innerHTML = `
        <div style="grid-column: 1 / -1; text-align: center; padding: 2rem 1rem; color: var(--text-muted);">
          <h3>${t('no_items_found')}</h3>
        </div>
      `;
      return;
    }

    const renderLimit = quickSearch.trim() ? items.length : 120;
    items.slice(0, renderLimit).forEach(it => {
      grid.appendChild(createCardElement(it));
    });
  }

  // --- ITEM PICKER MODAL LOGIC ---
  let pickerCategory = 'all';

  function openPickerModal(side) {
    activePickerSide = side;
    playClickSound();
    const modal = document.getElementById('itemPickerModal');
    const title = document.getElementById('pickerModalTitle');
    if (title) {
      title.textContent = side === 'you' ? t('picker_title_you') : t('picker_title_they');
    }
    modal.classList.add('open');
    filterPickerItems();
    document.getElementById('pickerSearchInput').focus();
  }

  function closePickerModal() {
    playClickSound();
    document.getElementById('itemPickerModal').classList.remove('open');
  }

  function filterPickerItems() {
    const q = (document.getElementById('pickerSearchInput').value || '').trim();
    const grid = document.getElementById('pickerItemsGrid');
    if (!grid) return;

    let items = (window.GPO_ITEMS || []).slice();

    if (q) {
      items = items.filter(it => matchItemQuery(it, q));
    }

    if (pickerCategory !== 'all') {
      items = items.filter(it => it.category === pickerCategory);
    }

    grid.innerHTML = '';
    if (items.length === 0) {
      grid.innerHTML = `
        <div style="grid-column: 1 / -1; text-align: center; padding: 2rem; color: var(--text-muted);">
          <h4>${t('no_items_found')}</h4>
        </div>
      `;
      return;
    }

    items.forEach(it => {
      const name = currentLang === 'ru' ? (it.nameRu || it.name) : it.name;
      const btn = document.createElement('div');
      btn.className = 'picker-item-btn';
      btn.onclick = () => {
        addItemToTrade(activePickerSide, it, 1);
        closePickerModal();
      };
      btn.innerHTML = `
        <img src="${it.image}" alt="${name}" class="picker-item-img" loading="lazy">
        <div class="picker-item-name" title="${name}">${name}</div>
        <div class="picker-item-val">${it.value.toLocaleString()} pts</div>
      `;
      grid.appendChild(btn);
    });
  }

  // --- ITEM DETAIL MODAL ---
  let currentDetailItem = null;

  function openDetailModal(itemId) {
    const it = (window.GPO_ITEMS || []).find(x => x.id === itemId);
    if (!it) return;
    currentDetailItem = it;
    playClickSound();

    const name = currentLang === 'ru' ? (it.nameRu || it.name) : it.name;
    document.getElementById('detailImg').src = it.image;
    document.getElementById('detailName').textContent = name;
    document.getElementById('detailValuePts').textContent = it.value.toLocaleString() + ' pts';
    document.getElementById('detailValueLc').textContent = it.lcValue + ' LC';

    const demandLabel = translations[currentLang].demand_labels[it.demand] || it.demand;
    const trendLabel = translations[currentLang].trend_labels[it.trend] || it.trend;

    document.getElementById('detailDemandVal').textContent = demandLabel;
    document.getElementById('detailTrendVal').textContent = trendLabel;
    document.getElementById('detailWikiLink').href = it.wikiUrl;

    const tagsBox = document.getElementById('detailTags');
    tagsBox.innerHTML = `
      <span class="hero-badge" style="background: #1e293b; color: #fff;">${it.tier}</span>
      <span class="hero-badge" style="background: #090e1b; color: var(--gold-beli);">${it.subTier}</span>
      ${it.abbreviation ? `<span class="card-abbr-badge">✦ ${it.abbreviation}</span>` : ''}
    `;

    document.getElementById('detailAddYouBtn').onclick = () => {
      addItemToTrade('you', it, 1);
      closeDetailModal();
      switchTab('calculator');
    };

    document.getElementById('detailAddThemBtn').onclick = () => {
      addItemToTrade('they', it, 1);
      closeDetailModal();
      switchTab('calculator');
    };

    document.getElementById('itemDetailModal').classList.add('open');
  }

  function closeDetailModal() {
    playClickSound();
    document.getElementById('itemDetailModal').classList.remove('open');
  }

  // --- MOBILE DRAWER NAVIGATION ---
  function openMobileDrawer() {
    playClickSound();
    const drawer = document.getElementById('mobileNavDrawer');
    const backdrop = document.getElementById('mobileNavBackdrop');
    const menuBtn = document.getElementById('mobileMenuBtn');
    if (drawer) {
      drawer.classList.add('open');
      drawer.setAttribute('aria-hidden', 'false');
    }
    if (backdrop) backdrop.classList.add('open');
    if (menuBtn) menuBtn.classList.add('active');
    document.body.classList.add('drawer-open');
  }

  function closeMobileDrawer() {
    const drawer = document.getElementById('mobileNavDrawer');
    const backdrop = document.getElementById('mobileNavBackdrop');
    const menuBtn = document.getElementById('mobileMenuBtn');
    if (drawer) {
      drawer.classList.remove('open');
      drawer.setAttribute('aria-hidden', 'true');
    }
    if (backdrop) backdrop.classList.remove('open');
    if (menuBtn) menuBtn.classList.remove('active');
    document.body.classList.remove('drawer-open');
  }

  function toggleMobileDrawer() {
    const drawer = document.getElementById('mobileNavDrawer');
    if (drawer && drawer.classList.contains('open')) {
      closeMobileDrawer();
    } else {
      openMobileDrawer();
    }
  }

  // --- TAB NAVIGATION ---
  function switchTab(tabId) {
    playClickSound();
    document.querySelectorAll('.nav-tab-btn').forEach(b => b.classList.remove('active'));
    document.querySelectorAll('.drawer-tab-btn').forEach(b => b.classList.remove('active'));
    document.querySelectorAll('.tab-section').forEach(s => s.style.display = 'none');

    const btn = document.querySelector(`.nav-tab-btn[data-tab="${tabId}"]`);
    if (btn) btn.classList.add('active');
    const drawerBtn = document.querySelector(`.drawer-tab-btn[data-tab="${tabId}"]`);
    if (drawerBtn) drawerBtn.classList.add('active');

    if (tabId === 'calculator') {
      document.getElementById('sectionCalculator').style.display = 'flex';
    } else if (tabId === 'tierlist') {
      document.getElementById('sectionTierlist').style.display = 'flex';
      renderItemsGrid();
    } else if (tabId === 'community') {
      document.getElementById('sectionCommunity').style.display = 'flex';
    } else if (tabId === 'guide') {
      document.getElementById('sectionGuide').style.display = 'block';
    }

    closeMobileDrawer();
  }

  // --- INITIALIZATION ---
  document.addEventListener('DOMContentLoaded', () => {
    // Nav Tabs click (Desktop)
    document.querySelectorAll('.nav-tab-btn').forEach(btn => {
      btn.addEventListener('click', () => {
        const tab = btn.getAttribute('data-tab');
        switchTab(tab);
      });
    });

    // Mobile Drawer buttons
    const menuBtn = document.getElementById('mobileMenuBtn');
    if (menuBtn) menuBtn.addEventListener('click', toggleMobileDrawer);

    const drawerCloseBtn = document.getElementById('mobileDrawerCloseBtn');
    if (drawerCloseBtn) drawerCloseBtn.addEventListener('click', closeMobileDrawer);

    const drawerBackdrop = document.getElementById('mobileNavBackdrop');
    if (drawerBackdrop) drawerBackdrop.addEventListener('click', closeMobileDrawer);

    const drawerBrandHomeBtn = document.getElementById('drawerBrandHomeBtn');
    if (drawerBrandHomeBtn) drawerBrandHomeBtn.addEventListener('click', () => switchTab('calculator'));

    document.querySelectorAll('.drawer-tab-btn').forEach(btn => {
      btn.addEventListener('click', () => {
        const tab = btn.getAttribute('data-tab');
        switchTab(tab);
      });
    });

    const drawerLangBtn = document.getElementById('drawerLangToggleBtn');
    if (drawerLangBtn) drawerLangBtn.addEventListener('click', toggleLanguage);

    const drawerAudioBtn = document.getElementById('drawerAudioToggleBtn');
    if (drawerAudioBtn) {
      drawerAudioBtn.addEventListener('click', () => {
        audioEnabled = !audioEnabled;
        const icon = audioEnabled ? '🔊' : '🔇';
        document.getElementById('audioToggleBtn').textContent = icon;
        const dIcon = document.getElementById('drawerAudioIcon');
        if (dIcon) dIcon.textContent = icon;
        if (audioEnabled) playCoinSound();
      });
    }

    document.getElementById('brandHomeBtn').addEventListener('click', () => switchTab('calculator'));

    // Language toggle (Desktop Header)
    document.getElementById('langToggleBtn').addEventListener('click', toggleLanguage);

    // Audio toggle (Desktop Header)
    document.getElementById('audioToggleBtn').addEventListener('click', () => {
      audioEnabled = !audioEnabled;
      const icon = audioEnabled ? '🔊' : '🔇';
      document.getElementById('audioToggleBtn').textContent = icon;
      const dIcon = document.getElementById('drawerAudioIcon');
      if (dIcon) dIcon.textContent = icon;
      if (audioEnabled) playCoinSound();
    });

    // Trade actions
    document.getElementById('btnSwapSides').addEventListener('click', swapTradeSides);
    document.getElementById('btnClearTrade').addEventListener('click', clearAllTrade);
    document.getElementById('btnShareTrade').addEventListener('click', copyTradeShareLink);

    // Search & Sort filters
    document.getElementById('searchInput').addEventListener('input', (e) => {
      searchQuery = e.target.value;
      renderItemsGrid();
    });

    document.getElementById('sortSelect').addEventListener('change', (e) => {
      currentSort = e.target.value;
      renderItemsGrid();
    });

    // Category pills
    document.querySelectorAll('#categoryPillsRow .filter-pill-btn').forEach(btn => {
      btn.addEventListener('click', () => {
        document.querySelectorAll('#categoryPillsRow .filter-pill-btn').forEach(b => b.classList.remove('active'));
        btn.classList.add('active');
        currentCategory = btn.getAttribute('data-cat');
        playClickSound();
        renderItemsGrid();
      });
    });

    // Tier pills
    document.querySelectorAll('#tierPillsRow .tier-pill-btn').forEach(btn => {
      btn.addEventListener('click', () => {
        document.querySelectorAll('#tierPillsRow .tier-pill-btn').forEach(b => b.classList.remove('active'));
        btn.classList.add('active');
        currentTier = btn.getAttribute('data-tier');
        playClickSound();
        renderItemsGrid();
      });
    });

    // Picker Category pills inside modal
    document.querySelectorAll('#pickerCategoryPills .filter-pill-btn').forEach(btn => {
      btn.addEventListener('click', () => {
        document.querySelectorAll('#pickerCategoryPills .filter-pill-btn').forEach(b => b.classList.remove('active'));
        btn.classList.add('active');
        pickerCategory = btn.getAttribute('data-pcat');
        playClickSound();
        filterPickerItems();
      });
    });

    // Close modals on clicking overlay outside card
    document.querySelectorAll('.comic-modal-overlay').forEach(overlay => {
      overlay.addEventListener('click', (e) => {
        if (e.target === overlay) {
          overlay.classList.remove('open');
        }
      });
    });

    // Load from URL hash if present
    loadTradeFromUrl();

    // Quick Category pills in calculator
    document.querySelectorAll('#quickCategoryPillsRow .filter-pill-btn').forEach(btn => {
      btn.addEventListener('click', () => {
        document.querySelectorAll('#quickCategoryPillsRow .filter-pill-btn').forEach(b => b.classList.remove('active'));
        btn.classList.add('active');
        quickCategory = btn.getAttribute('data-qcat');
        playClickSound();
        renderQuickItemsGrid();
      });
    });

    // Initial render with English default
    applyLanguage();
    renderQuickItemsGrid();
  });

  function handleQuickSearch(e) {
    quickSearch = e.target.value;
    renderQuickItemsGrid();
  }

  function handleQuickSort(e) {
    quickSort = e.target.value;
    renderQuickItemsGrid();
  }

  // Export globally for HTML onclick handlers
  window.GPO_APP = {
    removeItem: (side, id) => removeItemFromTrade(side, id),
    changeQty: (side, id, delta) => changeItemQty(side, id, delta),
    quickAdd: (side, id) => {
      const it = (window.GPO_ITEMS || []).find(x => x.id === id);
      if (it) {
        addItemToTrade(side, it, 1);
      }
    },
    openDetail: (id) => openDetailModal(id),
    openPicker: (side) => openPickerModal(side)
  };

  window.openPickerModal = openPickerModal;
  window.closePickerModal = closePickerModal;
  window.closeDetailModal = closeDetailModal;
  window.filterPickerItems = filterPickerItems;
  window.handleQuickSearch = handleQuickSearch;
  window.handleQuickSort = handleQuickSort;

})();
